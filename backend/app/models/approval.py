"""Approvals and risks (Phase 3 — Work Execution Engine)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_org_status", "organization_id", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    approval_type: Mapped[str] = mapped_column(
        String(40), default="project"
    )  # project|leave|purchase|budget|document|meeting|task|release|expense|other
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    requester_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approver_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|approved|rejected|cancelled
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    policy_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Risk(Base, TimestampMixin):
    __tablename__ = "risks"
    __table_args__ = (Index("ix_risks_org_project", "organization_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="identified"
    )  # identified|assessing|mitigating|accepted|monitoring|closed
    probability: Mapped[int] = mapped_column(Integer, default=2)  # 1-5
    impact: Mapped[int] = mapped_column(Integer, default=2)  # 1-5
    risk_score: Mapped[int] = mapped_column(Integer, default=4)  # probability * impact
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    detected_from: Mapped[Optional[str]] = mapped_column(String(60))  # e.g. "delay_detection"
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
