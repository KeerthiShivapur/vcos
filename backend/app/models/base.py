"""Base model utilities - shared across all models to avoid circular imports.

This module re-exports the shared Base from app.db.database to ensure
all models use the same SQLAlchemy Base and metadata registry.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.database import Base


def gen_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# Re-export the shared Base from app.db.database
__all__ = ["Base", "TimestampMixin", "gen_uuid", "utcnow"]