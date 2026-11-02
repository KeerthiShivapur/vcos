"""Decision History model."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class DecisionHistory(Base, TimestampMixin):
    __tablename__ = "decision_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    decision_maker_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    decision_date: Mapped[Optional[date]] = mapped_column(Date)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    business_impact: Mapped[Optional[str]] = mapped_column(Text)
    follow_up_actions: Mapped[Optional[list]] = mapped_column(JSON)
    future_review_date: Mapped[Optional[date]] = mapped_column(Date)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    goal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    meeting_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    options: Mapped[list] = mapped_column(JSON, default=list)
    participants: Mapped[list] = mapped_column(JSON, default=list)
    decisionhistory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("decision_id", "version", name="uq_decision_history_decision_version"),
        Index("ix_decision_history_org_date", "organization_id", "decision_date"),
        Index("ix_decision_history_org_decision", "organization_id", "decision_id"),
        {"extend_existing": True},
    )