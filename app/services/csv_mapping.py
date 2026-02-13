from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class FieldMapping:
    csv_column: str  # lowercase column header
    lead_field: str  # target LeadCreate field


@dataclass
class CSVFormatProfile:
    name: str
    detect_columns: set[str]  # columns that identify this format
    mappings: list[FieldMapping]
    enrichment_fields: dict[str, str]  # csv_col → key in enrichment_data JSON
    composite_transforms: list[Callable[[dict[str, str]], dict[str, str]]]
    source_value: str | None = None


def _apollo_name_transform(row: dict[str, str]) -> dict[str, str]:
    """Combine First Name + Last Name into name."""
    first = row.get("first name", "") or ""
    last = row.get("last name", "") or ""
    full = f"{first} {last}".strip()
    if full:
        row["name"] = full
    return row


def _apollo_phone_transform(row: dict[str, str]) -> dict[str, str]:
    """Pick the first available phone from Apollo's multiple phone columns."""
    for col in ("work direct phone", "mobile phone", "home phone", "corporate phone", "other phone"):
        val = row.get(col, "") or ""
        if val.strip():
            row["phone"] = val.strip().lstrip("'")
            break
    return row


APOLLO_PROFILE = CSVFormatProfile(
    name="apollo",
    detect_columns={"first name", "last name", "email"},
    mappings=[
        FieldMapping("email", "email"),
        FieldMapping("company name", "company"),
        FieldMapping("title", "title"),
    ],
    enrichment_fields={
        "person linkedin url": "linkedin_url",
        "website": "website",
        "city": "city",
        "state": "state",
        "country": "country",
        "industry": "industry",
        "# employees": "employee_count",
    },
    composite_transforms=[_apollo_name_transform, _apollo_phone_transform],
    source_value="apollo",
)

FORMAT_REGISTRY: dict[str, CSVFormatProfile] = {
    "apollo": APOLLO_PROFILE,
}


def detect_format(headers: list[str] | None) -> CSVFormatProfile | None:
    """Match CSV headers against registered format profiles.

    Returns the first matching profile, or None for identity mapping (existing format).
    """
    if not headers:
        return None
    normalized = {h.strip().lower() for h in headers}
    for profile in FORMAT_REGISTRY.values():
        if profile.detect_columns.issubset(normalized):
            return profile
    return None


def map_row(row: dict[str, str], profile: CSVFormatProfile | None) -> dict:
    """Transform a CSV row dict into a dict suitable for LeadCreate.

    If profile is None, passes through with empty-string→None cleanup.
    """
    if profile is None:
        return {k: (v if v != "" else None) for k, v in row.items()}

    # Normalize keys to lowercase
    normalized = {k.strip().lower(): v for k, v in row.items()}

    # Run composite transforms (e.g. first+last → name)
    for transform in profile.composite_transforms:
        normalized = transform(normalized)

    # Apply direct field mappings
    result: dict = {}
    for mapping in profile.mappings:
        val = normalized.get(mapping.csv_column)
        result[mapping.lead_field] = val if val != "" else None

    # Copy composite-produced fields (e.g. "name", "phone")
    for field in ("name", "phone"):
        if field in normalized and field not in result:
            result[field] = normalized[field] if normalized[field] != "" else None

    # Build enrichment_data from enrichment fields
    enrichment: dict[str, str] = {}
    for csv_col, enrich_key in profile.enrichment_fields.items():
        val = normalized.get(csv_col)
        if val and val.strip():
            enrichment[enrich_key] = val.strip()
    if enrichment:
        result["enrichment_data"] = enrichment

    # Auto-fill source
    if profile.source_value:
        result["source"] = profile.source_value

    return result
