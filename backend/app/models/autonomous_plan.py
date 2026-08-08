"""Phase 19 — Autonomous plans (daily, weekly, sprint, department, hiring,
infrastructure, learning, executive)."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

PLAN_KINDS = (
    "daily", "weekly", "sprint", "department", "hiring", "infrastructure",
    "learning", "executive",
)
PLAN_STATUSES = ("pending", "approved", "applied", "rejected")


class AutonomousPlan(Base, TimestampMixin):
    """An AI-generated plan awaiting manager approval."""

    __tablename__ = "autonomous_plans"
    __table_args__ = (
        Index("ix_autonomous_plans_org_kind", "organization_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    items: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    focus: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
