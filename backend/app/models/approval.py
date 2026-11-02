"""Approval and Risk models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ApprovalStatus(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalType(str):
    DOCUMENT = "document"
    BUDGET = "budget"
    HIRING = "hiring"
    PURCHASE = "purchase"
    LEAVE = "leave"
    EXPENSE = "expense"
    PROJECT = "project"
    POLICY = "policy"
    ACCESS = "access"
    CUSTOM = "custom"


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    approval_type: Mapped[str] = mapped_column(String(30), default=ApprovalType.CUSTOM, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default=ApprovalStatus.PENDING, nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    approver_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    current_approver_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    changes_requested: Mapped[Optional[str]] = mapped_column(Text)
    approvalstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_approvals_org_status", "organization_id", "status"),
        Index("ix_approvals_org_requester", "organization_id", "requester_id"),
        Index("ix_approvals_entity", "entity_type", "entity_id"),
    )


class ApprovalStep(Base, TimestampMixin):
    __tablename__ = "approval_steps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    approval_id: Mapped[str] = mapped_column(
        ForeignKey("approvals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), default="approver", nullable=False)  # approver, reviewer, notify
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(20))  # approved, rejected, changes_requested
    comment: Mapped[Optional[str]] = mapped_column(Text)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_delegate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delegated_to: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    delegated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("approval_id", "step_order", name="uq_approval_steps_approval_order"),
        Index("ix_approval_steps_approval", "approval_id"),
    )


class ApprovalTemplate(Base, TimestampMixin):
    __tablename__ = "approval_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    approval_type: Mapped[str] = mapped_column(String(30), default=ApprovalType.CUSTOM, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    steps: Mapped[List[dict]] = mapped_column(JSON, default=list)
    default_priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    default_due_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_approval_templates_org_name"),
    )


class RiskCategory(str):
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    STRATEGIC = "strategic"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    REPUTATIONAL = "reputational"
    LEGAL = "legal"
    TECHNOLOGY = "technology"
    PEOPLE = "people"
    EXTERNAL = "external"


class RiskSeverity(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskStatus(str):
    IDENTIFIED = "identified"
    ASSESSED = "assessed"
    MITIGATING = "mitigating"
    MONITORED = "monitored"
    CLOSED = "closed"
    ACCEPTED = "accepted"


class Risk(Base, TimestampMixin):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default=RiskCategory.OPERATIONAL, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default=RiskSeverity.MEDIUM, nullable=False, index=True)
    likelihood: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    impact: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # calculated
    status: Mapped[str] = mapped_column(String(20), default=RiskStatus.IDENTIFIED, nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    identified_by: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    identified_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False)
    assessed_date: Mapped[Optional[date]] = mapped_column(Date)
    target_resolution_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    actual_resolution_date: Mapped[Optional[date]] = mapped_column(Date)
    status_detail: Mapped[Optional[str]] = mapped_column(Text)
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text)
    contingency_plan: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    approvalstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    owner: Mapped["Employee"] = relationship(
        back_populates="owned_risks",
        foreign_keys="Risk.owner_id"
    )
    identified_by_employee: Mapped["Employee"] = relationship(
        foreign_keys="Risk.identified_by"
    )
    department: Mapped[Optional["Department"]] = relationship()
    project: Mapped[Optional["Project"]] = relationship()

    __table_args__ = (
        Index("ix_risks_org_status", "organization_id", "status"),
        Index("ix_risks_org_severity", "organization_id", "severity"),
        Index("ix_risks_org_category", "organization_id", "category"),
        Index("ix_risks_owner", "owner_id"),
    )


class RiskMitigation(Base, TimestampMixin):
    __tablename__ = "risk_mitigations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    risk_id: Mapped[str] = mapped_column(
        ForeignKey("risks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mitigation_type: Mapped[str] = mapped_column(String(30), default="preventive", nullable=False)  # preventive, detective, corrective
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, in_progress, implemented, verified
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_date: Mapped[Optional[date]] = mapped_column(Date)
    cost_estimate: Mapped[Optional[float]] = mapped_column(default=None)
    actual_cost: Mapped[Optional[float]] = mapped_column(default=None)
    effectiveness: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    review_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    risk: Mapped["Risk"] = relationship()
    owner: Mapped["Employee"] = relationship()

    __table_args__ = (
        Index("ix_risk_mitigations_risk", "risk_id"),
        Index("ix_risk_mitigations_owner", "owner_id"),
    )