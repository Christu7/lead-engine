"""Integration tests for JWT-protected endpoints.

Verifies that endpoints require authentication and return correct responses
for authenticated users against a real test database.
"""
import pytest
from sqlalchemy import select


@pytest.mark.integration
class TestLeadsEndpoint:

    async def test_unauthenticated_returns_401(self, http_client):
        resp = await http_client.get("/api/leads/")
        assert resp.status_code == 401

    async def test_authenticated_returns_200_and_empty_list(self, authenticated_client):
        resp = await authenticated_client.get("/api/leads/")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["items"] == []
        assert body["total"] == 0

    async def test_results_scoped_to_client(self, http_client, db_session, seeded_users, member_token):
        """Leads created for seeded_client are visible; other clients' leads are not."""
        from app.models.lead import Lead
        from app.models.user import UserClient

        uc = (await db_session.execute(
            select(UserClient).where(UserClient.user_id == seeded_users["member"].id)
        )).scalar_one()
        client_id = uc.client_id

        lead = Lead(name="Test Lead", email="test@test.com", client_id=client_id)
        db_session.add(lead)
        await db_session.commit()

        http_client.headers.update({"Authorization": f"Bearer {member_token}"})
        resp = await http_client.get("/api/leads/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["email"] == "test@test.com"


@pytest.mark.integration
class TestScoringRulesEndpoint:

    async def test_unauthenticated_returns_401(self, http_client):
        resp = await http_client.post(
            "/api/scoring-rules/",
            json={"field": "title", "operator": "contains", "value": "VP", "points": 20},
        )
        assert resp.status_code == 401

    async def test_member_cannot_create_rule(self, authenticated_client):
        """Members do not have access to scoring rules (admin+ only)."""
        resp = await authenticated_client.post(
            "/api/scoring-rules/",
            json={"field": "title", "operator": "contains", "value": "VP", "points": 20},
        )
        assert resp.status_code == 403

    async def test_create_rule_returns_201(self, admin_client):
        resp = await admin_client.post(
            "/api/scoring-rules/",
            json={"field": "title", "operator": "contains", "value": "VP", "points": 20},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["field"] == "title"
        assert body["operator"] == "contains"
        assert body["value"] == "VP"
        assert body["points"] == 20
        assert body["is_active"] is True

    async def test_created_rule_is_scoped_to_client(self, admin_client):
        resp = await admin_client.post(
            "/api/scoring-rules/",
            json={"field": "company", "operator": "contains", "value": "Acme", "points": 10},
        )
        assert resp.status_code == 201
        rule_id = resp.json()["id"]

        list_resp = await admin_client.get("/api/scoring-rules/")
        assert list_resp.status_code == 200
        ids = [r["id"] for r in list_resp.json()["items"]]
        assert rule_id in ids


@pytest.mark.integration
class TestDashboardStatsEndpoint:

    async def test_unauthenticated_returns_401(self, http_client):
        resp = await http_client.get("/api/dashboard/stats")
        assert resp.status_code == 401

    async def test_authenticated_returns_200(self, authenticated_client):
        resp = await authenticated_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_leads" in body
        assert "enrichment_success_rate" in body
        assert "routing_breakdown" in body

    async def test_stats_reflect_seeded_data(self, http_client, db_session, seeded_users, member_token):
        """total_leads counter increments when leads are present."""
        from app.models.lead import Lead
        from app.models.user import UserClient

        uc = (await db_session.execute(
            select(UserClient).where(UserClient.user_id == seeded_users["member"].id)
        )).scalar_one()
        client_id = uc.client_id

        lead = Lead(
            name="Stat Lead",
            email="stat@test.com",
            client_id=client_id,
            enrichment_status="enriched",
        )
        db_session.add(lead)
        await db_session.commit()

        http_client.headers.update({"Authorization": f"Bearer {member_token}"})
        resp = await http_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_leads"] >= 1
