"""Phase 19 — Organization health (overall score + per-domain health)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

HEALTH_DIMENSIONS = (
    "employees", "teams", "departments", "knowledge", "learning", "community",
    "finance", "customers", "infrastructure", "projects", "innovation",
    "workflow", "collaboration", "leadership",
)


class OrganizationHealth(Base, TimestampMixin):
    """A company health snapshot with per-domain scores (0-100)."""

    __tablename__ = "organization_health"
    __table_args__ = (
        Index("ix_org_health_org_computed", "organization_id", "computed_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="stable")
    dimensions: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    trend: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
