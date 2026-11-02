"""Finance & Business Operations models (Phase 13).

VCOS is the financial intelligence layer — these tables hold workflow
metadata and connections. The external accounting system remains the
source of truth for bookkeeping.
"""

from datetime import date, datetime
from decimal import Decimal
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


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        Index("ix_budgets_org_status", "organization_id", "status"),
        Index("ix_budgets_org_project", "organization_id", "project_id"),
        Index("ix_budgets_org_dept", "organization_id", "department_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # annual|quarterly|department|project|team|initiative|training|marketing|rnd|travel|it|other
    budget_type: Mapped[str] = mapped_column(String(30), default="annual")
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    allocated_amount: Mapped[float] = mapped_column(Float, default=0.0)
    used_amount: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    # draft|active|frozen|closed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    forecast_amount: Mapped[Optional[float]] = mapped_column(Float)
    # low|medium|high|critical
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    description: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class BudgetAllocation(Base, TimestampMixin):
    __tablename__ = "budget_allocations"
    __table_args__ = (Index("ix_budget_alloc_budget", "organization_id", "budget_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[str] = mapped_column(
        ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[Optional[str]] = mapped_column(String(20))  # e.g. "2026-Q1" or "2026-03"
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))


class BudgetRevision(Base, TimestampMixin):
    __tablename__ = "budget_revisions"
    __table_args__ = (Index("ix_budget_revisions_budget", "organization_id", "budget_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[str] = mapped_column(
        ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    previous_amount: Mapped[float] = mapped_column(Float, default=0.0)
    new_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))


class Expense(Base, TimestampMixin):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_expenses_org_status", "organization_id", "status"),
        Index("ix_expenses_org_employee", "organization_id", "employee_id"),
        Index("ix_expenses_org_project", "organization_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    # travel|food|office|software|hardware|training|marketing|client|cloud|miscellaneous
    expense_type: Mapped[str] = mapped_column(String(30), default="miscellaneous")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    incurred_at: Mapped[Optional[date]] = mapped_column(Date)
    merchant: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    budget_id: Mapped[Optional[str]] = mapped_column(ForeignKey("budgets.id", ondelete="SET NULL"))
    # draft|submitted|pending|approved|rejected|reimbursed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    approver_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    reimbursed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    receipt_url: Mapped[Optional[str]] = mapped_column(String(500))
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(32))  # expense id
    policy_flags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class PurchaseRequest(Base, TimestampMixin):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        Index("ix_purchase_requests_org_status", "organization_id", "status"),
        Index("ix_purchase_requests_org_project", "organization_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # laptop|monitor|software|furniture|services|cloud|training|equipment|marketing|other
    category: Mapped[str] = mapped_column(String(30), default="other")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    budget_id: Mapped[Optional[str]] = mapped_column(ForeignKey("budgets.id", ondelete="SET NULL"))
    # draft|submitted|manager_approved|finance_approved|approved|rejected|cancelled|ordered
    status: Mapped[str] = mapped_column(String(30), default="draft")
    approver_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    policy_flags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_org_status", "organization_id", "status"),
        Index("ix_purchase_orders_org_vendor", "organization_id", "vendor_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    purchase_request_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("purchase_requests.id", ondelete="SET NULL")
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    po_number: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    # draft|issued|accepted|partially_delivered|delivered|closed|cancelled
    status: Mapped[str] = mapped_column(String(30), default="draft")
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expected_delivery_at: Mapped[Optional[date]] = mapped_column(Date)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    external_reference: Mapped[Optional[str]] = mapped_column(String(120))
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("ix_vendors_org_status", "organization_id", "status"),
        UniqueConstraint("organization_id", "name", name="uq_vendor_name_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # supplier|vendor|consultant|contractor|partner
    kind: Mapped[str] = mapped_column(String(30), default="vendor")
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    website: Mapped[Optional[str]] = mapped_column(String(300))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    tax_id: Mapped[Optional[str]] = mapped_column(String(120))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(120))  # e.g. "net30"
    rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    performance_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|inactive|blacklisted
    description: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "contact_name": self.contact_name,
            "email": self.email,
            "phone": self.phone,
            "website": self.website,
            "country": self.country,
            "tax_id": self.tax_id,
            "payment_terms": self.payment_terms,
            "rating": self.rating,
            "performance_score": self.performance_score,
            "status": self.status,
            "description": self.description,
        }


class VendorContract(Base, TimestampMixin):
    __tablename__ = "vendor_contracts"
    __table_args__ = (
        Index("ix_vendor_contracts_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_contracts_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    renewal_status: Mapped[str] = mapped_column(String(20), default="not_due")  # not_due|due_soon|overdue
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|expiring|expired|terminated
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_org_status", "organization_id", "status"),
        Index("ix_invoices_org_vendor", "organization_id", "vendor_id"),
        Index("ix_invoices_org_customer", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # payable (vendor bills us) | receivable (we bill customers)
    direction: Mapped[str] = mapped_column(String(20), default="payable")
    vendor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    customer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    invoice_number: Mapped[Optional[str]] = mapped_column(String(120))
    reference_number: Mapped[Optional[str]] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    issued_at: Mapped[Optional[date]] = mapped_column(Date)
    due_at: Mapped[Optional[date]] = mapped_column(Date)
    # draft|pending|approved|paid|overdue|void|cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[Optional[str]] = mapped_column(String(120))
    external_system: Mapped[Optional[str]] = mapped_column(String(60))  # quickbooks|xero|sap|...
    external_id: Mapped[Optional[str]] = mapped_column(String(120))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_org_status", "organization_id", "status"),
        Index("ix_payments_org_invoice", "organization_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[Optional[str]] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    vendor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    # bank_transfer|credit_card|cheque|cash|erp_sync|other
    method: Mapped[str] = mapped_column(String(30), default="bank_transfer")
    # scheduled|pending|completed|failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reference: Mapped[Optional[str]] = mapped_column(String(120))
    external_id: Mapped[Optional[str]] = mapped_column(String(120))


class FinancialForecast(Base, TimestampMixin):
    __tablename__ = "financial_forecasts"
    __table_args__ = (Index("ix_forecasts_org_kind", "organization_id", "kind"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # cash_flow|budget_usage|expense|revenue|project_profitability
    kind: Mapped[str] = mapped_column(String(40), default="cash_flow")
    horizon_months: Mapped[int] = mapped_column(Integer, default=6)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    forecast_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    generated_by: Mapped[str] = mapped_column(String(30), default="worker")  # worker|manual|ai
    status: Mapped[str] = mapped_column(String(20), default="generated")


class FinancialMetric(Base, TimestampMixin):
    __tablename__ = "financial_metrics"
    __table_args__ = (
        Index("ix_financial_metrics_org_period", "organization_id", "period"),
        Index("ix_financial_metrics_org_type", "organization_id", "metric_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # revenue|expense|burn|runway|budget_usage|project_profitability|vendor_spend
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM
    value: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class FinanceIntegration(Base, TimestampMixin):
    __tablename__ = "finance_integrations"
    __table_args__ = (Index("ix_finance_integrations_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # sap|oracle|netsuite|dynamics|quickbooks|xero|tally|zoho|custom_erp|csv
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # rest|webhook|scheduled_sync|message_queue|csv_import
    integration_type: Mapped[str] = mapped_column(String(30), default="rest")
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="disabled")  # disabled|enabled|syncing|error
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


# =============================================================================
# GATE 27 — COMMERCIAL SUBSCRIPTION, PLAN, ENTITLEMENT, BILLING & PROVISIONING
# =============================================================================

# --- Plan Vocabulary ---
PLAN_INTERVALS = ("monthly", "annual")
PLAN_TIERS = ("starter", "professional", "enterprise", "custom")

# Subscription states
SUBSCRIPTION_STATES = (
    "trialing",
    "active",
    "past_due",
    "grace",
    "suspended",
    "cancelled",
    "expired",
)

# Entitlement keys (capability identifiers)
ENTITLEMENT_KEYS = (
    "employees.max",
    "storage.gb",
    "integrations.max",
    "api.calls.per_month",
    "ai.usage.per_month",
    "analytics.advanced",
    "governance.advanced",
    "security.advanced",
    "automation.workflows",
    "retention.days",
    "support.level",
    "workspace.advanced",
    "virtual_office.enabled",
    "sso.enabled",
    "audit_log.retention_days",
    "data_export.enabled",
    "custom_branding.enabled",
    "priority_support.enabled",
)

# Entitlement limit types
ENTITLEMENT_TYPES = ("limit", "boolean", "tier")

# Provisioning states
PROVISIONING_STATES = (
    "created",
    "provisioning",
    "validation",
    "ready",
    "active",
    "suspended",
    "deactivated",
)

# Billing interval types
BILLING_INTERVALS = ("monthly", "annual")

# Invoice states (extend existing)
INVOICE_STATES = (
    "draft",
    "issued",
    "due",
    "paid",
    "partially_paid",
    "past_due",
    "void",
    "cancelled",
)

# Payment states (extend existing)
PAYMENT_STATES = (
    "scheduled",
    "pending",
    "completed",
    "failed",
    "refunded",
    "partially_refunded",
)

# Provisioning step states
PROVISIONING_STEP_STATES = (
    "pending",
    "in_progress",
    "completed",
    "failed",
    "skipped",
)

# Payment provider types
PAYMENT_PROVIDERS = (
    "stripe",
    "paddle",
    "billing_internal",
    "manual",
)

# =============================================================================
# COMMERCIAL ACCOUNT — Organization's commercial identity
# =============================================================================

class CommercialAccount(Base, TimestampMixin):
    """
    Canonical Commercial Account — the organization's commercial identity
    and billing relationship with VCOS.
    
    One per organization. Contains billing contact, currency, tax info,
    and links to subscription.
    """
    
    __tablename__ = "commercial_accounts"
    __table_args__ = (
        Index("ix_comm_acc_org", "organization_id"),
        UniqueConstraint("organization_id", name="uq_comm_acc_org"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    
    # Billing contact
    billing_contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    billing_contact_email: Mapped[Optional[str]] = mapped_column(String(320))
    billing_contact_phone: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Address
    billing_address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    billing_address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    billing_city: Mapped[Optional[str]] = mapped_column(String(120))
    billing_state: Mapped[Optional[str]] = mapped_column(String(120))
    billing_postal_code: Mapped[Optional[str]] = mapped_column(String(30))
    billing_country: Mapped[Optional[str]] = mapped_column(String(2))
    
    # Tax
    tax_id: Mapped[Optional[str]] = mapped_column(String(60))
    tax_id_type: Mapped[Optional[str]] = mapped_column(String(30))  # vat|ein|gst|...
    tax_exempt: Mapped[bool] = mapped_column(default=False)
    tax_exempt_certificate: Mapped[Optional[str]] = mapped_column(String(120))
    
    # Currency & locale
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    locale: Mapped[str] = mapped_column(String(10), default="en")
    
    # Payment provider
    payment_provider: Mapped[Optional[str]] = mapped_column(String(30))  # stripe|paddle|manual
    payment_provider_customer_id: Mapped[Optional[str]] = mapped_column(String(120))
    payment_provider_account_id: Mapped[Optional[str]] = mapped_column(String(120))
    payment_method_token: Mapped[Optional[str]] = mapped_column(String(255))
    payment_method_type: Mapped[Optional[str]] = mapped_column(String(30))  # card|bank_transfer|...
    payment_method_details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    default_payment_method: Mapped[bool] = mapped_column(default=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|suspended|closed
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# PLAN — Commercial plan definition with entitlements
# =============================================================================

class Plan(Base, TimestampMixin):
    """
    Canonical Plan — defines a commercial tier with entitlements and limits.
    
    Plans are versioned. Entitlements are declarative and resolved at runtime.
    """
    
    __tablename__ = "plans"
    __table_args__ = (
        Index("ix_plans_active", "is_active"),
        UniqueConstraint("key", name="uq_plan_key"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    
    # Plan identity
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)  # starter|professional|enterprise|custom
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Tier
    tier: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # starter|professional|enterprise|custom
    
    # Pricing
    monthly_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    annual_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Billing intervals supported
    intervals: Mapped[List[str]] = mapped_column(JSON, default=list)  # ["monthly", "annual"]
    
    # Entitlements (declarative)
    # Structure: {"employees.max": {"type": "limit", "value": 50}, "storage.gb": {"type": "limit", "value": 100}, ...}
    entitlements: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Feature flags (what's included)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Limits (for display/UI)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    is_public: Mapped[bool] = mapped_column(default=True)  # Visible in plan selector
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Trial
    trial_days: Mapped[int] = mapped_column(default=14)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# ENTITLEMENT — Resolved capability for an organization
# =============================================================================

class Entitlement(Base, TimestampMixin):
    """
    Canonical Entitlement — a resolved capability/limit for an organization.
    
    Derived from Plan + Subscription + Overrides. This is what the system
    checks when enforcing limits and feature gates.
    """
    
    __tablename__ = "entitlements"
    __table_args__ = (
        Index("ix_entitlements_org_key", "organization_id", "key"),
        UniqueConstraint("organization_id", "key", name="uq_entitlement_org_key"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Entitlement key (e.g., "employees.max", "storage.gb", "ai.usage.per_month")
    key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    
    # Type: limit|boolean|tier
    entitlement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Current value
    # For limits: numeric value
    # For boolean: true/false
    # For tier: string tier name
    value: Mapped[Optional[str]] = mapped_column(String(120))
    numeric_value: Mapped[Optional[float]] = mapped_column(Float)
    boolean_value: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Source: plan|override|addon|promo
    source: Mapped[str] = mapped_column(String(20), default="plan")
    
    # Override info
    override_reason: Mapped[Optional[str]] = mapped_column(Text)
    override_by: Mapped[Optional[str]] = mapped_column(String(32))
    override_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Effective period
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# SUBSCRIPTION — Organization's subscription to a plan
# =============================================================================

class Subscription(Base, TimestampMixin):
    """
    Canonical Subscription — organization's active commercial relationship.
    
    One active subscription per organization at a time.
    Manages lifecycle: trial → active → past_due → grace → suspended → cancelled
    """
    
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_org", "organization_id"),
        Index("ix_subscriptions_plan", "plan_id"),
        Index("ix_subscriptions_renewal", "current_period_end"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    commercial_account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("commercial_accounts.id", ondelete="SET NULL"), index=True
    )
    
    # State machine
    state: Mapped[str] = mapped_column(String(20), default="trialing", index=True)  # SUBSCRIPTION_STATES
    previous_state: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Billing
    billing_interval: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly|annual
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Trial
    trial_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    trial_extended: Mapped[bool] = mapped_column(default=False)
    
    # Current period
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Renewal
    auto_renew: Mapped[bool] = mapped_column(default=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Grace period
    grace_period_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    in_grace_period: Mapped[bool] = mapped_column(default=False)
    
    # Payment
    payment_provider: Mapped[Optional[str]] = mapped_column(String(30))
    payment_provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(120))
    payment_method_id: Mapped[Optional[str]] = mapped_column(String(120))
    
    # Usage-based (if applicable)
    usage_based: Mapped[bool] = mapped_column(default=False)
    usage_threshold_cents: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Supersession for state changes
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)


# =============================================================================
# USAGE — Tracked usage against entitlements
# =============================================================================

class UsageRecord(Base, TimestampMixin):
    """
    Canonical Usage Record — tracks consumption of metered entitlements.
    
    Idempotent: same (organization_id, entitlement_key, period, event_id) = same record.
    """
    
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_org_entitlement_period", "organization_id", "entitlement_key", "period"),
        Index("ix_usage_org_period", "organization_id", "period"),
        UniqueConstraint(
            "organization_id", "entitlement_key", "period", "event_id",
            name="uq_usage_exact_once"
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )
    entitlement_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("entitlements.id", ondelete="SET NULL"), index=True
    )
    entitlement_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    
    # Period (e.g., "2024-01")
    period: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    
    # Quantity
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(20), default="units")
    
    # Idempotency
    event_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_source: Mapped[str] = mapped_column(String(40), default="system")  # system|api|worker|webhook
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# INVOICE — Extended for subscription billing
# =============================================================================

# (Existing Invoice model in finance.py already exists, we extend via SubscriptionInvoice link)


# =============================================================================
# SUBSCRIPTION INVOICE — Links subscription to invoice
# =============================================================================

class SubscriptionInvoice(Base, TimestampMixin):
    """
    Links a subscription billing event to an Invoice.
    
    One subscription period = one invoice (for recurring) or multiple (for usage-based).
    """
    
    __tablename__ = "subscription_invoices"
    __table_args__ = (
        Index("ix_sub_inv_subscription", "subscription_id"),
        Index("ix_sub_inv_invoice", "invoice_id"),
        UniqueConstraint("subscription_id", "period_start", "period_end", name="uq_sub_inv_period"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invoice_id: Mapped[str] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Billing period
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Amounts
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Breakdown
    line_items: Mapped[list] = mapped_column(JSON, default=list)  # [{"key", "description", "quantity", "unit_price_cents", "total_cents"}]
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="draft")  # INVOICE_STATES


# =============================================================================
# SUBSCRIPTION PAYMENT — Links payment to subscription
# =============================================================================

class SubscriptionPayment(Base, TimestampMixin):
    """
    Links a payment to a subscription invoice.
    """
    
    __tablename__ = "subscription_payments"
    __table_args__ = (
        Index("ix_sub_pay_subscription", "subscription_id"),
        Index("ix_sub_pay_invoice", "subscription_invoice_id"),
        Index("ix_sub_pay_payment", "payment_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_invoice_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscription_invoices.id", ondelete="SET NULL"), index=True
    )
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    # Amount applied
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # PAYMENT_STATES


# =============================================================================
# PROVISIONING — Company onboarding & setup
# =============================================================================

class Provisioning(Base, TimestampMixin):
    """
    Canonical Provisioning — tracks the end-to-end company onboarding lifecycle.
    
    States: created → provisioning → validation → ready → active → suspended → deactivated
    """
    
    __tablename__ = "provisionings"
    __table_args__ = (
        Index("ix_prov_org", "organization_id"),
        Index("ix_prov_state", "state"),
        UniqueConstraint("organization_id", name="uq_prov_org"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )
    commercial_account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("commercial_accounts.id", ondelete="SET NULL"), index=True
    )
    
    # State machine
    state: Mapped[str] = mapped_column(String(40), default="created", index=True)  # PROVISIONING_STATES
    previous_state: Mapped[Optional[str]] = mapped_column(String(40))
    
    # Steps
    # [{"step": "commercial_account", "state": "completed", "completed_at": "...", "error": null}, ...]
    steps: Mapped[list] = mapped_column(JSON, default=list)
    
    # Current step
    current_step: Mapped[Optional[str]] = mapped_column(String(60))
    
    # Administrator
    admin_user_id: Mapped[Optional[str]] = mapped_column(String(32))
    admin_email: Mapped[Optional[str]] = mapped_column(String(320))
    
    # Domain verification
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    domain_verified: Mapped[bool] = mapped_column(default=False)
    domain_verification_token: Mapped[Optional[str]] = mapped_column(String(120))
    domain_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Security policy applied
    security_policy_applied: Mapped[bool] = mapped_column(default=False)
    
    # Employee import
    employees_imported: Mapped[int] = mapped_column(default=0)
    employees_total: Mapped[int] = mapped_column(default=0)
    
    # Integrations configured
    integrations_configured: Mapped[int] = mapped_column(default=0)
    integrations_total: Mapped[int] = mapped_column(default=0)
    
    # Company import
    company_import_completed: Mapped[bool] = mapped_column(default=False)
    company_import_records: Mapped[int] = mapped_column(default=0)
    
    # Validation
    validation_passed: Mapped[bool] = mapped_column(default=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Activation
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Suspension/Deactivation
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[Optional[str]] = mapped_column(Text)
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deactivated_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# PROVISIONING STEP — Individual onboarding step
# =============================================================================

class ProvisioningStep(Base, TimestampMixin):
    """
    Individual step in the provisioning lifecycle.
    """
    
    __tablename__ = "provisioning_steps"
    __table_args__ = (
        Index("ix_prov_step_prov", "provisioning_id"),
        Index("ix_prov_step_state", "state"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    provisioning_id: Mapped[str] = mapped_column(
        ForeignKey("provisionings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    step: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # commercial_account|admin_user|security|domain|employees|integrations|import|validation|activation
    state: Mapped[str] = mapped_column(String(20), default="pending")  # PROVISIONING_STEP_STATES
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    
    # Output
    output_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# PAYMENT PROVIDER CONFIG — Organization's payment provider config
# =============================================================================

class PaymentProviderConfig(Base, TimestampMixin):
    """
    Organization's payment provider configuration.
    """
    
    __tablename__ = "payment_provider_configs"
    __table_args__ = (
        Index("ix_ppc_org", "organization_id"),
        UniqueConstraint("organization_id", "provider", name="uq_ppc_org_provider"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # stripe|paddle|billing_internal|manual
    
    # Credentials (encrypted)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    
    # Configuration
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="disabled")  # disabled|enabled|error
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Webhook
    webhook_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    webhook_events: Mapped[list] = mapped_column(JSON, default=list)
    
    # Default
    is_default: Mapped[bool] = mapped_column(default=False)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


class SubscriptionEvent(Base, TimestampMixin):
    """
    Audit trail for subscription lifecycle events.
    """
    
    __tablename__ = "subscription_events"
    __table_args__ = (
        Index("ix_sub_evt_org", "organization_id"),
        Index("ix_sub_evt_sub", "subscription_id"),
        Index("ix_sub_evt_type", "event_type"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # created|trial_started|activated|renewed|upgraded|downgraded|cancelled|past_due|grace|suspended|reactivated|payment_succeeded|payment_failed
    
    # State transition
    from_state: Mapped[Optional[str]] = mapped_column(String(20))
    to_state: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user|system|webhook|admin
    
    # Details
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Billing context
    amount_cents: Mapped[Optional[int]] = mapped_column(Integer)
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    invoice_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# USAGE AGGREGATION — Pre-computed usage totals for billing
# =============================================================================

class UsageAggregation(Base, TimestampMixin):
    """
    Pre-computed usage aggregation for a billing period.
    
    Represents the deterministic aggregation of UsageRecord into billable quantities.
    Versioned for audit trail and re-aggregation safety.
    """
    
    __tablename__ = "usage_aggregations"
    __table_args__ = (
        Index("ix_usage_agg_org_period", "organization_id", "period"),
        Index("ix_usage_agg_org_metric_period", "organization_id", "metric_code", "period"),
        UniqueConstraint("organization_id", "metric_code", "period", name="uq_usage_agg_unique"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )
    
    # Period (YYYY-MM)
    period: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    
    # Metric
    metric_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    
    # Aggregated quantity
    total_quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Aggregation metadata
    aggregation_type: Mapped[str] = mapped_column(String(20), default="sum")  # sum|max|avg|count
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# PRICING RULES — Versioned pricing configuration
# =============================================================================

class PricingRule(Base, TimestampMixin):
    """
    Versioned pricing rule for a metric on a plan.
    
    Supports per-unit, tiered, included allowance, flat fee, and percentage models.
    Versioned to prevent retroactive repricing of historical usage.
    """
    
    __tablename__ = "pricing_rules"
    __table_args__ = (
        Index("ix_pricing_rule_plan", "plan_id"),
        Index("ix_pricing_rule_metric", "metric_code"),
        UniqueConstraint("plan_id", "metric_code", "version", name="uq_pricing_rule_version"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    
    metric_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(20), nullable=False)  # per_unit|tiered|included_allowance|flat_fee|percentage
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Per-unit pricing
    unit_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Included allowance + overage pricing
    overage_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Flat fee pricing
    flat_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Percentage pricing
    base_amount_cents: Mapped[Optional[int]] = mapped_column(Integer)
    percentage: Mapped[Optional[Decimal]] = mapped_column(default=None)
    
    # Tiered pricing
    tiers: Mapped[List[dict]] = mapped_column(JSON, default=list)
    # [
    #   {"start_quantity": 0, "end_quantity": 100, "price_cents": 100},
    #   {"start_quantity": 100, "end_quantity": null, "price_cents": 80}
    # ]
    
    # Effective dates
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    
    # Metadata
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# =============================================================================
# PRICING RULE VERSION — Audit trail for pricing rule changes
# =============================================================================

class PricingRuleVersion(Base, TimestampMixin):
    """
    Immutable audit record of pricing rule versions.
    
    Captures full rule state at each version for audit and reproducibility.
    """
    
    __tablename__ = "pricing_rule_versions"
    __table_args__ = (
        Index("ix_prv_rule", "pricing_rule_id"),
        Index("ix_prv_plan", "plan_id"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    pricing_rule_id: Mapped[str] = mapped_column(
        ForeignKey("pricing_rules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_code: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    
    # Full rule snapshot
    model: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    overage_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    flat_price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    base_amount_cents: Mapped[Optional[int]] = mapped_column(Integer)
    percentage: Mapped[Optional[Decimal]] = mapped_column(default=None)
    tiers: Mapped[List[dict]] = mapped_column(JSON, default=list)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Audit
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
