"""Phase 4I.1 — Company Intent & Planning models.

Canonical Company Intent that extends and integrates with existing strategic primitives:
- CompanyGoal/CompanyObjective/CompanyInitiative (execution_strategy) → Strategic execution hierarchy
- StrategicHistory → Temporal intent trail with exact-once provenance
- StrategicSnapshot → Live intent+plan state materialization
- StrategicOutcome → Intent→outcome learning loop
- CompanyDecision/Contradiction/Precedent → Governance & evidence
- CompanyState/CompanyAction → Live state & governed actions
- 4H.7 Institutional Learning → Lessons, patterns, contradictions, provenance

The Intent architecture is NOT a parallel planning module. It anchors the top-level
semantic "Why" and "What" that connects strategy → planning → execution → outcomes → learning.

CompanyIntent represents the company's DECLARED directional commitment.
CompanyGoal/Objective/Initiative remain the canonical STRATEGIC EXECUTION hierarchy.
CompanyIntent CONNECTS to them via intent_id/goals/objectives/initiatives links.
"""

from datetime import datetime, date, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


# Canonical vocabularies - REUSE existing where possible
# Intent kinds - DECLARED directional commitments (not execution nodes)
INTENT_KINDS = (
    "strategic",       # "Become market leader in X"
    "operational",     # "Reduce order-processing time by 30%"
    "financial",       # "Reach $X revenue"
    "organizational",  # "Expand engineering organization"
    "project",         # "Launch product X by date Y"
    "risk",            # "Reduce dependency on supplier X"
    "customer",        # "Improve retention for segment Y"
    "resource",        # "Allocate capacity toward initiative X"
    "governance",      # "Establish new approval policy"
    "capability",      # "Build capability in domain X"
)

# Intent epistemic status - REUSE lifecycle pattern from 4H.7 (organizational_learning lifecycle)
INTENT_EPISTEMIC_STATUS = (
    "discovered",      # Inferred from evidence, not yet declared
    "proposed",        # Submitted for governance consideration
    "adopted",         # Officially adopted by governance
    "active",          # Currently driving execution
    "superseded",      # Superseded by newer intent
    "archived",        # No longer relevant
)

# Intent provenance type - CRITICAL: declared vs inferred distinction
INTENT_SOURCE = (
    "declared",        # Explicitly declared by leadership
    "inferred",        # Inferred from evidence (actions, decisions, resource allocation)
    "derived",         # Derived from other intents/objectives
    "proposed",        # Proposed but not yet adopted
    "contested",       # Under governance dispute
)

# Canonical plan kinds - REUSE existing plan taxonomy where possible
PLAN_KINDS = (
    "strategic",       # Multi-year, company-wide
    "annual",          # Annual operating plan
    "quarterly",       # Quarterly OKR cycle
    "initiative",      # Single initiative plan
    "project",         # Project execution plan
    "capacity",        # Capacity/resource plan
    "hiring",          # Hiring plan
    "contingency",     # Risk/contingency plan
)

PLAN_STATES = (
    "draft",
    "proposed",
    "approved",
    "active",
    "paused",
    "completed",
    "retired",
)

ADAPTATION_TRIGGERS = (
    "outcome_deviation",    # Actual vs expected outcome deviation
    "state_change",         # CompanyState significant change
    "lesson_learned",       # New institutional lesson (4H.7)
    "contradiction",        # New contradiction surfaced (4H.7)
    "prediction_change",    # Prediction significantly updated
    "governance_decision",  # Governance decision affecting plan
    "resource_change",      # Resource availability changed
    "dependency_shift",     # Dependency graph changed
)

