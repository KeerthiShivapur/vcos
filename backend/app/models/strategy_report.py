"""Strategy Report model."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class StrategyReportStatus(str):
    DRAFT = "draft"
    GENERATING = "generating"
    COMPLETED = "completed"
    DISTRIBUTED = "distributed"
    ARCHIVED = "archived"


class StrategyReportType(str):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    CUSTOM = "custom"


class StrategyReport(Base, TimestampMixin):
    __tablename__ = "strategy_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    report_type: Mapped[str] = mapped_column(String(24), default=StrategyReportType.MONTHLY, nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=StrategyReportStatus.DRAFT, nullable=False)
    generated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    key_findings: Mapped[List[str]] = mapped_column(JSON, default=list)
    strategic_priorities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    key_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    risks: Mapped[List[dict]] = mapped_column(JSON, default=list)
    opportunities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    action_items: Mapped[List[dict]] = mapped_column(JSON, default=list)
    resource_allocation: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    distributed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recipients: Mapped[List[str]] = mapped_column(JSON, default=list)
    strategyreportstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_strategy_reports_org_period", "organization_id", "period_end"),
        Index("ix_strategy_reports_org_type", "organization_id", "report_type"),
    )