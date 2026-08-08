"""Shared parsing helpers for the customer module (Phase 12).

Normalizes date/datetime inputs so the same payloads behave identically
on PostgreSQL and SQLite (the test database).
"""

from datetime import date, datetime
from typing import Optional

from app.core.timeutils import ensure_aware, utcnow


def to_date(value: Optional[str]) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def to_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_aware(value)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return ensure_aware(datetime.fromisoformat(text))
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text[:19], fmt)
                return parsed.replace(tzinfo=None)
            except ValueError:
                continue
        return None


def clamp_score(value: Optional[int], default: int = 50) -> int:
    if value is None:
        return default
    return max(0, min(100, int(value)))
