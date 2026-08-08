"""Phase 19 — Strategy reports from the executive strategy engine."""

from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class StrategyReport(Base, TimestampMixin):
    """A strategic analysis of the entire organization."""

    __tablename__ = "strategy_reports"
    __table_args__ = (
        Index("ix_strategy_reports_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), default="weekly")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    findings: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    recommendations: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    priorities: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    risks: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    focus_areas: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    weak_departments: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
