"""Custom field definition management and value persistence.

Values are stored in enrichment_data JSONB under the "custom_fields" namespace.
Atomic updates use PostgreSQL jsonb_set() to prevent concurrent-write data loss.
"""
import json
import logging
import re
from datetime import datetime, date
from math import isnan, isinf
from typing import Any

_ARRAY_INDEX_RE = re.compile(r"^([^\[]+)\[(\d+)\]$")

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_field import CustomFieldDefinition

logger = logging.getLogger(__name__)

FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class IncompatibleFieldTypeError(Exception):
    """Raised when a type change would invalidate existing data."""
    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(f"{count} record(s) have values incompatible with the new field type")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_custom_field_value(field_def: CustomFieldDefinition, value: Any) -> tuple[bool, str | None]:
    """Validate a value against its field definition.

    Returns (True, None) on success or (False, error_message) on failure.
    None/null is always valid — it clears the field.
    """
    if value is None:
        return True, None

    ft = field_def.field_type

    if ft == "text":
        if not isinstance(value, str):
            return False, "Value must be a string"
        if len(value) > 10_000:
            return False, "Text value exceeds maximum length of 10,000 characters"

    elif ft == "number":
        if not isinstance(value, (int, float)):
            return False, "Value must be a number"
        if isinstance(value, float) and (isnan(value) or isinf(value)):
            return False, "Value must be a finite number (NaN and Infinity are not allowed)"

    elif ft == "date":
        if not isinstance(value, str):
            return False, "Date value must be a string in YYYY-MM-DD format"
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False, "Date value must be in YYYY-MM-DD format"

    elif ft == "boolean":
        if not isinstance(value, bool):
            return False, "Value must be true or false"

    elif ft == "select":
        options = field_def.options or []
        if value not in options:
            return False, f"Value must be one of: {', '.join(options)}"

    return True, None


def _parse_stored_value(raw_json: str) -> Any:
    """Parse a JSON string from the database back to a Python value."""
    try:
        return json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return raw_json


# ---------------------------------------------------------------------------
# Field definition CRUD
# ---------------------------------------------------------------------------


async def get_field_definitions(
    db: AsyncSession,
    client_id: int,
    entity_type: str,
) -> list[CustomFieldDefinition]:
    """Return active (non-deleted) field definitions ordered by sort_order."""
    from sqlalchemy import select
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.client_id == client_id,
            CustomFieldDefinition.entity_type == entity_type,
            CustomFieldDefinition.deleted_at.is_(None),
        )
        .order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.created_at)
    )
    return list(result.scalars().all())


async def create_field_definition(
    db: AsyncSession,
    data,  # CustomFieldDefinitionCreate schema
    client_id: int,
) -> CustomFieldDefinition:
    """Create a new field definition.

    Raises HTTPException-style errors via ValueError for the API layer to handle.
    409 if the field_key already exists (including soft-deleted — suggest restore).
    """
    from sqlalchemy import select

    existing = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.client_id == client_id,
            CustomFieldDefinition.entity_type == data.entity_type,
            CustomFieldDefinition.field_key == data.field_key,
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        if found.deleted_at is not None:
            raise ValueError(f"RESTORE_HINT:{found.id}")
        raise ValueError("DUPLICATE_KEY")

    field_def = CustomFieldDefinition(
        client_id=client_id,
        entity_type=data.entity_type,
        field_key=data.field_key,
        field_label=data.field_label,
        field_type=data.field_type,
        options=data.options,
        is_required=data.is_required,
        show_in_table=data.show_in_table,
        sort_order=data.sort_order,
    )
    db.add(field_def)
    await db.commit()
    await db.refresh(field_def)
    return field_def


