"""Unit tests for ContactPullFilters schema and Apollo payload translation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.schemas.company import ContactPullFilters


def _make_pull_db():
    """Return a minimal db mock that supports the async calls made by pull_contacts_from_company."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ── Schema validation ──────────────────────────────────────────────────────────

class TestContactPullFiltersSchema:

    def test_defaults_are_empty_lists(self):
        f = ContactPullFilters()
        assert f.titles == []
        assert f.seniorities == []
        assert f.contact_locations == []
        assert f.include_keywords == []
        assert f.exclude_keywords == []
        assert f.limit == 25

    def test_all_fields_set(self):
        f = ContactPullFilters(
            titles=["VP of Sales"],
            seniorities=["vp", "director"],
            contact_locations=["New York", "United Kingdom"],
            include_keywords=["SaaS"],
            exclude_keywords=["intern"],
            limit=50,
        )
        assert f.titles == ["VP of Sales"]
        assert f.contact_locations == ["New York", "United Kingdom"]
        assert f.include_keywords == ["SaaS"]
        assert f.exclude_keywords == ["intern"]
        assert f.limit == 50

    def test_titles_capped_at_50(self):
        with pytest.raises(Exception, match="50"):
            ContactPullFilters(titles=[f"title_{i}" for i in range(51)])

    def test_seniorities_capped_at_20(self):
        with pytest.raises(Exception, match="20"):
            ContactPullFilters(seniorities=[f"s_{i}" for i in range(21)])

    def test_contact_locations_capped_at_10(self):
        with pytest.raises(Exception, match="10"):
            ContactPullFilters(contact_locations=[f"loc_{i}" for i in range(11)])

    def test_include_keywords_capped_at_10(self):
        with pytest.raises(Exception, match="10"):
            ContactPullFilters(include_keywords=[f"kw_{i}" for i in range(11)])

    def test_exclude_keywords_capped_at_10(self):
        with pytest.raises(Exception, match="10"):
            ContactPullFilters(exclude_keywords=[f"kw_{i}" for i in range(11)])

    def test_titles_truncated_to_200_chars(self):
        long_title = "A" * 300
        f = ContactPullFilters(titles=[long_title])
        assert len(f.titles[0]) == 200

    def test_locations_truncated_to_200_chars(self):
        long_loc = "B" * 300
        f = ContactPullFilters(contact_locations=[long_loc])
        assert len(f.contact_locations[0]) == 200

    def test_keywords_truncated_to_100_chars(self):
        long_kw = "C" * 150
        f = ContactPullFilters(include_keywords=[long_kw], exclude_keywords=[long_kw])
        assert len(f.include_keywords[0]) == 100
        assert len(f.exclude_keywords[0]) == 100

    def test_limit_min_1(self):
        with pytest.raises(Exception):
            ContactPullFilters(limit=0)

    def test_limit_max_100(self):
        with pytest.raises(Exception):
            ContactPullFilters(limit=101)

    def test_backward_compat_alias(self):
        from app.schemas.company import ContactPullRequest
        assert ContactPullRequest is ContactPullFilters


# ── Apollo payload translation ─────────────────────────────────────────────────

class TestApolloPayloadTranslation:
    """Verify that ContactPullFilters fields map to the correct Apollo API parameters.

    The ContactPullFilters schema uses provider-agnostic names (contact_locations).
    Translation to Apollo-specific names (person_locations, q_keywords, etc.)
    happens exclusively inside apollo_company.py.
    """

    def _make_company(self):
        company = MagicMock()
        company.id = "test-uuid"
        company.apollo_id = "apollo-org-123"
        company.name = "Acme Corp"
        return company

    @pytest.mark.asyncio
    async def test_basic_filters_in_payload(self):
        """titles, seniorities, and limit are always forwarded to Apollo."""
        filters = ContactPullFilters(
            titles=["VP of Sales"],
            seniorities=["vp"],
            limit=10,
        )
        captured = {}

        async def fake_post(url, headers, json):
            captured.update(json)
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        company = self._make_company()
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(_make_pull_db(), company, client_id=1, filters=filters)

        assert captured["organization_ids"] == ["apollo-org-123"]
        assert captured["person_titles"] == ["VP of Sales"]
        assert captured["person_seniorities"] == ["vp"]
        assert captured["per_page"] == 10

    @pytest.mark.asyncio
    async def test_contact_locations_translated_to_apollo_person_locations(self):
        """contact_locations (schema) is translated to person_locations (Apollo API)."""
        filters = ContactPullFilters(contact_locations=["New York", "London"])
        captured = {}

        async def fake_post(url, headers, json):
            captured.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        company = self._make_company()
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(_make_pull_db(), company, client_id=1, filters=filters)

        assert captured.get("person_locations") == ["New York", "London"]

    @pytest.mark.asyncio
    async def test_include_keywords_joined_as_q_keywords(self):
        filters = ContactPullFilters(include_keywords=["SaaS", "cloud"])
        captured = {}

        async def fake_post(url, headers, json):
            captured.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        company = self._make_company()
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(_make_pull_db(), company, client_id=1, filters=filters)

        assert captured.get("q_keywords") == "SaaS cloud"

    @pytest.mark.asyncio
    async def test_empty_contact_locations_not_in_payload(self):
        """person_locations must be omitted when empty (not sent as empty list)."""
        filters = ContactPullFilters()
        captured = {}

        async def fake_post(url, headers, json):
            captured.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        company = self._make_company()
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(_make_pull_db(), company, client_id=1, filters=filters)

        assert "person_locations" not in captured
        assert "q_keywords" not in captured


