"""Canonical People, Talent & Workforce Operating Fabric — Gate 21.

This is the SINGLE canonical workforce layer. It does NOT create a parallel
HR/Talent/People graph/brain/system. All workforce intelligence is derived from
existing canonical primitives.

Key architectural principles:
- Identity ≠ Employment ≠ Role ≠ Responsibility ≠ Authorization ≠ Accountability
- Person → Membership → Role → Responsibility → Commitment → Action → Outcome
- Capacity ≠ Availability ≠ Allocation ≠ Workload
- Skill ≠ Expertise ≠ Capability ≠ Capability Aggregate
- Development ≠ Course Completion ≠ Capability Change
- Performance ≠ AI Score ≠ Outcome Evidence ≠ Verification
- Offboarding must propagate impact through canonical reality
- No parallel HR/Talent/Workforce architecture

All data is composed from existing canonical primitives:
- Gates 6-9: Temporal truth, provenance, verification, institutional learning
- Gates 8-14: People, Work, Communication, Meetings, Org Intelligence, Capacity, Customer
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 18: Economic Intelligence
- Gate 19: Enterprise Operations & Business Process Fabric
- Gate 20: Canonical Knowledge, Documents & Institutional Context Fabric
"""

from datetime import date, datetime, timezone
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
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# WORKFORCE LIFECYCLE STATES
# =============================================================================

WORKFORCE_LIFECYCLE_STATES = (
    "candidate",           # Recruitment stage
    "offered",             # Offer extended
    "onboarding",          # Pre-employment setup
    "active",              # Currently employed/member
    "probation",           # Probationary period
    "notice",              # Resignation notice period
    "suspended",           # Temporarily suspended
    "inactive",            # Inactive (leave, sabbatical)
    "departed",            # Left organization
    "external",            # External (contractor, consultant, partner)
    "alumni",              # Former employee, maintained relationship
)

EMPLOYMENT_TYPES = (
    "full_time",
    "part_time",
    "contractor",
    "consultant",
    "intern",
    "temporary",
    "seasonal",
)

MEMBERSHIP_STATUSES = (
    "invited",
    "active",
    "probation",
    "notice",
    "suspended",
    "inactive",
    "departed",
    "external",
    "contractor",
    "consultant",
    "partner",
)

RELATIONSHIP_TYPES = (
    "reports_to",
    "matrix_manager",
    "project_manager",
    "functional_manager",
    "dotted_line_manager",
    "mentor",
)

ROLE_TYPES = (
    "functional",
    "project",
    "temporary",
    "acting",
    "advisory",
    "matrix",
)

RESPONSIBILITY_TYPES = (
    "accountable",
    "responsible",
    "consulted",
    "informed",
)

RESPONSIBILITY_SCOPES = (
    "objective",
    "initiative",
    "project",
    "commitment",
    "process",
    "process_step",
    "customer",
    "vendor",
    "knowledge_artifact",
)

ACCOUNTABILITY_TYPES = (
    "direct",
    "delegated",
    "shared",
)

WORKLOAD_STATES = (
    "normal",
    "stretched",
    "overloaded",
    "underutilized",
    "on_leave",
    "unavailable",
)

SUCCESSION_STATUSES = (
    "identified",
    "developing",
    "ready",
    "promoted",
)

DEVELOPMENT_STATES = (
    "identified",
    "planned",
    "in_progress",
    "completed",
    "verified",
    "applied",
)

PERFORMANCE_KINDS = (
    "project",
    "learning",
    "behavior",
    "leadership",
)


# =============================================================================
# CANONICAL PERSON OPERATING CONTEXT — Derived projection, NOT a model
# =============================================================================

