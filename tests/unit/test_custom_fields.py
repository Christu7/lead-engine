"""Unit tests for custom field service helpers.

DB interactions are mocked. Tests cover:
- safe_extract_path: dot-notation extraction, array indexing, edge cases
- validate_custom_field_value: all field types
- apply_enrichment_mappings: happy path + skips missing/invalid values
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.custom_fields import (
    safe_extract_path,
    validate_custom_field_value,
)
from app.models.custom_field import CustomFieldDefinition


# ---------------------------------------------------------------------------
# safe_extract_path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSafeExtractPath:

    def test_simple_key(self):
        assert safe_extract_path({"name": "Acme"}, "name") == "Acme"

    def test_nested_key(self):
        data = {"organization": {"name": "Acme", "employee_count": 100}}
        assert safe_extract_path(data, "organization.name") == "Acme"
        assert safe_extract_path(data, "organization.employee_count") == 100

    def test_deep_nesting(self):
        data = {"a": {"b": {"c": {"d": 42}}}}
        assert safe_extract_path(data, "a.b.c.d") == 42

    def test_array_index(self):
        data = {"technologies": [{"name": "Python"}, {"name": "Go"}]}
        assert safe_extract_path(data, "technologies[0].name") == "Python"
        assert safe_extract_path(data, "technologies[1].name") == "Go"

    def test_array_index_out_of_bounds(self):
        data = {"technologies": [{"name": "Python"}]}
        assert safe_extract_path(data, "technologies[5].name") is None

    def test_missing_key(self):
        assert safe_extract_path({"a": 1}, "b") is None

    def test_missing_nested_key(self):
        assert safe_extract_path({"a": {"b": 1}}, "a.c") is None

    def test_none_data(self):
        assert safe_extract_path(None, "a.b") is None

    def test_empty_path(self):
        assert safe_extract_path({"a": 1}, "") is None

    def test_non_dict_intermediate(self):
        data = {"a": "not_a_dict"}
        assert safe_extract_path(data, "a.b") is None

    def test_array_key_but_value_is_not_list(self):
        data = {"technologies": "Python"}
        assert safe_extract_path(data, "technologies[0]") is None

    def test_none_value_in_path(self):
        data = {"a": None}
        assert safe_extract_path(data, "a.b") is None

    def test_integer_value_returned(self):
        data = {"org": {"size": 250}}
        assert safe_extract_path(data, "org.size") == 250

    def test_boolean_value_returned(self):
        data = {"org": {"active": True}}
        assert safe_extract_path(data, "org.active") is True

    def test_list_value_returned(self):
        data = {"keywords": ["saas", "b2b"]}
        assert safe_extract_path(data, "keywords") == ["saas", "b2b"]


# ---------------------------------------------------------------------------
# validate_custom_field_value
# ---------------------------------------------------------------------------


def _make_fd(**kwargs):
    """Return a MagicMock that looks like a CustomFieldDefinition."""
    fd = MagicMock(spec=CustomFieldDefinition)
    for k, v in kwargs.items():
        setattr(fd, k, v)
    return fd


@pytest.mark.unit
class TestValidateCustomFieldValue:

    def test_none_always_valid(self):
        fd = _make_fd(field_type="text")
        valid, msg = validate_custom_field_value(fd, None)
        assert valid is True

    def test_text_valid(self):
        fd = _make_fd(field_type="text")
        valid, _ = validate_custom_field_value(fd, "hello")
        assert valid is True

    def test_text_not_string(self):
        fd = _make_fd(field_type="text")
        valid, msg = validate_custom_field_value(fd, 123)
        assert valid is False

    def test_text_too_long(self):
        fd = _make_fd(field_type="text")
        valid, msg = validate_custom_field_value(fd, "x" * 10_001)
        assert valid is False

    def test_number_int_valid(self):
        fd = _make_fd(field_type="number")
        valid, _ = validate_custom_field_value(fd, 42)
        assert valid is True

    def test_number_float_valid(self):
        fd = _make_fd(field_type="number")
        valid, _ = validate_custom_field_value(fd, 3.14)
        assert valid is True

    def test_number_string_invalid(self):
        fd = _make_fd(field_type="number")
        valid, _ = validate_custom_field_value(fd, "42")
        assert valid is False

    def test_number_nan_invalid(self):
        import math
        fd = _make_fd(field_type="number")
        valid, _ = validate_custom_field_value(fd, math.nan)
        assert valid is False

    def test_number_inf_invalid(self):
        import math
        fd = _make_fd(field_type="number")
        valid, _ = validate_custom_field_value(fd, math.inf)
        assert valid is False

    def test_date_valid(self):
        fd = _make_fd(field_type="date")
        valid, _ = validate_custom_field_value(fd, "2026-03-28")
        assert valid is True

    def test_date_invalid_format(self):
        fd = _make_fd(field_type="date")
        valid, _ = validate_custom_field_value(fd, "28/03/2026")
        assert valid is False

    def test_boolean_true_valid(self):
        fd = _make_fd(field_type="boolean")
        valid, _ = validate_custom_field_value(fd, True)
        assert valid is True

    def test_boolean_string_invalid(self):
        fd = _make_fd(field_type="boolean")
        valid, _ = validate_custom_field_value(fd, "true")
        assert valid is False

    def test_select_valid_option(self):
        fd = _make_fd(field_type="select", options=["hot", "warm", "cold"])
        valid, _ = validate_custom_field_value(fd, "hot")
        assert valid is True

    def test_select_invalid_option(self):
        fd = _make_fd(field_type="select", options=["hot", "warm", "cold"])
        valid, msg = validate_custom_field_value(fd, "lukewarm")
        assert valid is False
        assert "hot" in msg

    def test_select_empty_options(self):
        fd = _make_fd(field_type="select", options=[])
        valid, _ = validate_custom_field_value(fd, "anything")
        assert valid is False


# ---------------------------------------------------------------------------
# apply_enrichment_mappings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyEnrichmentMappings:

    def _make_mapped_fd(self, field_key, field_type, source, mapping, options=None):
        fd = _make_fd(
            field_key=field_key,
            field_type=field_type,
            enrichment_source=source,
            enrichment_mapping=mapping,
            options=options,
            deleted_at=None,
            client_id=1,
        )
        return fd

    async def test_happy_path_writes_value(self):
        """Field with enrichment_source/mapping should be auto-filled from enrichment data."""
        from app.services.custom_fields import apply_enrichment_mappings

        fd = self._make_mapped_fd("employee_count", "number", "apollo", "employee_count")
        entity = MagicMock()
        entity.__tablename__ = "leads"
        entity.id = 1
        entity.enrichment_data = {"apollo": {"employee_count": 500}}

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with (
            patch(
                "app.services.custom_fields.get_field_definitions",
                AsyncMock(return_value=[fd]),
            ),
        ):
            await apply_enrichment_mappings(db, entity, entity.enrichment_data, 1, "lead")

        # execute was called once (for the UPDATE)
        db.execute.assert_called_once()

    async def test_skips_when_source_not_in_enrichment_data(self):
        """Missing enrichment source → no write."""
        from app.services.custom_fields import apply_enrichment_mappings

        fd = self._make_mapped_fd("employee_count", "number", "clearbit", "employee_count")
        entity = MagicMock()
        entity.__tablename__ = "leads"
        entity.id = 1

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        with (
            patch(
                "app.services.custom_fields.get_field_definitions",
                AsyncMock(return_value=[fd]),
            ),
        ):
            await apply_enrichment_mappings(db, entity, {"apollo": {"employee_count": 100}}, 1, "lead")

        db.execute.assert_not_called()

    async def test_skips_invalid_value(self):
        """Value that fails type validation is silently skipped."""
        from app.services.custom_fields import apply_enrichment_mappings

        fd = self._make_mapped_fd("count", "number", "apollo", "count")
        entity = MagicMock()
        entity.__tablename__ = "leads"
        entity.id = 1

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        with (
            patch(
                "app.services.custom_fields.get_field_definitions",
                AsyncMock(return_value=[fd]),
            ),
        ):
            await apply_enrichment_mappings(
                db, entity, {"apollo": {"count": "not_a_number"}}, 1, "lead"
            )

        db.execute.assert_not_called()

    async def test_no_mapped_defs_returns_early(self):
        """Field defs without enrichment_source/mapping → no queries."""
        from app.services.custom_fields import apply_enrichment_mappings

        fd = _make_fd(
            field_key="notes", field_type="text",
            enrichment_source=None, enrichment_mapping=None,
            deleted_at=None,
        )

        db = MagicMock()
        db.execute = AsyncMock()

        with (
            patch(
                "app.services.custom_fields.get_field_definitions",
                AsyncMock(return_value=[fd]),
            ),
        ):
            await apply_enrichment_mappings(db, MagicMock(), {}, 1, "lead")

        db.execute.assert_not_called()

    async def test_nested_path_extraction(self):
        """Dot-notation path is correctly resolved before writing."""
        from app.services.custom_fields import apply_enrichment_mappings

        fd = self._make_mapped_fd("industry", "text", "organization", "industry")
        entity = MagicMock()
        entity.__tablename__ = "companies"
        entity.id = 1

        db = MagicMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        enrichment_data = {"organization": {"industry": "Software"}}

        with (
            patch(
                "app.services.custom_fields.get_field_definitions",
                AsyncMock(return_value=[fd]),
            ),
        ):
            await apply_enrichment_mappings(db, entity, enrichment_data, 1, "company")

        db.execute.assert_called_once()
