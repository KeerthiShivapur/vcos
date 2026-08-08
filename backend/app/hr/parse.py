"""Helpers for converting API payload values into date/datetime objects.

FastAPI hands JSON values through as strings; SQLAlchemy Date/DateTime
columns require native Python types, so every service converts at the
boundary.
"""

from datetime import date, datetime
from typing import Optional


def to_date(value: Optional[str]) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def to_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