# The person operating context is a DERIVED PROJECTION composed at request time.
# It does NOT persist as a separate model. The service builds it by composing:
# - Employee (identity, placement)
# - PersonMembership (employment lifecycle)
# - PersonRoleAssignment (role windows)
# - ReportingRelationship (reporting hierarchy)
# - OrganizationalResponsibility (explicit outcome ownership)
# - AccountabilityLink (commitment → auth → responsibility → person)
# - CompanyCommitment / CompanyAuthorization (governance chain)
# - EmployeeSkill / Expertise / CanonicalSkill (capability)
# - EmployeeAvailability / WorkloadSnapshot / CapacitySnapshot (capacity)
# - EmployeeAsset (resources)
# - OrganizationalLearning / OutcomeAssessment (learning)
# - CompanyAction (actions)
# - Process/Execution/Step/Approval (Gate 19)
# - KnowledgeArtifact/Claim (Gate 20)
# - Predictions/Counterfactuals/Digital Twin (Gates 10-12)
# - CustomerOperatingSlice/ProcessOperatingSlice (Gates 14/19)
# - Financial/Economic slices (Gates 15-18)


# =============================================================================
# SUPPORTING MODELS — Extensions to existing primitives where needed
# =============================================================================


# =============================================================================
# PERSON WORKFORCE EXTENSION — Extends Employee with workforce fabric fields
# =============================================================================

class PersonWorkforceExtension(Base, TimestampMixin):
    """
    Extension to Employee for workforce fabric fields.
    
    This extends Employee without modifying the core identity model.
    One-to-one with Employee. Fields that don't belong in the core
    identity model but are needed for the workforce operating fabric.
    """
    
    __tablename__ = "person_workforce_extensions"
    __table_args__ = (
        Index("ix_pwe_org_emp", "organization_id", "employee_id"),
        Index("ix_pwe_org_status", "organization_id", "workforce_status"),
        UniqueConstraint(
            "organization_id", "employee_id",
            name="uq_pwe_emp",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Workforce lifecycle (complements Employee.status)
    workforce_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)  # WORKFORCE_LIFECYCLE_STATES
    employment_type: Mapped[str] = mapped_column(String(30), nullable=False, default="full_time")  # EMPLOYMENT_TYPES
    
    # Lifecycle dates
    hire_date: Mapped[Optional[date]] = mapped_column(Date)
    probation_end_date: Mapped[Optional[date]] = mapped_column(Date)
    notice_date: Mapped[Optional[date]] = mapped_column(Date)
    departure_date: Mapped[Optional[date]] = mapped_column(Date)
    alumni_since_date: Mapped[Optional[date]] = mapped_column(Date)
    
    # Compensation/work context (not HR financials - links to Gates 15-18)
    compensation_band_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    cost_center_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    work_schedule_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Governance
    security_clearance: Mapped[Optional[str]] = mapped_column(String(50))
    compliance_profile_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# WORKFORCE CAPABILITY GAP — Canonical gap detection
# =============================================================================

class WorkforceCapabilityGap(Base, TimestampMixin):
    """
    Canonical Workforce Capability Gap — detected gap between required and available capability.
    
    Derived from: Process requirements, Commitment demands, Customer promises
    versus: Available capacity, Expertise, Allocations
    
    This is NOT a new capability model. It surfaces gaps using existing
    CanonicalSkill, Expertise, CapacityAllocation, AllocationDemand.
    """
    
    __tablename__ = "workforce_capability_gaps"
    __table_args__ = (
        Index("ix_wcg_org_skill", "organization_id", "skill_id"),
        Index("ix_wcg_org_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_wcg_org_severity", "organization_id", "severity"),
        Index("ix_wcg_org_status", "organization_id", "status"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_wcg_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What capability is missing
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Where the gap exists
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # team|department|business_unit|organization|project
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    
    # Quantification
    required_units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required_proficiency: Mapped[str] = mapped_column(String(24), nullable=False)  # high|expert
    available_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_proficiency: Mapped[Optional[str]] = mapped_column(String(24))
    
    # Severity & urgency
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium", index=True)  # info|warning|critical|existential
    urgency: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")  # low|medium|high|immediate
    
    # Source of gap detection
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # process_demand|commitment|customer_promise|capacity_plan|succession_risk
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Impact
    affected_process_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_commitment_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    affected_customer_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    financial_exposure: Mapped[Optional[float]] = mapped_column(Float)
    
    # Status & resolution
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)  # open|acknowledged|mitigating|hiring|training|resolved|accepted
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(30), default="derived")
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# WORKFORCE CONTINUITY EVENT — Offboarding/transition impact
# =============================================================================

class WorkforceContinuityEvent(Base, TimestampMixin):
    """
    Canonical Workforce Continuity Event — impact when a person becomes unavailable.
    
    Triggered by: Offboarding, Leave, Suspension, Role Change, Transfer
    
    Captures the organizational impact and feeds Operating Attention.
    This does NOT create a parallel attention system - it feeds the existing
    Operating Attention / Organizational Attention from Gates 8/13.
    """
    
    __tablename__ = "workforce_continuity_events"
    __table_args__ = (
        Index("ix_wce_org_person", "organization_id", "person_id"),
        Index("ix_wce_org_type", "organization_id", "event_type"),
        Index("ix_wce_org_severity", "organization_id", "severity"),
        Index("ix_wce_org_status", "organization_id", "status"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_wce_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What happened
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # offboarding|leave|suspension|role_change|transfer|notice
    trigger_source: Mapped[str] = mapped_column(String(30), nullable=False)  # offboarding_record|leave_request|suspension_record|role_assignment|transfer_record
    trigger_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Timing
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notice_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Severity & impact
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium", index=True)  # info|warning|critical|existential
    impact_summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Impacted entities (derived at event time)
    responsibilities_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    commitments_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    processes_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    process_steps_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    approvals_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    customers_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    knowledge_artifacts_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    dependencies_affected_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Capacity impact
    capacity_units_lost: Mapped[int] = mapped_column(Integer, default=0)
    critical_capabilities_lost_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    
    # Succession/mitigation
    successor_person_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    successor_readiness: Mapped[Optional[int]] = mapped_column(Integer)  # 0-100
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text)
    mitigation_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|in_progress|completed|failed
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)  # active|mitigating|resolved|accepted
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(30), default="derived")
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# WORKFORCE DEVELOPMENT NEED — Canonical development tracking
# =============================================================================

