"""Partner & vendor models (Phase 12.9/12.10 — External Ecosystem).

Partners (technology, business, consultants, resellers, distributors,
universities, government) and vendors (suppliers with contracts, invoices,
assets, compliance and performance) — all tenant-scoped graph citizens.
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


class Partner(Base, TimestampMixin):
    __tablename__ = "partners"
    __table_args__ = (Index("ix_partners_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # partner | vendor | consultant | supplier | reseller | distributor | government | university
    kind: Mapped[str] = mapped_column(String(20), default="partner")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(300))
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # technology | business | consulting | referral | integration | channel
    partner_type: Mapped[Optional[str]] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    started_at: Mapped[Optional[date]] = mapped_column(Date)
    performance_score: Mapped[Optional[int]] = mapped_column(Integer)
    # for vendors: on-time delivery / quality/compliance rating
    rating: Mapped[Optional[float]] = mapped_column(Float)
    payment_terms: Mapped[Optional[str]] = mapped_column(String(120))
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class PartnerContact(Base, TimestampMixin):
    __tablename__ = "partner_contacts"
    __table_args__ = (Index("ix_partner_contacts", "organization_id", "partner_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(60))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class PartnerContractLink(Base, TimestampMixin):
    __tablename__ = "partner_contract_links"
    __table_args__ = (Index("ix_partner_contracts", "organization_id", "partner_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[str] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[str] = mapped_column(String(32), nullable=False)