ADAPTATION_ACTIONS = (
    "adjust_timeline",
    "adjust_scope",
    "adjust_resources",
    "adjust_priority",
    "add_initiative",
    "remove_initiative",
    "reassign_ownership",
    "escalate",
    "retire",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyIntent(Base, TimestampMixin):
    """
    Company Intent — the canonical representation of what the company
    DECLARES it intends to achieve. This is the semantic anchor connecting
    the company's directional commitment to the strategic execution hierarchy.

    Does NOT duplicate CompanyGoal/CompanyObjective/CompanyInitiative.
    Instead, it CONNECTS to them via intent_id/goals/objectives/initiatives links.

    The Intent is the DECLARED "Why" and "What" that anchors the strategic
    execution hierarchy (Goal → Objective → Initiative → Project → Execution).
    """

    __tablename__ = "company_intents"
    __table_args__ = (
        Index("ix_ci_org_epistemic", "organization_id", "epistemic_status"),
        Index("ix_ci_org_kind", "organization_id", "kind"),
        Index("ix_ci_org_source", "organization_id", "source"),
        Index("ix_ci_org_supersedes", "organization_id", "supersedes_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Core intent identity
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # INTENT_KINDS
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Epistemic status - CRITICAL: declared vs inferred distinction
    epistemic_status: Mapped[str] = mapped_column(String(20), default="discovered", nullable=False, index=True)  # INTENT_EPISTEMIC_STATUS
    source: Mapped[str] = mapped_column(String(20), default="inferred", nullable=False)  # INTENT_SOURCE

    # Core intent identity
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # INTENT_KINDS
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    rationale: Mapped[Optional[str]] = mapped_column(Text)

    # Governance
    state: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)  # draft|proposed|adopted|active|paused|completed|retired|failed
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=highest..5=lowest
    # company | department | team | project | initiative
    scope: Mapped[str] = mapped_column(String(20), default="company", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # Ownership & sponsorship
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    owner_label: Mapped[str] = mapped_column(String(255), default="")
    sponsor_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    sponsor_label: Mapped[str] = mapped_column(String(255), default="")

    # Governance workflow
    policy: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)

    # Temporal
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Supersession chain - CRITICAL for temporal truth
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # intent this supersedes
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # intent that supersedes this

    # Learning integration (4H.7 consumption)
    lesson_fingerprints: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_intent_id: Mapped[Optional[str]] = mapped_column(String(32))  # if supersedes
    source_decision_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_scenario_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Metrics & success criteria
    metric_kind: Mapped[Optional[str]] = mapped_column(String(80))
    metric_unit: Mapped[Optional[str]] = mapped_column(String(40))
    target_value: Mapped[Optional[float]] = mapped_column(Float)
    current_value: Mapped[Optional[float]] = mapped_column(Float)

    # Expected outcome (structured)
    expected_outcome: Mapped[Optional[dict]] = mapped_column(JSON)

    # Governance note
    governance_note: Mapped[Optional[str]] = mapped_column(Text)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_company_intents_fingerprint",
        ),
    )


class CompanyPlan(Base, TimestampMixin):
    """
    Company Plan — the operational plan to achieve one or more intents.
    CONNECTS to CompanyIntent via intent_id.
    CONNECTS to CompanyGoal/Objective/Initiative via goal_id/objective_ids/initiative_ids.

    Extends the strategic execution hierarchy with adaptive planning,
    learning integration, and governance.
    """

    __tablename__ = "company_plans"
    __table_args__ = (
        Index("ix_cp_org_state", "organization_id", "state"),
        Index("ix_cp_org_kind", "organization_id", "kind"),
        Index("ix_cp_org_intent", "organization_id", "intent_id"),
        Index("ix_cp_org_goal", "organization_id", "goal_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Core plan identity
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # PLAN_KINDS
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Governance
    state: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)  # PLAN_STATES
    priority: Mapped[int] = mapped_column(Integer, default=3)
    scope: Mapped[str] = mapped_column(String(20), default="company", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # Ownership
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    owner_label: Mapped[str] = mapped_column(String(255), default="")

    # Governance workflow
    policy: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)

    # Temporal
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Intent linkage
    intent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_intents.id", ondelete="SET NULL"), index=True
    )

    # Linked strategic execution elements
    goal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    objective_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    initiative_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Plan structure (structured items)
    # [{"type": "initiative|milestone|task|dependency|resource",
    #   "title": "...", "description": "...", "owner_id": "...",
    #   "due_date": "...", "dependencies": [...], "resources": [...],
    #   "expected_outcome": {...}, "confidence": 0.8}]
    items: Mapped[Optional[list[dict]]] = mapped_column(JSON, default=list)

    # Focus areas
    focus: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Learning integration (4H.7 consumption)
    lesson_fingerprints: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Adaptive planning
    adaptation_state: Mapped[str] = mapped_column(String(20), default="stable")
    last_adapted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    adaptation_count: Mapped[int] = mapped_column(Integer, default=0)

    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_intent_id: Mapped[Optional[str]] = mapped_column(String(32))
    source_plan_id: Mapped[Optional[str]] = mapped_column(String(32))
    source_scenario_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Governance
    policy: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_company_plans_fingerprint",
        ),
    )


