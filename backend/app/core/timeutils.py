"""Timezone-safe datetime helpers.

PostgreSQL returns timezone-aware datetimes; SQLite returns naive UTC.
Every comparison goes through these helpers so behavior is identical on
both backends.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def ensure_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def is_expired(value: datetime) -> bool:
    return ensure_aware(value) < utcnow()
