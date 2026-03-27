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
    for col in ("corporate phone", "work direct phone", "mobile phone", "home phone", "other phone"):
        val = row.get(col, "") or ""
        if val.strip():
            row["phone"] = val.strip().lstrip("'")
            break
    return row


def _apollo_company_transform(row: dict[str, str]) -> dict[str, str]:
    """Normalise company to a single key, accepting both 'Company' and 'Company Name'."""
    val = row.get("company") or row.get("company name") or ""
    if val.strip():
        row["company"] = val.strip()
    return row


def _apollo_linkedin_transform(row: dict[str, str]) -> dict[str, str]:
    """Normalise LinkedIn URL to a single key, accepting multiple column names."""
    val = (
        row.get("linkedin url")
        or row.get("person linkedin url")
        or row.get("linkedin")
        or ""
    )
    if val.strip():
        row["linkedin url"] = val.strip()
    return row


APOLLO_PROFILE = CSVFormatProfile(
    name="apollo",
    detect_columns={"first name", "last name", "email"},
    mappings=[
        FieldMapping("email", "email"),
        FieldMapping("company", "company"),
        FieldMapping("title", "title"),
        FieldMapping("apollo contact id", "apollo_id"),
    ],
    enrichment_fields={
        "linkedin url": "linkedin_url",
        "website": "website",
        "city": "city",
        "state": "state",
        "country": "country",
        "industry": "industry",
        "# employees": "employee_count",
    },
    composite_transforms=[
        _apollo_name_transform,
        _apollo_phone_transform,
        _apollo_company_transform,
        _apollo_linkedin_transform,
    ],
    source_value="apollo",
)

FORMAT_REGISTRY: dict[str, CSVFormatProfile] = {
    "apollo": APOLLO_PROFILE,
}


# ---------------------------------------------------------------------------
# Company CSV mappings
# ---------------------------------------------------------------------------


@dataclass
class CompanyFieldMapping:
    csv_columns: list[str]  # lowercase aliases that map to this field
    company_field: str
    cast: type | None = None  # optional type cast (e.g. int)
    post_process: str | None = None  # named transform key (e.g. "normalize_domain")


def _normalize_domain_value(val: str) -> str:
    """Strip protocol, www., and trailing slash from a domain/URL."""
    val = val.strip()
    for prefix in ("https://", "http://"):
        if val.startswith(prefix):
            val = val[len(prefix):]
    if val.startswith("www."):
        val = val[4:]
    return val.rstrip("/").lower()


COMPANY_FIELD_MAPPINGS: list[CompanyFieldMapping] = [
    CompanyFieldMapping(["company", "name"], "name"),
    CompanyFieldMapping(["domain", "website", "company website url"], "domain", post_process="normalize_domain"),
    CompanyFieldMapping(["industry"], "industry"),
    CompanyFieldMapping(["# employees", "employees", "number of employees", "employee count"], "employee_count", cast=int),
    CompanyFieldMapping(["city"], "location_city"),
    CompanyFieldMapping(["state"], "location_state"),
    CompanyFieldMapping(["country"], "location_country"),
    CompanyFieldMapping(["apollo account id", "account id", "apollo id"], "apollo_id"),
    CompanyFieldMapping(["funding stage"], "funding_stage"),
]


def parse_company_csv_row(row: dict[str, str]) -> dict:
    """Map a raw CSV row dict to a Company data dict using COMPANY_FIELD_MAPPINGS."""
    normalized = {k.strip().lower(): v for k, v in row.items()}
    result: dict = {}

    for mapping in COMPANY_FIELD_MAPPINGS:
        for col in mapping.csv_columns:
            val = normalized.get(col)
            if val and val.strip():
                val = val.strip()
                if mapping.post_process == "normalize_domain":
                    val = _normalize_domain_value(val)
                if mapping.cast is not None:
                    try:
                        val = mapping.cast(val)
                    except (ValueError, TypeError):
                        val = None
                if val is not None:
                    result[mapping.company_field] = val
                break  # first alias wins

    return result


# Sentinel value sent by the frontend when the user wants to skip a column
SKIP_SENTINEL = "__skip__"

# Field-level cast and post-process rules, keyed by company field name
_USER_MAPPING_CAST: dict[str, type] = {
    "employee_count": int,
}
_USER_MAPPING_POSTPROCESS: dict[str, object] = {
    "domain": _normalize_domain_value,
    "website": _normalize_domain_value,
}


def apply_user_mapping(row: dict[str, str], column_mapping: dict[str, str]) -> dict:
    """Build a Company data dict from a CSV row using a user-provided column mapping.

    column_mapping: {csv_header: company_field_name | SKIP_SENTINEL}
    Skips columns mapped to SKIP_SENTINEL or empty string.
    Applies the same cast/post-process rules as parse_company_csv_row.
    """
    result: dict = {}
    for csv_header, field_name in column_mapping.items():
        if not field_name or field_name == SKIP_SENTINEL:
            continue
        val = (row.get(csv_header) or "").strip()
        if not val:
            continue
        postprocess = _USER_MAPPING_POSTPROCESS.get(field_name)
        if postprocess:
            val = postprocess(val)  # type: ignore[operator]
        cast = _USER_MAPPING_CAST.get(field_name)
        if cast is not None:
            try:
                val = cast(val)
            except (ValueError, TypeError):
                continue  # skip bad cast rather than store garbage
        result[field_name] = val
    return result


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
