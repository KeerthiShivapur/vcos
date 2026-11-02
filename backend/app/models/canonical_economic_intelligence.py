"""Canonical Financial–Resource–Procurement Operating Intelligence — Gate 18.

Derives the unified economic operating intelligence by composing Gates 15, 16, and 17
into a single coherent economic operating fabric.

This is a DERIVED PROJECTION layer — it does NOT create a second economic reality.
All data is composed from existing canonical primitives:
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric  
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
"""

from datetime import date, datetime, timezone
from typing import Any, Optional, List

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


# =============================================================================
# CANONICAL VOCABULARIES
# =============================================================================

# Economic state distinctions (epistemic boundaries)
ECONOMIC_STATES = (
    "planned",          # Plan/estimate
    "demanded",         # ResourceDemand created
    "authorized",       # Authorization granted (Decision ≠ Authorization)
    "committed",        # Financial commitment made (Authorization ≠ Commitment)
    "procured",         # Procurement in progress
    "allocated",        # Resource assigned (Commitment ≠ Allocation)
    "executed",         # Work performed (Allocation ≠ Execution)
    "actualized",       # Actual financial outcome recorded (Execution ≠ Actual)
    "outcome_verified", # Business outcome verified (Financial ≠ Business Outcome)
)

# Economic bottleneck types
BOTTLENECK_TYPES = (
    "financial",        # Budget constraint
    "human_capacity",   # People/skills constraint
    "physical_resource", # Equipment/facility constraint
    "digital_infrastructure", # Compute/storage/network constraint
    "procurement",      # Acquisition lead time
    "vendor",           # External dependency
    "allocation",       # Resource assignment conflict
    "strategic",        # Priority misalignment
)

# Cost variance categories
COST_VARIANCE_CATEGORIES = (
    "budget_vs_committed",
    "committed_vs_actual",
    "procurement_vs_budget",
    "vendor_vs_internal",
    "plan_vs_actual",
)


# =============================================================================
# ECONOMIC OPERATING SLICE — Unified economic operating projection
# =============================================================================

