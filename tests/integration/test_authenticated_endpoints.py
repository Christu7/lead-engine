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


@pytest.mark.integration
class TestLeadsDelete:
    """DELETE /api/leads/{lead_id} — hard delete, scoped to client_id."""

    async def test_delete_own_lead_returns_204(self, authenticated_client, db_session, seeded_users):
        """Deleting a lead owned by the user's client returns 204 and removes the row."""
        from app.models.lead import Lead
        from app.models.user import UserClient

        uc = (await db_session.execute(
            select(UserClient).where(UserClient.user_id == seeded_users["member"].id)
        )).scalar_one()

        lead = Lead(name="To Delete", email="del@test.com", client_id=uc.client_id)
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await authenticated_client.delete(f"/api/leads/{lead.id}")
        assert resp.status_code == 204

        # Row must be gone — hard delete
        result = await db_session.execute(
            select(Lead).where(Lead.id == lead.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_cross_tenant_returns_404(self, authenticated_client, db_session):
        """Cannot delete a lead belonging to a different client — returns 404."""
        from app.models.client import Client
        from app.models.lead import Lead

        other_client = Client(name="Other Client", settings={})
        db_session.add(other_client)
        await db_session.commit()
        await db_session.refresh(other_client)

        lead = Lead(name="Other Lead", email="other@test.com", client_id=other_client.id)
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await authenticated_client.delete(f"/api/leads/{lead.id}")
        assert resp.status_code == 404

        # Row must still exist — we did not touch another client's data
        result = await db_session.execute(
            select(Lead).where(Lead.id == lead.id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_delete_nonexistent_returns_404(self, authenticated_client):
        resp = await authenticated_client.delete("/api/leads/99999")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, http_client):
        resp = await http_client.delete("/api/leads/1")
        assert resp.status_code == 401


@pytest.mark.integration
class TestCompaniesDelete:
    """DELETE /api/companies/{company_id} — soft delete (abm_status='inactive'), scoped to client_id."""

    async def test_soft_delete_own_company_returns_204(self, authenticated_client, db_session, seeded_users):
        """Soft-deleting a company sets abm_status='inactive' and returns 204."""
        import uuid
        from app.models.company import Company
        from app.models.user import UserClient

        uc = (await db_session.execute(
            select(UserClient).where(UserClient.user_id == seeded_users["member"].id)
        )).scalar_one()

        company = Company(
            id=uuid.uuid4(),
            name="Soft Delete Co",
            client_id=uc.client_id,
            enrichment_status="pending",
            abm_status="target",
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        resp = await authenticated_client.delete(f"/api/companies/{company.id}")
        assert resp.status_code == 204

        # Row must still exist — soft delete preserves the record
        await db_session.refresh(company)
        assert company.abm_status == "inactive"

    async def test_delete_cross_tenant_returns_404(self, authenticated_client, db_session):
        """Cannot delete a company belonging to a different client — returns 404."""
        import uuid
        from app.models.client import Client
        from app.models.company import Company

        other_client = Client(name="Other Client C", settings={})
        db_session.add(other_client)
        await db_session.commit()
        await db_session.refresh(other_client)

        company = Company(
            id=uuid.uuid4(),
            name="Foreign Co",
            client_id=other_client.id,
            enrichment_status="pending",
            abm_status="target",
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        resp = await authenticated_client.delete(f"/api/companies/{company.id}")
        assert resp.status_code == 404

        # abm_status must be unchanged — we did not touch another client's data
        await db_session.refresh(company)
        assert company.abm_status == "target"

    async def test_delete_nonexistent_returns_404(self, authenticated_client):
        import uuid
        resp = await authenticated_client.delete(f"/api/companies/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, http_client):
        import uuid
        resp = await http_client.delete(f"/api/companies/{uuid.uuid4()}")
        assert resp.status_code == 401


@pytest.mark.integration
class TestClientOwnershipChecks:
    """MT-2: admins may only assign/unassign users to clients they belong to."""

    async def test_admin_cannot_assign_user_to_foreign_client(
        self, admin_client, db_session, seeded_users
    ):
        """Admin of Client A gets 403 when assigning a user to Client B."""
        from app.models.client import Client

        client_b = Client(name="Client B", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        resp = await admin_client.post(
            f"/api/admin/users/{seeded_users['member'].id}/clients",
            json={"client_id": client_b.id},
        )
        assert resp.status_code == 403

    async def test_superadmin_can_assign_user_to_any_client(
        self, superadmin_client, db_session, seeded_superadmin, seeded_users
    ):
        """Superadmin bypasses the ownership check and can assign to any client."""
        from app.models.client import Client

        client_b = Client(name="Client B", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        resp = await superadmin_client.post(
            f"/api/admin/users/{seeded_users['member'].id}/clients",
            json={"client_id": client_b.id},
        )
        assert resp.status_code == 201
