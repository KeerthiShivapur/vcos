"""Phase 19 — Company Memory, Organization Timeline & Universal Context models.

The company memory layer makes the organization's history permanent: major
decisions, lessons learned, milestones, policies, innovations and executive
decisions are captured as memories; the organization timeline records every
meaningful event across all modules so users can travel through company
history; the context engine links entities across modules so context flows
automatically (meeting -> project -> knowledge -> tasks -> dashboard).

Slice 4D.3 (organizational memory automation) extends ``CompanyMemory`` with
the evidence-backed memory semantics: memory categories (event / experience /
lesson / outcome), evidence lineage (``evidence_json``, ``source_event_ids``),
context snapshots (``context_json``), lessons, outcomes, confidence and
governance-scoped visibility (``auth_scope`` / ``auth_project_id``). The
``MemoryEvent`` and ``MemoryOutcome`` tables record which events fed a memory
(idempotent, replay-safe) and how a memory's outcome was later observed.
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

# --- Slice 4D.3 taxonomy ---------------------------------------------------

# Memory categories: how a memory was formed / what it represents.
MEMORY_CATEGORIES = ("event", "experience", "lesson", "outcome")

# Canonical domains for automated memories (extensible; mirrors the event catalog).
MEMORY_DOMAINS = (
    "decision", "project", "task", "milestone", "approval", "policy",
    "document", "meeting", "incident", "customer", "release",
    "architecture", "process", "employee", "governance",
)

# Outcome observations for outcome memories.
OUTCOME_TYPES = ("positive", "negative", "partial", "unresolved")
OUTCOME_TYPES_VALID = frozenset(OUTCOME_TYPES)

# Fact/observation/inference/lesson safety distinction — VCOS never presents
# inference as fact; lessons are labeled as such and always carry evidence.
FACT_KINDS = ("fact", "observation", "inference", "lesson")

# Lifecycle status for automated memories.
MEMORY_STATUSES = ("active", "superseded", "archived")


class CompanyMemory(Base, TimestampMixin):
    """A permanent organizational memory entry (Phase 19.1, extended in 4D.3)."""

    __tablename__ = "company_memory"
    __table_args__ = (
        Index("ix_company_memory_org_type", "organization_id", "memory_type"),
        Index("ix_company_memory_org_importance", "organization_id", "importance"),
        Index(
            "ix_company_memory_org_category", "organization_id", "memory_category"
        ),
        Index("ix_company_memory_org_dedupe", "organization_id", "dedupe_key"),
        Index(
            "ix_company_memory_org_auth",
            "organization_id",
            "auth_scope",
            "auth_project_id",
        ),
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

    # --- Slice 4D.3: organizational memory automation -----------------------
    # event | experience | lesson | outcome
    memory_category: Mapped[str] = mapped_column(String(16), default="event")
    # canonical domain: decision | project | task | ... (from the event catalog)
    domain: Mapped[str] = mapped_column(String(30), default="event")
    # human-readable summary of the experience (evidence-backed short form)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # context snapshot: {"project": {...}, "task": {...}, "dependencies": [...]}
    context_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # evidence lineage: [{"type": "task", "id": "...", "relationship": "blocked_task"}]
    evidence_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, default=list
    )
    # lesson derived for lesson memories (never presented as fact)
    lesson: Mapped[Optional[str]] = mapped_column(Text)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    # positive | negative | partial | unresolved
    outcome_type: Mapped[Optional[str]] = mapped_column(String(16))
    # 1.0 = structured evidence · 0.6 = multiple corroborating evidence ·
    # 0.3 = semantic inference (never presented as fact)
    confidence: Mapped[float] = mapped_column(Float, default=0.3)
    # fact | observation | inference | lesson
    fact_kind: Mapped[str] = mapped_column(String(16), default="fact")
    # origin events (deduplicated event ids that fed this memory)
    source_event_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # deterministic deduplication key (org-scoped), e.g. "task.blocked:<task_id>"
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(255))
    # governance scope inherited from evidence:
    #   org -> organization-wide | project -> project-scoped | personal -> personal
    auth_scope: Mapped[str] = mapped_column(String(16), default="org")
    auth_project_id: Mapped[Optional[str]] = mapped_column(String(32))
    auth_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    # active | superseded | archived
    status: Mapped[str] = mapped_column(String(16), default="active")
    # when a later event contradicts / replaces this memory, point at successor
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32))
    # related memories discovered through semantic similarity
    related_memory_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)


class MemoryEvent(Base, TimestampMixin):
    """Lineage link between a memory and the events that formed it (Slice 4D.3).

    ``event_id`` is unique organization-wide: a single event can only ever
    contribute to one memory, which makes the formation pipeline idempotent
    and replay-safe even if the worker runs twice for the same event.
    """

    __tablename__ = "memory_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_memory_events_event_id"),
        Index("ix_memory_events_org", "organization_id"),
        Index("ix_memory_events_memory", "memory_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("company_memory.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # how the event relates to the memory, e.g. "formation" | "outcome" | "update"
    relationship: Mapped[str] = mapped_column(String(20), default="formation")


class MemoryOutcome(Base, TimestampMixin):
    """Observed outcome of a memory (Slice 4D.3 outcome feedback loop).

    Each row is one application of a lesson/experience to an entity with its
    observed outcome. The memory itself records only the latest outcome;
    this table keeps the full outcome history so confidence evolution is
    traceable. No operating-layer mutation is performed — outcomes are
    observed from events, never written by the memory layer itself.
    """

    __tablename__ = "memory_outcomes"
    __table_args__ = (
        Index("ix_memory_outcomes_memory", "memory_id"),
        Index("ix_memory_outcomes_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("company_memory.id", ondelete="CASCADE"), nullable=False
    )
    # entity the lesson/experience was applied to (task, project, ...)
    applied_entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    applied_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    outcome_type: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    # events that produced this outcome observation
    evidence_json: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON, default=list
    )
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