class PlanItem(Base, TimestampMixin):
    """
    Individual item within a CompanyPlan. More granular than initiatives/tasks.
    """

    __tablename__ = "company_plan_items"
    __table_args__ = (
        Index("ix_cpi_org_plan", "organization_id", "plan_id"),
        Index("ix_cpi_org_due", "organization_id", "due_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("company_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Item identity
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # initiative|milestone|task|dependency|resource
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Execution
    state: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    owner_label: Mapped[str] = mapped_column(String(255), default="")
    assignee_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    assignee_label: Mapped[str] = mapped_column(String(255), default="")

    # Temporal
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Dependencies (other plan item IDs)
    dependencies: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Resources
    # [{"type": "person|budget|capability|document", "id": "...", "amount": ...}]
    resources: Mapped[Optional[list[dict]]] = mapped_column(JSON, default=list)

    # Expected outcome
    expected_outcome: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # Learning integration
    lesson_fingerprints: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_intent_id: Mapped[Optional[str]] = mapped_column(String(32))
    source_initiative_id: Mapped[Optional[str]] = mapped_column(String(32))
    source_task_id: Mapped[Optional[str]] = mapped_column(String(32))

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "plan_id", "fingerprint",
            name="uq_company_plan_items_fingerprint",
        ),
    )


class PlanAdaptation(Base, TimestampMixin):
    """
    Record of a plan adaptation triggered by learning, state change,
    contradiction, or governance decision. The adaptive planning audit trail.
    """

    __tablename__ = "plan_adaptations"
    __table_args__ = (
        Index("ix_pa_org_plan", "organization_id", "plan_id"),
        Index("ix_pa_org_trigger", "organization_id", "trigger"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("company_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # What triggered the adaptation
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)  # see ADAPTATION_TRIGGERS
    trigger_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    trigger_reason: Mapped[str] = mapped_column(Text)

    # What adaptation was made
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # see ADAPTATION_ACTIONS
    action_detail: Mapped[str] = mapped_column(Text)

    # Before/after snapshot
    before_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    after_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)

    # Learning integration
    lesson_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    pattern_id: Mapped[Optional[str]] = mapped_column(String(32))
    contradiction_id: Mapped[Optional[str]] = mapped_column(String(32))

    # Governance
    state: Mapped[str] = mapped_column(String(16), default="proposed")
    approver_person_id: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)

    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "plan_id", "fingerprint",
            name="uq_plan_adaptations_fingerprint",
        ),
    )


class IntentPrediction(Base, TimestampMixin):
    """
    Prediction about an intent's trajectory. Generated by the planning engine
    consuming company state, predictions, and institutional learning.
    """

    __tablename__ = "intent_predictions"
    __table_args__ = (
        Index("ix_ip_org_intent", "organization_id", "intent_id"),
        Index("ix_org_time", "organization_id", "generated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intent_id: Mapped[str] = mapped_column(
        ForeignKey("company_intents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Prediction type
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # trajectory|risk|resource|timeline

    # Prediction detail
    prediction: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # Evidence
    evidence_fingerprints: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    lesson_fingerprints: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Horizon
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "intent_id", "fingerprint",
            name="uq_intent_predictions_fingerprint",
        ),
    )


class PlanSimulation(Base, TimestampMixin):
    """
    What-if simulation for a plan. Extends SimulationRun with plan-specific context.
    """

    __tablename__ = "plan_simulations"
    __table_args__ = (
        Index("ix_ps_org_plan", "organization_id", "plan_id"),
        UniqueConstraint(
            "organization_id", "plan_id", "fingerprint",
            name="uq_plan_simulations_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("company_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Simulation identity
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[Optional[str]] = mapped_column(Text)
    assumptions: Mapped[Optional[list[dict]]] = mapped_column(JSON, default=list)
    domains: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    # Results
    results: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    risk: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Comparison with base plan
    delta: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Governance
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(default=0)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


class IntentPlanState(Base, TimestampMixin):
    """
    Live composite state of an intent + its plans. Materialized view for dashboards.
    """

    __tablename__ = "intent_plan_states"
    __table_args__ = (
        Index("ix_ips_org_intent", "organization_id", "intent_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intent_id: Mapped[str] = mapped_column(
        ForeignKey("company_intents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Computed state
    overall_state: Mapped[str] = mapped_column(String(20), default="draft")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    health: Mapped[str] = mapped_column(String(16), default="critical")  # healthy|at_risk|critical

    # Aggregated metrics
    total_plans: Mapped[int] = mapped_column(Integer, default=0)
    active_plans: Mapped[int] = mapped_column(Integer, default=0)
    completed_plans: Mapped[int] = mapped_column(Integer, default=0)

    # Learning signals
    active_contradictions: Mapped[int] = mapped_column(Integer, default=0)
    supporting_lessons: Mapped[int] = mapped_column(Integer, default=0)
    supporting_patterns: Mapped[int] = mapped_column(Integer, default=0)

    # Temporal
    last_adaptation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_prediction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_state_change_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Computed at
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "intent_id", "fingerprint",
            name="uq_intent_plan_states_fingerprint",
        ),
    )