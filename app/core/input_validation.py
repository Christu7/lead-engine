"""Input validation and sanitisation utilities for CSV upload endpoints.

Prevents:
- File-size abuse (10 MB hard cap, 10 000-row cap)
- CSV formula injection  (=, +, -, @ starters stripped)
- Data corruption via control characters / null bytes
"""
import logging
import re

logger = logging.getLogger(__name__)

# Max upload limits
MAX_CSV_FILE_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_CSV_ROWS = 10_000

# MIME types accepted as CSV uploads (browsers vary)
ALLOWED_CSV_CONTENT_TYPES = frozenset([
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
    "text/x-csv",
    "application/x-csv",
    "application/octet-stream",  # macOS Safari sometimes sends this for .csv
])

# Strip all ASCII control characters except HT (\t), LF (\n), CR (\r)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Characters that launch spreadsheet formulas — a common CSV-injection vector
_FORMULA_STARTERS = frozenset(["=", "+", "-", "@"])


def sanitize_csv_field(value: str, field_name: str = "field") -> str:
    """Sanitise a single CSV field value.

    Steps:
    1. Remove null bytes and non-printable ASCII control characters (tab/lf/cr kept).
    2. Strip leading/trailing whitespace.
    3. If the result starts with a formula-injection character, strip that character
       and log a WARNING so the attempt is visible in logs.
    """
    if not isinstance(value, str):
        return value

    value = _CONTROL_CHAR_RE.sub("", value).strip()

    if value and value[0] in _FORMULA_STARTERS:
        injection_char = value[0]
        value = value[1:].lstrip()
        logger.warning(
            "CSV formula injection character stripped",
            extra={"field": field_name, "injection_char": injection_char},
        )

    return value


def sanitize_csv_row(row: dict) -> dict:
    """Apply sanitize_csv_field to every string value in a CSV row dict."""
    return {
        k: sanitize_csv_field(v, field_name=k) if isinstance(v, str) else v
        for k, v in row.items()
    }
