"""Execution Strategy models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CompanyGoal(Base, TimestampMixin):
    __tablename__ = "company_goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(String(40), default="strategic", nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(24), default="yearly", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planning", nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_goal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    success_criteria: Mapped[List[str]] = mapped_column(JSON, default=list)
    key_results: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_goals_org_status", "organization_id", "status"),
        Index("ix_company_goals_org_owner", "organization_id", "owner_id"),
    )


class CompanyInitiative(Base, TimestampMixin):
    __tablename__ = "company_initiatives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_goals.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    initiative_type: Mapped[str] = mapped_column(String(40), default="project", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planning", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_amount: Mapped[Optional[float]] = mapped_column(default=None)
    actual_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_initiatives_org_status", "organization_id", "status"),
        Index("ix_company_initiatives_org_goal", "organization_id", "goal_id"),
    )


class CompanyObjective(Base, TimestampMixin):
    __tablename__ = "company_objectives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    initiative_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_initiatives.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    objective_type: Mapped[str] = mapped_column(String(40), default="output", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="not_started", nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    metric: Mapped[Optional[str]] = mapped_column(String(100))
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    current_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_objectives_org_status", "organization_id", "status"),
    )


class StrategicHistory(Base, TimestampMixin):
    __tablename__ = "strategic_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    old_state: Mapped[Optional[dict]] = mapped_column(JSON)
    new_state: Mapped[Optional[dict]] = mapped_column(JSON)
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_strategic_history_org_time", "organization_id", "created_at"),
        Index("ix_strategic_history_org_entity", "organization_id", "entity_type", "entity_id"),
        {"extend_existing": True},
    )


class StrategicLink(Base, TimestampMixin):
    __tablename__ = "strategic_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    link_type: Mapped[str] = mapped_column(String(40), nullable=False)
    strength: Mapped[float] = mapped_column(default=1.0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "target_type", "target_id", "link_type", name="uq_strategic_links_unique"),
        Index("ix_strategic_links_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_strategic_links_org_target", "organization_id", "target_type", "target_id"),
        {"extend_existing": True},
    )


class StrategicOutcome(Base, TimestampMixin):
    __tablename__ = "strategic_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_goals.id", ondelete="SET NULL"), index=True
    )
    initiative_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_initiatives.id", ondelete="SET NULL"), index=True
    )
    outcome_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    quantitative_results: Mapped[dict] = mapped_column(JSON, default=dict)
    qualitative_assessment: Mapped[Optional[str]] = mapped_column(Text)
    lessons_learned: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_strategic_outcomes_org_time", "organization_id", "created_at"),
        {"extend_existing": True},
    )


class StrategicSnapshot(Base, TimestampMixin):
    __tablename__ = "strategic_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(24), default="monthly", nullable=False)
    goals_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    initiatives_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    objectives_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    health_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", "snapshot_type", name="uq_strategic_snapshots_org_date_type"),
        Index("ix_strategic_snapshots_org_type", "organization_id", "snapshot_type"),
        {"extend_existing": True},
    )


class CompanyAuthorization(Base, TimestampMixin):
    """Authorization from governance to execute a commitment."""

    __tablename__ = "company_authorizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, department, team, organization
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    authorization_type: Mapped[str] = mapped_column(String(40), nullable=False)  # budget, resource, execution, hiring
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="requested", nullable=False)  # requested, under_review, approved, conditional, rejected, superseded
    conditions: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    requested_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    policy_ref: Mapped[Optional[str]] = mapped_column(String(200))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_auth_org_status", "organization_id", "status"),
        Index("ix_company_auth_org_commitment", "organization_id", "commitment_id"),
        Index("ix_company_auth_scope", "scope_type", "scope_id"),
    )


class CompanyCommitment(Base, TimestampMixin):
    """A governed commitment from decision to execution."""

    __tablename__ = "company_commitments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    authorization_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, department, team, organization
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    commitment_type: Mapped[str] = mapped_column(String(40), nullable=False)  # budget, resource, execution, hiring, delivery
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)  # proposed, pending_authorization, authorized, active, paused, fulfilled, cancelled, expired, superseded, rejected
    expected_outcome: Mapped[Optional[dict]] = mapped_column(JSON)
    metrics: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    requested_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    authorized_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_commit_org_status", "organization_id", "status"),
        Index("ix_company_commit_org_auth", "organization_id", "authorization_id"),
        Index("ix_company_commit_scope", "scope_type", "scope_id"),
    )


COMMITMENT_STATES = ("proposed", "pending_authorization", "authorized", "active", "paused", "fulfilled", "cancelled", "expired", "superseded", "rejected")
COMMITMENT_TYPES = ("budget", "resource", "execution", "hiring", "delivery")
AUTHORIZATION_TYPES = ("budget", "resource", "execution", "hiring")
AUTHORIZATION_STATES = ("requested", "under_review", "approved", "conditional", "rejected", "superseded")
OUTCOME_STATES = ("projected", "in_progress", "achieved", "exceeded", "missed", "abandoned")
ASSESSMENT_STATES = ("pending", "completed", "deferred")
MEASUREMENT_QUALITY = ("high", "medium", "low", "estimated")
SUPERSESSION_REASON = ("superseded", "cancelled", "expired", "replaced")


class ObjectiveOutcome(Base, TimestampMixin):
    """Recorded outcome for an objective - expected vs actual."""

    __tablename__ = "objective_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    objective_id: Mapped[str] = mapped_column(
        ForeignKey("company_objectives.id", ondelete="CASCADE"), index=True, nullable=False
    )
    initiative_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    metric_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_value: Mapped[Optional[float]] = mapped_column(default=None)
    actual_value: Mapped[Optional[float]] = mapped_column(default=None)
    variance_pct: Mapped[Optional[float]] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(24), default="projected", nullable=False)  # projected, in_progress, achieved, exceeded, missed, abandoned
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(32))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_outcome_org_obj", "organization_id", "objective_id"),
        Index("ix_obj_outcome_org_init", "organization_id", "initiative_id"),
    )


class ObjectiveOutcomeAssessment(Base, TimestampMixin):
    """Assessment of an objective outcome - qualitative evaluation."""

    __tablename__ = "objective_outcome_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    outcome_id: Mapped[str] = mapped_column(
        ForeignKey("objective_outcomes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    objective_id: Mapped[str] = mapped_column(String(32), index=True)
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False)  # qualitative, quantitative, peer_review
    assessment_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, completed, deferred
    quality: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # high, medium, low, estimated
    summary: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_assess_org_outcome", "organization_id", "outcome_id"),
        Index("ix_obj_assess_org_obj", "organization_id", "objective_id"),
    )


class ObjectiveContradiction(Base, TimestampMixin):
    """Contradiction between expected and actual outcomes."""

    __tablename__ = "objective_contradictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    outcome_id: Mapped[str] = mapped_column(
        ForeignKey("objective_outcomes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contradiction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # variance, missed_target, unexpected_result
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)  # open, acknowledged, resolved
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_contr_org_outcome", "organization_id", "outcome_id"),
        Index("ix_obj_contr_org_status", "organization_id", "status"),
    )


class ObjectivePrediction(Base, TimestampMixin):
    __tablename__ = "objective_predictions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    objective_id: Mapped[str] = mapped_column(String(32), index=True)
    initiative_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    prediction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecast, simulation, trend
    predicted_value: Mapped[Optional[float]] = mapped_column(default=None)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    horizon_days: Mapped[int] = mapped_column(default=30, nullable=False)
    model_name: Mapped[str] = mapped_column(String(60), nullable=False)
    features: Mapped[Optional[dict]] = mapped_column(JSON)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_pred_org_obj", "organization_id", "objective_id"),
    )


class ObjectiveSimulation(Base, TimestampMixin):
    __tablename__ = "objective_simulations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    objective_id: Mapped[str] = mapped_column(String(32), index=True)
    scenario_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    iterations: Mapped[int] = mapped_column(default=1000, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_sim_org_obj", "organization_id", "objective_id"),
    )


class ObjectivePlanState(Base, TimestampMixin):
    __tablename__ = "objective_plan_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    objective_id: Mapped[str] = mapped_column(String(32), index=True)
    plan_state: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    state_data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_obj_plan_state_org_obj", "organization_id", "objective_id"),
    )


class StrategicAlignment(Base, TimestampMixin):
    __tablename__ = "strategic_alignments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    alignment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    strength: Mapped[float] = mapped_column(default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_strat_align_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_strat_align_org_target", "organization_id", "target_type", "target_id"),
        {"extend_existing": True},
    )


class AlignmentGap(Base, TimestampMixin):
    __tablename__ = "alignment_gaps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    gap_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    target_entity_type: Mapped[str] = mapped_column(String(40))
    target_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_align_gap_org_status", "organization_id", "status"),
        Index("ix_align_gap_org_type", "organization_id", "gap_type"),
        {"extend_existing": True},
    )


class StrategicConflict(Base, TimestampMixin):
    __tablename__ = "strategic_conflicts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity1_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity1_id: Mapped[str] = mapped_column(String(32), nullable=False)
    entity2_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity2_id: Mapped[str] = mapped_column(String(32), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_strat_conf_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )


class StrategicAlignmentState(Base, TimestampMixin):
    __tablename__ = "strategic_alignment_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alignment_id: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    state_data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_align_state_org_align", "organization_id", "alignment_id"),
        {"extend_existing": True},
    )


class StrategicDependency(Base, TimestampMixin):
    __tablename__ = "strategic_dependencies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(40), nullable=False)
    strength: Mapped[float] = mapped_column(default=1.0, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_strat_dep_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_strat_dep_org_target", "organization_id", "target_type", "target_id"),
        {"extend_existing": True},
    )


class AlignmentGapDetection(Base, TimestampMixin):
    __tablename__ = "alignment_gap_detections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    detection_type: Mapped[str] = mapped_column(String(40), nullable=False)
    gap_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_align_gap_det_org_time", "organization_id", "detected_at"),
    )


class CompanyPlanningContext(Base, TimestampMixin):
    __tablename__ = "company_planning_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_plan_ctx_org_scope", "organization_id", "scope_type", "scope_id"),
    )


class CompanyStateTransition(Base, TimestampMixin):
    __tablename__ = "company_state_transitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[str] = mapped_column(String(40), nullable=False)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_event_id: Mapped[Optional[str]] = mapped_column(String(32))
    initiated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_state_trans_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_state_trans_org_time", "organization_id", "transitioned_at"),
    )


class PlanningContextProvenance(Base, TimestampMixin):
    __tablename__ = "planning_context_provenance"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_plan_prov_org_ctx", "organization_id", "context_id"),
        UniqueConstraint("organization_id", "context_id", "fingerprint", name="uq_plan_prov_exact_once"),
    )


class AdaptivePlanningContext(Base, TimestampMixin):
    __tablename__ = "adaptive_planning_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    planning_context_id: Mapped[str] = mapped_column(String(32), index=True)
    adaptation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    adaptation_data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_adapt_plan_ctx_org_status", "organization_id", "status"),
    )


class AttentionSignal(Base, TimestampMixin):
    __tablename__ = "attention_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_context_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_attn_sig_org_status", "organization_id", "status"),
        Index("ix_attn_sig_org_entity", "organization_id", "entity_type", "entity_id"),
    )


class ReplanningProposal(Base, TimestampMixin):
    __tablename__ = "replanning_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    attention_signal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    proposal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    impact_assessment: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    proposed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_replan_prop_org_status", "organization_id", "status"),
    )


class DecisionContext(Base, TimestampMixin):
    __tablename__ = "decision_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    options: Mapped[List[dict]] = mapped_column(JSON, default=list)
    recommendation: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="prepared", nullable=False)
    prepared_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    decided_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_ctx_org_status", "organization_id", "status"),
        Index("ix_dec_ctx_org_entity", "organization_id", "entity_type", "entity_id"),
    )


class AdaptivePlanningTransition(Base, TimestampMixin):
    __tablename__ = "adaptive_planning_transitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_id: Mapped[str] = mapped_column(String(32), index=True)
    transition_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_state: Mapped[str] = mapped_column(String(24), nullable=False)
    to_state: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_adapt_plan_trans_org_ctx", "organization_id", "context_id"),
        UniqueConstraint("organization_id", "context_id", "fingerprint", name="uq_adapt_plan_trans_exact_once"),
    )


class DecisionIntelligenceContext(Base, TimestampMixin):
    __tablename__ = "decision_intelligence_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    intelligence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    intelligence_data: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    source_events: Mapped[List[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_dec_intel_ctx_org_dec", "organization_id", "decision_id"),
    )


class DecisionAlternative(Base, TimestampMixin):
    __tablename__ = "decision_alternatives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    alternative_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    pros: Mapped[List[str]] = mapped_column(JSON, default=list)
    cons: Mapped[List[str]] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_alt_org_dec", "organization_id", "decision_id"),
    )


def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    import hashlib
    import json
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


# Constants / Enums
OBJECTIVE_STATES = ("active", "paused", "completed", "cancelled", "on_hold", "archived")
PLANNING_CONTEXT_SECTIONS = ("goals", "objectives", "initiatives", "alignments", "gaps", "conflicts", "dependencies")
PLANNING_CONTEXT_EPISTEMIC_STATUS = ("observed", "inferred", "predicted", "proposed", "contested")
PLANNING_CONTEXT_CONFIDENCE = ("high", "medium", "low", "estimated")
STATE_TRANSITION_TRIGGERS = ("manual", "automatic", "time_based", "event_driven", "threshold_crossed")
STATE_TRANSITION_KINDS = ("create", "update", "delete", "transition", "replan", "align")
DECISION_INTELLIGENCE_TYPES = ("strategic", "tactical", "operational", "governance")
DECISION_INTELLIGENCE_STATES = ("prepared", "under_review", "decided", "implemented", "cancelled")
DECISION_ALTERNATIVE_STATES = ("proposed", "analyzing", "recommended", "rejected")
CONSEQUENCE_TYPES = ("financial", "operational", "strategic", "reputational", "compliance", "people")
RISK_ASSESSMENT_LEVELS = ("low", "medium", "high", "critical")
EVIDENCE_QUALITY_LEVELS = ("direct", "corroborated", "inferred", "estimated")
PRECEDENT_RELEVANCE_LEVELS = ("binding", "persuasive", "informational", "irrelevant")
ASSESSMENT_CONFIDENCE = ("high", "medium", "low")
ALIGNMENT_TYPES = ("supports", "conflicts", "depends_on", "blocks", "duplicates", "unrelated")
ALIGNMENT_STATES = ("active", "pending", "resolved", "superseded")
ALIGNMENT_STRENGTH = ("strong", "moderate", "weak", "indirect")
ALIGNMENT_GAP_TYPES = ("missing_initiative", "missing_objective", "misaligned_priority", "resource_gap", "timeline_gap", "dependency_gap")
ALIGNMENT_GAP_SEVERITY = ("critical", "high", "medium", "low")
CONTRIBUTION_LEVELS = ("primary", "secondary", "supporting", "incidental")


class DecisionConsequence(Base, TimestampMixin):
    __tablename__ = "decision_consequences"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )


    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    consequence_type: Mapped[str] = mapped_column(String(40), nullable=False)  # financial, operational, strategic, reputational, compliance, people
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # low, medium, high, critical
    likelihood: Mapped[str] = mapped_column(String(24), default="possible", nullable=False)  # rare, unlikely, possible, likely, almost_certain
    impact_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(24), default="medium_term", nullable=False)  # immediate, short_term, medium_term, long_term
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="identified", nullable=False)  # identified, assessed, mitigated, accepted, occurred
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_cons_org_dec", "organization_id", "decision_id"),
        Index("ix_dec_cons_org_status", "organization_id", "status"),
    )


EVIDENCE_QUALITY = EVIDENCE_QUALITY_LEVELS

class CompanyDecisionAlternative(Base, TimestampMixin):
    __tablename__ = "company_decision_alternatives"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    pros: Mapped[List[str]] = mapped_column(JSON, default=list)
    cons: Mapped[List[str]] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)  # proposed, analyzing, recommended, rejected
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_comp_dec_alt_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class CompanyDecisionEvidence(Base, TimestampMixin):
    __tablename__ = "company_decision_evidence"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    relevance: Mapped[float] = mapped_column(default=0.5, nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="estimated", nullable=False)
    supports_alternative: Mapped[Optional[str]] = mapped_column(String(32))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_comp_dec_ev_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class CompanyDecisionPrecedent(Base, TimestampMixin):
    __tablename__ = "company_decision_precedents"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    precedent_decision_id: Mapped[str] = mapped_column(String(32), index=True)
    similarity: Mapped[float] = mapped_column(default=0.5, nullable=False)
    relevance: Mapped[str] = mapped_column(String(24), default="informational", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_comp_dec_prec_org_dec", "organization_id", "decision_id"),
        UniqueConstraint("organization_id", "decision_id", "precedent_decision_id", name="uq_comp_dec_prec_unique"),
        {"extend_existing": True},
    )


class DecisionPrecedentLink(Base, TimestampMixin):
    """Link between a decision and a precedent decision."""

    __tablename__ = "decision_precedent_links"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    precedent_decision_id: Mapped[str] = mapped_column(String(32), index=True)
    link_type: Mapped[str] = mapped_column(String(40), default="supports", nullable=False)  # supports, contradicts, supersedes, references
    relevance: Mapped[float] = mapped_column(default=0.5, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_prec_link_org_dec", "organization_id", "decision_id"),
        UniqueConstraint("organization_id", "decision_id", "precedent_decision_id", name="uq_dec_prec_link_unique"),
        {"extend_existing": True},
    )


class CompanyDecisionQuality(Base, TimestampMixin):
    __tablename__ = "company_decision_quality"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    quality_dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(default=0.5, nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_comp_dec_qual_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class CompanyDecisionTrack(Base, TimestampMixin):
    __tablename__ = "company_decision_tracks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    track_type: Mapped[str] = mapped_column(String(40), nullable=False)  # implementation, monitoring, review, closure
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    milestones: Mapped[List[dict]] = mapped_column(JSON, default=list)
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_comp_dec_track_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class DecisionEvidence(Base, TimestampMixin):
    """Evidence supporting a decision."""

    __tablename__ = "decision_evidence"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    relevance: Mapped[float] = mapped_column(default=0.5, nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="estimated", nullable=False)
    supports_alternative: Mapped[Optional[str]] = mapped_column(String(32))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_evidence_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class DecisionRiskAssessment(Base, TimestampMixin):
    """Risk assessment for a decision."""

    __tablename__ = "decision_risk_assessments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    risk_type: Mapped[str] = mapped_column(String(40), nullable=False)  # financial, operational, reputational, compliance, people
    description: Mapped[str] = mapped_column(Text, nullable=False)
    likelihood: Mapped[str] = mapped_column(String(24), default="possible", nullable=False)  # rare, unlikely, possible, likely, almost_certain
    impact: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # negligible, minor, moderate, major, severe
    risk_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="identified", nullable=False)  # identified, assessed, mitigated, accepted, occurred
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_risk_org_dec", "organization_id", "decision_id"),
        {"extend_existing": True},
    )


class DecisionIntelligenceTransition(Base, TimestampMixin):
    """State transition for decision intelligence."""

    __tablename__ = "decision_intelligence_transitions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True)
    from_state: Mapped[str] = mapped_column(String(24), nullable=False)
    to_state: Mapped[str] = mapped_column(String(24), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_dec_intel_trans_org_dec", "organization_id", "decision_id"),
        Index("ix_dec_intel_trans_org_time", "organization_id", "transitioned_at"),
        {"extend_existing": True},
    )


class OrganizationalResponsibility(Base, TimestampMixin):
    __tablename__ = "organizational_responsibilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_id: Mapped[str] = mapped_column(String(32), index=True)
    person_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, department, team, organization
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    responsibility_type: Mapped[str] = mapped_column(String(40), nullable=False)  # accountability, ownership, approval, consultation, information
    description: Mapped[Optional[str]] = mapped_column(Text)
    authority_level: Mapped[int] = mapped_column(default=1, nullable=False)  # 1-5
    delegated_from: Mapped[Optional[str]] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_org_resp_org_role", "organization_id", "role_id"),
        Index("ix_org_resp_org_scope", "organization_id", "scope_type", "scope_id"),
        UniqueConstraint("organization_id", "role_id", "scope_type", "scope_id", "responsibility_type", name="uq_org_resp_unique"),
    )


__table_args__ = (
        Index("ix_org_resp_org_role", "organization_id", "role_id"),
        Index("ix_org_resp_org_scope", "organization_id", "scope_type", "scope_id"),
        UniqueConstraint("organization_id", "role_id", "scope_type", "scope_id", "responsibility_type", name="uq_org_resp_unique"),
    )


class AccountabilityLink(Base, TimestampMixin):
    """Link between commitment, authorization, and responsibility."""

    __tablename__ = "accountability_links"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    commitment_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    authorization_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    responsibility_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    accountability_type: Mapped[str] = mapped_column(String(40), nullable=False)  # direct, delegated, shared, oversight
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    companygoal_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_acc_link_org_commitment", "organization_id", "commitment_id"),
        Index("ix_org_link_org_auth", "organization_id", "authorization_id"),
        UniqueConstraint("organization_id", "commitment_id", "authorization_id", "responsibility_id", name="uq_acc_link_unique"),
        {"extend_existing": True},
    )


# =========================================================================
# Constants for Attention Signals (adaptive planning engine)
# =========================================================================

ATTENTION_SIGNAL_TYPES = (
    "threshold_breach",
    "trend_reversal",
    "anomaly_detected",
    "milestone_missed",
    "capacity_exceeded",
    "dependency_risk",
    "commitment_at_risk",
    "customer_signal",
    "competitor_move",
    "regulatory_change",
)

ATTENTION_SEVERITY = ("info", "warning", "critical")

REPLANNING_PROPOSAL_TYPES = (
    "reallocate_capacity",
    "adjust_timeline",
    "reprioritize",
    "add_resources",
    "reduce_scope",
    "escalate_decision",
    "pause_initiative",
    "cancel_initiative",
)

REPLANNING_PROPOSAL_STATES = (
    "draft",
    "under_review",
    "approved",
    "rejected",
    "implemented",
    "cancelled",
)

# Alias for backward compatibility
REPLANNING_PROPOSAL_STATUS = REPLANNING_PROPOSAL_STATES

# =========================================================================
# Decision Context Types and Status
# =========================================================================

DECISION_CONTEXT_TYPES = (
    "strategic",
    "tactical",
    "operational",
    "governance",
    "crisis",
    "opportunity",
)

DECISION_CONTEXT_STATUS = (
    "prepared",
    "under_review",
    "decided",
    "implemented",
    "cancelled",
    "deferred",
)

NODE_STATUSES = (
    "active",
    "inactive",
    "pending",
    "archived",
    "error",
)

VERIFICATION_STATES = (
    "pending",
    "running",
    "completed",
    "failed",
)


VERIFICATION_TRIGGERS = (
    "plan_vs_reality",
    "commitment_fulfillment",
    "objective_achievement",
    "capacity_exceeded",
    "dependency_risk",
    "budget_variance",
    "timeline_deviation",
    "quality_degradation",
    "risk_threshold_breach",
)

VERIFICATION_TYPES = (
    "plan_vs_reality",
    "commitment_fulfillment",
    "objective_achievement",
    "capacity_exceeded",
    "dependency_risk",
    "budget_variance",
    "timeline_deviation",
    "quality_degradation",
    "risk_threshold_breach",
)


EVIDENCE_TYPES = (
    "document",
    "metric",
    "log",
    "event",
    "testimony",
)

ASSESSMENT_VERDICTS = (
    "pass",
    "fail",
    "conditional_pass",
    "inconclusive",
)


RESPONSIBILITY_TYPES = (
    "accountability",
    "ownership",
    "approval",
    "consultation",
    "information",
)

RESPONSIBILITY_SCOPES = (
    "project",
    "department",
    "team",
    "organization",
    "global",
)

ACCOUNTABILITY_TYPES = (
    "direct",
    "delegated",
    "shared",
    "oversight",
)

RESPONSIBILITY_RACI_ROLES = (
    "responsible",
    "accountable",
    "consulted",
    "informed",
)

ASSESSMENT_VERDICTS = (
    "pass",
    "fail",
    "conditional_pass",
    "inconclusive",
)


class AssessmentRecord(Base, TimestampMixin):
    """Assessment record for decision quality tracking."""

    __tablename__ = "assessment_records"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False)  # quality, alignment, risk, performance
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    assessor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    details: Mapped[Optional[str]] = mapped_column(Text)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

class LessonVerificationLink(Base, TimestampMixin):
    """Link between a lesson and its verification status."""

    __tablename__ = "lesson_verification_links"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lesson_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, verified, failed, superseded
    verification_method: Mapped[str] = mapped_column(String(40), nullable=False)  # manual, automated, peer_review
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_lesson_verify_org_lesson", "organization_id", "lesson_id"),
        Index("ix_lesson_verify_org_status", "organization_id", "verification_status"),
        UniqueConstraint("organization_id", "lesson_id", "verification_status", name="uq_lesson_verify_unique"),
        {"extend_existing": True},
    )


class PatternVerificationLink(Base, TimestampMixin):
    """Link between a pattern and its verification status."""

    __tablename__ = "pattern_verification_links"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pattern_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, verified, failed, superseded
    verification_method: Mapped[str] = mapped_column(String(40), nullable=False)  # manual, automated, peer_review
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_pattern_verify_org_pattern", "organization_id", "pattern_id"),
        Index("ix_pattern_verify_org_status", "organization_id", "verification_status"),
        UniqueConstraint("organization_id", "pattern_id", "verification_status", name="uq_pattern_verify_unique"),
        {"extend_existing": True},
    )


class VerificationContext(Base, TimestampMixin):
    """Context for a verification run - plan vs reality, commitment fulfillment, etc."""

    __tablename__ = "verification_contexts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    verification_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # plan_vs_reality, commitment_fulfillment, objective_achievement
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(24), default="company", nullable=False)  # company, department, team, project, initiative, objective, commitment
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    authorization_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)  # pending, running, completed, failed
    plan_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    reality_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    discrepancies_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    initiated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status_details: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_verif_ctx_org_status", "organization_id", "status"),
        Index("ix_verif_ctx_org_type", "organization_id", "verification_type"),
        {"extend_existing": True},
    )


class VerificationEvidence(Base, TimestampMixin):
    """Evidence for a verification context."""

    __tablename__ = "verification_evidence"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    verification_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)  # document, metric, log, event, testimony
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    quality: Mapped[str] = mapped_column(String(24), default="estimated", nullable=False)  # high, medium, low, estimated
    supports_verification: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_verif_evidence_org_verif", "organization_id", "verification_id"),
        Index("ix_verif_evidence_org_type", "organization_id", "evidence_type"),
        {"extend_existing": True},
    )