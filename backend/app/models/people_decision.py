"""People Decision models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class PeopleDecisionStatus(str):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    WITHDRAWN = "withdrawn"


LIFECYCLE_STATES = (
    "proposed",
    "under_review",
    "approved",
    "rejected",
    "implemented",
    "withdrawn",
)


class PeopleDecisionType(str):
    HIRING = "hiring"
    PROMOTION = "promotion"
    TRANSFER = "transfer"
    TERMINATION = "termination"
    ROLE_CHANGE = "role_change"
    COMPENSATION = "compensation"
    LEAVE = "leave"
    PERFORMANCE = "performance"
    REORG = "reorg"


DECISION_TYPES = (
    "hiring",
    "promotion",
    "transfer",
    "termination",
    "role_change",
    "compensation",
    "leave",
    "performance",
    "reorg",
)


OUTCOME_STATUSES = (
    "pending",
    "success",
    "partial",
    "failed",
    "cancelled",
)


RISK_TIERS = (
    "low",
    "medium",
    "high",
    "critical",
)


ROLE_RECOMMENDED = "recommended"
ROLE_ALTERNATIVE = "alternative"
ROLE_EXCLUDED = "excluded"


class PeopleDecision(Base, TimestampMixin):
    __tablename__ = "people_decisions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_type: Mapped[str] = mapped_column(String(40), default=PeopleDecisionType.HIRING, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=PeopleDecisionStatus.PROPOSED, nullable=False, index=True)
    proposer_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_employee_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    affected_employees: Mapped[List[str]] = mapped_column(JSON, default=list)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    proposed_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text)
    budget_impact: Mapped[Optional[float]] = mapped_column(default=None)
    required_approvals: Mapped[List[str]] = mapped_column(JSON, default=list)
    approvals_received: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default=PeopleDecisionStatus.PROPOSED, nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    peopledecisionstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_people_decisions_org_status", "organization_id", "status"),
        Index("ix_people_decisions_org_type", "organization_id", "decision_type"),
        Index("ix_people_decisions_org_proposer", "organization_id", "proposer_id"),
    )


class DecisionCandidate(Base, TimestampMixin):
    __tablename__ = "decision_candidates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("people_decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(300), nullable=False)
    current_role: Mapped[Optional[str]] = mapped_column(String(200))
    fit_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    strengths: Mapped[List[str]] = mapped_column(JSON, default=list)
    concerns: Mapped[List[str]] = mapped_column(JSON, default=list)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="under_consideration", nullable=False)  # under_consideration, shortlisted, selected, rejected
    feedback: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_decision_candidates_decision", "decision_id"),
        Index("ix_decision_candidates_org_candidate", "organization_id", "candidate_id"),
    )


class DecisionEvidenceItem(Base, TimestampMixin):
    __tablename__ = "decision_evidence_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("people_decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)  # document, interview, assessment, reference, data
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_supporting: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_decision_evidence_decision", "decision_id"),
    )


class DecisionSimulation(Base, TimestampMixin):
    __tablename__ = "decision_simulations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("people_decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scenario_name: Mapped[str] = mapped_column(String(300), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_outcomes: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_decision_simulations_decision", "decision_id"),
    )


class DecisionAudit(Base, TimestampMixin):
    __tablename__ = "decision_audit"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    auditor_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    audit_type: Mapped[str] = mapped_column(String(40), nullable=False)  # compliance, fairness, bias, process
    findings: Mapped[List[str]] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    peopledecisionstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_decision_audit_org_decision", "organization_id", "decision_id"),
        Index("ix_decision_audit_org_auditor", "organization_id", "auditor_id"),
    )