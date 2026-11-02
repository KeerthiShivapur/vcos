"""Canonical Enterprise Operations & Business Process Fabric — Gate 19.

Establishes the canonical business process operating fabric that represents
how the company actually operates — processes, ownership, execution,
dependencies, and outcomes — all derived from canonical primitives.

This is a DERIVED PROJECTION layer — it does NOT create a second process/operations graph.
All data is composed from existing canonical primitives:
- Gates 8-14: People, Work, Communication, Meetings, Organizational Intelligence, Capacity
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 18: Economic Intelligence

All models follow canonical invariants:
- Tenant isolation
- Governance-first
- Temporal truth (valid_from/valid_to, supersession)
- Provenance chains
- Exact-once semantics
- Epistemic boundaries (Prediction ≠ Truth ≠ Recommendation ≠ Decision ≠ Authorization ≠ Execution)
- No parallel process/operations/operations graphs
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

# Process lifecycle states — universal, not industry-specific
PROCESS_LIFECYCLE_STATES = (
    "defined",          # Process defined, not yet ready
    "ready",            # Ready to be triggered
    "triggered",        # Trigger received, initializing
    "in_progress",      # Actively executing
    "blocked",          # Blocked by dependency/condition
    "waiting",          # Waiting for external event/person
    "completed",        # Successfully completed
    "verified",         # Verified/accepted
    "superseded",       # Superseded by new version
    "archived",         # Archived, no longer active
)

# Process types — universal categories
PROCESS_TYPES = (
    "operational",      # Day-to-day operations
    "project_based",    # Project-specific processes
    "customer_facing",  # Customer-facing processes
    "internal",         # Internal processes
    "compliance",       # Compliance/governance processes
    "emergency",        # Emergency/incident processes
    "strategic",        # Strategic initiatives
)

# Process trigger types
PROCESS_TRIGGERS = (
    "manual",           # Manually triggered
    "event",            # Event-driven
    "schedule",         # Scheduled/recurring
    "webhook",          # External webhook
    "condition",        # Condition-based
    "approval",         # Approval-gated
    "threshold",        # Threshold-based
    "manual_override",  # Manual override
)

# Process priority
PROCESS_PRIORITIES = (
    "critical",         # Critical priority
    "high",             # High priority
    "medium",           # Medium priority
    "low",              # Low priority
)

# Process severity (for bottlenecks/issues)
PROCESS_SEVERITY = (
    "info",             # Informational
    "warning",          # Warning
    "critical",         # Critical
)

# Process ownership roles
PROCESS_ROLES = (
    "owner",            # Process owner
    "accountable",      # Accountable authority
    "participant",      # Participant
    "reviewer",         # Reviewer/approver
    "executor",         # Executor/performer
    "stakeholder",      # Stakeholder
)


# =============================================================================
# CANONICAL BUSINESS PROCESS — Universal process reality
# =============================================================================

class CanonicalBusinessProcess(Base, TimestampMixin):
    """
    Canonical Business Process — a governed, governed business process.
    
    This is the SINGLE canonical process model. It subsumes and replaces any
    parallel process representations. All process types are represented here.
    
    Connects:
    - Strategic Intent → Process → Execution → Outcome
    - Objectives/Initiatives/Projects → Process → Work → Results
    - People → Responsibilities → Process → Work → Results
    - Resources/Assets → Process → Allocation → Utilization
    - Customers/Commitments → Process → Delivery → Outcome
    - Procurement/Vendors → Process → External Capacity → Resource
    """
    
    __tablename__ = "canonical_business_processes"
    __table_args__ = (
        Index("ix_cbp_org_type", "organization_id", "process_type"),
        Index("ix_cbp_org_state", "organization_id", "lifecycle_state"),
        Index("ix_cbp_org_owner", "organization_id", "owner_id"),
        Index("ix_cbp_org_scope", "organization_id", "scope_type", "scope_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cbp_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    process_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # PROCESS_TYPES
    category: Mapped[Optional[str]] = mapped_column(String(100))  # e.g., "sales", "hr", "finance"
    subcategory: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Lifecycle
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="defined", index=True)  # PROCESS_LIFECYCLE_STATES
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    state_change_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")  # PROCESS_TRIGGERS
    trigger_config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    trigger_condition: Mapped[Optional[str]] = mapped_column(Text)
    
    # Inputs/Outputs
    inputs_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    outputs_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    actual_outcome: Mapped[Optional[str]] = mapped_column(Text)
    
    # Ownership & Governance
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Person/Employee
    owner_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|team|department|role
    accountable_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Accountable authority
    accountable_type: Mapped[Optional[str]] = mapped_column(String(30))
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Scope (for multi-scope processes)
    scope_type: Mapped[Optional[str]] = mapped_column(String(30))  # organization|department|team|project|customer
    scope_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Participants
    participants_json: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    # e.g., [{"role": "owner", "person_id": "..."}, {"role": "executor", "person_id": "..."}]
    
    # Required capabilities/resources
    required_capabilities_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    required_resources_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    required_capabilities_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Dependencies
    depends_on_process_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    blocks_process_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Strategic alignment
    objective_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    initiative_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Priority
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)  # PROCESS_PRIORITIES
    
    # Time tracking
    estimated_duration_hours: Mapped[Optional[float]] = mapped_column(Float)
    actual_duration_hours: Mapped[Optional[float]] = mapped_column(Float)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Verification
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Supersession
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Learning integration
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def is_active(self) -> bool:
        return self.lifecycle_state in ("triggered", "in_progress", "waiting", "blocked")
    
    @property
    def is_terminal(self) -> bool:
        return self.lifecycle_state in ("completed", "verified", "superseded", "archived")


# =============================================================================
# PROCESS EXECUTION — Actual execution instance
# =============================================================================

class ProcessExecution(Base, TimestampMixin):
    """
    Canonical Process Execution — an actual execution instance of a process.
    
    Each execution is a governed instance of a canonical process.
    Connects: Process → Execution → Work/Actions → Outcome
    """
    
    __tablename__ = "process_executions"
    __table_args__ = (
        Index("ix_pe_org_process", "organization_id", "process_id"),
        Index("ix_pe_org_state", "organization_id", "state"),
        Index("ix_pe_org_owner", "organization_id", "owner_id"),
        Index("ix_pe_org_time", "organization_id", "started_at"),
        UniqueConstraint(
            "organization_id", "process_id", "execution_number",
            name="ux_pe_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Reference to canonical process
    process_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Execution identity
    execution_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    
    # Execution state
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="initializing")  # initializing|running|paused|waiting|blocked|completed|failed|cancelled
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(30))  # manual|event|schedule|webhook|condition
    trigger_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    trigger_payload_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Inputs/Context
    inputs_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    context_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Execution tracking
    current_step_key: Mapped[Optional[str]] = mapped_column(String(64))
    step_history_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Owner/Participants
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Person responsible for this execution
    participants_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Resources allocated
    allocated_resources_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    allocated_capacity_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Duration tracking
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    active_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    waiting_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Outputs
    outputs_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    actual_outcome: Mapped[Optional[str]] = mapped_column(Text)
    outcome_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Error/Failure
    error: Mapped[Optional[str]] = mapped_column(Text)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS STEP — Individual step within execution
# =============================================================================

class ProcessStep(Base, TimestampMixin):
    """
    Canonical Process Step — an individual step within a process execution.
    
    Represents one node/step in the process execution graph.
    """
    
    __tablename__ = "process_steps"
    __table_args__ = (
        Index("ix_ps_exec_step", "execution_id", "step_key"),
        UniqueConstraint(
            "execution_id", "step_key",
            name="ux_ps_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("process_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Step identity
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_name: Mapped[str] = mapped_column(String(300))
    step_type: Mapped[str] = mapped_column(String(30), nullable=False)  # approval|task|meeting|notification|delay|ai_decision|integration|webhook|parallel|script|condition|approval|approval_chain|manual
    step_config_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # State
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending|running|succeeded|failed|skipped|waiting_approval|waiting_delay|blocked
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Input/Output
    input_data_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    output_data_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    expected_output_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Assignment
    assignee_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    assignee_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|role|team|department
    role_in_step: Mapped[Optional[str]] = mapped_column(String(50))  # approver|executor|reviewer|observer
    
    # Dependencies
    depends_on_step_keys_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    blocks_step_keys_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    estimated_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    actual_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Duration tracking
    waiting_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    active_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Output
    output_data_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    actual_output_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Error handling
    error: Mapped[Optional[str]] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Approval specific
    approval_status: Mapped[Optional[str]] = mapped_column(String(30))  # pending|approved|rejected|escalated
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_id: Mapped[Optional[str]] = mapped_column(String(64))
    approval_decided_by: Mapped[Optional[str]] = mapped_column(String(64))
    approval_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Error handling
    error: Mapped[Optional[str]] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS APPROVAL — Governed approval within process
# =============================================================================

class ProcessApproval(Base, TimestampMixin):
    """
    Canonical Process Approval — a governed approval within a process execution.
    
    Extends existing Approval/WorkflowApproval with process-specific context.
    """
    
    __tablename__ = "process_approvals"
    __table_args__ = (
        Index("ix_pa_org_exec", "organization_id", "execution_id"),
        Index("ix_pa_org_step", "organization_id", "step_id"),
        Index("ix_pa_org_state", "organization_id", "status"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_pa_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("process_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_steps.id", ondelete="CASCADE"), index=True
    )
    
    # Approval identity
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Approval type
    approval_type: Mapped[str] = mapped_column(String(30), default="sequential")  # sequential|parallel|consensus|single|conditional
    
    # Approvers
    approver_type: Mapped[str] = mapped_column(String(30), default="user")  # user|role|manager|group|system
    required_approvers_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)  # [{"type": "user", "id": "..."}]
    minimum_approvals: Mapped[int] = mapped_column(Integer, default=1)
    
    # State
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|escalated|cancelled|skipped
    previous_status: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Decisions
    decisions_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)  # [{"approver_id": "...", "decision": "approved|rejected", "at": "...", "note": "..."}]
    approval_count: Mapped[int] = mapped_column(Integer, default=0)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Decision
    decided_by: Mapped[Optional[str]] = mapped_column(String(64))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Escalation
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    escalated_to_id: Mapped[Optional[str]] = mapped_column(String(64))
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timing
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Escalation
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    escalation_path_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    max_escalation_level: Mapped[int] = mapped_column(Integer, default=3)
    
    # Governance
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Context
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    requested_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS BOTTLENECK — Derived bottleneck intelligence
# =============================================================================

class ProcessBottleneck(Base, TimestampMixin):
    """
    Canonical Process Bottleneck — derived intelligence about process constraints.
    
    These are DERIVED projections, NOT canonical truths. They feed the existing
    Operating Attention architecture (Gate 13). Do NOT create a parallel attention system.
    
    Types:
    - approval_bottleneck: Approval taking too long
    - resource_bottleneck: Resource over-allocated/constrained
    - dependency_bottleneck: Dependency blocking progress
    - approval_chain_bottleneck: Approval chain too long/slow
    - handoff_bottleneck: Handoff between people/teams slow
    - resource_capacity: Resource capacity exceeded
    - vendor_dependency: Vendor delivery delay
    - approval_chain: Approval chain too long
    - capacity_exhausted: Capacity exhausted
    - approval_delay: Approval taking too long
    - dependency_block: Dependency blocking
    - handoff_delay: Handoff delay
    - vendor_delay: Vendor delay
    - capacity_exhaustion: Capacity exhausted
    - repeated_failure: Repeated failures
    - excessive_rework: Excessive rework
    - sla_risk: SLA at risk
    - repeated_failure: Repeated failures
    - excessive_cycle_time: Excessive cycle time
    - handoff_delay: Handoff delay
    """
    
    __tablename__ = "process_bottlenecks"
    __table_args__ = (
        Index("ix_pb_org_type", "organization_id", "bottleneck_type"),
        Index("ix_pb_org_severity", "organization_id", "severity"),
        Index("ix_pb_org_exec", "organization_id", "execution_id"),
        Index("ix_pb_org_step", "organization_id", "step_id"),
        Index("ix_pb_org_status", "organization_id", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    bottleneck_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")  # info|warning|critical
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|mitigating|resolved
    
    # Primary execution/step
    execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_executions.id", ondelete="SET NULL"), index=True
    )
    step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_steps.id", ondelete="SET NULL"), index=True
    )
    process_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="SET NULL"), index=True
    )
    
    # Affected entities
    affected_execution_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_step_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_process_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_project_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_commitment_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_customer_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_person_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Description
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Quantitative
    wait_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    throughput_per_day: Mapped[Optional[float]] = mapped_column(Float)
    
    # Mitigation
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    mitigated_by: Mapped[Optional[str]] = mapped_column(String(64))
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(50), default="derived")
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# PROCESS OPERATING SLICE — Derived projection for process context
# =============================================================================

class ProcessOperatingSlice(Base, TimestampMixin):
    """
    Canonical Process Operating Slice — governed, point-in-time derived
    projection of all company process/operations reality.
    
    This is a VIEW/PROJECTION, not a data store. Materialized for performance.
    """
    
    __tablename__ = "process_operating_slices"
    __table_args__ = (
        Index("ix_pos_org_computed", "organization_id", "computed_at"),
        UniqueConstraint(
            "organization_id", "input_fingerprint",
            name="uq_pos_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Input fingerprint for exact-once
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Process summary
    processes_by_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    processes_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    processes_by_category: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    processes_by_owner: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Execution summary
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    active_executions: Mapped[int] = mapped_column(Integer, default=0)
    completed_executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    executions_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    executions_by_process_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Step summary
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    active_steps: Mapped[int] = mapped_column(Integer, default=0)
    blocked_steps: Mapped[int] = mapped_column(Integer, default=0)
    waiting_approval_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    
    # Approval summary
    pending_approvals: Mapped[int] = mapped_column(Integer, default=0)
    overdue_approvals: Mapped[int] = mapped_column(Integer, default=0)
    approval_by_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Performance
    avg_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    median_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    avg_wait_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    completion_rate: Mapped[Optional[float]] = mapped_column(Float)
    failure_rate: Mapped[Optional[float]] = mapped_column(Float)
    rework_rate: Mapped[Optional[float]] = mapped_column(Float)
    sla_breach_rate: Mapped[Optional[float]] = mapped_column(Float)
    
    # Bottlenecks
    bottleneck_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_bottlenecks: Mapped[int] = mapped_column(Integer, default=0)
    bottlenecks_by_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Financial (Gate 18)
    total_process_cost: Mapped[Optional[float]] = mapped_column(Float)
    avg_cost_per_execution: Mapped[Optional[float]] = mapped_column(Float)
    
    # Customer impact
    customer_impacting_processes: Mapped[int] = mapped_column(Integer, default=0)
    at_risk_customers: Mapped[int] = mapped_column(Integer, default=0)
    
    # Computed metadata
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once fingerprint (on canonical inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# PROCESS IMPACT ANALYSIS — Cross-domain process impact
# =============================================================================

class ProcessImpactAnalysis(Base, TimestampMixin):
    """
    Canonical Process Impact Analysis — derives the cross-domain impact
    of a process change (start, stop, modify, delay, reallocate) on
    executions, projects, commitments, customers, and objectives.
    
    Extends Gate 13/15/18 cross-domain impact with process context.
    """
    
    __tablename__ = "process_impact_analyses"
    __table_args__ = (
        Index("ix_pia_proc_org_trigger", "organization_id", "trigger_type"),
        Index("ix_pia_proc_org_entity", "organization_id", "trigger_entity_type", "trigger_entity_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_pia_proc_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # process_started|process_stopped|process_modified|process_delayed|resource_changed|vendor_changed|capacity_changed|approval_changed
    trigger_entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # process|execution|step|approval|resource|vendor|capacity|approval
    trigger_entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Impact scope
    affected_processes: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_executions: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_steps: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_approvals: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_resources: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_allocations: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_demands: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_projects: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_objectives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_people: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_customers: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_vendors: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_external_capacity: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Quantitative impact
    capacity_impact: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    margin_impact: Mapped[Optional[float]] = mapped_column(Float)
    timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Risk assessment
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    new_bottlenecks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    escalated_bottlenecks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    resolved_bottlenecks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
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
# PROCESS PERFORMANCE — Evidence-based process metrics
# =============================================================================

class ProcessPerformance(Base, TimestampMixin):
    """
    Canonical Process Performance — evidence-based process performance metrics.
    
    Derived from execution history, not a standalone prediction.
    """
    
    __tablename__ = "process_performances"
    __table_args__ = (
        Index("ix_pp_org_period", "organization_id", "period_start", "period_end"),
        Index("ix_pp_org_process", "organization_id", "process_id"),
        UniqueConstraint(
            "organization_id", "process_id", "period_start", "period_end",
            name="uq_pp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    process_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Period
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Execution metrics
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    completed_executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_executions: Mapped[int] = mapped_column(Integer, default=0)
    
    # Cycle time
    avg_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    median_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    p95_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    min_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    max_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    
    # Wait times
    avg_wait_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    avg_approval_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    avg_handoff_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    
    # Quality
    completion_rate: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    failure_rate: Mapped[Optional[float]] = mapped_column(Float)
    rework_rate: Mapped[Optional[float]] = mapped_column(Float)
    first_pass_yield: Mapped[Optional[float]] = mapped_column(Float)
    sla_breach_rate: Mapped[Optional[float]] = mapped_column(Float)
    
    # Throughput
    executions_per_day: Mapped[Optional[float]] = mapped_column(Float)
    peak_executions_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    throughput_trend: Mapped[Optional[str]] = mapped_column(String(20))  # increasing|stable|decreasing
    
    # Resource efficiency
    resource_utilization: Mapped[Optional[float]] = mapped_column(Float)
    avg_resource_cost_per_execution: Mapped[Optional[float]] = mapped_column(Float)
    
    # Quality
    rework_rate: Mapped[Optional[float]] = mapped_column(Float)
    first_pass_yield: Mapped[Optional[float]] = mapped_column(Float)
    defect_rate: Mapped[Optional[float]] = mapped_column(Float)
    customer_satisfaction: Mapped[Optional[float]] = mapped_column(Float)
    
    # SLA
    sla_compliance_rate: Mapped[Optional[float]] = mapped_column(Float)
    sla_breach_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_sla_breach_hours: Mapped[Optional[float]] = mapped_column(Float)
    
    # Evidence
    evidence_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    
    # Computed metadata
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS DEPENDENCY — Process-to-process dependencies
# =============================================================================

class ProcessDependency(Base, TimestampMixin):
    """
    Canonical Process Dependency — dependency between processes.
    
    Represents: Process A depends on Process B (or execution, step, approval)
    """
    
    __tablename__ = "process_dependencies"
    __table_args__ = (
        Index("ix_pd_org_source", "organization_id", "source_process_id"),
        Index("ix_pd_org_target", "organization_id", "target_process_id"),
        Index("ix_pd_org_type", "organization_id", "dependency_type"),
        UniqueConstraint(
            "organization_id", "source_process_id", "target_process_id", "dependency_type",
            name="ux_pd_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Dependency direction: source depends on target
    source_process_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_process_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Or execution/step level
    source_execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_executions.id", ondelete="SET NULL"), index=True
    )
    target_execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_executions.id", ondelete="SET NULL"), index=True
    )
    source_step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_steps.id", ondelete="SET NULL"), index=True
    )
    target_step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_steps.id", ondelete="SET NULL"), index=True
    )
    
    # Dependency type
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # finish_to_start|start_to_start|finish_to_finish|start_to_finish|approval|resource|data|vendor|approval_chain
    dependency_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timing
    lag_hours: Mapped[Optional[float]] = mapped_column(Float)
    lead_hours: Mapped[Optional[float]] = mapped_column(Float)
    
    # Strength
    is_hard: Mapped[bool] = mapped_column(Boolean, default=True)  # hard vs soft dependency
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|satisfied|blocked|broken|waived
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS COUNTERFACTUAL — Process scenario modeling
# =============================================================================

class ProcessScenario(Base, TimestampMixin):
    """
    Canonical Process Scenario — a counterfactual scenario for a process.
    
    Reuses Gate 11 counterfactual intelligence. Does NOT create a new simulation engine.
    """
    
    __tablename__ = "process_scenarios"
    __table_args__ = (
        Index("ix_ps_org_process", "organization_id", "process_id"),
        Index("ix_ps_org_kind", "organization_id", "scenario_kind"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Reference
    process_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="SET NULL"), index=True
    )
    execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_executions.id", ondelete="SET NULL"), index=True
    )
    
    # Scenario identity
    scenario_name: Mapped[str] = mapped_column(String(300), nullable=False)
    scenario_kind: Mapped[str] = mapped_column(String(50), nullable=False)  # remove_approval|add_approval|change_owner|add_resource|remove_resource|reallocate|change_vendor|automate_step|change_sequence|add_approval|remove_approval|change_sequence|add_parallel|remove_parallel|simulate_failure|simulate_delay|simulate_resource_add|simulate_resource_remove
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Changes
    changes_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Structured description of changes
    
    # Projected impacts
    projected_budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_capacity_impact: Mapped[Optional[float]] = mapped_column(Float)
    projected_timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    projected_cycle_time_change_hours: Mapped[Optional[float]] = mapped_column(Float)
    projected_resource_utilization_change: Mapped[Optional[float]] = mapped_column(Float)
    
    # Affected entities
    affected_process_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_execution_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_project_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_commitment_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_objective_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_customer_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_vendor_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_vendor_capability_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_external_capacity_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Risk
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|critical
    risk_factors_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Recommendations
    recommendations_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Confidence & metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# PROCESS KNOWLEDGE — Institutional learning from processes
# =============================================================================

class ProcessKnowledge(Base, TimestampMixin):
    """
    Canonical Process Knowledge — institutional learning from process execution.
    
    Connects process execution → outcome → evidence → verification → pattern → lesson.
    Reuses Gate 9 institutional intelligence.
    """
    
    __tablename__ = "process_knowledge"
    __table_args__ = (
        Index("ix_pk_org_process", "organization_id", "process_id"),
        Index("ix_pk_org_kind", "organization_id", "knowledge_kind"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    process_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_business_processes.id", ondelete="SET NULL"), index=True
    )
    execution_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("process_executions.id", ondelete="SET NULL"), index=True
    )
    
    knowledge_kind: Mapped[str] = mapped_column(String(40), nullable=False)  # pattern|lesson|pattern_variation|anti_pattern|best_practice|failure_mode|success_pattern
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Evidence
    evidence_fingerprints_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    execution_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    outcome_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Pattern details
    pattern_frequency: Mapped[Optional[int]] = mapped_column(Integer)
    pattern_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    pattern_support: Mapped[Optional[int]] = mapped_column(Integer)
    pattern_contradictions: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    
    # Applicability
    applicable_process_types_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    applicable_conditions_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Outcome
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    typical_outcome: Mapped[Optional[str]] = mapped_column(Text)
    outcome_variance: Mapped[Optional[float]] = mapped_column(Float)
    
    # Recommendations
    recommendations_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="hypothesis")  # hypothesis|validated|refuted|archived
    validated_by: Mapped[Optional[str]] = mapped_column(String(64))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "CanonicalBusinessProcess",
    "ProcessExecution",
    "ProcessStep",
    "ProcessApproval",
    "ProcessBottleneck",
    "ProcessOperatingSlice",
    "ProcessImpactAnalysis",
    "ProcessPerformance",
    "ProcessDependency",
    "ProcessScenario",
    "ProcessKnowledge",
    "PROCESS_LIFECYCLE_STATES",
    "PROCESS_TYPES",
    "PROCESS_TRIGGERS",
    "PROCESS_PRIORITIES",
    "PROCESS_SEVERITY",
    "PROCESS_ROLES",
]