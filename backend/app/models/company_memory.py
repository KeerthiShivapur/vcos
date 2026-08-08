"""Phase 19 — Company Memory, Organization Timeline & Universal Context models.

The company memory layer makes the organization's history permanent: major
decisions, lessons learned, milestones, policies, innovations and executive
decisions are captured as memories; the organization timeline records every
meaningful event across all modules so users can travel through company
history; the context engine links entities across modules so context flows
automatically (meeting -> project -> knowledge -> tasks -> dashboard).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

MEMORY_TYPES = (
    "decision", "lesson", "milestone", "policy", "innovation",
    "architecture", "success", "failure", "customer", "meeting_outcome",
    "executive_decision", "institutional",
)
MEMORY_IMPORTANCES = ("low", "medium", "high", "critical")


class CompanyMemory(Base, TimestampMixin):
    """A permanent organizational memory entry (Phase 19.1)."""

    __tablename__ = "company_memory"
    __table_args__ = (
        Index("ix_company_memory_org_type", "organization_id", "memory_type"),
        Index("ix_company_memory_org_importance", "organization_id", "importance"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(30), default="institutional")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    importance: Mapped[str] = mapped_column(String(20), default="medium")
    # linked entity (project/task/decision/meeting/document...) so memory is traversable
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    source_event: Mapped[Optional[str]] = mapped_column(String(120))
    recorded_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class OrganizationTimeline(Base, TimestampMixin):
    """One entry in the organization-wide company timeline (Phase 19.2)."""

    __tablename__ = "organization_timeline"
    __table_args__ = (
        Index("ix_org_timeline_org_date", "organization_id", "occurred_at"),
        Index("ix_org_timeline_org_type", "organization_id", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # hiring | projects | releases | meetings | knowledge | learning | community
    # | innovation | customers | finance | leadership | system | health
    category: Mapped[str] = mapped_column(String(30), default="system")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)


class OrganizationContext(Base, TimestampMixin):
    """A context bundle linking an entity to related organizational items (Phase 19.3)."""

    __tablename__ = "organization_context"
    __table_args__ = (
        Index("ix_org_context_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # related items: {"projects": [...], "meetings": [...], "knowledge": [...]}
    related: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    freshness: Mapped[float] = mapped_column(Float, default=1.0)
    built_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
