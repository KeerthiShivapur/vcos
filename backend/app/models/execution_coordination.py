"""Slice 4G.2 — Execution Coordination & Dependency Intelligence.

The coordination layer of the Living Company Model: how the WHOLE
organization coordinates work — cross-project dependency pressure,
shared-capacity contention, handoffs between owners and teams, coordination
gaps, propagation of one project's blockage to others, and deterministic,
evidence-backed coordination recommendations with confidence.

Everything is change-driven from the SAME durable events the platform
already emits (task.*, dependency.*, project.*, milestone.*, decision.*,
goal.*, team.member.*, employee.transferred) and every event-driven write is
exact-once on source_event_id. The engine is advisory-only: it writes only
its own tables, never projects, tasks, people, capacity or collaboration.

One coordination surface instead of a separate module: incidents, handoffs
and history ARE the Execution Command Center's coordination view — the same
project ledger the 4G.1 record lives in.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
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

# Incident kinds — the canonical vocabulary of coordination pressure.
INCIDENT_KINDS: tuple[str, ...] = (
    "handoff_risk",        # a task's ownership sat in limbo past the risk window
    "recurring_handoff",   # the same from->to handoff is repeatedly slow
    "shared_capacity",     # active projects contend for one constrained capability
    "critical_conflict",   # a critical path is blocked where capacity is shared
    "coordination_gap",    # a project needs cross-team coordination with no evidence
    "propagation_risk",    # a blocked critical path reaches goals/decisions/downstream
)

SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low")

# Which incident kinds a scoped (non-org-wide) caller may see. Pair/org kinds
# (critical_conflict, shared_capacity) reveal other projects' names and
# capacity — they stay org-wide surfaces.
SCOPED_KINDS: frozenset[str] = frozenset(
    ("handoff_risk", "recurring_handoff", "coordination_gap", "propagation_risk")
)


class CoordinationIncident(Base, TimestampMixin):
    """One open coordination finding, deduplicated by fingerprint.

    A fingerprint is the deterministic identity of the finding
    (e.g. ``handoff:{task_id}``, ``shared_capacity:{skill_id}``,
    ``critical_conflict:{pid_a}:{pid_b}:{skill_id}``). One row per
    fingerprint; the engine reopens it while its condition holds and marks it
    resolved when the condition clears. Evidence is a bounded list of
    human-readable, data-backed lines. Severity and confidence are
    deterministic functions of the evidence — never invented.
    """

    __tablename__ = "coordination_incidents"
    __table_args__ = (
        Index("ix_coord_inc_org_status", "organization_id", "status"),
        Index("ix_coord_inc_org_kind", "organization_id", "kind", "status"),
        Index("ix_coord_inc_project", "organization_id", "project_id", "status"),
        Index("ix_coord_inc_severity", "organization_id", "severity", "status"),
        # One finding per fingerprint — replays converge, never duplicate.
        UniqueConstraint(
            "organization_id", "fingerprint", name="uq_coord_inc_fingerprint"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="high")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|resolved
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), default=None
    )
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    subject_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text)
    evidence: Mapped[Optional[list]] = mapped_column(JSON)
    propagation: Mapped[Optional[list]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    # When a human resolves (or the condition clears) — history is retained.
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    resolve_note: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CoordinationHandoff(Base, TimestampMixin):
    """One task ownership transition (from owner -> to owner).

    A pending handoff opens the moment a task's assignee changes and closes
    when the task is completed/unblocked or changes owner again. Completed
    handoffs keep their duration so recurrence is measurable. The unique
    (organization_id, source_event_id) constraint makes replays exact-once.
    """

    __tablename__ = "coordination_handoffs"
    __table_args__ = (
        Index("ix_coord_handoff_org_status", "organization_id", "status"),
        Index("ix_coord_handoff_task", "organization_id", "task_id"),
        Index("ix_coord_handoff_org_dur", "organization_id", "status", "duration_hours"),
        UniqueConstraint(
            "organization_id", "source_event_id", name="uq_coord_handoff_event"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), default=None
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    from_owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    from_owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    to_owner_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    to_owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending|completed|abandoned
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    duration_hours: Mapped[Optional[float]] = mapped_column(Float, default=None)


class CoordinationHistory(Base, TimestampMixin):
    """Append-only trail of coordination findings (exact-once on the event).

    One row per incident state transition (open -> resolved -> reopened) so
    "what changed in coordination" stays answerable over time without any
    rescan. Rows carry the incident's kind/severity/title at that moment.
    """

    __tablename__ = "coordination_history"
    __table_args__ = (
        Index("ix_coord_history_org_inc", "organization_id", "incident_id"),
        Index("ix_coord_history_project", "organization_id", "project_id"),
        Index("ix_coord_history_org_time", "organization_id", "occurred_at"),
        # Exact-once per (incident, event): one transition row per event.
        UniqueConstraint(
            "organization_id", "incident_id", "source_event_id",
            name="uq_coord_history_event",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    incident_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), default=None
    )
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="high")
    event_name: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