class EconomicOperatingSlice(Base, TimestampMixin):
    """
    Canonical Economic Operating Slice — governed, point-in-time derived
    projection of the unified company economic reality.
    
    Composes Gates 15, 16, 17 into a single coherent economic view.
    This is a VIEW/PROJECTION, not a data store. Materialized for performance.
    """
    
    __tablename__ = "economic_operating_slices"
    __table_args__ = (
        Index("ix_eos_org_computed", "organization_id", "computed_at"),
        UniqueConstraint(
            "organization_id", "input_fingerprint",
            name="uq_eos_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Input fingerprint for exact-once
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # --- Strategic Context ---
    objectives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    initiatives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    projects: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # --- Customer/Commercial ---
    customers: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    commercial_intents: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # --- Financial (Gate 15) ---
    budgets: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    budget_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    expenses: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    invoices: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    payments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    financial_outcomes: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # --- Resource & Asset (Gate 16) ---
    resources: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    assets: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    resource_demands: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    allocations: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # --- Procurement & Vendor (Gate 17) ---
    procurements: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    vendors: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    external_capacity: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    vendor_performance: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # --- Summary Metrics ---
    
    # Financial
    total_budgeted: Mapped[Optional[float]] = mapped_column(Float)
    total_committed: Mapped[Optional[float]] = mapped_column(Float)
    total_spent: Mapped[Optional[float]] = mapped_column(Float)
    total_available: Mapped[Optional[float]] = mapped_column(Float)
    budget_utilization: Mapped[Optional[float]] = mapped_column(Float)
    cost_variance: Mapped[Optional[float]] = mapped_column(Float)
    
    # Procurement
    pending_procurements: Mapped[int] = mapped_column(Integer, default=0)
    overdue_procurements: Mapped[int] = mapped_column(Integer, default=0)
    procurement_risk_score: Mapped[Optional[float]] = mapped_column(Float)
    
    # Resource & Asset
    total_resources: Mapped[int] = mapped_column(Integer, default=0)
    total_assets: Mapped[int] = mapped_column(Integer, default=0)
    total_capacity: Mapped[Optional[float]] = mapped_column(Float)
    total_committed_capacity: Mapped[Optional[float]] = mapped_column(Float)
    total_available_capacity: Mapped[Optional[float]] = mapped_column(Float)
    overall_utilization: Mapped[Optional[float]] = mapped_column(Float)
    critical_asset_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Demand & Allocation
    total_demands: Mapped[int] = mapped_column(Integer, default=0)
    unfulfilled_demands: Mapped[int] = mapped_column(Integer, default=0)
    total_allocations: Mapped[int] = mapped_column(Integer, default=0)
    active_allocations: Mapped[int] = mapped_column(Integer, default=0)
    overall_allocation_utilization: Mapped[Optional[float]] = mapped_column(Float)
    
    # Vendor & External Capacity
    total_vendors: Mapped[int] = mapped_column(Integer, default=0)
    active_vendors: Mapped[int] = mapped_column(Integer, default=0)
    critical_vendors: Mapped[int] = mapped_column(Integer, default=0)
    total_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    available_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    committed_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    procurement_risk_score: Mapped[Optional[float]] = mapped_column(Float)
    
    # Customer/Commercial
    total_customers: Mapped[int] = mapped_column(Integer, default=0)
    total_commitments: Mapped[int] = mapped_column(Integer, default=0)
    at_risk_commitments: Mapped[int] = mapped_column(Integer, default=0)
    projected_revenue: Mapped[Optional[float]] = mapped_column(Float)
    projected_cost: Mapped[Optional[float]] = mapped_column(Float)
    projected_margin: Mapped[Optional[float]] = mapped_column(Float)
    
    # Risk & Conflicts
    total_conflicts: Mapped[int] = mapped_column(Integer, default=0)
    critical_conflicts: Mapped[int] = mapped_column(Integer, default=0)
    vendor_dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_vendor_dependencies: Mapped[int] = mapped_column(Integer, default=0)
    
    # Economic State Distribution
    economic_state_distribution: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Bottlenecks
    bottlenecks: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Predictions (Gate 10)
    active_predictions: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Counterfactual scenarios (Gate 11)
    active_scenarios: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Digital Twin state (Gate 12)
    digital_twin_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Computed metadata
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once fingerprint (on canonical inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# ECONOMIC IMPACT ANALYSIS — Unified cross-domain economic impact
# =============================================================================

class EconomicImpactAnalysis(Base, TimestampMixin):
    """
    Canonical Economic Impact Analysis — derives the unified cross-domain economic impact
    of a change across Financial, Resource, Procurement, Vendor, Customer, and Strategic domains.
    
    Unifies FinancialImpactAnalysis, ResourceImpactAnalysis, and ProcurementImpactAnalysis
    into a single coherent economic impact assessment.
    """
    
    __tablename__ = "economic_impact_analyses"
    __table_args__ = (
        Index("ix_eia_org_trigger", "organization_id", "trigger_type"),
        Index("ix_eia_org_entity", "organization_id", "trigger_entity_type", "trigger_entity_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_eia_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # budget_cut|resource_shift|procurement_delay|revenue_change|vendor_change|capacity_change|budget_increase|vendor_replacement
    trigger_entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # budget|resource|procurement|commitment|vendor|external_capacity|project|objective|vendor_capability
    trigger_entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Impact scope — Financial
    affected_budgets: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_budget_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_financial_outcomes: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Impact scope — Resource/Asset
    affected_resources: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_assets: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_allocations: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_demands: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Impact scope — Procurement/Vendor
    affected_procurements: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_vendors: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_external_capacity: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_vendor_capabilities: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Impact scope — Cross-domain (Gate 13/14)
    affected_projects: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_objectives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_people: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_customers: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Quantitative impact
    capacity_impact: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    margin_impact: Mapped[Optional[float]] = mapped_column(Float)
    cash_flow_impact: Mapped[Optional[float]] = mapped_column(Float)
    timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Cost variance breakdown
    cost_variance_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Risk assessment
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    new_risks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    escalated_risks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Bottleneck detection
    new_bottlenecks: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    resolved_bottlenecks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Economic state transitions
    state_transitions: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Related scenarios (Gate 11)
    scenario_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Confidence & metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ECONOMIC BOTTLENECK — Derived bottleneck intelligence
# =============================================================================

class EconomicBottleneck(Base, TimestampMixin):
    """
    Canonical Economic Bottleneck — derived intelligence about economic constraints.
    
    These are DERIVED projections, NOT canonical truths. They feed the existing
    Operating Attention architecture (Gate 13). Do NOT create a parallel attention system.
    """
    
    __tablename__ = "economic_bottlenecks"
    __table_args__ = (
        Index("ix_eb_org_type", "organization_id", "bottleneck_type"),
        Index("ix_eb_org_severity", "organization_id", "severity"),
        Index("ix_eb_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_eb_org_status", "organization_id", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    bottleneck_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # BOTTLENECK_TYPES
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")  # info|warning|critical
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|mitigating|resolved
    
    # Primary entity causing bottleneck
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # budget|resource|vendor|project|commitment|objective
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Affected entities
    affected_project_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_commitment_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_objective_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_customer_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_resource_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_vendor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Quantitative
    constrained_amount: Mapped[Optional[float]] = mapped_column(Float)
    required_amount: Mapped[Optional[float]] = mapped_column(Float)
    available_amount: Mapped[Optional[float]] = mapped_column(Float)
    utilization_rate: Mapped[Optional[float]] = mapped_column(Float)
    
    # Description
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Mitigation
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    mitigated_by: Mapped[Optional[str]] = mapped_column(String(64))
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    mitigation_cost_estimate: Mapped[Optional[float]] = mapped_column(Float)
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(50), default="derived")
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# ECONOMIC COST VARIANCE — Plan vs Commit vs Actual tracking
# =============================================================================

class EconomicCostVariance(Base, TimestampMixin):
    """
    Canonical Economic Cost Variance — tracks plan vs commit vs actual across domains.
    
    Maintains the critical epistemic distinction:
    Plan ≠ Demand ≠ Authorization ≠ Commitment ≠ Procurement ≠ Execution ≠ Actual ≠ Outcome
    """
    
    __tablename__ = "economic_cost_variances"
    __table_args__ = (
        Index("ix_ecv_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ecv_org_period", "organization_id", "period_start", "period_end"),
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id", "period_start", "period_end", "variance_category",
            name="uq_ecv_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Entity
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # project|commitment|procurement|vendor|budget|resource|objective
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Period
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Variance category
    variance_category: Mapped[str] = mapped_column(String(30), nullable=False)  # COST_VARIANCE_CATEGORIES
    
    # Plan / Demand
    planned_amount: Mapped[Optional[float]] = mapped_column(Float)
    demanded_amount: Mapped[Optional[float]] = mapped_column(Float)
    
    # Authorization / Commitment
    authorized_amount: Mapped[Optional[float]] = mapped_column(Float)
    committed_amount: Mapped[Optional[float]] = mapped_column(Float)
    
    # Procurement / Execution
    procured_amount: Mapped[Optional[float]] = mapped_column(Float)
    executed_amount: Mapped[Optional[float]] = mapped_column(Float)
    
    # Actual / Outcome
    actual_amount: Mapped[Optional[float]] = mapped_column(Float)
    outcome_value: Mapped[Optional[float]] = mapped_column(Float)
    
    # Variance
    plan_vs_committed_variance: Mapped[Optional[float]] = mapped_column(Float)
    committed_vs_actual_variance: Mapped[Optional[float]] = mapped_column(Float)
    plan_vs_actual_variance: Mapped[Optional[float]] = mapped_column(Float)
    variance_percentage: Mapped[Optional[float]] = mapped_column(Float)
    
    # Context
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    variance_explanation: Mapped[Optional[str]] = mapped_column(Text)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ECONOMIC STATE TRANSITION — Track economic state changes
# =============================================================================

class EconomicStateTransition(Base, TimestampMixin):
    """
    Canonical Economic State Transition — tracks transitions between economic states.
    
    Maintains the temporal truth of economic state changes:
    Plan → Demand → Authorization → Commitment → Procurement → Allocation → Execution → Actual → Outcome
    """
    
    __tablename__ = "economic_state_transitions"
    __table_args__ = (
        Index("ix_est_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_est_org_time", "organization_id", "transitioned_at"),
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id", "from_state", "to_state", "source_event_id",
            name="uq_est_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(300))
    
    from_state: Mapped[str] = mapped_column(String(30), nullable=False)  # ECONOMIC_STATES
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    
    # Context
    transition_reason: Mapped[Optional[str]] = mapped_column(Text)
    transition_context_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    financial_impact: Mapped[Optional[float]] = mapped_column(Float)
    
    # Actor
    triggered_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Timing
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# ECONOMIC PREDICTION CONTEXT — Prediction integration context
# =============================================================================

class EconomicPredictionContext(Base, TimestampMixin):
    """
    Canonical Economic Prediction Context — provides economic context for predictions.
    
    Reuses Gate 10 predictive_intelligence_service. Does NOT create a new prediction engine.
    """
    
    __tablename__ = "economic_prediction_contexts"
    __table_args__ = (
        Index("ix_epc_org_kind", "organization_id", "prediction_kind"),
        Index("ix_epc_org_entity", "organization_id", "entity_type", "entity_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    prediction_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # budget_pressure|financial_exposure|resource_cost_pressure|procurement_cost_risk|vendor_cost_risk
    # capacity_financial_mismatch|project_financial_risk|commitment_financial_risk|resource_outcome_risk
    
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Prediction input features
    features_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Prediction result
    predicted_value: Mapped[Optional[float]] = mapped_column(Float)
    predicted_range_min: Mapped[Optional[float]] = mapped_column(Float)
    predicted_range_max: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    
    # Evidence
    evidence_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    supporting_data_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Metadata
    model_version: Mapped[Optional[str]] = mapped_column(String(50))
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# ECONOMIC COUNTERFACTUAL CONTEXT — Counterfactual integration
# =============================================================================

class EconomicCounterfactualContext(Base, TimestampMixin):
    """
    Canonical Economic Counterfactual Context — economic context for counterfactual scenarios.
    
    Reuses Gate 11 counterfactual_intelligence_service. Does NOT create a new scenario engine.
    """
    
    __tablename__ = "economic_counterfactual_contexts"
    __table_args__ = (
        Index("ix_ecc_org_scenario", "organization_id", "scenario_id"),
        Index("ix_ec_org_entity", "organization_id", "entity_type", "entity_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_name: Mapped[str] = mapped_column(String(300), nullable=False)
    
    # Scenario parameters
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # budget_reduction|budget_increase|hire_vs_outsource|outsource_vs_internalize|vendor_replacement
    # procurement_delay|procurement_acceleration|resource_reallocation|capacity_increase|capacity_decrease
    
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Projected impacts
    projected_budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_capacity_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Affected entities
    affected_project_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_commitment_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_customer_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_objective_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_vendor_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Confidence & metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "EconomicOperatingSlice",
    "EconomicImpactAnalysis",
    "EconomicBottleneck",
    "EconomicCostVariance",
    "EconomicStateTransition",
    "EconomicPredictionContext",
    "EconomicCounterfactualContext",
    "ECONOMIC_STATES",
    "BOTTLENECK_TYPES",
    "COST_VARIANCE_CATEGORIES",
]