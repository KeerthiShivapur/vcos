"""Slice 4F.4 — Ownership & Responsibility Intelligence.

The canonical, temporal record of who is responsible for what in the
organization. One table answers "who owns X", "who owned X six months ago",
"who takes over when the owner leaves" and "where is ownership missing or
dangerously concentrated" — without ever overwriting history (a change closes
the old window and opens a new one) and without inventing owners.

The model is deliberately separate from:
  - EXPERTISE (4F.2/4F.3): what someone knows / how trustworthy it is.
  - DELEGATION (4C): who may act. 4F.4 reads delegations read-only so the
    continuity story always reflects the governed reality.
  - TASK OWNERSHIP (4A) and PROJECT/GOAL ownership fields: existing app
    data lands here as DECLARED evidence via change-driven handlers, but this
    is the single canonical view with time windows, backup, escalation and
    history that the app's per-entity columns do not provide.

Scalability rule: every read is a bounded indexed lookup; every write is a
single window close + open. No full rescan: analysis runs in bounded batches
with explicit continuation, and change events reconcile exactly-once.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# Responsibility types (canonical, fixed vocabulary).
RESPONSIBILITY_TYPES: tuple[str, ...] = (
    "primary",        # the single accountable owner of an object
    "operational",    # day-to-day operation
    "technical",      # technical/architecture decisions
    "business",       # business outcomes
    "knowledge",      # canonical knowledge of a topic
    "decision",       # decision authority
    "customer",       # customer relationship
    "backup",         # explicit fallback when the primary is unavailable
    "delegated",      # 4C delegation of authority at a governed scope
)

# What can own/be owned. Bounded vocabulary keeps the surface governable.
OBJECT_TYPES: tuple[str, ...] = (
    "project", "goal", "unit", "knowledge", "decision",
    "customer", "partner", "budget", "compliance", "role", "custom",
)

# Where a responsibility relationship came from.
SOURCES: tuple[str, ...] = (
    "declared",   # an explicit human/manager assignment (highest confidence)
    "observed",   # inferred from activity evidence only
    "transfer",   # created through an explicit transfer
    "backup",     # created as a backup role
    "delegated",  # mirrored from a 4C delegation (read-only for 4F.4)
)


class OwnershipRelationship(Base, TimestampMixin):
    """One responsibility window: who owned WHAT, of WHICH type, WHEN.

    A primary responsibility is the single accountable owner for the object at
    a moment in time; other responsibility types may stack on top of it. The
    window is temporal: closing a relationship never overwrites it, so history
    queries reconstruct the exact state at any moment.
    """

    __tablename__ = "ownership_relationships"
    __table_args__ = (
        Index("ix_ownership_rel_object", "organization_id", "object_type", "object_id"),
        Index("ix_ownership_rel_owner", "organization_id", "owner_id", "status"),
        Index("ix_ownership_rel_scope", "organization_id", "scope_id"),
        # One active window per (object, responsibility type): the engine's
        # exact-once law, enforced atomically so concurrent replays (event
        # worker + drain) converge instead of duplicating or losing windows.
        Index(
            "uq_ownership_rel_active",
            "organization_id", "object_type", "object_id", "responsibility_type",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    responsibility_type: Mapped[str] = mapped_column(String(24), nullable=False, default="primary")
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scope_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|expired|closed
    declared_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    declared_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="declared")
    backup_owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    backup_owner_label: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    escalation_scope_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    closed_reason: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)


class OwnershipChange(Base, TimestampMixin):
    """Append-only ledger of every ownership event (assigned/transferred/...).

    This is the history feed: "who owned X six months ago" is answered here
    and from closed relationship windows, never from overwriting columns.
    """

    __tablename__ = "ownership_changes"
    __table_args__ = (
        Index("ix_ownership_changes_object", "organization_id", "object_type", "object_id"),
        Index("ix_ownership_changes_owner", "organization_id", "to_owner_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    relationship_id: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    responsibility_type: Mapped[str] = mapped_column(String(24), nullable=False, default="primary")
    action: Mapped[str] = mapped_column(String(24), nullable=False)  # assigned|transferred|backup_set|backup_removed|closed|expired|reopened|mismatch
    from_owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    from_owner_label: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    to_owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    to_owner_label: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    reason: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    event_name: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class OwnershipSignal(Base, TimestampMixin):
    """Advisory findings from ownership analysis — NEVER auto-fixes.

    Analysis may only surface findings (mismatch, gap, single-point). Any fix
    (assigning, transferring, promoting) is an explicit governed write by a
    human. Signals are deduplicated per open finding.
    """

    __tablename__ = "ownership_signals"
    __table_args__ = (
        Index("ix_ownership_signals_org_kind", "organization_id", "kind", "status"),
        Index("ix_ownership_signals_object", "organization_id", "object_type", "object_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # mismatch|gap|single_point
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="warning")  # info|warning|critical
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    noted_by: Mapped[Optional[str]] = mapped_column(String(64), default=None)