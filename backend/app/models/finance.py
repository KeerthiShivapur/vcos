"""Finance & Business Operations models (Phase 13).

VCOS is the financial intelligence layer — these tables hold workflow
metadata and connections. The external accounting system remains the
source of truth for bookkeeping.
"""

from datetime import date, datetime
from typing import Any, Optional

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
