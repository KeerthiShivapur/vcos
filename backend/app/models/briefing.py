"""Phase 19 — Autonomous executive briefings."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

BRIEFING_SECTIONS = (
    "company_summary", "project_risks", "hiring_status", "knowledge_growth",
    "customer_health", "financial_summary", "innovation_summary", "recommendations",
)


class ExecutiveBriefing(Base, TimestampMixin):
    """The autonomous morning briefing delivered without asking."""

    __tablename__ = "executive_briefings"
    __table_args__ = (
        Index("ix_exec_briefings_org_date", "organization_id", "briefing_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    briefing_date: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sections: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    highlights: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    risks: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    recommendations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
