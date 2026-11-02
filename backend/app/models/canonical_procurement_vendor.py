"""Canonical Procurement, Vendor & External Capacity Operating Fabric — Gate 17.

Establishes the canonical external supply reality connecting the company's
internal needs to external vendors, suppliers, contractors, and capacity.

Key connections:
- Resource Demand (Gate 16) → Procurement → Vendor/External Capacity → Resource/Asset
- Procurement (Gate 15) → Vendor → External Capability → Allocation → Execution
- Strategic Alignment (Gate 13) → Project → Resource Demand → Procurement → Vendor
- Customer (Gate 14) → Commitment → Project → Resource Demand → Procurement → Vendor
- Financial (Gate 15) → Budget Commitment → Procurement → Invoice → Payment
- Digital Twin (Gate 12) → Vendor/Procurement/External Capacity Scenario Modeling
- Prediction (Gate 10) → Vendor Delivery/Capacity/Cost Risk Prediction
- Counterfactual (Gate 11) → Vendor Unavailability / Alternative Sourcing Scenarios

All models follow canonical invariants:
- Tenant isolation
- Governance-first
- Temporal truth (valid_from/valid_to, supersession)
- Provenance chains
- Exact-once semantics
- Epistemic boundaries
- No parallel procurement/vendor/external-capacity graphs
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

# Vendor/Supplier kinds
VENDOR_KINDS = (
    "supplier",           # Physical goods supplier
    "vendor",             # General vendor
    "contractor",         # Labor/services contractor
    "consultant",         # Professional consultant
    "cloud_provider",     # Cloud infrastructure provider
    "saas_provider",      # SaaS provider
    "logistics",          # Logistics/shipping
    "manufacturing",      # Contract manufacturing
    "professional_services", # Professional services firm
    "staffing",           # Staffing agency
    "outsourced_ops",     # Outsourced operations
    "maintenance",        # Maintenance provider
    "utility",            # Utility provider
    "financial_services", # Financial services
    "legal",              # Legal services
    "other",
)

# Vendor relationship states
VENDOR_STATES = (
    "active",             # Currently engaged
    "onboarding",         # In onboarding process
    "qualified",          # Qualified but not yet engaged
    "preferred",          # Preferred vendor
    "approved",           # Approved for use
    "conditional",        # Conditional approval
    "restricted",         # Restricted use
    "suspended",          # Temporarily suspended
    "terminated",         # Terminated
    "blacklisted",        # Blacklisted
    "archived",           # Archived
)

# External capacity types
EXTERNAL_CAPACITY_TYPES = (
    "contractor_fte",           # Contractor full-time equivalent
    "consultant_hours",         # Consultant hours
    "cloud_compute_units",      # Cloud compute units
    "cloud_storage_gb",         # Cloud storage GB
    "saas_seats",              # SaaS seats
    "managed_service_hours",   # Managed service hours
    "manufacturing_capacity",  # Manufacturing capacity
    "logistics_capacity",      # Logistics capacity
    "professional_services",   # Professional services capacity
    "staffing_pool",           # Staffing pool
    "facility_space",          # External facility space
    "specialist_availability", # Specialist availability
)

# Procurement lifecycle states - canonical
PROCUREMENT_LIFECYCLE_STATES = (
    "identified",           # Need identified
    "requested",            # Request submitted
    "under_review",         # Under review/approval
    "quoted",               # Quotes received
    "approved",             # Approved for procurement
    "sourcing",             # Actively sourcing
    "ordered",              # Order placed
    "in_fulfillment",       # Being fulfilled
    "partially_delivered",  # Partially delivered
    "received",             # Received
    "inspection",           # Under inspection/acceptance
    "accepted",             # Accepted
    "allocated",            # Allocated to demand
    "completed",            # Completed
    "rejected",             # Rejected
    "cancelled",            # Cancelled
    "disputed",             # Disputed
    "delayed",              # Delayed
    "on_hold",              # On hold
)

# Procurement kinds
PROCUREMENT_KINDS = (
    "purchase",             # Direct purchase
    "subscription",         # Recurring subscription
    "contract",             # Contract-based
    "internal_transfer",    # Internal transfer
    "lease",                # Lease
    "license",              # License acquisition
    "service",              # Service procurement
    "contingent",           # Contingent
    "blanket_order",        # Blanket order
    "emergency",            # Emergency procurement
)

# Authorization states
AUTHORIZATION_STATES = (
    "not_required",
    "pending",
    "approved",
    "rejected",
    "escalated",
    "conditional",
)

# Vendor capability categories
VENDOR_CAPABILITY_CATEGORIES = (
    "cloud_infrastructure",
    "compute_capacity",
    "storage_capacity",
    "network_capacity",
    "saas_platform",
    "professional_services",
    "consulting",
    "implementation",
    "managed_services",
    "staffing",
    "manufacturing",
    "logistics",
    "facilities",
    "maintenance",
    "hardware_supply",
    "software_licenses",
    "specialized_expertise",
    "training",
    "support_services",
)

# Dependency criticality
DEPENDENCY_CRITICALITY = (
    "critical",       # Single source, no alternatives
    "high",           # Few alternatives, high switching cost
    "medium",         # Some alternatives available
    "low",            # Many alternatives, low switching cost
    "none",           # No dependency
)

# Risk kinds for vendors
VENDOR_RISK_KINDS = (
    "delivery_risk",          # Late/delayed delivery
    "quality_risk",           # Quality issues
    "capacity_risk",          # Insufficient capacity
    "financial_risk",         # Vendor financial instability
    "concentration_risk",     # Over-dependence on vendor
    "contract_risk",          # Contract expiry/unfavorable terms
    "compliance_risk",        # Regulatory/compliance issues
    "security_risk",          # Security/privacy concerns
    "substitution_risk",      # No alternative available
    "performance_risk",       # Poor performance history
    "dependency_risk",        # Critical internal dependency
    "geopolitical_risk",      # Geographic/political risk
)


# =============================================================================
# CANONICAL VENDOR — External supplier reality
# =============================================================================

class CanonicalVendor(Base, TimestampMixin):
    """
    Canonical Vendor — an external supplier/provider the company depends on.
    
    Extends the existing Vendor model with canonical integration:
    - Capabilities and capacity
    - Performance intelligence
    - Dependency tracking
    - Procurement linkage
    - Risk assessment
    - Contract management
    - Governance and authorization
    """
    
    __tablename__ = "canonical_vendors"
    __table_args__ = (
        Index("ix_cv_org_kind", "organization_id", "kind"),
        Index("ix_cv_org_state", "organization_id", "state"),
        Index("ix_cv_org_criticality", "organization_id", "criticality"),
        Index("ix_cv_org_owner", "organization_id", "owner_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cv_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # VENDOR_KINDS
    vendor_code: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Classification
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    region: Mapped[Optional[str]] = mapped_column(String(80))
    size_class: Mapped[Optional[str]] = mapped_column(String(30))  # small|medium|large|enterprise
    
    # Contact
    primary_contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    primary_contact_email: Mapped[Optional[str]] = mapped_column(String(320))
    primary_contact_phone: Mapped[Optional[str]] = mapped_column(String(60))
    billing_contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    billing_contact_email: Mapped[Optional[str]] = mapped_column(String(320))
    
    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(300))
    address_line2: Mapped[Optional[str]] = mapped_column(String(300))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    state_province: Mapped[Optional[str]] = mapped_column(String(120))
    postal_code: Mapped[Optional[str]] = mapped_column(String(30))
    
    # Legal/Compliance
    legal_name: Mapped[Optional[str]] = mapped_column(String(300))
    tax_id: Mapped[Optional[str]] = mapped_column(String(120))
    registration_number: Mapped[Optional[str]] = mapped_column(String(120))
    duns_number: Mapped[Optional[str]] = mapped_column(String(20))
    lei_code: Mapped[Optional[str]] = mapped_column(String(20))  # Legal Entity Identifier
    
    # Relationship
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)  # VENDOR_STATES
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")  # DEPENDENCY_CRITICALITY
    tier: Mapped[int] = mapped_column(Integer, default=2)  # 1=strategic, 2=important, 3=standard, 4=commodity
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # Internal owner
    owner_type: Mapped[Optional[str]] = mapped_column(String(30))  # person|team|department
    
    # Financial
    payment_terms: Mapped[Optional[str]] = mapped_column(String(120))  # net30, net60, etc.
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    credit_limit: Mapped[Optional[float]] = mapped_column(Float)
    annual_spend: Mapped[Optional[float]] = mapped_column(Float)
    lifetime_spend: Mapped[Optional[float]] = mapped_column(Float)
    
    # Performance (evidence-derived)
    on_time_delivery_rate: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    quality_acceptance_rate: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    fulfillment_accuracy_rate: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    cost_variance: Mapped[Optional[float]] = mapped_column(Float)  # actual vs expected
    average_lead_time_days: Mapped[Optional[float]] = mapped_column(Float)
    performance_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-100 composite
    last_performance_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Contracts
    current_contract_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    contract_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_value: Mapped[Optional[float]] = mapped_column(Float)
    
    # Capabilities
    capability_categories_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    capability_details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # External capacity
    external_capacity_types_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    max_capacity_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    available_capacity_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    capacity_utilization: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    
    # Risk
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high|critical
    risk_factors_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    risk_assessment_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    last_risk_assessment: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Governance
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    authorization_state: Mapped[str] = mapped_column(String(30), default="not_required")  # AUTHORIZATION_STATES
    
    # Compliance
    compliance_certifications_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    compliance_requirements_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    compliance_status: Mapped[str] = mapped_column(String(20), default="compliant")
    
    # Learning integration
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    onboarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    onboarded_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def is_critical(self) -> bool:
        return self.criticality in ("critical", "high")
    
    @property
    def is_contract_expiring_soon(self) -> bool:
        if not self.contract_expires_at:
            return False
        from app.core.timeutils import utcnow
        days_until = (self.contract_expires_at - utcnow()).days
        return 0 <= days_until <= 90
    
    @property
    def has_capacity_available(self) -> bool:
        if not self.available_capacity_json:
            return False
        return any(v > 0 for v in self.available_capacity_json.values())


# =============================================================================
# VENDOR CAPABILITY — What a vendor can provide
# =============================================================================

class VendorCapability(Base, TimestampMixin):
    """
    Canonical Vendor Capability — a specific capability a vendor offers.
    
    Links vendor to capability categories with capacity, pricing, and SLA details.
    """
    
    __tablename__ = "vendor_capabilities"
    __table_args__ = (
        Index("ix_vc_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vc_org_category", "organization_id", "capability_category"),
        UniqueConstraint(
            "organization_id", "vendor_id", "capability_category", "capability_name",
            name="uq_vc_unique",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Capability
    capability_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # VENDOR_CAPABILITY_CATEGORIES
    capability_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Capacity
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")
    max_capacity: Mapped[Optional[float]] = mapped_column(Float)
    current_utilization: Mapped[Optional[float]] = mapped_column(Float)  # 0-1
    available_capacity: Mapped[Optional[float]] = mapped_column(Float)
    capacity_elastic: Mapped[bool] = mapped_column(Boolean, default=False)  # Can scale up
    scaling_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Pricing
    unit_cost: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    volume_discount_tiers_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    setup_cost: Mapped[Optional[float]] = mapped_column(Float)
    minimum_commitment: Mapped[Optional[float]] = mapped_column(Float)
    
    # SLA
    sla_details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    availability_sla: Mapped[Optional[float]] = mapped_column(Float)  # e.g., 0.999
    response_time_sla_hours: Mapped[Optional[float]] = mapped_column(Float)
    escalation_path_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Quality
    quality_standards_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    certifications_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Status
    state: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|inactive|deprecated
    
    # Learning
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# EXTERNAL CAPACITY — External capacity as resource
# =============================================================================

class ExternalCapacity(Base, TimestampMixin):
    """
    Canonical External Capacity — external capacity available to the company.
    
    This represents external capacity as a first-class resource that can be
    allocated, tracked, and reasoned about like internal capacity.
    """
    
    __tablename__ = "external_capacity"
    __table_args__ = (
        Index("ix_ec_org_vendor", "organization_id", "vendor_id"),
        Index("ix_ec_org_type", "organization_id", "capacity_type"),
        Index("ix_ec_org_state", "organization_id", "state"),
        Index("ix_ec_org_window", "organization_id", "window_start", "window_end"),
        UniqueConstraint(
            "organization_id", "vendor_id", "capacity_type", "window_start", "window_end",
            name="uq_ec_live",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Capacity specification
    capacity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # EXTERNAL_CAPACITY_TYPES
    capacity_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Unit and quantity
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="units")
    total_capacity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    committed_capacity: Mapped[float] = mapped_column(Float, default=0.0)
    reserved_capacity: Mapped[float] = mapped_column(Float, default=0.0)
    available_capacity: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Time window
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Pricing
    cost_per_unit: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    billing_frequency: Mapped[Optional[str]] = mapped_column(String(30))  # monthly|quarterly|annual|per_use
    
    # SLA
    availability_sla: Mapped[Optional[float]] = mapped_column(Float)
    response_sla_hours: Mapped[Optional[float]] = mapped_column(Float)
    penalty_clauses_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # State
    state: Mapped[str] = mapped_column(String(20), default="available", index=True)  # available|committed|constrained|unavailable
    
    # Linkage
    capability_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # VendorCapability
    procurement_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # ProcurementRecord
    
    # Allocation tracking
    allocation_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Learning
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def utilization_rate(self) -> float:
        if self.total_capacity <= 0:
            return 0.0
        return min(1.0, self.committed_capacity / self.total_capacity)
    
    @property
    def is_constrained(self) -> bool:
        return self.available_capacity <= 0 and self.total_capacity > 0


# =============================================================================
# PROCUREMENT — Canonical procurement lifecycle
# =============================================================================

class CanonicalProcurement(Base, TimestampMixin):
    """
    Canonical Procurement — full lifecycle procurement of resources from vendors.
    
    Extends Gate 15 ProcurementRecord with:
    - Full lifecycle states
    - Authorization workflow
    - Vendor capability linkage
    - External capacity linkage
    - Approval workflow
    - Milestone tracking
    """
    
    __tablename__ = "canonical_procurement"
    __table_args__ = (
        Index("ix_cp_org_vendor", "organization_id", "vendor_id"),
        Index("ix_cp_org_state", "organization_id", "state"),
        Index("ix_cp_org_kind", "organization_id", "kind"),
        Index("ix_cp_org_demand", "organization_id", "demand_id"),
        Index("ix_cp_org_window", "organization_id", "window_start", "window_end"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_cp_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Core
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # PROCUREMENT_KINDS
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Linkage to demand (Gate 16)
    demand_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # ResourceDemand
    requirement_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # ResourceRequirement
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    budget_commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Vendor
    vendor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_vendors.id", ondelete="SET NULL"), index=True
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    capability_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # VendorCapability
    external_capacity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # ExternalCapacity
    
    # Commercial
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # PROCUREMENT_KINDS
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Financial
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float)
    actual_cost: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    budget_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    budget_line_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Quantity
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(30), default="units")
    
    # Governance - full lifecycle
    state: Mapped[str] = mapped_column(String(30), default="identified", nullable=False, index=True)  # PROCUREMENT_LIFECYCLE_STATES
    previous_state: Mapped[Optional[str]] = mapped_column(String(30))
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    state_change_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Authorization (decision != authorization != commitment != action != execution)
    authorization_state: Mapped[str] = mapped_column(String(30), default="not_required")  # AUTHORIZATION_STATES
    authorization_required: Mapped[bool] = mapped_column(Boolean, default=False)
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    authorization_amount: Mapped[Optional[float]] = mapped_column(Float)
    authorization_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Request
    requested_by: Mapped[Optional[str]] = mapped_column(String(64))
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    justification: Mapped[Optional[str]] = mapped_column(Text)
    
    # Approval
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_amount: Mapped[Optional[float]] = mapped_column(Float)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timeline
    needed_by: Mapped[Optional[date]] = mapped_column(Date)
    ordered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expected_delivery: Mapped[Optional[date]] = mapped_column(Date)
    promised_delivery: Mapped[Optional[date]] = mapped_column(Date)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Milestones
    milestones_json: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Terms
    payment_terms: Mapped[Optional[str]] = mapped_column(String(120))
    contract_reference: Mapped[Optional[str]] = mapped_column(String(120))
    warranty_until: Mapped[Optional[date]] = mapped_column(Date)
    
    # Receipt/Quality
    received_quantity: Mapped[Optional[float]] = mapped_column(Float)
    accepted_quantity: Mapped[Optional[float]] = mapped_column(Float)
    rejected_quantity: Mapped[Optional[float]] = mapped_column(Float)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    quality_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Supersession
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Time window
    window_start: Mapped[Optional[date]] = mapped_column(Date)
    window_end: Mapped[Optional[date]] = mapped_column(Date)
    
    # Learning
    lesson_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    pattern_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    contradiction_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    @property
    def is_active(self) -> bool:
        return self.state not in ("completed", "cancelled", "rejected", "accepted")
    
    @property
    def is_delayed(self) -> bool:
        if not self.expected_delivery or not self.delivered_at:
            from app.core.timeutils import utcnow
            if self.expected_delivery and utcnow().date() > self.expected_delivery:
                return True
        return False
    
    @property
    def lead_time_days(self) -> Optional[int]:
        if self.ordered_at and self.delivered_at:
            return (self.delivered_at.date() - self.ordered_at.date()).days
        return None


# =============================================================================
# VENDOR PERFORMANCE — Evidence-derived vendor performance
# =============================================================================

class VendorPerformance(Base, TimestampMixin):
    """
    Canonical Vendor Performance — evidence-derived vendor performance metrics.
    
    Derived from procurement history, delivery data, quality inspections,
    and financial outcomes. Feeds Operating Attention.
    """
    
    __tablename__ = "vendor_performance"
    __table_args__ = (
        Index("ix_vp_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vp_org_period", "organization_id", "period_start", "period_end"),
        UniqueConstraint(
            "organization_id", "vendor_id", "period_start", "period_end", "metric_kind",
            name="uq_vp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Period
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Metric
    metric_kind: Mapped[str] = mapped_column(String(50), nullable=False)  # on_time_delivery|quality|cost|lead_time|availability
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_unit: Mapped[str] = mapped_column(String(30), default="ratio")
    
    # Comparison
    target_value: Mapped[Optional[float]] = mapped_column(Float)
    variance: Mapped[Optional[float]] = mapped_column(Float)
    trend: Mapped[Optional[str]] = mapped_column(String(20))  # improving|stable|declining
    
    # Sample
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    
    # Evidence
    evidence_fingerprints: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    procurement_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# VENDOR DEPENDENCY — Derived dependency intelligence
# =============================================================================

class VendorDependency(Base, TimestampMixin):
    """
    Canonical Vendor Dependency — derived intelligence about vendor dependencies.
    
    These are DERIVED projections, not canonical truths. Feed Operating Attention.
    """
    
    __tablename__ = "vendor_dependencies"
    __table_args__ = (
        Index("ix_vd_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vd_org_criticality", "organization_id", "criticality"),
        Index("ix_vd_org_risk", "organization_id", "risk_level"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Dependency
    criticality: Mapped[str] = mapped_column(String(20), nullable=False)  # DEPENDENCY_CRITICALITY
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False)  # single_source|concentrated|distributed
    
    # Affected entities
    affected_resource_kinds_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_capability_categories_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_project_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_commitment_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_customer_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    affected_external_capacity_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Risk
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high|critical
    risk_kinds_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)  # VENDOR_RISK_KINDS
    risk_details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Substitution
    alternative_vendor_ids_json: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    substitution_cost_estimate: Mapped[Optional[float]] = mapped_column(Float)
    substitution_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer)
    substitution_feasibility: Mapped[str] = mapped_column(String(20), default="unknown")  # easy|moderate|difficult|impossible
    
    # Description
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detected_by: Mapped[str] = mapped_column(String(64), default="system")
    detection_method: Mapped[str] = mapped_column(String(50), default="derived")
    
    # Mitigation
    mitigation_status: Mapped[str] = mapped_column(String(20), default="open")  # open|mitigating|mitigated|monitoring
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text)
    mitigated_by: Mapped[Optional[str]] = mapped_column(String(64))
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Provenance
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# VENDOR OPERATING SLICE — Derived projection
# =============================================================================

class VendorOperatingSlice(Base, TimestampMixin):
    """
    Canonical Vendor Operating Slice — governed, point-in-time derived
    projection of all vendor/procurement/external-capacity reality.
    """
    
    __tablename__ = "vendor_operating_slices"
    __table_args__ = (
        Index("ix_vos_org_computed", "organization_id", "computed_at"),
        UniqueConstraint(
            "organization_id", "input_fingerprint",
            name="uq_vos_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Input fingerprint for exact-once
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Vendor summary
    vendors_by_kind: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    vendors_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    vendors_by_criticality: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    total_vendors: Mapped[int] = mapped_column(Integer, default=0)
    active_vendors: Mapped[int] = mapped_column(Integer, default=0)
    critical_vendors: Mapped[int] = mapped_column(Integer, default=0)
    
    # External capacity
    external_capacity_by_type: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    total_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    available_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    committed_external_capacity: Mapped[Optional[float]] = mapped_column(Float)
    
    # Procurement summary
    procurements_by_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    procurements_by_kind: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    active_procurements: Mapped[int] = mapped_column(Integer, default=0)
    delayed_procurements: Mapped[int] = mapped_column(Integer, default=0)
    overdue_procurements: Mapped[int] = mapped_column(Integer, default=0)
    
    # Financial
    total_committed_spend: Mapped[Optional[float]] = mapped_column(Float)
    total_actual_spend: Mapped[Optional[float]] = mapped_column(Float)
    pending_invoice_amount: Mapped[Optional[float]] = mapped_column(Float)
    
    # Performance
    avg_on_time_delivery: Mapped[Optional[float]] = mapped_column(Float)
    avg_quality_rate: Mapped[Optional[float]] = mapped_column(Float)
    avg_cost_variance: Mapped[Optional[float]] = mapped_column(Float)
    
    # Dependencies & Risks
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    vendor_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_vendor_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    contract_expiring_soon: Mapped[int] = mapped_column(Integer, default=0)
    
    # Computed metadata
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    computation_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)


# =============================================================================
# PROCUREMENT IMPACT ANALYSIS — Cross-domain impact
# =============================================================================

class ProcurementImpactAnalysis(Base, TimestampMixin):
    """
    Canonical Procurement Impact Analysis — cross-domain impact of procurement
    changes on resources, projects, commitments, customers, and financials.
    """
    
    __tablename__ = "procurement_impact_analyses"
    __table_args__ = (
        Index("ix_pia_org_trigger", "organization_id", "trigger_type"),
        Index("ix_pia_org_entity", "organization_id", "trigger_entity_type", "trigger_entity_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_pia_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Trigger
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # procurement_created|delayed|cancelled|vendor_changed|capacity_changed
    trigger_entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # procurement|vendor|external_capacity
    trigger_entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Impact scope
    affected_procurements: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_vendors: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_external_capacity: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_resources: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_allocations: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_demands: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_projects: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_commitments: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_objectives: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    affected_customers: Mapped[Optional[List[dict]]] = mapped_column(JSON, default=list)
    
    # Quantitative
    capacity_impact: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    budget_impact: Mapped[Optional[float]] = mapped_column(Float)
    revenue_impact: Mapped[Optional[float]] = mapped_column(Float)
    cost_impact: Mapped[Optional[float]] = mapped_column(Float)
    timeline_impact_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Risk
    risk_assessment: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    new_risks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    escalated_risks: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Scenarios
    scenario_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, default=list)
    
    # Metadata
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)