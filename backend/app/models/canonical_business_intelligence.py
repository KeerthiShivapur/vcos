"""Gate 23 — Canonical Business Intelligence & Decision Operating Fabric models.

The Canonical Business Intelligence & Decision Operating Fabric is a governed
projection/reasoning capability over the ONE canonical company reality.
It does NOT create a parallel BI graph, analytics graph, dashboard graph,
decision graph, metrics brain, or any second company state.

Every model here:
- Retains organization, scope, temporal validity, provenance
- Traces to underlying canonical entities
- Preserves epistemic boundaries (observation ≠ inference ≠ prediction ≠ decision)
- Enforces governance (tenant → org → scope → role → permission → temporal)
- Supports exact-once semantics and temporal truth
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# --- canonical vocabularies ---------------------------------------------------

# Metric categories (universal, not dashboard-specific)
METRIC_CATEGORIES = (
    "strategic",       # objective progress, goal attainment, strategic alignment
    "operational",     # throughput, cycle time, blocked work, process performance
    "people",          # capacity, utilization, capability gaps, workforce continuity
    "customer",        # customer health, commitments, delivery, commercial outcomes
    "financial",       # revenue, cost, budget, variance, cash indicators
    "resource",        # utilization, allocation, shortage, excess capacity
    "procurement",     # delivery, vendor performance, procurement cycle
    "risk",            # emerging risks, dependency risks, capacity risks, financial risks
)

# Metric direction: which direction is "good"
METRIC_DIRECTIONS = ("up_is_good", "down_is_good", "target_is_good", "stable_is_good")

# Metric status
METRIC_STATUSES = ("active", "deprecated", "archived")

# Observation labels (quantitative nature)
OBSERVATION_LABELS = (
    "actual", "forecast", "plan", "target", "estimated", "baseline", "benchmark", "other"
)

# Observation sources (provider-neutral)
OBSERVATION_SOURCES = (
    "manual", "survey", "export", "crm", "system", "measurement",
    "financial", "customer", "operator", "canonical_engine", "derived", "other"
)

# Epistemic status of a metric value
EPISTEMIC_STATUSES = (
    "observed",           # direct observation from canonical reality
    "derived",            # computed from other observations
    "projected",          # forecast/projection from Gate 10
    "counterfactual",     # scenario-based from Gate 11
    "simulated",          # digital twin projection from Gate 12
    "inferred",           # AI/ML inference with confidence
    "estimated",          # human estimate
)

# Lineage relationship types
LINEAGE_RELATIONS = (
    "computed_from",      # this metric computed from source metrics
    "aggregates",         # this metric aggregates source metrics
    "derives_from",       # this metric derives from source observations
    "evidenced_by",       # this metric evidenced by canonical entities
    "linked_to",          # linked to canonical entity
    "strongly_associated_with",
    "evidence_indicates",
    "likely_contributor",
)

# Variance direction
VARIANCE_DIRECTIONS = ("favorable", "unfavorable", "neutral")

# Variance cause candidate status
CAUSE_CANDIDATE_STATUS = ("candidate", "investigating", "confirmed", "ruled_out")

# Company health dimensions
HEALTH_DIMENSIONS = (
    "strategic", "operational", "financial", "customer",
    "workforce", "capacity", "process", "knowledge",
    "execution", "governance", "risk"
)

HEALTH_STATES = ("healthy", "concerned", "at_risk", "critical")

# Decision context sections
DECISION_CONTEXT_SECTIONS = (
    "question", "current_state", "evidence", "relevant_metrics",
    "constraints", "dependencies", "risks", "predictions",
    "counterfactuals", "options", "expected_outcomes",
    "contradictions", "epistemic_status", "governance", "authority"
)

# Decision states (distinct from recommendation/authorization/commitment/action)
DECISION_STATES = (
    "framed", "evidence_gathered", "options_defined", "deliberating",
    "decided", "authorized", "committed", "executed", "outcome_recorded", "verified", "learned"
)


class CanonicalMetric(Base, TimestampMixin):
    """One canonical business metric — the unit of business measurement.

    Universally defined: category, direction, unit and visibility are canonical
    so the same metric key aggregates across any company size. The metric is
    the anchor for observations, targets, forecasts, drivers, lineage and links.

    This extends (not replaces) BusinessMetric from 4G.6 with additional
    canonical BI semantics: epistemic status, calculation definition,
    comparison baseline, confidence, temporal validity.
    """

    __tablename__ = "canonical_metrics"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_cm_metric_key"),
        Index("ix_cm_org", "organization_id"),
        Index("ix_cm_org_category", "organization_id", "category"),
        Index("ix_cm_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # canonical metric key, e.g. "recurring_revenue", "customer_churn_rate"
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text)
    # strategic | operational | people | customer | financial | resource | procurement | risk
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="operational")
    # up_is_good | down_is_good | target_is_good | stable_is_good
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="up_is_good")
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # public | internal | restricted
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    # daily | weekly | monthly | quarterly | yearly
    period_granularity: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    # org_wide | business_unit | project | team | person
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="org_wide")
    scope_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Calculation definition (SQL-like expression or function reference)
    calculation_definition: Mapped[Optional[str]] = mapped_column(Text)
    # Semantic meaning: what this metric represents in company reality
    semantic_meaning: Mapped[Optional[str]] = mapped_column(Text)
    # Current observed value (cached for performance)
    current_value: Mapped[Optional[float]] = mapped_column(Float)
    current_value_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Comparison baseline (e.g., prior period, target, benchmark)
    comparison_baseline: Mapped[Optional[float]] = mapped_column(Float)
    comparison_baseline_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # Confidence in current value (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # Epistemic status of the current value
    epistemic_status: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    # Temporal validity of this metric definition
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Source event that created/updated this metric
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class MetricObservation(Base, TimestampMixin):
    """One observed value of a canonical metric.

    The grounding unit of business intelligence: an actual/forecast/plan/target
    number with its source, provenance, and epistemic status. Exact-once on
    (org, metric, observed_at, source_event) so replays never double-count.
    """

    __tablename__ = "metric_observations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "metric_id", "observed_at", "source_event_id",
            name="uq_mo_exact_once",
        ),
        Index("ix_mo_org_metric_time", "organization_id", "metric_id", "observed_at"),
        Index("ix_mo_org_time", "organization_id", "observed_at"),
        Index("ix_mo_org_label", "organization_id", "label"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_metrics.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # actual | forecast | plan | target | estimated | baseline | benchmark | other
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="actual")
    # manual | survey | export | crm | system | measurement | financial | customer | operator | canonical_engine | derived | other
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    # Where the number came from, e.g. "customer.outcome.recorded:abc123"
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # Epistemic status of this observation
    epistemic_status: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    # Confidence in this observation (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class MetricLineage(Base, TimestampMixin):
    """Metric lineage — why a metric has its value.

    Traces: Metric → Calculation → Source Observations → Canonical Entities → Evidence → Provenance → Time Window.
    A user must be able to click a number and understand WHY it is that value.
    """

    __tablename__ = "metric_lineage"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "metric_id", "source_type", "source_id", "relation", "source_event_id",
            name="uq_ml_exact_once",
        ),
        Index("ix_ml_org_metric", "organization_id", "metric_id"),
        Index("ix_ml_org_source", "organization_id", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_metrics.id", ondelete="CASCADE"), nullable=False
    )
    # What this lineage entry traces to
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # canonical_metric | metric_observation | canonical_entity
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # computed_from | aggregates | derives_from | evidenced_by | linked_to | strongly_associated_with | evidence_indicates | likely_contributor
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    # Human-readable explanation of the relationship
    explanation: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Evidence count supporting this lineage link
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    # Time window this lineage applies to
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Provenance of this lineage determination
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # Confidence in this lineage link (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessIntelligenceContext(Base, TimestampMixin):
    """Governed Business Intelligence Context — a derived read model, not another company reality.

    Provides role/scope appropriate derived intelligence for:
    person, team, department, project, customer, process, company.

    Same underlying reality, different authorized projection.
    """

    __tablename__ = "business_intelligence_contexts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "context_type", "context_entity_id", "period_label", "source_event_id",
            name="uq_bic_exact_once",
        ),
        Index("ix_bic_org_type_entity", "organization_id", "context_type", "context_entity_id"),
        Index("ix_bic_org_period", "organization_id", "period_label"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # person | team | department | project | customer | process | company
    context_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context_entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Period this context covers (e.g., "2026-01", "2026-Q1", "2026")
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # Governance: who can access this context
    governance_scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="org")
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Metrics relevant to this context
    metric_keys_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Key performance indicators for this context
    kpi_keys_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Current health assessment
    health_score: Mapped[Optional[int]] = mapped_column(Integer)
    health_state: Mapped[Optional[str]] = mapped_column(String(16))
    # Variance alerts
    variance_alerts_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Top risks for this context
    top_risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Decisions requiring attention in this context
    pending_decisions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Summary narrative
    summary_narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Provenance of this context derivation
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalCompanyHealth(Base, TimestampMixin):
    """Multidimensional Company Health — explainable, not a black-box score.

    Every dimension traces to canonical evidence/observations.
    Never creates: CompanyHealthScore = 82 without explanation.
    """

    __tablename__ = "canonical_company_health"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "period_label", "compute_mode", "source_event_id",
            name="uq_ch_exact_once",
        ),
        Index("ix_ch_org_period", "organization_id", "period_label"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # observed | derived | projected | scenario
    compute_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    # Overall health (weighted aggregate of dimensions)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_state: Mapped[str] = mapped_column(String(16), nullable=False, default="concerned")
    # Per-dimension health with reasons and evidence
    dimensions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Key metrics driving health
    driving_metrics_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Active risks affecting health
    active_risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Summary narrative with evidence references
    summary_narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Computation timestamps
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class VarianceAnalysis(Base, TimestampMixin):
    """Expected vs Actual variance intelligence across canonical domains.

    Supports: objectives, commitments, projects, processes, customer outcomes,
    budgets, resource allocations, procurement, workforce capacity, timelines.

    Preserves: Expected ≠ Actual ≠ Cause Candidate ≠ Confirmed Cause.
    """

    __tablename__ = "variance_analyses"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "domain", "entity_id", "period_label", "source_event_id",
            name="uq_va_exact_once",
        ),
        Index("ix_va_org_domain", "organization_id", "domain"),
        Index("ix_va_org_entity", "organization_id", "entity_id"),
        Index("ix_va_org_period", "organization_id", "period_label"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # objective | commitment | project | process | customer_outcome | budget | resource_allocation | procurement | workforce_capacity | timeline
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # Expected value
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    # Actual observed value
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    # Variance magnitude and direction
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    variance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # favorable | unfavorable | neutral
    # Unit of measurement
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # Cause candidates with evidence (not confirmed causes)
    cause_candidates_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Impact assessment
    impact_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")  # low | medium | high | critical
    impact_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Attention required
    attention_required: Mapped[bool] = mapped_column(default=False)
    attention_reason: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CauseCandidate(Base, TimestampMixin):
    """A candidate cause for a variance — NOT a confirmed cause.

    Preserves epistemic boundary: cause candidate ≠ confirmed cause.
    """

    __tablename__ = "cause_candidates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "variance_id", "candidate_type", "candidate_id", "source_event_id",
            name="uq_cc_cause_exact_once",
        ),
        Index("ix_cc_org_variance", "organization_id", "variance_id"),
        Index("ix_cc_org_candidate", "organization_id", "candidate_type", "candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    variance_id: Mapped[str] = mapped_column(
        ForeignKey("variance_analyses.id", ondelete="CASCADE"), nullable=False
    )
    # What type of entity is the candidate cause
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)  # person | team | commitment | dependency | process | vendor | resource | external
    candidate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # candidate | investigating | confirmed | ruled_out
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    # Evidence supporting this candidate
    evidence_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Strength of evidence (0..1)
    evidence_strength: Mapped[float] = mapped_column(Float, default=0.5)
    # Explanation of why this is a candidate
    rationale: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class RootCauseTrace(Base, TimestampMixin):
    """Cross-domain root-cause traceability using canonical graph.

    Example trace:
    Customer → Outcome → Commitment → Responsibility → Person → Capacity → Dependency → Task → Process → Vendor → Procurement

    Reuses canonical relationships, does NOT create a new causal graph.
    """

    __tablename__ = "root_cause_traces"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "origin_type", "origin_id", "trace_path_hash", "source_event_id",
            name="uq_rct_exact_once",
        ),
        Index("ix_rct_org_origin", "organization_id", "origin_type", "origin_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Where the trace starts (e.g., customer delivery late)
    origin_type: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_id: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # The trace path as a hash for deduplication
    trace_path_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Full trace path: [{"type": "customer", "id": "...", "relation": "has_outcome", "evidence": "..."}, ...]
    trace_path_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Strongest observed contributor (not confirmed cause)
    strongest_contributor_type: Mapped[Optional[str]] = mapped_column(String(32))
    strongest_contributor_id: Mapped[Optional[str]] = mapped_column(String(32))
    strongest_contributor_label: Mapped[Optional[str]] = mapped_column(String(200))
    strongest_contributor_evidence: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    # Confidence in the trace (0..1)
    trace_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalDecisionContext(Base, TimestampMixin):
    """Canonical Decision Context — integrates evidence, metrics, predictions, scenarios, digital twin.

    A decision context contains:
    - Question
    - Current State
    - Evidence
    - Relevant Metrics
    - Constraints
    - Dependencies
    - Risks
    - Predictions (Gate 10)
    - Counterfactuals (Gate 11)
    - Digital Twin Projections (Gate 12)
    - Options
    - Expected Outcomes
    - Contradictions
    - Epistemic Status
    - Governance
    - Authority

    Maintains absolute distinctions:
    Decision ≠ Recommendation ≠ Authorization ≠ Commitment ≠ Action ≠ Execution ≠ Outcome
    """

    __tablename__ = "canonical_decision_contexts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id", "version", "source_event_id",
            name="uq_dc_exact_once",
        ),
        Index("ix_dc_org_decision", "organization_id", "decision_id"),
        Index("ix_dc_org_status", "organization_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Link to CompanyDecision (4A/4G)
    decision_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Version of this decision context
    version: Mapped[int] = mapped_column(Integer, default=1)
    # The decision question
    question: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Current state summary
    current_state: Mapped[Optional[str]] = mapped_column(Text)
    # Evidence supporting the context
    evidence_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Relevant metric IDs
    metric_ids_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Constraints
    constraints_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Dependencies
    dependencies_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Risks
    risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Predictions (Gate 10)
    predictions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Counterfactuals (Gate 11)
    counterfactuals_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Digital twin projections (Gate 12)
    twin_projections_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Options being considered
    options_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Expected outcomes per option
    expected_outcomes_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Contradictions in evidence
    contradictions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Epistemic status of the context
    epistemic_status: Mapped[str] = mapped_column(String(16), nullable=False, default="evidence_based")
    # Overall confidence (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Governance scope
    governance_scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="org")
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Decision authority (who can decide)
    authority_role: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    authority_person_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Current state of this decision context
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="framed")
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalDecisionOption(Base, TimestampMixin):
    """One option within a decision context."""

    __tablename__ = "canonical_decision_options"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_context_id", "option_key", "source_event_id",
            name="uq_do_exact_once",
        ),
        Index("ix_do_org_context", "organization_id", "decision_context_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_context_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_decision_contexts.id", ondelete="CASCADE"), nullable=False
    )
    option_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Expected outcomes for this option
    expected_outcomes_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Risks for this option
    risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Counterfactual projection for this option
    counterfactual_json: Mapped[Optional[dict]] = mapped_column(JSON)
    # Confidence in this option's outcomes (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Epistemic status
    epistemic_status: Mapped[str] = mapped_column(String(16), nullable=False, default="projected")
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalDecisionAssessment(Base, TimestampMixin):
    """Assessment of a decision context — the output of deliberation.

    Not a decision itself. Feeds into the governance process.
    """

    __tablename__ = "canonical_decision_assessments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_context_id", "assessor_id", "source_event_id",
            name="uq_da_exact_once",
        ),
        Index("ix_da_org_context", "organization_id", "decision_context_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_context_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_decision_contexts.id", ondelete="CASCADE"), nullable=False
    )
    assessor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Recommended option
    recommended_option_key: Mapped[Optional[str]] = mapped_column(String(80))
    # Assessment rationale
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Confidence in recommendation (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Key concerns
    concerns_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalDecisionCockpitItem(Base, TimestampMixin):
    """Decisions requiring attention — the decision cockpit surface.

    Example:
    "Customer delivery decision"
    Why: Critical dependency blocked.
    Impact: ₹X projected exposure.
    Evidence: ...
    Prediction: 72% probability of missing target.
    Options: A — add capacity, B — change sequence, C — renegotiate timeline
    Counterfactual: Option B reduces predicted delay by ...
    Authority: COO
    Status: Awaiting decision
    """

    __tablename__ = "canonical_decision_cockpit_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_context_id", "source_event_id",
            name="uq_dci_exact_once",
        ),
        Index("ix_dci_org_status", "organization_id", "status"),
        Index("ix_dci_org_priority", "organization_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_context_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_decision_contexts.id", ondelete="CASCADE"), nullable=False
    )
    # Priority: critical | high | medium | low
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    # Why this decision needs attention
    why: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Projected impact if not decided
    impact_description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    impact_monetized: Mapped[Optional[float]] = mapped_column(Float)
    # Key evidence summary
    evidence_summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Prediction summary
    prediction_summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Options summary
    options_summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Counterfactual insight
    counterfactual_insight: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Decision authority
    authority_role: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    authority_person_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Status: awaiting_decision | deliberating | decided | authorized | executed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="awaiting_decision")
    # Deadline for decision
    decision_deadline: Mapped[Optional[date]] = mapped_column(Date)
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CanonicalIntelligenceLoopEvent(Base, TimestampMixin):
    """The canonical intelligence → decision → execution → outcome → verification → learning loop.

    This closes the intelligence loop. The system learns whether its decision
    intelligence was actually useful. That is part of the moat.
    """

    __tablename__ = "canonical_intelligence_loop_events"
    __table_args__ = (
        Index("ix_ile_org_decision", "organization_id", "decision_id"),
        Index("ix_ile_org_stage", "organization_id", "stage"),
        Index("ix_ile_org_time", "organization_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # observation → insight → decision_context → decision → authorization → commitment → responsibility → action → execution → outcome → verification → learning → future_bi
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    # Entity involved at this stage
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # What happened at this stage
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Whether this stage validated the prior intelligence
    validated_prior_intelligence: Mapped[Optional[bool]] = mapped_column(default=None)
    # Learning captured
    learning_captured: Mapped[Optional[str]] = mapped_column(Text)
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CanonicalExecutiveBriefing(Base, TimestampMixin):
    """Automated executive briefings — views over canonical reality, not a reporting database.

    Daily: What changed overnight? What needs attention? What decisions pending?
    Weekly: Company changes, Execution, Customers, Finance, People, Capacity, Risks, Predictions, Decisions
    Monthly: Strategic progress, Financial performance, Operational performance, Organizational changes, Customer outcomes, Institutional learning, Future risks
    """

    __tablename__ = "canonical_executive_briefings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "briefing_type", "period_label", "recipient_scope", "source_event_id",
            name="uq_eb_exact_once",
        ),
        Index("ix_eb_org_type_period", "organization_id", "briefing_type", "period_label"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # daily | weekly | monthly
    briefing_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Period label: "2026-01-15", "2026-W03", "2026-01"
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # Recipient scope: executive | manager | all | org_wide
    recipient_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="executive")
    # Governance scope
    governance_scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="org")
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    # Sections content
    sections_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Key metrics snapshot
    metrics_snapshot_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Decisions requiring attention
    pending_decisions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Top risks
    top_risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Provenance
    provenance: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CanonicalNaturalLanguageQuery(Base, TimestampMixin):
    """Governed natural-language company questions and their evidence-backed answers.

    Questions like:
    - "Why are we behind this quarter?"
    - "Which customers are most at risk?"
    - "Where are our biggest capacity bottlenecks?"
    - "What caused the increase in procurement costs?"
    - "What happens if we delay Project X?"

    Answers grounded in authorized canonical reality with traceable evidence.
    """

    __tablename__ = "canonical_natural_language_queries"
    __table_args__ = (
        Index("ix_nlq_org_user", "organization_id", "user_id"),
        Index("ix_nlq_org_time", "organization_id", "asked_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Parsed intent
    intent: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # Answer with claims and evidence
    answer_json: Mapped[Optional[dict]] = mapped_column(JSON)
    # Sources consulted
    sources_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # Confidence in answer (0..1)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Epistemic status of answer
    epistemic_status: Mapped[str] = mapped_column(String(16), nullable=False, default="evidence_based")
    # Governance: was answer scoped to user's access?
    governance_applied: Mapped[bool] = mapped_column(default=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))