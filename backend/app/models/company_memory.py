"""Company Memory models."""

from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


# Memory type constants
MEMORY_TYPES = [
    "fact", "decision", "pattern", "lesson", "policy", "context",
    "milestone", "innovation", "risk", "opportunity", "meeting", "conversation"
]

MEMORY_TYPES_SET = set(MEMORY_TYPES)


class CompanyMemory(Base, TimestampMixin):
    __tablename__ = "company_memory"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # fact, decision, pattern, lesson, policy, context
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # document, meeting, decision, event, conversation, system
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companymemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_memory_org_type", "organization_id", "memory_type"),
        Index("ix_company_memory_org_confidence", "organization_id", "confidence"),
        Index("ix_company_memory_org_valid", "organization_id", "valid_from", "valid_until"),
    )


class OrganizationContext(Base, TimestampMixin):
    __tablename__ = "organization_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # strategic, operational, cultural, technical, financial
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60), default="system", nullable=False)  # system, user, ai, external
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)  # organization, department, team, project
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    companymemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "context_type", "key", "version", name="uq_org_context_type_key_version"),
        Index("ix_org_context_org_type", "organization_id", "context_type"),
        Index("ix_org_context_org_active", "organization_id", "is_active"),
    )


class OrganizationTimeline(Base, TimestampMixin):
    __tablename__ = "organization_timeline"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # milestone, decision, hire, departure, funding, acquisition, crisis, achievement
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_date_precision: Mapped[str] = mapped_column(String(20), default="day", nullable=False)  # year, month, day, hour, minute
    significance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    entities_involved: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(40), default="system", nullable=False)  # system, user, ai, external
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companymemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_org_timeline_org_date", "organization_id", "event_date"),
        Index("ix_org_timeline_org_type", "organization_id", "event_type"),
    )


class MemoryEvent(Base, TimestampMixin):
    """Event in company memory timeline."""

    __tablename__ = "memory_events"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # milestone, decision, hire, departure, funding, acquisition, crisis, achievement
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_date_precision: Mapped[str] = mapped_column(String(20), default="day", nullable=False)  # year, month, day, hour, minute
    significance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    entities_involved: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(40), default="system", nullable=False)  # system, user, ai, external
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companymemory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_memory_events_org_date", "organization_id", "event_date"),
        Index("ix_org_timeline_org_type", "organization_id", "event_type"),
        {"extend_existing": True},
    )


class MemoryOutcome(Base, TimestampMixin):
    """Outcome assessment for a memory event."""

    __tablename__ = "memory_outcomes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(40), nullable=False)  # achieved, partial, missed, exceeded
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)
    actual_outcome: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    assessed_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_memory_outcome_org_event", "organization_id", "event_id"),
        {"extend_existing": True},
    )