class WorkforceDevelopmentNeed(Base, TimestampMixin):
    """
    Canonical Workforce Development Need — a capability gap requiring development.
    
    Links: Capability Gap → Person → Development Action → Capability Change → Outcome
    
    This is NOT an LMS. It tracks the canonical development loop where
    development is tied to organizational capability requirements.
    """
    
    __tablename__ = "workforce_development_needs"
    __table_args__ = (
        Index("ix_wdn_org_person", "organization_id", "person_id"),
        Index("ix_wdn_org_skill", "organization_id", "skill_id"),
        Index("ix_wdn_org_state", "organization_id", "state"),
        Index("ix_wdn_org_source", "organization_id", "source_type", "source_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_wdn_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What capability is needed
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_proficiency: Mapped[str] = mapped_column(String(24), nullable=False)  # high|expert
    current_proficiency: Mapped[Optional[str]] = mapped_column(String(24))
    
    # Why this need exists
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)  # capability_gap|succession_plan|role_change|process_demand|customer_need|commitment
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Development plan
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="identified", index=True)  # DEVELOPMENT_STATES
    planned_actions_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # [{action_type: learning_path|course|certification|mentoring|project_assignment|stretch_task, target: ..., due_date: ..., owner: ...}]
    
    # Progress tracking
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Outcome
    capability_change_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    new_expertise_score: Mapped[Optional[float]] = mapped_column(Float)
    applied_to_work: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Constants
    "WORKFORCE_LIFECYCLE_STATES",
    "EMPLOYMENT_TYPES",
    "MEMBERSHIP_STATUSES",
    "RELATIONSHIP_TYPES",
    "ROLE_TYPES",
    "RESPONSIBILITY_TYPES",
    "RESPONSIBILITY_SCOPES",
    "ACCOUNTABILITY_TYPES",
    "WORKLOAD_STATES",
    "SUCCESSION_STATUSES",
    "DEVELOPMENT_STATES",
    "PERFORMANCE_KINDS",
    # Models
    "PersonWorkforceExtension",
    "WorkforceCapabilityGap",
    "WorkforceContinuityEvent",
    "WorkforceDevelopmentNeed",
]