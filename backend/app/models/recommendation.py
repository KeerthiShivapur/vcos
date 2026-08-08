"""Phase 19 — Organization recommendations and optimization history."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

RECOMMENDATION_CATEGORIES = (
    "documentation", "mentorship", "hiring", "promotion", "workflow", "automation",
    "learning", "risk_mitigation", "innovation", "customers", "meetings",
    "team_structure", "project_allocation", "budget", "knowledge", "planning",
    "strategy", "infrastructure",
)
RECOMMENDATION_STATUSES = ("pending", "approved", "rejected", "applied", "dismissed")


class Recommendation(Base, TimestampMixin):
    """An evidence-backed, explainable organizational recommendation."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_org_cat", "organization_id", "category"),
        Index("ix_recommendations_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    evidence: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    impact: Mapped[str] = mapped_column(String(20), default="medium")
    estimated_benefit: Mapped[Optional[str]] = mapped_column(String(255))
    approval_required: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))
    resolved_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
