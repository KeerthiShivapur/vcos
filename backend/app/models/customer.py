"""Customer Relationship models (Phase 12 — Clients, CRM & External Ecosystem).

Customers are first-class citizens of the organization graph: accounts,
contacts, tags, notes, health, relationship links and the link tables that
connect customers to projects, meetings and documents — all tenant-scoped.
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


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "company_name", name="uq_customer_name_org"),
        Index("ix_customers_org", "organization_id"),
        Index("ix_customers_owner", "organization_id", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # prospect | customer | inactive
    status: Mapped[str] = mapped_column(String(20), default="customer")
    # enterprise | mid_market | smb | startup | government | nonprofit
    segment: Mapped[str] = mapped_column(String(20), default="mid_market")
    # basic | silver | gold | platinum | enterprise
    tier: Mapped[str] = mapped_column(String(20), default="basic")
    industry: Mapped[Optional[str]] = mapped_column(String(120))
    website: Mapped[Optional[str]] = mapped_column(String(300))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)
    # website | referral | marketing | events | cold_outreach | partner | advertisement
    source: Mapped[str] = mapped_column(String(30), default="website")
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    health_score: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(20), default="new")
    # when the last meaningful touchpoint happened (meeting, ticket, note)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    annual_value: Mapped[Optional[float]] = mapped_column(Float)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class CustomerAddress(Base, TimestampMixin):
    __tablename__ = "customer_addresses"
    __table_args__ = (Index("ix_cust_addr_customer", "organization_id", "customer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # billing | shipping | registered | headquarters
    kind: Mapped[str] = mapped_column(String(20), default="registered")
    line1: Mapped[Optional[str]] = mapped_column(String(255))
    line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    state: Mapped[Optional[str]] = mapped_column(String(120))
    postal_code: Mapped[Optional[str]] = mapped_column(String(40))
    country: Mapped[Optional[str]] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerContact(Base, TimestampMixin):
    __tablename__ = "customer_contacts"
    __table_args__ = (Index("ix_contact_customer", "organization_id", "customer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # ceo | cto | manager | finance | support | hr | legal | procurement | technical | other
    role: Mapped[str] = mapped_column(String(40), default="other")
    designation: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    linkedin: Mapped[Optional[str]] = mapped_column(String(300))
    timezone: Mapped[Optional[str]] = mapped_column(String(80))
    preferred_language: Mapped[str] = mapped_column(String(20), default="en")
    decision_maker: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class CustomerTag(Base, TimestampMixin):
    __tablename__ = "customer_tags"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_customer_tag_org"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="brand")


class CustomerNote(Base, TimestampMixin):
    __tablename__ = "customer_notes"
    __table_args__ = (Index("ix_cust_note_customer", "organization_id", "customer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[Optional[str]] = mapped_column(String(32))
    # note | call | email | meeting | follow_up | decision
    kind: Mapped[str] = mapped_column(String(20), default="note")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class CustomerRelationship(Base, TimestampMixin):
    __tablename__ = "customer_relationships"
    __table_args__ = (Index("ix_cust_rel_customer", "organization_id", "customer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # partner | vendor | investor | consultant | government | university | other
    relation_type: Mapped[str] = mapped_column(String(30), default="other")
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    entity_type: Mapped[Optional[str]] = mapped_column(String(30))
    name: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    # active | paused | ended
    status: Mapped[str] = mapped_column(String(20), default="active")


class CustomerHealth(Base, TimestampMixin):
    __tablename__ = "customer_health"
    __table_args__ = (UniqueConstraint("organization_id", "customer_id", name="uq_cust_health"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="new")
    renewal_probability: Mapped[float] = mapped_column(Float, default=50.0)
    factors: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    signals: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class CustomerProjectLink(Base, TimestampMixin):
    __tablename__ = "customer_project_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", "project_id", name="uq_cust_project"),
        Index("ix_cust_project_link", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # implementation | support | pilot | expansion | other
    kind: Mapped[str] = mapped_column(String(30), default="implementation")
    status: Mapped[str] = mapped_column(String(20), default="active")


class CustomerMeetingLink(Base, TimestampMixin):
    __tablename__ = "customer_meeting_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", "meeting_id", name="uq_cust_meeting"),
        Index("ix_cust_meeting_link", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # discovery | proposal | status | review | training | other
    kind: Mapped[str] = mapped_column(String(30), default="status")


class CustomerDocumentLink(Base, TimestampMixin):
    __tablename__ = "customer_document_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_id", "document_id", name="uq_cust_document"),
        Index("ix_cust_document_link", "organization_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # proposal | contract | requirement | faq | training | deployment | other
    kind: Mapped[str] = mapped_column(String(30), default="other")


class CustomerTimeline(Base, TimestampMixin):
    """Human-readable timeline entry for a customer (mirrors events, denormalized)."""

    __tablename__ = "customer_timeline"
    __table_args__ = (Index("ix_cust_timeline", "organization_id", "customer_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # lead.created | opportunity.won | contract.signed | ticket.created | ticket.resolved | meeting.recorded | note.added | customer.created | ...
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
