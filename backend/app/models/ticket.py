"""Support ticket models (Phase 12.8 — Customer Support).

Tickets, incidents, requests, bug reports, feature requests, escalations,
priority, resolution and knowledge links — the pulse of the support function.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_tickets_org", "organization_id"),
        Index("ix_tickets_status", "organization_id", "status", "priority"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(String(32))
    project_id: Mapped[Optional[str]] = mapped_column(String(32))
    # incident | bug | feature_request | question | escalation | service_request
    category: Mapped[str] = mapped_column(String(30), default="question")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # open | in_progress | waiting_customer | escalated | resolved | closed
    status: Mapped[str] = mapped_column(String(20), default="open")
    # low | medium | high | urgent
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    assignee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    reporter_id: Mapped[Optional[str]] = mapped_column(String(32))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    root_cause: Mapped[Optional[str]] = mapped_column(String(255))
    # how many minutes the SLA allowed for first response / resolution
    sla_first_response_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    sla_resolution_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    first_responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # external: raised through the customer portal
    via_portal: Mapped[bool] = mapped_column(Boolean, default=False)
    portal_user_id: Mapped[Optional[str]] = mapped_column(String(32))
    # duplicate of another ticket
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(32))
    satisfaction_rating: Mapped[Optional[int]] = mapped_column(Integer)
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class TicketKnowledgeLink(Base, TimestampMixin):
    __tablename__ = "ticket_knowledge_links"
    __table_args__ = (Index("ix_ticket_knowledge", "organization_id", "ticket_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[str] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(String(32), nullable=False)
    document_title: Mapped[Optional[str]] = mapped_column(String(300))
    # suggested | attached | resolved_by
    kind: Mapped[str] = mapped_column(String(20), default="suggested")