async def update_field_definition(
    db: AsyncSession,
    field_id,
    data,  # CustomFieldDefinitionUpdate schema
    client_id: int,
    force: bool = False,
) -> CustomFieldDefinition:
    """Update a field definition.

    If field_type is changing, checks for incompatible existing data.
    Raises IncompatibleFieldTypeError (count) unless force=True, in which case
    nullifies incompatible records.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.client_id == client_id,
            CustomFieldDefinition.deleted_at.is_(None),
        )
    )
    field_def = result.scalar_one_or_none()
    if field_def is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # If field_type is changing, check for incompatible existing values
    new_type = update_data.get("field_type")
    if new_type and new_type != field_def.field_type:
        # Build a temporary field_def with the new type to validate against
        temp_def = CustomFieldDefinition(
            field_type=new_type,
            field_key=field_def.field_key,
            options=update_data.get("options", field_def.options),
        )
        incompatible_ids = await _find_incompatible_records(
            db, field_def, temp_def, client_id
        )
        if incompatible_ids:
            if not force:
                raise IncompatibleFieldTypeError(len(incompatible_ids))
            # Nullify incompatible values
            table = "leads" if field_def.entity_type == "lead" else "companies"
            await _nullify_field_values(db, table, incompatible_ids, field_def.field_key, client_id)
            logger.warning(
                "Force-nullified %d record(s) with incompatible values for field %s",
                len(incompatible_ids),
                field_def.field_key,
                extra={"field_key": field_def.field_key, "client_id": client_id, "count": len(incompatible_ids)},
            )

    # Warn if select options are being reduced
    new_options = update_data.get("options")
    if (
        new_options is not None
        and field_def.field_type == "select"
        and field_def.options
    ):
        removed = set(field_def.options) - set(new_options)
        if removed:
            table = "leads" if field_def.entity_type == "lead" else "companies"
            count = await _count_records_with_values(
                db, table, field_def.field_key, client_id, value_in=list(removed)
            )
            if count > 0:
                logger.warning(
                    "Reducing select options for field %s: %d record(s) use removed option(s) %s",
                    field_def.field_key,
                    count,
                    removed,
                    extra={"field_key": field_def.field_key, "client_id": client_id},
                )

    for key, value in update_data.items():
        setattr(field_def, key, value)

    await db.commit()
    await db.refresh(field_def)
    return field_def


async def delete_field_definition(
    db: AsyncSession,
    field_id,
    client_id: int,
) -> bool:
    """Soft-delete a field definition."""
    from sqlalchemy import select
    from datetime import timezone

    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.client_id == client_id,
            CustomFieldDefinition.deleted_at.is_(None),
        )
    )
    field_def = result.scalar_one_or_none()
    if field_def is None:
        return False

    # Warn about records that have data for this field
    table = "leads" if field_def.entity_type == "lead" else "companies"
    count = await _count_records_with_field(db, table, field_def.field_key, client_id)
    if count > 0:
        logger.warning(
            "Soft-deleting field %s: %d record(s) still have data for this field",
            field_def.field_key,
            count,
            extra={"field_key": field_def.field_key, "client_id": client_id, "record_count": count},
        )

    field_def.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def restore_field_definition(
    db: AsyncSession,
    field_id,
    client_id: int,
) -> CustomFieldDefinition | None:
    """Restore a soft-deleted field definition."""
    from sqlalchemy import select

    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.client_id == client_id,
            CustomFieldDefinition.deleted_at.isnot(None),
        )
    )
    field_def = result.scalar_one_or_none()
    if field_def is None:
        return None

    field_def.deleted_at = None
    await db.commit()
    await db.refresh(field_def)
    return field_def


# ---------------------------------------------------------------------------
# Value get/set
# ---------------------------------------------------------------------------


def get_custom_field_values(
    entity,
    field_definitions: list[CustomFieldDefinition],
) -> dict[str, Any]:
    """Extract custom field values from entity.enrichment_data.

    Only returns values for active (non-deleted) field definitions.
    Returns None for fields with no value set.
    """
    raw = (entity.enrichment_data or {}).get("custom_fields", {}) or {}
    active_keys = {fd.field_key for fd in field_definitions if fd.deleted_at is None}
    return {key: raw.get(key) for key in active_keys}


async def set_custom_field_values(
    db: AsyncSession,
    entity,
    updates: dict[str, Any],
    field_definitions: list[CustomFieldDefinition],
    client_id: int,
) -> Any:
    """Set custom field values on an entity using atomic jsonb_set() calls.

    Validates all values before writing. Returns the refreshed entity.
    """
    field_def_map = {fd.field_key: fd for fd in field_definitions if fd.deleted_at is None}

    # Validate all values first — fail fast before any writes
    errors: dict[str, str] = {}
    for key, value in updates.items():
        if key not in field_def_map:
            errors[key] = "Unknown or inactive field"
            continue
        valid, msg = validate_custom_field_value(field_def_map[key], value)
        if not valid:
            errors[key] = msg  # type: ignore[assignment]

    if errors:
        raise ValueError(f"Validation errors: {errors}")

    table = entity.__tablename__
    entity_id = entity.id

    for key, value in updates.items():
        json_value = json.dumps(value)
        # Atomically merge one custom field into enrichment_data using jsonb || concat.
        # COALESCE only catches SQL NULL, not JSON null scalars, so we use jsonb_typeof
        # to ensure both the base object and the custom_fields sub-object are real objects.
        stmt = text(f"""
            UPDATE {table}
            SET enrichment_data =
                CASE
                    WHEN enrichment_data IS NULL
                      OR jsonb_typeof(enrichment_data) != 'object'
                    THEN CAST('{{}}' AS jsonb)
                    ELSE enrichment_data
                END
                ||
                jsonb_build_object(
                    'custom_fields',
                    CASE
                        WHEN enrichment_data->'custom_fields' IS NULL
                          OR jsonb_typeof(enrichment_data->'custom_fields') != 'object'
                        THEN CAST('{{}}' AS jsonb)
                        ELSE enrichment_data->'custom_fields'
                    END
                    ||
                    jsonb_build_object(CAST(:field_key AS text), CAST(:json_value AS jsonb))
                )
            WHERE id = :entity_id AND client_id = :client_id
        """)  # nosec — table name comes from ORM __tablename__, not user input
        await db.execute(stmt, {
            "field_key": key,
            "json_value": json_value,
            "entity_id": entity_id,
            "client_id": client_id,
        })

    await db.commit()
    await db.refresh(entity)
    return entity


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_records_with_field(
    db: AsyncSession,
    table: str,
    field_key: str,
    client_id: int,
) -> int:
    """Count records that have a non-null value for a custom field."""
    stmt = text(f"""
        SELECT COUNT(*) FROM {table}
        WHERE client_id = :client_id
          AND enrichment_data->'custom_fields' ? :field_key
          AND enrichment_data->'custom_fields'->:field_key != 'null'::jsonb
    """)  # nosec — table name is from model, not user input
    result = await db.execute(stmt, {"client_id": client_id, "field_key": field_key})
    return result.scalar_one()


async def _count_records_with_values(
    db: AsyncSession,
    table: str,
    field_key: str,
    client_id: int,
    value_in: list[str],
) -> int:
    """Count records whose custom field value is in the given list."""
    if not value_in:
        return 0
    # Build parameterized placeholders to avoid SQL injection
    value_params = {f"v{i}": v for i, v in enumerate(value_in)}
    in_clause = ", ".join(f":v{i}" for i in range(len(value_in)))
    stmt = text(f"""
        SELECT COUNT(*) FROM {table}
        WHERE client_id = :client_id
          AND enrichment_data->'custom_fields'->>:field_key IN ({in_clause})
    """)
    result = await db.execute(stmt, {"client_id": client_id, "field_key": field_key, **value_params})
    return result.scalar_one()


async def _find_incompatible_records(
    db: AsyncSession,
    old_def: CustomFieldDefinition,
    new_def: CustomFieldDefinition,
    client_id: int,
) -> list:
    """Return IDs of records whose current value fails the new field type."""
    table = "leads" if old_def.entity_type == "lead" else "companies"
    stmt = text(f"""
        SELECT id, enrichment_data->'custom_fields'->:field_key AS val
        FROM {table}
        WHERE client_id = :client_id
          AND enrichment_data->'custom_fields' ? :field_key
          AND enrichment_data->'custom_fields'->:field_key != 'null'::jsonb
    """)  # nosec
    rows = await db.execute(stmt, {"client_id": client_id, "field_key": old_def.field_key})

    incompatible = []
    for row in rows:
        try:
            value = json.loads(row.val) if isinstance(row.val, str) else row.val
        except (TypeError, json.JSONDecodeError):
            value = row.val
        valid, _ = validate_custom_field_value(new_def, value)
        if not valid:
            incompatible.append(row.id)
    return incompatible


# ---------------------------------------------------------------------------
# Enrichment mapping helpers
# ---------------------------------------------------------------------------


def safe_extract_path(data: Any, path: str) -> Any:
    """Safely extract a value from nested dict/list using dot-notation path.

    Supports array indexing syntax: e.g. "technologies[0].name"
    Returns None if the path is missing, type is wrong, or any error occurs.
    Never raises. Never calls eval/exec.
    """
    if not path or data is None:
        return None

    current: Any = data
    for segment in path.split("."):
        if current is None:
            return None
        array_match = _ARRAY_INDEX_RE.match(segment)
        if array_match:
            key = array_match.group(1)
            idx = int(array_match.group(2))
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(segment)

    return current


async def apply_enrichment_mappings(
    db: AsyncSession,
    entity: Any,
    enrichment_data_raw: dict,
    client_id: int,
    entity_type: str,
) -> None:
    """Auto-fill custom fields from enrichment provider responses.

    For each field definition that has enrichment_source + enrichment_mapping set,
    looks up enrichment_data_raw[enrichment_source] and extracts the value at
    enrichment_mapping (dot-notation path).  Only writes values that are present
    and pass validation; silently skips missing or invalid values.
    """
    field_defs = await get_field_definitions(db, client_id, entity_type)
    mapped_defs = [
        fd for fd in field_defs
        if fd.enrichment_source and fd.enrichment_mapping
    ]
    if not mapped_defs:
        return

    updates: dict[str, Any] = {}
    for fd in mapped_defs:
        source_data = enrichment_data_raw.get(fd.enrichment_source)
        if source_data is None:
            continue
        value = safe_extract_path(source_data, fd.enrichment_mapping)
        if value is None:
            continue
        valid, msg = validate_custom_field_value(fd, value)
        if not valid:
            logger.debug(
                "apply_enrichment_mappings: skipping field %s — value %r failed validation: %s",
                fd.field_key,
                value,
                msg,
                extra={"field_key": fd.field_key, "client_id": client_id},
            )
            continue
        updates[fd.field_key] = value

    if updates:
        await set_custom_field_values(db, entity, updates, field_defs, client_id)


async def _nullify_field_values(
    db: AsyncSession,
    table: str,
    entity_ids: list,
    field_key: str,
    client_id: int,
) -> None:
    """Set the custom field to JSON null for the given entity IDs."""
    if not entity_ids:
        return
    id_params = {f"id_{i}": str(eid) for i, eid in enumerate(entity_ids)}
    placeholders = ", ".join(f":id_{i}" for i in range(len(entity_ids)))
    stmt = text(f"""
        UPDATE {table}
        SET enrichment_data = jsonb_set(
            enrichment_data,
            ARRAY['custom_fields', :field_key]::text[],
            CAST('null' AS jsonb),
            false
        )
        WHERE client_id = :client_id
          AND id::text IN ({placeholders})
    """)  # nosec
    await db.execute(stmt, {"field_key": field_key, "client_id": client_id, **id_params})
