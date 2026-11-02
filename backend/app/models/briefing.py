"""Executive Briefing models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ExecutiveBriefing(Base, TimestampMixin):
    __tablename__ = "executive_briefings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    briefing_type: Mapped[str] = mapped_column(String(40), default="daily", nullable=False)  # daily, weekly, monthly, quarterly, custom
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recipient_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    generated_by: Mapped[str] = mapped_column(String(40), default="system", nullable=False)  # system, ai, human
    sections: Mapped[List[dict]] = mapped_column(JSON, default=list)
    key_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    insights: Mapped[List[str]] = mapped_column(JSON, default=list)
    action_items: Mapped[List[dict]] = mapped_column(JSON, default=list)
    risks: Mapped[List[dict]] = mapped_column(JSON, default=list)
    opportunities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    executivebriefing_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_executive_briefings_org_recipient", "organization_id", "recipient_id"),
        Index("ix_executive_briefings_org_period", "organization_id", "period_end"),
        Index("ix_executive_briefings_recipient_read", "recipient_id", "is_read"),
    )