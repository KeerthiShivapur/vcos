"""Phase 19 — Organizational decision history (decision intelligence).

Sensitive decisions are explained by AI (advantages, risks, alternatives,
historical evidence, predictions) and recorded only after human approval.
"""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

DECISION_CATEGORIES = (
    "hiring", "termination", "budget", "legal", "contract", "acquisition",
    "expansion", "product", "pricing", "infrastructure", "strategy", "other",
)
DECISION_STATUSES = ("draft", "pending_approval", "approved", "rejected", "implemented")


class DecisionHistory(Base, TimestampMixin):
    """One important organizational decision with context and outcomes."""

    __tablename__ = "org_decision_history"
    __table_args__ = (
        Index("ix_decision_history_org_cat", "organization_id", "category"),
        Index("ix_decision_history_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="strategy")
    context: Mapped[Optional[str]] = mapped_column(Text)
    alternatives: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    analysis: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    participants: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    outcome: Mapped[Optional[str]] = mapped_column(String(255))
    results: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    lessons: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending_approval")
    decided_by: Mapped[Optional[str]] = mapped_column(String(32))
    decided_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
