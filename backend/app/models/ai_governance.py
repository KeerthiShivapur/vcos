"""Phase 20 — Responsible AI governance records.

Every AI recommendation carries why it was made, its supporting evidence,
a confidence level and the affected systems. Humans review, approve, reject
or override AI suggestions, and high-impact actions require approval before
anything executes.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# proposed -> approved | rejected | overridden | implemented
GOVERNANCE_STATUSES = ("proposed", "approved", "rejected", "overridden", "implemented")


class GovernanceRecommendation(Base, TimestampMixin):
    """One explainable, governable AI recommendation (Phase 20.17)."""

    __tablename__ = "governance_recommendations"
    __table_args__ = (
        Index("ix_ai_rec_org_status", "organization_id", "status"),
        Index("ix_ai_rec_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # hiring | knowledge | workflow | investment | risk | innovation | customer | learning | people
    category: Mapped[str] = mapped_column(String(40), default="knowledge")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    # {"type": "opportunity"|"risk"|"action", "evidence": [{"type", "entity_type", "entity_id", "summary"}]}
    evidence: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # e.g. ["projects", "documents", "workflow"] — the systems an action would touch
    affected_systems: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # high-impact actions require a human decision before execution
    requires_approval: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    source: Mapped[str] = mapped_column(String(120), default="kernel.governance")
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    decided_by: Mapped[Optional[str]] = mapped_column(String(64))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
