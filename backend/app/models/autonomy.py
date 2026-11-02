"""Autonomy models for self-governance and decision making."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class AutonomyPolicyType(str):
    DECISION = "decision"
    RESOURCE = "resource"
    HIRING = "hiring"
    BUDGET = "budget"
    PROCESS = "process"
    TECHNOLOGY = "technology"
    PARTNERSHIP = "partnership"
    COMMUNICATION = "communication"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class AutonomyProposalStatus(str):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class AutonomyPolicy(Base, TimestampMixin):
    __tablename__ = "autonomy_policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    policy_type: Mapped[str] = mapped_column(String(40), default=AutonomyPolicyType.DECISION, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)  # organization, department, team, project
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    decision_authority: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_limit: Mapped[Optional[float]] = mapped_column(default=None)
    requires_approval_above: Mapped[Optional[float]] = mapped_column(default=None)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    exceptions: Mapped[List[str]] = mapped_column(JSON, default=list)
    review_cadence_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_autonomy_policies_org_type", "organization_id", "policy_type"),
        Index("ix_autonomy_policies_org_active", "organization_id", "is_active"),
    )


class AutonomyProposal(Base, TimestampMixin):
    __tablename__ = "autonomy_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    policy_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("autonomy_policies.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(40), default=AutonomyPolicyType.DECISION, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=AutonomyProposalStatus.DRAFT, nullable=False, index=True)
    proposer_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    requested_authority: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_requested: Mapped[Optional[float]] = mapped_column(default=None)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[List[str]] = mapped_column(JSON, default=list)
    risk_assessment: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    autonomypolicytype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_autonomy_proposals_org_status", "organization_id", "status"),
        Index("ix_autonomy_proposals_org_proposer", "organization_id", "proposer_id"),
        Index("ix_autonomy_proposals_org_type", "organization_id", "proposal_type"),
    )


class AutonomyPolicyEvaluation(Base, TimestampMixin):
    __tablename__ = "autonomy_policy_evaluations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("autonomy_policies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evaluation_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    evaluation_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    proposals_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_approval_time_days: Mapped[float] = mapped_column(default=0.0, nullable=False)
    success_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    issues_identified: Mapped[List[str]] = mapped_column(JSON, default=list)
    recommendations: Mapped[List[str]] = mapped_column(JSON, default=list)
    evaluated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_autonomy_evals_org_policy", "organization_id", "policy_id"),
    )


class AutonomyEligibility(Base, TimestampMixin):
    __tablename__ = "autonomy_eligibility"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("autonomy_policies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eligibility_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    criteria_met: Mapped[List[str]] = mapped_column(JSON, default=list)
    criteria_missing: Mapped[List[str]] = mapped_column(JSON, default=list)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "policy_id", name="uq_autonomy_eligibility_emp_policy"),
        Index("ix_autonomy_eligibility_org_eligible", "organization_id", "is_eligible"),
    )


class AutonomyEligibilityCache(Base):
    __tablename__ = "autonomy_eligibility_cache"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    policy_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eligibility_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    criteria_met: Mapped[List[str]] = mapped_column(JSON, default=list)
    criteria_missing: Mapped[List[str]] = mapped_column(JSON, default=list)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "policy_id", name="uq_autonomy_cache_emp_policy"),
        Index("ix_autonomy_cache_expires", "expires_at"),
    )


class AutonomyEvent(Base, TimestampMixin):
    __tablename__ = "autonomy_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # policy_created, proposal_submitted, proposal_approved, etc.
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)  # policy, proposal, eligibility
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    autonomypolicytype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_autonomy_events_org_type", "organization_id", "event_type"),
        Index("ix_autonomy_events_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_autonomy_events_org_time", "organization_id", "created_at"),
    )


class AutonomyExecution(Base, TimestampMixin):
    __tablename__ = "autonomy_executions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("autonomy_proposals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    executor_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    issues_encountered: Mapped[List[str]] = mapped_column(JSON, default=list)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_autonomy_executions_org_proposal", "organization_id", "proposal_id"),
        Index("ix_autonomy_executions_org_executor", "organization_id", "executor_id"),
    )


class AutonomyLearning(Base, TimestampMixin):
    __tablename__ = "autonomy_learning"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # proposal_outcome, execution_result, policy_evaluation
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    insight_type: Mapped[str] = mapped_column(String(40), nullable=False)  # pattern, best_practice, warning, improvement
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    applicability: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_autonomy_learning_org_type", "organization_id", "insight_type"),
    )


class AutonomyRisk(Base, TimestampMixin):
    __tablename__ = "autonomy_risks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    policy_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("autonomy_policies.id", ondelete="SET NULL"), index=True
    )
    proposal_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("autonomy_proposals.id", ondelete="SET NULL"), index=True
    )
    risk_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # authority_overreach, budget_overspend, compliance_violation, etc.
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_by: Mapped[Optional[str]] = mapped_column(String(32))  # system, human, audit
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    mitigated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    mitigated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    mitigation_actions: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_autonomy_risks_org_severity", "organization_id", "severity"),
        Index("ix_autonomy_risks_org_detected", "organization_id", "detected_at"),
    )


class AutonomyContext(Base):
    __tablename__ = "autonomy_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, team, department, initiative
    context_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    policies: Mapped[List[str]] = mapped_column(JSON, default=list)
    active_proposals: Mapped[List[str]] = mapped_column(JSON, default=list)
    eligible_employees: Mapped[List[str]] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)  # low, medium, high
    last_assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "context_type", "context_id", name="uq_autonomy_contexts_org_type_id"),
    )


# Constants for Autonomy
AUTONOMY_STATES = ["draft", "submitted", "under_review", "approved", "rejected", "implemented", "withdrawn", "expired"]
AUTONOMY_RISK_CLASSES = ["authority_overreach", "budget_overspend", "compliance_violation", "security_risk", "operational_risk", "reputational_risk"]
AUTONOMY_PROPOSAL_TYPES = ["decision", "resource", "hiring", "budget", "process", "technology", "partnership", "communication", "security", "compliance"]
POLICY_DECISIONS = ["approved", "rejected", "changes_requested", "deferred"]
AUTONOMY_EVENT_TYPES = [
    "policy_created", "policy_updated", "policy_deleted",
    "proposal_submitted", "proposal_approved", "proposal_rejected", "proposal_withdrawn",
    "eligibility_granted", "eligibility_revoked", "execution_completed", "risk_detected"
]