"""Slice 4E.6 — Universal Company Actions: the governed knowledge-to-action
layer of the Company Brain.

One canonical action model across the six universal action types
(task | decision | communication | knowledge | meeting | project). Actions
are the *contract* between knowledge intelligence and the operating systems:
every action carries its full lineage (which recommendation, insight, claim
or event produced it) and the reason ('why') the organization should act;
the actual work is routed into the existing governed operating services
(tasks, decisions, announcements, documents, meetings, projects) — this
layer never duplicates those systems, it governs them.

State machine: proposed -> validating -> awaiting_approval | approved ->
ready -> in_progress -> (blocked) -> completed -> verified, with the
terminal states rejected | cancelled | expired | failed | superseded.
Rows are keyed by a stable fingerprint (organization + scope + action_type +
target + source_problem) so proposal is exact-once: replays never duplicate,
and a finished action's successor links back through ``supersedes_id``.
Every transition is recorded as an immutable ``CompanyActionEvent``
(action.created, action.approved, action.verified, …): the audit trail is
append-only and never edited or deleted.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyAction(Base):
    """The universal, governed action row (Slice 4E.6)."""

    __tablename__ = "company_actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False, index=True)
    risk: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), default="org", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    # exact-once key: organization + action_type + scope + target + source_problem
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    target_label: Mapped[Optional[str]] = mapped_column(String(160))
    source_problem: Mapped[Optional[str]] = mapped_column(Text)
    why: Mapped[Optional[str]] = mapped_column(Text)
    # lineage — where this action came from in the knowledge layer
    source_recommendation_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source_insight_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_claim_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    # the routed operating artifact (created via the existing services)
    target_type: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    # governance
    policy: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approver_id: Mapped[Optional[str]] = mapped_column(String(32))
    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[Optional[str]] = mapped_column(Text)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text)
    # execution
    assignee_type: Mapped[str] = mapped_column(String(12), default="employee", nullable=False)
    assignee_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    dependencies_json: Mapped[Optional[str]] = mapped_column(Text)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[Optional[str]] = mapped_column(String(32))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(String(32))
    verification_note: Mapped[Optional[str]] = mapped_column(Text)
    outcome_id: Mapped[Optional[str]] = mapped_column(String(32))
    fail_reason: Mapped[Optional[str]] = mapped_column(Text)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(32))
    # optimistic concurrency for event-driven workers (CAS on every mutation)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "action_type", "fingerprint",
            name="uq_company_actions_fingerprint",
        ),
    )


class CompanyActionEvent(Base):
    """Immutable audit trail — one row per action lifecycle event
    (action.created, action.validated, action.approved, action.rejected,
    action.assigned, action.started, action.blocked, action.unblocked,
    action.completed, action.verified, action.failed, action.cancelled,
    action.expired, action.superseded, action.escalated,
    action.outcome_recorded). Append-only: rows are never edited or deleted.
    """

    __tablename__ = "company_action_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_id: Mapped[str] = mapped_column(
        ForeignKey("company_actions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text)
    details_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CompanyActionOutcome(Base):
    """4E.6 outcome intelligence: what the action actually achieved, recorded
    with evidence after verification, and what the company learns from it."""

    __tablename__ = "company_action_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_id: Mapped[str] = mapped_column(
        ForeignKey("company_actions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    outcome_type: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    verdict: Mapped[Optional[str]] = mapped_column(Text)
    effectiveness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(32))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("action_id", name="uq_company_action_outcomes_action"),
    )