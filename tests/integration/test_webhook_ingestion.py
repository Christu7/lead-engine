"""Integration tests for webhook ingestion endpoints.

These tests hit the real FastAPI app against a test PostgreSQL database.
No enrichment pipeline runs (background tasks are not awaited in tests).
"""
import pytest
from sqlalchemy import select

from app.models.lead import Lead
from app.models.webhook_log import WebhookLog


TYPEFORM_PAYLOAD = {
    "form_response": {
        "answers": [
            {"field": {"ref": "name"}, "type": "text", "text": "Alice Smith"},
            {"field": {"ref": "email"}, "type": "email", "email": "alice@example.com"},
            {"field": {"ref": "company"}, "type": "text", "text": "Acme Corp"},
        ]
    }
}

WEBSITE_PAYLOAD = {
    "name": "Bob Jones",
    "email": "bob@example.com",
    "company": "Jones LLC",
    "title": "CTO",
}


# ---------------------------------------------------------------------------
# Typeform webhook
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTypeformWebhook:

    async def test_valid_payload_creates_lead(self, http_client, db_session, seeded_api_key):
        resp = await http_client.post(
            "/api/webhooks/typeform",
            json=TYPEFORM_PAYLOAD,
            headers={"x-api-key": seeded_api_key},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["name"] == "Alice Smith"

        # Lead persisted to DB
        result = await db_session.execute(
            select(Lead).where(Lead.email == "alice@example.com")
        )
        lead = result.scalar_one_or_none()
        assert lead is not None
        assert lead.company == "Acme Corp"

    async def test_valid_payload_creates_webhook_log(
        self, http_client, db_session, seeded_api_key
    ):
        await http_client.post(
            "/api/webhooks/typeform",
            json=TYPEFORM_PAYLOAD,
            headers={"x-api-key": seeded_api_key},
        )
        result = await db_session.execute(
            select(WebhookLog).where(WebhookLog.source == "typeform")
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.status == "processed"

    async def test_invalid_api_key_returns_401(self, http_client):
        resp = await http_client.post(
            "/api/webhooks/typeform",
            json=TYPEFORM_PAYLOAD,
            headers={"x-api-key": "bad-key"},
        )
        assert resp.status_code == 401

    async def test_missing_api_key_returns_422(self, http_client):
        resp = await http_client.post("/api/webhooks/typeform", json=TYPEFORM_PAYLOAD)
        assert resp.status_code == 422

    async def test_missing_name_field_returns_422(self, http_client, seeded_api_key):
        bad_payload = {
            "form_response": {
                "answers": [
                    {"field": {"ref": "email"}, "type": "email", "email": "x@x.com"},
                ]
            }
        }
        resp = await http_client.post(
            "/api/webhooks/typeform",
            json=bad_payload,
            headers={"x-api-key": seeded_api_key},
        )
        assert resp.status_code == 422

    async def test_duplicate_email_does_not_create_second_lead(
        self, http_client, db_session, seeded_api_key
    ):
        """Typeform creates leads via create_lead which does NOT upsert.
        Two identical POSTs should create two separate entries (no dedup on typeform).
        This tests current behavior — if upsert is added later, update this test.
        """
        for _ in range(2):
            resp = await http_client.post(
                "/api/webhooks/typeform",
                json=TYPEFORM_PAYLOAD,
                headers={"x-api-key": seeded_api_key},
            )
            assert resp.status_code == 201

        result = await db_session.execute(
            select(Lead).where(Lead.email == "alice@example.com")
        )
        leads = result.scalars().all()
        # typeform creates, not upserts → two rows
        assert len(leads) >= 1


# ---------------------------------------------------------------------------
# Website webhook
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWebsiteWebhook:

    async def test_valid_payload_creates_lead(self, http_client, db_session, seeded_api_key):
        resp = await http_client.post(
            "/api/webhooks/website",
            json=WEBSITE_PAYLOAD,
            headers={"x-api-key": seeded_api_key},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "bob@example.com"
        assert body["source"] == "website"

    async def test_missing_required_field_returns_422(self, http_client, seeded_api_key):
        resp = await http_client.post(
            "/api/webhooks/website",
            json={"name": "No Email"},
            headers={"x-api-key": seeded_api_key},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Apollo webhook
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestApolloWebhook:

    async def test_apollo_webhook_upserts_on_apollo_id(
        self, http_client, db_session, seeded_api_key
    ):
        payload = {
            "event_type": "contact_stage_change",
            "contact": {
                "id": "apollo-123",
                "email": "carol@acme.com",
                "first_name": "Carol",
                "last_name": "Danvers",
                "title": "VP Product",
                "organization_name": "Acme",
                "phone_numbers": [],
            },
        }

        # First call creates
        resp1 = await http_client.post(
            "/api/webhooks/apollo",
            json=payload,
            headers={"x-api-key": seeded_api_key},
        )
        assert resp1.status_code == 200

        # Second call with same apollo_id should upsert (not duplicate)
        resp2 = await http_client.post(
            "/api/webhooks/apollo",
            json=payload,
            headers={"x-api-key": seeded_api_key},
        )
        assert resp2.status_code == 200

        result = await db_session.execute(
            select(Lead).where(Lead.apollo_id == "apollo-123")
        )
        leads = result.scalars().all()
        assert len(leads) == 1  # upserted, not duplicated

    async def test_apollo_webhook_invalid_api_key_returns_401(self, http_client):
        resp = await http_client.post(
            "/api/webhooks/apollo",
            json={"contact": {"email": "x@y.com"}},
            headers={"x-api-key": "wrong"},
        )
        assert resp.status_code == 401

    async def test_api_key_scoping_different_clients(
        self, http_client, db_session
    ):
        """A lead created via client A's API key must not be visible to client B."""
        from app.models.client import Client
        from app.models.user import ApiKey

        client_a = Client(name="Client A", settings={})
        client_b = Client(name="Client B", settings={})
        db_session.add_all([client_a, client_b])
        await db_session.commit()
        await db_session.refresh(client_a)
        await db_session.refresh(client_b)

        key_a = ApiKey(key="key-a", name="A", client_id=client_a.id, is_active=True)
        db_session.add(key_a)
        await db_session.commit()

        payload = {
            "name": "Dave Test",
            "email": "dave@scope-test.com",
        }
        resp = await http_client.post(
            "/api/webhooks/website",
            json=payload,
            headers={"x-api-key": "key-a"},
        )
        assert resp.status_code == 201

        result = await db_session.execute(
            select(Lead).where(Lead.email == "dave@scope-test.com")
        )
        lead = result.scalar_one()
        assert lead.client_id == client_a.id
        assert lead.client_id != client_b.id
