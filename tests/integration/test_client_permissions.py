"""Integration tests for client API permission hardening.

Covers:
  1. GET /clients/me and GET /clients/{id} never expose settings
  2. GET /clients/me rejects deactivated users (uses get_current_active_user via get_client_id)
  3. PATCH /clients/{id} — member receives 403, admin receives 200
  4. PATCH /clients/{id} settings field — member blocked at role level
  5. Admin PATCH response includes settings so the caller can verify what changed
"""
import pytest
from app.core.security import create_access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _member_token(user, client_id: int) -> str:
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role="member",
        active_client_id=client_id,
        token_version=user.token_version,
    )


def _admin_token(user, client_id: int) -> str:
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role="admin",
        active_client_id=client_id,
        token_version=user.token_version,
    )


# ---------------------------------------------------------------------------
# GET /clients/me — settings must not appear; auth must be enforced
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetMyClient:

    async def test_settings_absent_from_me_response(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """GET /clients/me must not include settings for any role."""
        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        resp = await http_client.get("/api/clients/me", headers=_auth(token))

        assert resp.status_code == 200
        body = resp.json()
        assert "settings" not in body, (
            "settings key must not appear in /clients/me response for a member"
        )
        # Verify the public fields are present
        assert body["id"] == seeded_client.id
        assert "name" in body

    async def test_admin_also_gets_no_settings_from_me(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Admins also receive the public (settings-free) response from /clients/me."""
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        resp = await http_client.get("/api/clients/me", headers=_auth(token))

        assert resp.status_code == 200
        assert "settings" not in resp.json()

    async def test_deactivated_user_cannot_call_me(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """A deactivated user must be rejected — /me now validates via get_client_id
        which chains through get_current_user and checks is_active."""
        from app.models.user import User
        from sqlalchemy import update as sa_update

        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        # Confirm it works before deactivation
        resp = await http_client.get("/api/clients/me", headers=_auth(token))
        assert resp.status_code == 200

        # Deactivate the user
        await db_session.execute(
            sa_update(User).where(User.id == member.id).values(is_active=False)
        )
        await db_session.commit()

        resp = await http_client.get("/api/clients/me", headers=_auth(token))
        assert resp.status_code == 401, (
            "Deactivated user was not rejected by /clients/me — "
            "endpoint is not using get_current_active_user"
        )

    async def test_unauthenticated_request_rejected(self, http_client):
        """No bearer token → 401."""
        resp = await http_client.get("/api/clients/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /clients/{id} — settings must not appear
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetClientById:

    async def test_settings_absent_for_member(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        resp = await http_client.get(
            f"/api/clients/{seeded_client.id}", headers=_auth(token)
        )

        assert resp.status_code == 200
        assert "settings" not in resp.json(), (
            "settings must not appear in GET /clients/{id} for a member"
        )

    async def test_settings_absent_for_admin(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        resp = await http_client.get(
            f"/api/clients/{seeded_client.id}", headers=_auth(token)
        )

        assert resp.status_code == 200
        assert "settings" not in resp.json(), (
            "settings must not appear in GET /clients/{id} even for admins"
        )

    async def test_member_cannot_access_foreign_client(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """A member's token for client A must not grant access to client B."""
        from app.models.client import Client

        client_b = Client(name="Foreign Client", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        resp = await http_client.get(
            f"/api/clients/{client_b.id}", headers=_auth(token)
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /clients/{id} — member blocked, admin allowed
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateClientPermissions:

    async def test_member_cannot_update_client(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Members must receive 403 on PATCH /clients/{id}."""
        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"name": "Hacked Name"},
        )
        assert resp.status_code == 403, (
            f"Member received {resp.status_code} — expected 403. "
            "PATCH /clients must be restricted to admin+"
        )

    async def test_member_cannot_update_settings(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Members must be blocked from updating the settings dict."""
        member = seeded_users["member"]
        token = _member_token(member, seeded_client.id)

        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"settings": {"enrichment": {"apollo_api_key": "stolen"}}},
        )
        assert resp.status_code == 403, (
            "Member was able to submit a settings update — role gate is missing"
        )

    async def test_admin_can_update_client_name(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Admins must be able to PATCH /clients/{id}."""
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        new_name = "Admin Renamed Workspace"
        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"name": new_name},
        )
        assert resp.status_code == 200, (
            f"Admin received {resp.status_code} — expected 200"
        )
        assert resp.json()["name"] == new_name

    async def test_admin_update_response_includes_settings(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Admin PATCH response must include settings so the caller can verify the change."""
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"name": "Settings Visible"},
        )
        assert resp.status_code == 200
        assert "settings" in resp.json(), (
            "Admin PATCH response must include settings — admins need to verify their changes"
        )

    async def test_admin_can_update_settings(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """Admins must be able to update the settings dict via PATCH."""
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        new_settings = {"routing": {"score_inbound_threshold": 50}}
        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"settings": new_settings},
        )
        assert resp.status_code == 200
        assert resp.json()["settings"] == new_settings

    async def test_admin_cannot_deactivate_client(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """is_active=False is superadmin-only even when the caller is an admin."""
        admin = seeded_users["admin"]
        token = _admin_token(admin, seeded_client.id)

        resp = await http_client.patch(
            f"/api/clients/{seeded_client.id}",
            headers=_auth(token),
            json={"is_active": False},
        )
        assert resp.status_code == 403

    async def test_admin_of_foreign_client_cannot_update(
        self, http_client, db_session, seeded_users, seeded_client
    ):
        """An admin's token for client A must be rejected for client B's PATCH."""
        from app.models.client import Client

        client_b = Client(name="Other Workspace", settings={})
        db_session.add(client_b)
        await db_session.commit()
        await db_session.refresh(client_b)

        admin = seeded_users["admin"]
        # Token is scoped to seeded_client, not client_b
        token = _admin_token(admin, seeded_client.id)

        resp = await http_client.patch(
            f"/api/clients/{client_b.id}",
            headers=_auth(token),
            json={"name": "Cross-tenant rename"},
        )
        assert resp.status_code == 403