# ── exclude_keywords post-filter ───────────────────────────────────────────────

class TestExcludeKeywordsPostFilter:
    """exclude_keywords is applied client-side after Apollo response."""

    def _make_person(self, title: str, email: str = "test@example.com") -> dict:
        return {
            "id": "person-1",
            "first_name": "Test",
            "last_name": "User",
            "email": email,
            "title": title,
            "organization": {"name": "Acme"},
            "linkedin_url": None,
        }

    @pytest.mark.asyncio
    async def test_exclude_keywords_removes_matching_titles(self):
        filters = ContactPullFilters(exclude_keywords=["intern"])
        people = [
            self._make_person("Software Engineer", "eng@example.com"),
            self._make_person("Marketing Intern", "intern@example.com"),
        ]

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 2}}
            return resp

        company = MagicMock()
        company.id = "test-uuid"
        company.apollo_id = "apollo-org-123"
        company.name = "Acme"

        upserted = []

        async def fake_upsert(db, lead_data, client_id):
            upserted.append(lead_data.email)
            lead = MagicMock()
            lead.company_id = company.id
            return lead, "created"

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            result = await svc.pull_contacts_from_company(
                _make_pull_db(), company, client_id=1, filters=filters
            )

        assert "intern@example.com" not in upserted
        assert "eng@example.com" in upserted
        assert result["created"] == 1

    @pytest.mark.asyncio
    async def test_no_exclude_keywords_keeps_all(self):
        filters = ContactPullFilters()
        people = [
            self._make_person("CEO", "ceo@example.com"),
            self._make_person("CTO", "cto@example.com"),
        ]

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 2}}
            return resp

        company = MagicMock()
        company.id = "test-uuid"
        company.apollo_id = "apollo-org-123"
        company.name = "Acme"

        upserted = []

        async def fake_upsert(db, lead_data, client_id):
            upserted.append(lead_data.email)
            lead = MagicMock()
            lead.company_id = company.id
            return lead, "created"

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            result = await svc.pull_contacts_from_company(
                _make_pull_db(), company, client_id=1, filters=filters
            )

        assert set(upserted) == {"ceo@example.com", "cto@example.com"}
        assert result["created"] == 2

    @pytest.mark.asyncio
    async def test_exclude_keywords_case_insensitive(self):
        filters = ContactPullFilters(exclude_keywords=["INTERN"])
        people = [
            self._make_person("Marketing intern", "intern@example.com"),
            self._make_person("Director", "dir@example.com"),
        ]

        async def fake_post(url, headers, json):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": people, "pagination": {"total_entries": 2}}
            return resp

        company = MagicMock()
        company.id = "test-uuid"
        company.apollo_id = "apollo-org-123"
        company.name = "Acme"

        upserted = []

        async def fake_upsert(db, lead_data, client_id):
            upserted.append(lead_data.email)
            lead = MagicMock()
            lead.company_id = company.id
            return lead, "created"

        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("app.services.apollo_company.upsert_lead", new=fake_upsert), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.services.apollo_company import ApolloCompanyEnrichmentService
            svc = ApolloCompanyEnrichmentService()
            await svc.pull_contacts_from_company(
                _make_pull_db(), company, client_id=1, filters=filters
            )

        assert "intern@example.com" not in upserted
        assert "dir@example.com" in upserted


# ── Legacy kwargs backward compat ──────────────────────────────────────────────

class TestLegacyKwargsCompat:

    @pytest.mark.asyncio
    async def test_legacy_kwargs_produce_same_payload_as_filters(self):
        """Calling with legacy titles/seniorities/limit produces the same Apollo payload."""
        captured_legacy = {}
        captured_new = {}

        async def fake_post_legacy(url, headers, json):
            captured_legacy.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        async def fake_post_new(url, headers, json):
            captured_new.update(json)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"people": [], "pagination": {"total_entries": 0}}
            return resp

        company = MagicMock()
        company.id = "test-uuid"
        company.apollo_id = "apollo-org-123"
        company.name = "Acme"

        from app.services.apollo_company import ApolloCompanyEnrichmentService
        svc = ApolloCompanyEnrichmentService()

        # Legacy call
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post_legacy
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc.pull_contacts_from_company(
                _make_pull_db(), company, client_id=1,
                titles=["VP"], seniorities=["vp"], limit=10
            )

        # New-style call
        with patch("app.services.apollo_company._apollo_headers", new=AsyncMock(return_value={})), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post_new
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await svc.pull_contacts_from_company(
                _make_pull_db(), company, client_id=1,
                filters=ContactPullFilters(titles=["VP"], seniorities=["vp"], limit=10)
            )

        assert captured_legacy["person_titles"] == captured_new["person_titles"]
        assert captured_legacy["person_seniorities"] == captured_new["person_seniorities"]
        assert captured_legacy["per_page"] == captured_new["per_page"]
