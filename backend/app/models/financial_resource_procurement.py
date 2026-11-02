"""Financial Resource Procurement models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ResourceKind(str):
    PERSONNEL = "personnel"
    EQUIPMENT = "equipment"
    SOFTWARE = "software"
    INFRASTRUCTURE = "infrastructure"
    FACILITIES = "facilities"
    SERVICES = "services"
    MATERIALS = "materials"
    BUDGET = "budget"


class ResourceState(str):
    REQUESTED = "requested"
    APPROVED = "approved"
    ORDERED = "ordered"
    DELIVERED = "delivered"
    ACTIVE = "active"
    RETIRED = "retired"
    CANCELLED = "cancelled"


class AllocationState(str):
    PLANNED = "planned"
    COMMITTED = "committed"
    ACTIVE = "active"
    RELEASED = "released"
    CANCELLED = "cancelled"


class ProcurementKind(str):
    PURCHASE = "purchase"
    LEASE = "lease"
    SUBSCRIPTION = "subscription"
    RENTAL = "rental"
    CONTRACT = "contract"
    INTERNAL = "internal"


class ProcurementState(str):
    REQUESTED = "requested"
    APPROVED = "approved"
    SOURCING = "sourcing"
    NEGOTIATING = "negotiating"
    ORDERED = "ordered"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BudgetKind(str):
    OPERATIONAL = "operational"
    CAPITAL = "capital"
    PROJECT = "project"
    DEPARTMENT = "department"
    CONTINGENCY = "contingency"


class BudgetState(str):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    ACTIVE = "active"
    CLOSED = "closed"
    EXCEEDED = "exceeded"


class AllocationState(str):
    PLANNED = "planned"
    COMMITTED = "committed"
    ACTIVE = "active"
    RELEASED = "released"
    CANCELLED = "cancelled"


class FinancialTransactionKind(str):
    PURCHASE = "purchase"
    EXPENSE = "expense"
    REVENUE = "revenue"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class FinancialTransactionState(str):
    PENDING = "pending"
    APPROVED = "approved"
    POSTED = "posted"
    RECONCILED = "reconciled"
    VOIDED = "voided"


class ResourceRequirement(Base, TimestampMixin):
    __tablename__ = "resource_requirements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30), default=ResourceKind.PERSONNEL, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), default="each", nullable=False)
    specifications: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    estimated_cost: Mapped[Optional[float]] = mapped_column(default=None)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_by: Mapped[Optional[date]] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="requested", nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resourcekind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_resource_reqs_org_status", "organization_id", "status"),
        Index("ix_resource_reqs_org_kind", "organization_id", "kind"),
    )


class ResourceAllocationRecord(Base, TimestampMixin):
    __tablename__ = "resource_allocations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requirement_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("resource_requirements.id", ondelete="SET NULL"), index=True
    )
    resource_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    resource_kind: Mapped[str] = mapped_column(String(30), default="personnel", nullable=False)
    allocated_to_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, department, team, employee
    allocated_to_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    cost_per_unit: Mapped[Optional[float]] = mapped_column(default=None)
    total_cost: Mapped[Optional[float]] = mapped_column(default=None)
    state: Mapped[str] = mapped_column(String(24), default=AllocationState.PLANNED, nullable=False)
    allocated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resourcekind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_resource_allocs_org_dates", "organization_id", "start_date", "end_date"),
        Index("ix_resource_allocs_org_resource", "organization_id", "resource_id"),
        {"extend_existing": True},
    )


class ProcurementRecord(Base, TimestampMixin):
    __tablename__ = "procurement_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requirement_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("resource_requirements.id", ondelete="SET NULL"), index=True
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30), default=ProcurementKind.PURCHASE, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), default="each", nullable=False)
    unit_cost_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    unit_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    total_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    state: Mapped[str] = mapped_column(String(24), default=ProcurementState.REQUESTED, nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ordered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    vendor_name: Mapped[Optional[str]] = mapped_column(String(200))
    vendor_contact: Mapped[Optional[str]] = mapped_column(String(300))
    contract_reference: Mapped[Optional[str]] = mapped_column(String(200))
    invoice_reference: Mapped[Optional[str]] = mapped_column(String(200))
    resourcekind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_procurement_records_org_state", "organization_id", "state"),
        Index("ix_procurement_records_org_vendor", "organization_id", "vendor_id"),
    )


class BudgetCommitmentRecord(Base, TimestampMixin):
    __tablename__ = "budget_commitments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    budget_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    commitment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[Optional[int]] = mapped_column(Integer)
    month: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    committed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resourcekind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_budget_commitments_org_year", "organization_id", "fiscal_year"),
        Index("ix_budget_commitments_org_state", "organization_id", "status"),
    )


class FinancialOutcomeRecord(Base, TimestampMixin):
    __tablename__ = "financial_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # purchase, expense, revenue, transfer, adjustment
    transaction_kind: Mapped[str] = mapped_column(String(40), nullable=False)  # purchase, expense, revenue, transfer, adjustment
    amount_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    vendor_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    invoice_reference: Mapped[Optional[str]] = mapped_column(String(200))
    resourcekind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_financial_outcomes_org_date", "organization_id", "occurred_at"),
        Index("ix_financial_outcomes_org_type", "organization_id", "transaction_type"),
    )


RESOURCE_KINDS = [ResourceKind.PERSONNEL, ResourceKind.EQUIPMENT, ResourceKind.SOFTWARE, ResourceKind.INFRASTRUCTURE, ResourceKind.FACILITIES, ResourceKind.SERVICES, ResourceKind.MATERIALS, ResourceKind.BUDGET]
RESOURCE_STATES = [ResourceState.REQUESTED, ResourceState.APPROVED, ResourceState.ORDERED, ResourceState.DELIVERED, ResourceState.ACTIVE, ResourceState.RETIRED, ResourceState.CANCELLED]
ALLOCATION_STATES = [AllocationState.PLANNED, AllocationState.COMMITTED, AllocationState.ACTIVE, AllocationState.RELEASED, AllocationState.CANCELLED]
PROCUREMENT_KINDS = [ProcurementKind.PURCHASE, ProcurementKind.LEASE, ProcurementKind.SUBSCRIPTION, ProcurementKind.RENTAL, ProcurementKind.CONTRACT, ProcurementKind.INTERNAL]
PROCUREMENT_STATES = [ProcurementState.REQUESTED, ProcurementState.APPROVED, ProcurementState.SOURCING, ProcurementState.NEGOTIATING, ProcurementState.ORDERED, ProcurementState.DELIVERED, ProcurementState.COMPLETED, ProcurementState.CANCELLED]
BUDGET_KINDS = [BudgetKind.OPERATIONAL, BudgetKind.CAPITAL, BudgetKind.PROJECT, BudgetKind.DEPARTMENT, BudgetKind.CONTINGENCY]
BUDGET_STATES = [BudgetState.DRAFT, BudgetState.PROPOSED, BudgetState.APPROVED, BudgetState.ACTIVE, BudgetState.CLOSED, BudgetState.EXCEEDED]
FINANCIAL_TRANSACTION_KINDS = [FinancialTransactionKind.PURCHASE, FinancialTransactionKind.EXPENSE, FinancialTransactionKind.REVENUE, FinancialTransactionKind.TRANSFER, FinancialTransactionKind.ADJUSTMENT]
FINANCIAL_TRANSACTION_STATES = [FinancialTransactionState.PENDING, FinancialTransactionState.APPROVED, FinancialTransactionState.POSTED, FinancialTransactionState.RECONCILED, FinancialTransactionState.VOIDED]


class FinancialOperatingSlice(Base, TimestampMixin):
    """Financial operating slice for resource allocation."""
    __tablename__ = "financial_operating_slices"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slice_type: Mapped[str] = mapped_column(String(40), nullable=False)  # budget, forecast, actual
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    slice_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    financialoperatingslice_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_fin_os_org_period", "organization_id", "period_start", "period_end"),
        {"extend_existing": True},
    )


class FinancialImpactAnalysis(Base, TimestampMixin):
    """Financial impact analysis for resource allocation decisions."""
    __tablename__ = "financial_impact_analyses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    allocation_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    impact_type: Mapped[str] = mapped_column(String(40), nullable=False)  # cost, revenue, roi, cash_flow
    estimated_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    assumptions: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    financialresourceprocurement_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_fin_impact_org_allocation", "organization_id", "allocation_id"),
        {"extend_existing": True},
    )