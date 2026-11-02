from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def is_expired(dt: datetime) -> bool:
    """Check if datetime is expired (in the past)."""
    return ensure_aware(dt) < utcnow()


def ensure_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)