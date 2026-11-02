"""Canonical Resource, Asset & Allocation Operating Fabric — Gate 16.

Establishes the canonical resource and asset reality that connects the company's
intent, demand, capacity, execution, and outcomes into ONE canonical company reality.

Key connections:
- Strategic Intent → Resource Demand → Resource/Asset → Allocation → Execution → Outcome
- Financial (Gate 15) → Procurement → Resource/Asset Creation → Allocation
- Customer (Gate 14) → Commitments → Resource Requirements → Allocation
- Strategic Alignment (Gate 13) → Objectives → Projects → Resource Demand
- Capacity (Gate 8/4F.6) → OrgCapability/CapacityAllocation → Resource Supply
- Digital Twin (Gate 12) → Resource State in Twin
- Prediction (Gate 10) → Resource Capacity/Pressure Predictions
- Counterfactual (Gate 11) → Resource Scenario Modeling

All models follow canonical invariants:
- Tenant isolation
- Governance-first
- Temporal truth (valid_from/valid_to, supersession)
- Provenance chains
- Exact-once semantics
- Epistemic boundaries
- No parallel resource/asset/capacity graphs
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

# Universal resource categories - NOT industry-specific
RESOURCE_CATEGORIES = (
    "human",              # Human capacity, expertise, availability
    "physical",           # Equipment, machinery, vehicles, facilities
    "digital",            # Cloud capacity, compute, storage, environments
    "software",           # Licenses, tools, platforms, subscriptions
    "infrastructure",     # Physical infrastructure, data centers, networks
    "financial",          # Budget, funding, financial capacity
    "organizational",     # Capabilities, processes, institutional knowledge
    "external",           # Vendors, contractors, partners, external capacity
)

RESOURCE_KINDS = (
    # Human resources
    "employee_capacity",
    "contractor_capacity",
    "specialist_availability",
    "leadership_capacity",
    # Physical resources
    "equipment",
    "machinery",
    "vehicles",
    "facilities",
    "lab_space",
    "office_space",
    # Digital resources
    "cloud_compute",
    "cloud_storage",
    "gpu_capacity",
    "database_capacity",
    "network_bandwidth",
    "k8s_cluster",
    "ci_cd_capacity",
    # Software resources
    "saas_license",
    "perpetual_license",
    "subscription_seat",
    "api_quota",
    # Infrastructure
    "server",
    "rack_space",
    "power_capacity",
    "cooling_capacity",
    # Financial
    "budget_allocation",
    "funding_reserve",
    "capital_expenditure",
    # Organizational capabilities
    "engineering_capability",
    "sales_capability",
    "legal_capability",
    "manufacturing_capability",
    # External
    "vendor_capacity",
    "partner_capacity",
    "contractor_pool",
)

# Asset lifecycle states - canonical, not hardcoded per industry
ASSET_LIFECYCLE_STATES = (
    "required",           # Identified as needed
    "requested",          # Request submitted for procurement
    "procured",           # Procurement completed (Gate 15 link)
    "received",           # Physically/logically received
    "provisioned",        # Configured and ready
    "available",          # In available pool
    "allocated",          # Assigned to work
    "in_use",             # Actively being used
    "maintenance",        # Under maintenance/restricted
    "deallocated",        # Released from allocation
    "retired",            # End of useful life
    "disposed",           # Removed from company control
)

# Allocation states
ALLOCATION_STATES = (
    "requested",          # Allocation requested
    "approved",           # Approved by governance
    "reserved",           # Reserved for upcoming
    "active",             # Currently allocated
    "partial",            # Partially fulfilled
    "completed",          # Fulfilled and released
    "released",           # Released back to pool
    "cancelled",          # Cancelled
)

# Allocation target types
ALLOCATION_TARGET_TYPES = (
    "person",
    "team",
    "department",
    "project",
    "commitment",
    "customer",
    "operation",
    "objective",
    "initiative",
)

# Resource demand sources
DEMAND_SOURCES = (
    "project",
    "commitment",
    "customer",
    "objective",
    "initiative",
    "operation",
    "forecast",
    "strategic_plan",
)

# Supply sources
SUPPLY_SOURCES = (
    "internal",
    "procurement",
    "transfer",
    "lease",
    "subscription",
    "vendor",
    "partner",
    "contractor",
)


# =============================================================================
# CANONICAL RESOURCE — Universal resource reality
# =============================================================================

class CanonicalResource(Base, TimestampMixin):
    """
    Canonical Resource — a unit of capacity the company owns, controls, or can access.
    
    This is the SINGLE canonical resource model. It subsumes and replaces any
    parallel resource representations. All resource types (human, physical,
    digital, financial, organizational, external) are represented here with
    category/kind discrimination.
    
    Connects:
    - Resource Demand → Canonical Resource (supply)
    - Procurement → Canonical Resource (creation)
    - Allocation → Canonical Resource (consumption)
    - Capacity/OrgCapability → Canonical Resource (human supply)
    - Asset → Canonical Resource (physical/digital asset as resource)
    - Financial (Gate 15) → Canonical Resource (budget as resource)
    """
    
    __tablename__ = "canonical_resources"
    __table_args__ = (
        Index("ix_cr_org_category", "organization_id", "category"),
        Index("ix_cr_org_kind", "organization_id", "kind"),
        Index("ix_cr_org_state", "organization_id", "state"),
        Index("ix_cr_org_supply", "organization_id", "supply_source"),
        # Exact-once per (org, identity fingerprint)
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cr_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Universal classification
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # RESOURCE_CATEGORIES
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)       # RESOURCE_KINDS
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Identity & ownership
    # For human: employee_id; for asset: asset_id; for budget: budget_id; etc.
    resource_identity: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    resource_identity_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|asset|budget|license|etc
    
    # Ownership/control
    owned_by_organization: Mapped[bool] = mapped_column(Boolean, default=True)
    vendor_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # If external
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Capacity model (universal units)
    # For human: hours/FTE; for compute: cpu-hours/gpu-hours; for storage: GB/TB; etc.
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")  # hours|fte|gb|tb|cpu-hr|gpu-hr|seat|etc
    total_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    committed_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reserved_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    available_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    # Proficiency/quality (for human/digital)
    proficiency: Mapped[Optional[str]] = mapped_column(String(30))  # high|expert|standard|basic
    
    # Lifecycle
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="available", index=True)
    supply_source: Mapped[str] = mapped_column(String(30), nullable=False, default="internal")  # SUPPLY_SOURCES
    
    # Temporal validity
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Financial (Gate 15 integration)
    cost_per_unit: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    budget_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Procurement link (Gate 15)
    procurement_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    procurement_kind: Mapped[Optional[str]] = mapped_column(String(30))
    
    # Governance
    governed: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Learning integration
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint (on canonical inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def utilization_rate(self) -> float:
        """Current utilization as fraction of total capacity."""
        if self.total_capacity <= 0:
            return 0.0
        return min(1.0, self.committed_capacity / self.total_capacity)
    
    @property
    def is_constrained(self) -> bool:
        return self.available_capacity <= 0 and self.total_capacity > 0


# =============================================================================
# CANONICAL ASSET — Physical/digital asset reality
# =============================================================================

class CanonicalAsset(Base, TimestampMixin):
    """
    Canonical Asset — a tangible or intangible asset the company owns or controls.
    
    Assets are a specialization of resources with full lifecycle management,
    financial tracking, and dependency tracking.
    
    Connects:
    - Procurement (Gate 15) → Canonical Asset (creation)
    - Canonical Resource ← Canonical Asset (asset IS a resource)
    - Allocation → Canonical Asset (assignment)
    - Financial (Gate 15) → Canonical Asset (depreciation, value)
    - Customer/Project → Canonical Asset (dependency)
    - Maintenance → Canonical Asset (lifecycle)
    """
    
    __tablename__ = "canonical_assets"
    __table_args__ = (
        Index("ix_ca_org_category", "organization_id", "asset_category"),
        Index("ix_ca_org_state", "organization_id", "lifecycle_state"),
        Index("ix_ca_org_custodian", "organization_id", "custodian_id"),
        Index("ix_ca_org_location", "organization_id", "location"),
        # Exact-once per (org, identity fingerprint)
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_ca_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Classification
    asset_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # hardware|software|facility|vehicle|license|data|ip
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)       # laptop|server|license|building|etc
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255))
    model: Mapped[Optional[str]] = mapped_column(String(255))
    serial_number: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    asset_tag: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    
    # Lifecycle (canonical state machine)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False, default="required", index=True)  # ASSET_LIFECYCLE_STATES
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    state_change_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Resource link (asset IS a resource)
    resource_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # Links to CanonicalResource
    
    # Custodian/responsibility
    custodian_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Person responsible
    custodian_type: Mapped[Optional[str]] = mapped_column(String(20))  # person|team|department
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Location
    location: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    location_detail: Mapped[Optional[str]] = mapped_column(Text)
    
    # Financial (Gate 15)
    purchase_cost: Mapped[Optional[float]] = mapped_column(Float)
    current_value: Mapped[Optional[float]] = mapped_column(Float)
    depreciation_method: Mapped[Optional[str]] = mapped_column(String(30))  # straight_line|accelerated|none
    depreciation_schedule_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    budget_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Procurement (Gate 15)
    procurement_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    vendor_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    purchase_order_id: Mapped[Optional[str]] = mapped_column(String(32))
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    warranty_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Dependencies (what depends on this asset)
    dependent_project_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    dependent_commitment_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    dependent_customer_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    dependent_resource_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Maintenance
    maintenance_schedule_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    last_maintenance_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_maintenance_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    maintenance_window: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Compliance/certification
    compliance_requirements_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    certifications_json: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Learning integration
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint (on canonical inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def is_critical(self) -> bool:
        """Asset is critical if it has dependent commitments/customers."""
        return len(self.dependent_commitment_ids or []) > 0 or len(self.dependent_customer_ids or []) > 0
    
    @property
    def is_approaching_maintenance(self) -> bool:
        if not self.next_maintenance_at:
            return False
        from app.core.timeutils import utcnow
        return utcnow() >= self.next_maintenance_at


# =============================================================================
# RESOURCE DEMAND — Canonical demand for resources
# =============================================================================

class ResourceDemand(Base, TimestampMixin):
    """
    Canonical Resource Demand — explicit demand for resources from work/commitments.
    
    Extends/replaces AllocationDemand with universal resource support.
    One live demand per (org, source, resource_kind, window).
    
    Connects:
    - Project/Commitment/Customer/Objective → Resource Demand
    - Resource Demand → Canonical Resource (supply matching)
    - Allocation → Resource Demand (fulfillment)
    """
    
    __tablename__ = "resource_demands"
    __table_args__ = (
        Index("ix_rd_org_category", "organization_id", "resource_category"),
        Index("ix_rd_org_kind", "organization_id", "resource_kind"),
        Index("ix_rd_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_rd_org_window", "organization_id", "window_start", "window_end"),
        # One live demand per source/resource/window
        UniqueConstraint(
            "organization_id", "source_type", "source_id", "resource_category", "resource_kind", "window_start", "window_end",
            name="uq_rd_live",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Source of demand
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # DEMAND_SOURCES
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Resource specification
    resource_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # RESOURCE_CATEGORIES
    resource_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)       # RESOURCE_KINDS
    units_requested: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")
    proficiency: Mapped[Optional[str]] = mapped_column(String(30))
    
    # Time window
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Priority & urgency
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=critical, 5=low
    urgency: Mapped[str] = mapped_column(String(20), default="normal")  # critical|high|normal|low
    
    # Fulfillment tracking
    units_fulfilled: Mapped[float] = mapped_column(Float, default=0.0)
    fulfillment_status: Mapped[str] = mapped_column(String(20), default="unfulfilled")  # unfulfilled|partial|fulfilled|overfulfilled
    
    # Allocation links
    allocation_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Notes
    justification: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    @property
    def units_remaining(self) -> float:
        return max(0.0, self.units_requested - self.units_fulfilled)
    
    @property
    def is_fulfilled(self) -> bool:
        return self.units_fulfilled >= self.units_requested


# =============================================================================
# RESOURCE ALLOCATION — Governed allocation of resources to work
# =============================================================================

class ResourceAllocation(Base, TimestampMixin):
    """
    Canonical Resource Allocation — governed assignment of resources to work.
    
    This is the SINGLE canonical allocation model. It subsumes CapacityAllocation
    and any other parallel allocation representations.
    
    Connects:
    - Canonical Resource → Resource Allocation
    - Resource Demand → Resource Allocation (fulfills demand)
    - Person/Team/Project/Commitment/Customer → Resource Allocation (target)
    - Financial (Gate 15) → Resource Allocation (budget tracking)
    """
    
    __tablename__ = "resource_allocations"
    __table_args__ = (
        Index("ix_ra_org_resource", "organization_id", "resource_id"),
        Index("ix_ra_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_ra_org_window", "organization_id", "window_start", "window_end"),
        Index("ix_ra_org_state", "organization_id", "state"),
        Index("ix_ra_org_demand", "organization_id", "demand_id"),
        # Exact-once per (org, resource, target, window)
        UniqueConstraint(
            "organization_id", "resource_id", "target_type", "target_id", "window_start", "window_end",
            name="uq_ra_exact_once",
        ),
        {"extend_existing": True},
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Resource being allocated
    resource_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # CanonicalResource
    resource_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    resource_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Allocation target
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # ALLOCATION_TARGET_TYPES
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_name: Mapped[Optional[str]] = mapped_column(String(300))
    
    # Demand being fulfilled (optional)
    demand_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Allocation quantity
    units_allocated: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")
    
    # Time window
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # State
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="requested", index=True)  # ALLOCATION_STATES
    
    # Purpose & context
    purpose: Mapped[Optional[str]] = mapped_column(Text)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    
    # Actual utilization tracking
    actual_utilization: Mapped[Optional[float]] = mapped_column(Float)
    utilization_measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Financial (Gate 15)
    cost_allocated: Mapped[Optional[float]] = mapped_column(Float)
    budget_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Governance
    requested_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[Optional[str]] = mapped_column(String(64))
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# RESOURCE CONFLICT — Derived intelligence, not canonical truth
# =============================================================================

class ResourceConflict(Base, TimestampMixin):
    """
    Canonical Resource Conflict — derived intelligence about resource constraints.
    
    These are DERIVED projections, NOT canonical truths. They feed the existing
    Operating Attention architecture (Gate 13). Do NOT create a parallel attention system.
    
    Kinds:
    - double_allocation: Same resource allocated to incompatible targets
    - capacity_overload: Demand > available capacity
    - underutilization: Allocated >> actual usage
    - critical_dependency: Major commitment depends on single resource
    - bottleneck: Multiple workstreams compete for same resource
    - procurement_gap: Required resource not yet available
    - financial_mismatch: Budget exists but capacity doesn't
    - lifecycle_risk: Critical asset approaching retirement
    """
    
    __tablename__ = "resource_conflicts"
    __table_args__ = (
        Index("ix_rc_org_kind", "organization_id", "conflict_kind"),
        Index("ix_rc_org_severity", "organization_id", "severity"),
        Index("ix_rc_org_resource", "organization_id", "resource_id"),
        Index("ix_rc_org_status", "organization_id", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    conflict_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")  # info|warning|critical
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|mitigating|resolved
    
    # Primary resource involved
    resource_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    resource_kind: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Affected entities
    affected_allocation_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_demand_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_project_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_commitment_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_customer_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Description & evidence
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Mitigation
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    mitigated_by: Mapped[Optional[str]] = mapped_column(String(64))
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(50), default="derived")
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint (on detection inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# RESOURCE OPERATING SLICE — Derived projection for resource context
# =============================================================================

class ResourceOperatingSlice(Base, TimestampMixin):
    """
    Canonical Resource Operating Slice — governed, point-in-time derived
    projection of all company resource/asset/allocation reality.
    
    This is a VIEW/PROJECTION, not a data store. Materialized for performance.
    """
    
    __tablename__ = "resource_operating_slices"
    __table_args__ = (
        Index("ix_ros_org_computed", "organization_id", "computed_at"),
        UniqueConstraint(
            "organization_id", "input_fingerprint",
            name="uq_ros_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Input fingerprint for exact-once
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Resource summary
    resources_by_category: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    resources_by_kind: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    resources_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Asset summary
    assets_by_category: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    assets_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    critical_asset_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Allocation summary
    total_allocations: Mapped[int] = mapped_column(Integer, default=0)
    active_allocations: Mapped[int] = mapped_column(Integer, default=0)
    allocations_by_target_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Capacity summary
    total_capacity: Mapped[Optional[float]] = mapped_column(Float)
    total_committed: Mapped[Optional[float]] = mapped_column(Float)
    total_reserved: Mapped[Optional[float]] = mapped_column(Float)
    total_available: Mapped[Optional[float]] = mapped_column(Float)
    overall_utilization: Mapped[Optional[float]] = mapped_column(Float)
    
    # Demand summary
    total_demands: Mapped[int] = mapped_column(Integer, default=0)
    unfulfilled_demands: Mapped[int] = mapped_column(Integer, default=0)
    demand_by_kind: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Conflicts
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_by_kind: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Financial (Gate 15)
    total_resource_cost: Mapped[Optional[float]] = mapped_column(Float)
    allocated_budget: Mapped[Optional[float]] = mapped_column(Float)
    
    # Computed metadata
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once fingerprint (on canonical inputs)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# RESOURCE IMPACT ANALYSIS — Cross-domain resource impact
# =============================================================================

class ResourceImpactAnalysis(Base, TimestampMixin):
    """
    Canonical Resource Impact Analysis — derives the cross-domain impact
    of a resource change (addition, removal, reallocation, failure) on
    commitments, projects, customers, and objectives.
    
    Extends Gate 13/15 cross-domain impact with resource context.
    """
    
    __tablename__ = "resource_impact_analyses"
    __table_args__ = (
        Index("ix_ria_org_trigger", "organization_id", "trigger_type"),
        Index("ix_ria_org_entity", "organization_id", "trigger_entity_type", "trigger_entity_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_ria_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # resource_added|removed|reallocated|failed|delayed|capacity_changed
    trigger_entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # resource|asset|allocation|demand
    trigger_entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Impact scope
    affected_resources: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_allocations: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_demands: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_assets: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_projects: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_objectives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_people: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_customers: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_capabilities: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Quantitative impact
    capacity_impact: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Risk assessment
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    new_conflicts: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    escalated_conflicts: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
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