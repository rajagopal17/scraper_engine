from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")


def _looks_like_date_field(name: str) -> bool:
    return name.endswith("_date") or name in ("start_date", "end_date", "deadline")


def _parse_date(value: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def validate_record(data: dict) -> ValidationResult:
    """Deterministic, schema-level checks run on every extracted record before merge.

    This is the (A)-tier review from the design: cheap, automatic, no AI calls.
    Records that fail stay in the rejected bucket and are never merged.
    """
    reasons: list[str] = []

    if not any(v not in (None, "") for v in data.values()):
        reasons.append("record has no non-empty fields at all")

    for key, value in data.items():
        if value in (None, ""):
            continue  # missing fields are allowed, not an error
        if _looks_like_date_field(key) and isinstance(value, str):
            if _parse_date(value) is None:
                reasons.append(f"field '{key}' does not parse as a date: {value!r}")

    start = data.get("start_date")
    end = data.get("end_date") or data.get("deadline")
    if isinstance(start, str) and isinstance(end, str):
        start_d, end_d = _parse_date(start), _parse_date(end)
        if start_d and end_d and end_d < start_d:
            reasons.append(f"end_date {end!r} is before start_date {start!r}")

    return ValidationResult(ok=not reasons, reasons=reasons)


def compute_active(end_date: str | None, run_date: date | None = None) -> bool | None:
    """Rule-based (not AI) field: active iff end_date is missing or >= run_date."""
    if not end_date:
        return None
    parsed = _parse_date(end_date)
    if parsed is None:
        return None
    run_date = run_date or date.today()
    return parsed >= run_date
