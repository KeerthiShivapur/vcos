"""Contract models (Phase 12.6 — Agreement & Renewal Lifecycle).

NDA, MSA, SOW, purchase orders, service agreements and SLAs with
approval, versioning, expiry, renewal and signature tracking.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"
    __table_args__ = (Index("ix_contracts_org", "organization_id"), Index("ix_contracts_customer", "organization_id", "customer_id"))

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    partner_id: Mapped[Optional[str]] = mapped_column(String(32))
    vendor_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # nda | msa | sow | purchase_order | service_agreement | sla | license | other
    contract_type: Mapped[str] = mapped_column(String(30), default="service_agreement")
    # draft | in_approval | signed | active | expiring | expired | terminated | renewed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    value: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_terms: Mapped[Optional[str]] = mapped_column(String(300))
    renewal_status: Mapped[str] = mapped_column(String(20), default="not_due")
    renewal_probability: Mapped[float] = mapped_column(Float, default=50.0)
    # draft | pending_approval | approved | rejected
    approval_status: Mapped[str] = mapped_column(String(20), default="draft")
    approver_id: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    signed_by: Mapped[Optional[str]] = mapped_column(String(200))
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # none | esign | manual | docusign
    signature_method: Mapped[str] = mapped_column(String(20), default="none")
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    description: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class ContractVersion(Base, TimestampMixin):
    __tablename__ = "contract_versions"
    __table_args__ = (Index("ix_contract_versions", "organization_id", "contract_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    change_note: Mapped[Optional[str]] = mapped_column(Text)
    editor_id: Mapped[Optional[str]] = mapped_column(String(32))
    content_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class ContractRenewal(Base, TimestampMixin):
    __tablename__ = "contract_renewals"
    __table_args__ = (Index("ix_contract_renewals", "organization_id", "contract_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    # planned | proposed | approved | signed | completed | declined
    status: Mapped[str] = mapped_column(String(20), default="planned")
    proposed_value: Mapped[Optional[float]] = mapped_column(Float)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(String(300))
