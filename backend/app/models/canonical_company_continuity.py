"""Gate 30 — Canonical Company Continuity & Universal Company Context Models.

This module implements the canonical company continuity layer that composes
all existing VCOS capabilities into ONE universal virtual company operating system.

The canonical loop:
PAST
  → PRESENT
  → FUTURE (predictions, scenarios, digital twin)
  → OBSERVED FUTURE (actual outcomes)
  → LEARNING (verification, assessment, institutional memory)
  → UPDATED FUTURE CONTEXT (calibrated predictions, improved scenarios)

All components operate over the SAME canonical company reality.
No parallel graphs, databases, or truth systems are created.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLEnum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid
from app.core.timeutils import utcnow


# =============================================================================
# VOCABULARIES
# =============================================================================

# Company operating loop phases
COMPANY_LOOP_PHASES = (
    "identity",        # Who is in the company
    "organization",    # What is the company (structure)
    "intent",          # What does it want
    "objectives",      # What are its objectives
    "strategy",        # What has it decided (strategy)
    "decisions",       # What decisions exist
    "authorization",   # What is authorized
    "commitments",     # What commitments exist
    "responsibilities", # Who is responsible
    "people",          # People & capacity
    "capacity",        # Available capacity
    "actions",         # What actions are being done
    "work",            # Work execution
    "execution",       # Execution state
    "outcomes",        # What happened
    "evidence",        # What evidence exists
    "verification",    # Was it verified
    "assessment",      # Assessment of outcomes
    "learning",        # What was learned
    "institutional_memory", # What does the company know
    "prediction",      # What does it expect
    "counterfactual",  # What could happen
    "digital_twin",    # What should be considered
    "optimization",    # What is governed to happen
    "governed_autonomy", # What actually happens next
    "execution_next",  # Next execution cycle
    "outcome_next",    # Next outcome cycle
)

# Canonical state dimensions (from Gate 29)
COMPANY_STATE_DIMENSIONS = (
    "organization",
    "people",
    "roles",
    "responsibilities",
    "capacity",
    "work",
    "projects",
    "customers",
    "commercial",
    "financial",
    "resources",
    "procurement",
    "processes",
    "knowledge",
    "decisions",
    "commitments",
    "actions",
    "outcomes",
    "predictions",
    "counterfactuals",
    "digital_twin",
    "institutional_memory",
    "integrations",
    "security",
    "governance",
)

# Operating continuity event types
CONTINUITY_EVENT_TYPES = (
    "state_transition",       # Company state changed
    "decision_made",          # Governed decision recorded
    "authorization_granted",  # Authorization created
    "commitment_created",     # Commitment established
    "responsibility_assigned", # Responsibility assigned
    "action_proposed",        # Action proposed
    "action_approved",        # Action approved
    "action_started",         # Action execution started
    "action_completed",       # Action completed
    "outcome_recorded",       # Outcome observed
    "evidence_submitted",     # Evidence provided
    "verification_completed", # Verification done
    "assessment_done",        # Assessment completed
    "learning_extracted",     # Learning captured
    "memory_recorded",        # Institutional memory entry
    "prediction_made",        # Prediction created
    "calibration_done",       # Prediction calibrated
    "scenario_evaluated",     # Counterfactual evaluated
    "twin_synced",            # Digital twin synchronized
    "optimization_run",       # Optimization completed
    "autonomy_proposed",      # Autonomous operation proposed
    "autonomy_authorized",    # Autonomous operation authorized
    "autonomy_executed",      # Autonomous operation executed
    "autonomy_verified",      # Autonomous outcome verified
    "contradiction_surfaced", # Cross-domain contradiction found
    "health_check",           # Operating health assessed
)

# Epistemic states (critical for preserving boundaries)
EPISTEMIC_STATES = (
    "observed",           # Directly measured/observed
    "measured",           # Instrument-measured
    "evidence_backed",    # Supported by explicit evidence
    "inferred",           # Derived from evidence
    "predicted",          # Model prediction
    "proposed",           # Proposed but not decided
    "contested",          # Under dispute
    "simulated",          # Digital twin scenario
    "counterfactual",     # What-if analysis
    "hypothetical",       # Theoretical
)

# Company operating health states
OPERATING_HEALTH_STATES = (
    "healthy",
    "concerned",
    "at_risk",
    "critical",
    "unknown",
)

# Cross-domain consistency check types
CONSISTENCY_CHECK_TYPES = (
    "commitment_without_responsibility",
    "responsibility_without_person",
    "action_without_authorization",
    "execution_without_action",
    "outcome_without_execution",
    "verified_without_evidence",
    "prediction_marked_observed",
    "scenario_marked_actual",
    "autonomy_without_eligibility",
    "financial_exceeds_constraint",
    "external_without_provenance",
    "commitment_exceeds_capacity",
    "decision_without_evidence",
    "learning_without_outcome",
    "memory_without_provenance",
)


# Self-compounding loop phases (used by SelfCompoundingLoopState)
LOOP_PHASES = (
    "reality",
    "understanding",
    "intelligence",
    "prediction",
    "counterfactual",
    "digital_twin",
    "optimization",
    "decision",
    "governance",
    "autonomy",
    "execution",
    "outcome",
    "verification",
    "learning",
    "institutional_memory",
    "calibration",
    "improved_future_context",
)


# =============================================================================
# SHARED ENUM INSTANCES — Avoid duplicate CREATE TYPE attempts
# schema="public" ensures enums are created in the public schema
# =============================================================================

COMPANY_LOOP_PHASE_ENUM = PGEnum(
    *COMPANY_LOOP_PHASES,
    name="company_loop_phase",
    schema="public",
    create_type=True,
)

OPERATING_HEALTH_STATE_ENUM = PGEnum(
    *OPERATING_HEALTH_STATES,
    name="operating_health_state",
    schema="public",
    create_type=True,
)

CONTINUITY_EVENT_TYPE_ENUM = PGEnum(
    *CONTINUITY_EVENT_TYPES,
    name="continuity_event_type",
    schema="public",
    create_type=True,
)

EPISTEMIC_STATE_ENUM = PGEnum(
    *EPISTEMIC_STATES,
    name="epistemic_state",
    schema="public",
    create_type=True,
)

COMPANY_STATE_DIMENSION_G30_ENUM = PGEnum(
    *COMPANY_STATE_DIMENSIONS,
    name="company_state_dimension_g30",
    schema="public",
    create_type=True,
)

CONSISTENCY_CHECK_TYPE_ENUM = PGEnum(
    *CONSISTENCY_CHECK_TYPES,
    name="consistency_check_type",
    schema="public",
    create_type=True,
)

COMPOUNDING_LOOP_PHASE_ENUM = PGEnum(
    *LOOP_PHASES,
    name="compounding_loop_phase",
    schema="public",
    create_type=True,
)


# =============================================================================
# COMPANY OPERATING CONTINUITY
# =============================================================================

class CompanyOperatingContinuity(Base, TimestampMixin):
    """
    The canonical company operating continuity record.
    
    Tracks the complete loop: Identity → Intent → Decision → Execution → Outcome → Learning.
    Every cycle through the loop creates a new continuity record with temporal provenance.
    """
    
    __tablename__ = "company_operating_continuity"
    __table_args__ = (
        Index("ix_coc_org_cycle", "organization_id", "cycle_number"),
        Index("ix_coc_org_phase", "organization_id", "current_phase"),
        Index("ix_coc_org_time", "organization_id", "cycle_started_at"),
        UniqueConstraint("organization_id", "cycle_number", name="uq_coc_cycle"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Cycle identification
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cycle_label: Mapped[Optional[str]] = mapped_column(String(120))
    
    # Current phase in the operating loop
    current_phase: Mapped[str] = mapped_column(
        COMPANY_LOOP_PHASE_ENUM,
        default="identity", nullable=False, index=True
    )
    
    # Temporal boundaries
    cycle_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    cycle_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phase_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    
    # State snapshots (composed from canonical sources)
    identity_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Who is in company
    organization_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Structure
    intent_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # What company wants
    objectives_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Objectives
    strategy_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Strategy/decisions
    authorization_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # What's authorized
    commitment_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Commitments
    responsibility_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Responsibilities
    capacity_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # People/capacity
    work_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Work in progress
    execution_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Execution
    outcome_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Outcomes
    learning_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Learning
    prediction_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Predictions
    twin_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Digital twin
    autonomy_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Autonomous ops
    
    # Epistemic integrity
    epistemic_summary_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Counts by epistemic state
    
    # Health assessment
    operating_health: Mapped[str] = mapped_column(
        OPERATING_HEALTH_STATE_ENUM,
        default=lambda: "unknown", index=True, nullable=False,
        server_default="unknown"
    )
    health_details_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    
    # Contradictions surfaced in this cycle
    contradictions_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Learning accumulation
    lessons_learned: Mapped[int] = mapped_column(Integer, default=0)
    patterns_updated: Mapped[int] = mapped_column(Integer, default=0)
    calibration_improvements: Mapped[int] = mapped_column(Integer, default=0)
    
    # Provenance
    source_events_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class CompanyContinuityEvent(Base, TimestampMixin):
    """
    Individual event in the company operating continuity.
    
    Each event represents one step in the canonical loop with full provenance.
    """
    
    __tablename__ = "company_continuity_events"
    __table_args__ = (
        Index("ix_cce_org_time", "organization_id", "occurred_at"),
        Index("ix_cce_org_type", "organization_id", "event_type"),
        Index("ix_cce_org_phase", "organization_id", "loop_phase"),
        Index("ix_cce_org_cycle", "organization_id", "continuity_cycle_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    continuity_cycle_id: Mapped[str] = mapped_column(
        ForeignKey("company_operating_continuity.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Event classification
    event_type: Mapped[str] = mapped_column(
        CONTINUITY_EVENT_TYPE_ENUM,
        nullable=False, index=True
    )
    loop_phase: Mapped[str] = mapped_column(
        COMPANY_LOOP_PHASE_ENUM,
        nullable=False, index=True
    )
    
    # Temporal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    sequence_in_phase: Mapped[int] = mapped_column(Integer, default=0)
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="human")  # human | agent | system
    
    # What happened
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    details_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    
    # Entity references (the canonical entities involved)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Cross-domain links
    related_entities_json: Mapped[Optional[Dict]] = mapped_column(JSON, default=dict)
    
    # Provenance & Epistemic state
    epistemic_state: Mapped[str] = mapped_column(
        EPISTEMIC_STATE_ENUM,
        default="observed", nullable=False, index=True
    )
    evidence_fingerprints: Mapped[List[str]] = mapped_column(JSON, default=list)
    source_event_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Governance
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Fingerprint for exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class CompanyStateSnapshotGate30(Base, TimestampMixin):
    """
    Gate 30 company state snapshot - composed from all canonical domains.
    
    This is the authoritative projection of canonical reality at a point in time.
    Derived from all canonical sources (decisions, commitments, actions, outcomes, etc.).
    """
    
    __tablename__ = "company_state_snapshots_g30"
    __table_args__ = (
        Index("ix_css30_org_time", "organization_id", "captured_at"),
        Index("ix_css30_org_dim", "organization_id", "dimension"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(
        COMPANY_STATE_DIMENSION_G30_ENUM,
        nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # State content (dimension-specific JSON)
    state_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Provenance
    source_events_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Epistemic composition
    epistemic_composition_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # % by epistemic state


# =============================================================================
# UNIVERSAL COMPANY CONTEXT
# =============================================================================

class UniversalCompanyContext(Base, TimestampMixin):
    """
    The universal governed company context for a caller.
    
    Composes the appropriate view of company reality based on:
    - Who (identity, role, permissions)
    - What organization
    - What scope
    - Current company state
    - Relevant historical state
    - Active objectives
    - Decisions & commitments
    - Responsibilities
    - Work & capacity
    - Customers & resources
    - Financial constraints
    - Processes & knowledge
    - Predictions & scenarios
    - Digital twin state
    - Autonomous operations
    - Risks & attention
    - Institutional learning
    """
    
    __tablename__ = "universal_company_contexts"
    __table_args__ = (
        Index("ix_ucc_org_caller", "organization_id", "caller_user_id"),
        Index("ix_ucc_org_scope", "organization_id", "scope_type", "scope_id"),
        UniqueConstraint("organization_id", "caller_user_id", "context_version", name="uq_ucc_caller_version"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    caller_user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    
    # Governance scope
    org_wide: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_type: Mapped[Optional[str]] = mapped_column(String(20))  # org | department | team | project | person
    scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Context content (governed, bounded)
    identity_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Who
    organization_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Structure
    intent_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Intent
    objectives_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Objectives
    decisions_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Decisions
    authorization_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Authorizations
    commitments_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Commitments
    responsibilities_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Responsibilities
    people_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # People
    capacity_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Capacity
    work_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Work
    projects_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Projects
    customers_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Customers
    commercial_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Commercial
    financial_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Financial
    resources_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Resources
    procurement_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Procurement
    processes_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Processes
    knowledge_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Knowledge
    predictions_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Predictions
    counterfactuals_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Counterfactuals
    digital_twin_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Digital twin
    autonomy_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Autonomous ops
    risks_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Risks
    attention_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Attention
    learning_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Learning
    institutional_memory_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Institutional memory
    
    # Meta
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    context_version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Epistemic breakdown
    epistemic_breakdown_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Count by epistemic state
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


# =============================================================================
# CROSS-DOMAIN CONSISTENCY
# =============================================================================

class CrossDomainConsistencyCheck(Base, TimestampMixin):
    """
    Deterministic consistency checks across company domains.
    
    These are integrity checks, not AI judgments. Surface contradictions
    instead of hiding them.
    """
    
    __tablename__ = "cross_domain_consistency_checks"
    __table_args__ = (
        Index("ix_cdcc_org_type", "organization_id", "check_type"),
        Index("ix_cdcc_org_status", "organization_id", "status"),
        Index("ix_cdcc_org_time", "organization_id", "checked_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    check_type: Mapped[str] = mapped_column(
        CONSISTENCY_CHECK_TYPE_ENUM,
        nullable=False, index=True
    )
    
    # What was checked
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    check_scope_json: Mapped[Optional[Dict]] = mapped_column(JSON)  # Which entities/domains
    
    # Results
    status: Mapped[str] = mapped_column(
        String(20), default="passing", index=True
    )  # passing | warning | contradiction | blocked
    
    # Contradiction details
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    contradictions_json: Mapped[Optional[List[Dict]]] = mapped_column(JSON)
    
    # Affected entities
    affected_entities_json: Mapped[Optional[List[Dict]]] = mapped_column(JSON)
    
    # Resolution
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(64))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


# =============================================================================
# COMPANY OPERATING HEALTH
# =============================================================================

class CompanyOperatingHealth(Base, TimestampMixin):
    """
    Governed projection of operating integrity.
    
    Uses existing Gate 23 intelligence infrastructure.
    Provides operating integrity without creating company scores or ranking employees.
    """
    
    __tablename__ = "company_operating_health"
    __table_args__ = (
        Index("ix_coh_org_time", "organization_id", "assessed_at"),
        Index("ix_coh_org_state", "organization_id", "overall_state"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Overall assessment
    overall_state: Mapped[str] = mapped_column(
        OPERATING_HEALTH_STATE_ENUM,
        default="unknown", index=True
    )
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    
    # Domain health (from Gate 23)
    domain_health_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    
    # Integrity indicators (counts, not scores)
    unresolved_contradictions: Mapped[int] = mapped_column(Integer, default=0)
    missing_responsibility: Mapped[int] = mapped_column(Integer, default=0)
    stale_state_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    unknown_outcomes: Mapped[int] = mapped_column(Integer, default=0)
    prediction_divergence_count: Mapped[int] = mapped_column(Integer, default=0)
    twin_divergence_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_operations: Mapped[int] = mapped_column(Integer, default=0)
    governance_issues: Mapped[int] = mapped_column(Integer, default=0)
    integration_failures: Mapped[int] = mapped_column(Integer, default=0)
    learning_gaps: Mapped[int] = mapped_column(Integer, default=0)
    
    # Details
    details_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    
    # Fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


# =============================================================================
# UNIVERSAL COMPANY TIMELINE
# =============================================================================

class UniversalCompanyTimeline(Base, TimestampMixin):
    """
    Canonical company timeline projection.
    
    Allows authorized users to see relevant chronological continuity:
    Decision → Authorization → Commitment → Responsibility → Action → Execution → Outcome → Verification → Learning
    
    And:
    Company Change → Observation → State Change → Twin Change → Prediction Change → Attention
    
    Reuses existing event infrastructure, composes timeline from canonical sources.
    """
    
    __tablename__ = "universal_company_timeline"
    __table_args__ = (
        Index("ix_uct_org_time", "organization_id", "occurred_at"),
        Index("ix_uct_org_type", "organization_id", "event_type"),
        Index("ix_uct_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_uct_org_phase", "organization_id", "loop_phase"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Event classification
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    loop_phase: Mapped[str] = mapped_column(
        COMPANY_LOOP_PHASE_ENUM,
        nullable=False, index=True
    )
    
    # Temporal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    
    # Content
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Entity references
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="human")
    
    # Governance scope
    scope_type: Mapped[Optional[str]] = mapped_column(String(20))
    scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Cross-references
    related_events_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    continuity_cycle_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Epistemic state
    epistemic_state: Mapped[str] = mapped_column(
        EPISTEMIC_STATE_ENUM,
        default="observed", nullable=False
    )
    evidence_fingerprints: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Governance
    visible_to_org_wide: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_scope_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


# =============================================================================
# COMPANY SELF-COMPOUNDING LOOP
# =============================================================================

class SelfCompoundingLoopState(Base, TimestampMixin):
    """
    Tracks the self-compounding loop state.
    
    REALITY
    → UNDERSTANDING (company context, brain)
    → INTELLIGENCE (patterns, insights, predictions)
    → PREDICTION (predictive intelligence)
    → COUNTERFACTUAL (what-if scenarios)
    → DIGITAL TWIN (future state projection)
    → OPTIMIZATION (constrained optimization)
    → DECISION (governed decisions)
    → GOVERNANCE (authorization)
    → AUTONOMY (governed autonomous execution)
    → EXECUTION (actual operation)
    → OUTCOME (observed results)
    → VERIFICATION (evidence-backed confirmation)
    → LEARNING (institutional memory)
    → INSTITUTIONAL MEMORY (durable lessons)
    → CALIBRATION (prediction accuracy improvement)
    → IMPROVED FUTURE CONTEXT
    → REALITY
    """
    
    __tablename__ = "self_compounding_loop_states"
    __table_args__ = (
        Index("ix_scls_org_cycle", "organization_id", "cycle_number"),
        Index("ix_scls_org_phase", "organization_id", "current_phase"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    current_phase: Mapped[str] = mapped_column(
        COMPOUNDING_LOOP_PHASE_ENUM,
        default="reality", nullable=False, index=True
    )
    
    # Phase state snapshots
    reality_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    understanding_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    intelligence_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    prediction_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    counterfactual_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    digital_twin_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    optimization_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    decision_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    governance_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    autonomy_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    execution_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    outcome_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    verification_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    learning_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    memory_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    calibration_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    future_context_state_json: Mapped[Optional[Dict]] = mapped_column(JSON)
    
    # Metrics
    loop_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    phases_completed: Mapped[int] = mapped_column(Integer, default=lambda: 0, nullable=False, server_default="0")
    calibration_delta: Mapped[float] = mapped_column(Float, default=0.0)
    learning_accumulated: Mapped[int] = mapped_column(Integer, default=0)
    
    # Temporal
    cycle_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    cycle_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phase_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    
    # Fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Vocabularies
    "COMPANY_LOOP_PHASES",
    "COMPANY_STATE_DIMENSIONS",
    "CONTINUITY_EVENT_TYPES",
    "EPISTEMIC_STATES",
    "OPERATING_HEALTH_STATES",
    "CONSISTENCY_CHECK_TYPES",
    "LOOP_PHASES",
    
    # Models
    "CompanyOperatingContinuity",
    "CompanyContinuityEvent",
    "CompanyStateSnapshotGate30",
    "UniversalCompanyContext",
    "CrossDomainConsistencyCheck",
    "CompanyOperatingHealth",
    "UniversalCompanyTimeline",
    "SelfCompoundingLoopState",
    
    # Shared enums
    "COMPANY_LOOP_PHASE_ENUM",
    "OPERATING_HEALTH_STATE_ENUM",
    "CONTINUITY_EVENT_TYPE_ENUM",
    "EPISTEMIC_STATE_ENUM",
    "COMPANY_STATE_DIMENSION_G30_ENUM",
    "CONSISTENCY_CHECK_TYPE_ENUM",
    "COMPOUNDING_LOOP_PHASE_ENUM",
]