"""Security regression tests for the hostile code review fixes.

Tests:
  1. token_version_rejection     — logged-out JWT rejected on admin endpoints
  2. metrics_tenant_scope        — non-superadmin metrics never leak cross-tenant data
  3. routing_ssrf_blocked        — private-IP webhook URLs return 400
  4. role_change_cross_client    — admin A cannot change a user from workspace B
  5. bulk_upsert_company_linking — bulk import auto-links leads to matching companies
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.services.auth import invalidate_user_tokens


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. token_version_rejection
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTokenVersionRejection:
    """Revoked tokens must be rejected by admin and metrics endpoints."""

    async def test_old_jwt_rejected_on_admin_users_get(
        self, http_client, db_session, seeded_users
    ):
        admin = seeded_users["admin"]
        # Token carries version 1 (default); user also starts at version 1.
        old_token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=1,
            token_version=1,
        )

        # Confirm the token works before invalidation.
        resp = await http_client.get("/api/admin/users", headers=_auth(old_token))
        assert resp.status_code == 200

        # Simulate logout / role change — bumps token_version to 2.
        await invalidate_user_tokens(db_session, admin.id)

        # Old token must now be rejected.
        resp = await http_client.get("/api/admin/users", headers=_auth(old_token))
        assert resp.status_code == 401

    async def test_old_jwt_rejected_on_admin_users_post(
        self, http_client, db_session, seeded_users
    ):
        admin = seeded_users["admin"]
        old_token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=1,
            token_version=1,
        )
        await invalidate_user_tokens(db_session, admin.id)

        resp = await http_client.post(
            "/api/admin/users",
            headers=_auth(old_token),
            json={
                "email": "newuser@test.com",
                "password": "test1234",
                "role": "member",
                "client_ids": [1],
            },
        )
        assert resp.status_code == 401

    async def test_old_jwt_rejected_on_metrics(
        self, http_client, db_session, seeded_users
    ):
        admin = seeded_users["admin"]
        old_token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=1,
            token_version=1,
        )
        await invalidate_user_tokens(db_session, admin.id)

        resp = await http_client.get("/api/metrics", headers=_auth(old_token))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. metrics_tenant_scope
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMetricsTenantScope:
    """Admin A's metrics must only reflect client A's leads — never client B's."""

    async def test_metrics_scoped_to_requesting_admin_client(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        from app.models.client import Client
        from app.models.lead import Lead
        from app.models.user import User, UserClient
        from app.core.security import hash_password

        # Client A is seeded_client (id=1). Create client B.
        client_b = Client(name="Client B Metrics", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        # Add 3 leads to client B.
        for i in range(3):
            db_session.add(
                Lead(name=f"B Lead {i}", email=f"blead{i}@clientb.com", client_id=client_b.id)
            )
        await db_session.commit()

        # Admin user is linked to client A (seeded_client) only.
        admin = seeded_users["admin"]
        token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=seeded_client.id,
            token_version=1,
        )

        resp = await http_client.get("/api/metrics", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()

        # Client A has no leads today, so leads_today must be 0 — not 3.
        assert body["leads_today"] == 0

    async def test_metrics_with_explicit_foreign_client_id_returns_403(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        from app.models.client import Client

        client_b = Client(name="Client B Metrics 403", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        admin = seeded_users["admin"]
        token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=seeded_client.id,
            token_version=1,
        )

        resp = await http_client.get(
            f"/api/metrics?client_id={client_b.id}", headers=_auth(token)
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 3. routing_ssrf_blocked
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRoutingSSRFBlocked:
    """Private-range and metadata-service URLs must be rejected with 400."""

    async def test_aws_metadata_url_blocked(self, admin_client):
        resp = await admin_client.put(
            "/api/settings/routing",
            json={
                "ghl_inbound_webhook_url": "https://169.254.169.254/latest/meta-data/",
                "score_inbound_threshold": 70,
                "score_outbound_threshold": 40,
            },
        )
        assert resp.status_code == 400
        assert "ghl_inbound_webhook_url" in resp.json()["detail"]

    async def test_localhost_url_blocked(self, admin_client):
        resp = await admin_client.put(
            "/api/settings/routing",
            json={
                "ghl_inbound_webhook_url": "https://localhost/hook",
                "score_inbound_threshold": 70,
                "score_outbound_threshold": 40,
            },
        )
        assert resp.status_code == 400

    async def test_private_rfc1918_ip_blocked(self, admin_client):
        resp = await admin_client.put(
            "/api/settings/routing",
            json={
                "ghl_outbound_webhook_url": "https://192.168.1.1/hook",
                "score_inbound_threshold": 70,
                "score_outbound_threshold": 40,
            },
        )
        assert resp.status_code == 400

    async def test_http_not_https_blocked(self, admin_client):
        resp = await admin_client.put(
            "/api/settings/routing",
            json={
                "ghl_inbound_webhook_url": "http://example.com/hook",
                "score_inbound_threshold": 70,
                "score_outbound_threshold": 40,
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4. role_change_cross_client_blocked
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRoleChangeCrossClientBlocked:
    """Admin A must not be able to change the role of a user only in workspace B."""

    async def test_admin_cannot_change_role_of_user_in_foreign_workspace(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        from app.models.client import Client
        from app.models.user import User, UserClient
        from app.core.security import hash_password

        # Create a second workspace.
        client_b = Client(name="Workspace B Role", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        # Create a member who belongs ONLY to workspace B.
        member_b = User(
            email="member_b@workspaceb.com",
            hashed_password=hash_password("test"),
            role="member",
            is_active=True,
        )
        db_session.add(member_b)
        await db_session.commit()
        await db_session.refresh(member_b)
        db_session.add(UserClient(user_id=member_b.id, client_id=client_b.id))
        await db_session.commit()

        # Admin A belongs to seeded_client (client A) only.
        admin = seeded_users["admin"]
        token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=seeded_client.id,
            token_version=1,
        )

        # Admin A tries to change member B's role — must be 403.
        resp = await http_client.patch(
            f"/api/admin/users/{member_b.id}",
            headers=_auth(token),
            json={"role": "admin"},
        )
        assert resp.status_code == 403

    async def test_superadmin_can_change_role_across_workspaces(
        self, http_client, db_session, seeded_superadmin, seeded_client
    ):
        from app.models.client import Client
        from app.models.user import User, UserClient
        from app.core.security import hash_password

        client_b = Client(name="Workspace B Role SA", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        member_b = User(
            email="member_b2@workspaceb.com",
            hashed_password=hash_password("test"),
            role="member",
            is_active=True,
        )
        db_session.add(member_b)
        await db_session.commit()
        await db_session.refresh(member_b)
        db_session.add(UserClient(user_id=member_b.id, client_id=client_b.id))
        await db_session.commit()

        token = create_access_token(
            user_id=seeded_superadmin.id,
            email=seeded_superadmin.email,
            role="superadmin",
            active_client_id=seeded_client.id,
            token_version=1,
        )

        resp = await http_client.patch(
            f"/api/admin/users/{member_b.id}",
            headers=_auth(token),
            json={"role": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


# ---------------------------------------------------------------------------
# 5. bulk_upsert_company_linking
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBulkUpsertCompanyLinking:
    """Leads created via bulk_upsert_leads must get company_id auto-linked."""

    async def test_leads_linked_to_matching_company_by_domain(
        self, db_session, seeded_client
    ):
        from app.models.company import Company
        from app.models.lead import Lead
        from app.schemas.lead import LeadCreate
        from app.services.lead import bulk_upsert_leads

        # Create a company with domain "bulktest.com".
        company = Company(
            name="Bulk Test Corp",
            domain="bulktest.com",
            client_id=seeded_client.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        # Bulk import two leads with emails at bulktest.com.
        leads_data = [
            LeadCreate(name="Alice", email="alice@bulktest.com"),
            LeadCreate(name="Bob", email="bob@bulktest.com"),
        ]
        result = await bulk_upsert_leads(
            db_session, leads_data, seeded_client.id, on_duplicate="skip"
        )
        assert result["created"] == 2

        # Verify company_id was set on both leads.
        rows = (
            await db_session.execute(
                select(Lead).where(Lead.client_id == seeded_client.id)
            )
        ).scalars().all()
        assert len(rows) == 2
        for lead in rows:
            assert lead.company_id == company.id, (
                f"Lead {lead.email} was not linked to company {company.id}"
            )

    async def test_leads_without_matching_domain_not_linked(
        self, db_session, seeded_client
    ):
        from app.schemas.lead import LeadCreate
        from app.services.lead import bulk_upsert_leads
        from app.models.lead import Lead

        leads_data = [LeadCreate(name="Carol", email="carol@nomatch.com")]
        result = await bulk_upsert_leads(
            db_session, leads_data, seeded_client.id, on_duplicate="skip"
        )
        assert result["created"] == 1

        lead = (
            await db_session.execute(
                select(Lead).where(Lead.email == "carol@nomatch.com")
            )
        ).scalar_one()
        assert lead.company_id is None


# ---------------------------------------------------------------------------
# 6. client_deactivation_blocks_jwt
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestClientDeactivationBlocksJWT:
    """Deactivating a client must immediately block JWT access and invalidate tokens."""

    async def test_jwt_access_blocked_after_client_deactivation(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """A valid JWT for an active client returns 200; after deactivation it is rejected."""
        from app.schemas.client import ClientUpdate
        from app.services.client import update_client as svc_update_client

        member = seeded_users["member"]
        token = create_access_token(
            user_id=member.id,
            email=member.email,
            role="member",
            active_client_id=seeded_client.id,
            token_version=member.token_version,
        )

        # Confirm the token works before deactivation
        resp = await http_client.get("/api/leads/", headers=_auth(token))
        assert resp.status_code == 200

        # Deactivate the client — this also bumps token_version for all members
        await svc_update_client(db_session, seeded_client.id, ClientUpdate(is_active=False))

        # The same JWT must now be rejected
        resp = await http_client.get("/api/leads/", headers=_auth(token))
        assert resp.status_code != 200, (
            "JWT was accepted after client deactivation — get_client_id did not "
            "validate client.is_active"
        )

    async def test_token_version_incremented_for_all_client_members_on_deactivation(
        self, db_session, seeded_users, seeded_client
    ):
        """All user token_versions in the client must be bumped so old JWTs are dead."""
        from app.schemas.client import ClientUpdate
        from app.services.client import update_client as svc_update_client
        from app.models.user import User

        member = seeded_users["member"]
        admin = seeded_users["admin"]
        pre_member_version = member.token_version
        pre_admin_version = admin.token_version

        await svc_update_client(db_session, seeded_client.id, ClientUpdate(is_active=False))

        await db_session.refresh(member)
        await db_session.refresh(admin)

        assert member.token_version == pre_member_version + 1, (
            "member token_version was not incremented on client deactivation"
        )
        assert admin.token_version == pre_admin_version + 1, (
            "admin token_version was not incremented on client deactivation"
        )

    async def test_only_superadmin_can_deactivate_via_api(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """An admin (not superadmin) must receive 403 when trying to set is_active=False."""
        admin = seeded_users["admin"]
        token = create_access_token(
            user_id=admin.id,
            email=admin.email,
            role="admin",
            active_client_id=seeded_client.id,
            token_version=admin.token_version,
        )

        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"is_active": False},
        )
        assert resp.status_code == 403

    async def test_membership_revocation_blocks_access(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Removing a user from user_clients must cause get_client_id to return 403."""
        from app.models.user import UserClient

        member = seeded_users["member"]
        token = create_access_token(
            user_id=member.id,
            email=member.email,
            role="member",
            active_client_id=seeded_client.id,
            token_version=member.token_version,
        )

        # Confirm access is granted before removal
        resp = await http_client.get("/api/leads/", headers=_auth(token))
        assert resp.status_code == 200

        # Remove the user from the client directly
        membership = (
            await db_session.execute(
                select(UserClient).where(
                    UserClient.user_id == member.id,
                    UserClient.client_id == seeded_client.id,
                )
            )
        ).scalar_one()
        await db_session.delete(membership)
        await db_session.commit()

        # Access must now be denied — JWT is still valid but membership is gone
        resp = await http_client.get("/api/leads/", headers=_auth(token))
        assert resp.status_code == 403, (
            "Request was not rejected after user was removed from client — "
            "get_client_id did not verify user_clients membership"
        )


# ---------------------------------------------------------------------------
# 7. client_deactivation_blocks_api_key
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestClientDeactivationBlocksAPIKey:
    """Deactivating a client must immediately block webhook API-key access."""

    async def test_api_keys_deactivated_on_client_deactivation(
        self, db_session, seeded_client, seeded_api_key
    ):
        """API keys linked to the client must have is_active=False after deactivation."""
        from app.models.user import ApiKey
        from app.schemas.client import ClientUpdate
        from app.services.auth import hash_api_key
        from app.services.client import update_client as svc_update_client

        await svc_update_client(db_session, seeded_client.id, ClientUpdate(is_active=False))

        api_key_row = (
            await db_session.execute(
                select(ApiKey).where(ApiKey.key == hash_api_key(seeded_api_key))
            )
        ).scalar_one()
        assert api_key_row.is_active is False, (
            "API key was not deactivated when its client was deactivated"
        )

    async def test_webhook_blocked_after_client_deactivation(
        self, http_client, db_session, seeded_client, seeded_api_key
    ):
        """Webhook requests using an API key for a deactivated client must be rejected."""
        from app.schemas.client import ClientUpdate
        from app.services.client import update_client as svc_update_client

        # Deactivation deactivates the API key as a side effect
        await svc_update_client(db_session, seeded_client.id, ClientUpdate(is_active=False))

        resp = await http_client.post(
            "/api/webhooks/leads",
            headers={"X-Api-Key": seeded_api_key},
            json={"name": "Test Lead", "email": "test@example.com"},
        )
        assert resp.status_code != 201, (
            "Webhook was accepted after client deactivation — API key or client "
            "active check is not enforced"
        )

    async def test_active_api_key_for_inactive_client_blocked_by_dep(
        self, http_client, db_session, seeded_client, seeded_api_key
    ):
        """get_client_id_from_api_key must reject an active API key if its client is
        inactive — this covers the case where deactivation side effects are bypassed
        (e.g., direct DB write) but the client row is still marked inactive."""
        from sqlalchemy import update as sa_update
        from app.models.client import Client

        # Mark the client inactive without going through update_client,
        # so the API key retains is_active=True
        await db_session.execute(
            sa_update(Client)
            .where(Client.id == seeded_client.id)
            .values(is_active=False)
        )
        await db_session.commit()

        resp = await http_client.post(
            "/api/webhooks/leads",
            headers={"X-Api-Key": seeded_api_key},
            json={"name": "Test Lead", "email": "test@example.com"},
        )
        assert resp.status_code == 403, (
            f"Expected 403 from get_client_id_from_api_key for inactive client, "
            f"got {resp.status_code}"
        )
