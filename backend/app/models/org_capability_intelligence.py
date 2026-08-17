"""Slice 4F.6 — Organizational Capability & Capacity Intelligence.

The canonical, change-driven record of what the organization can do and how
much of it is currently in use. One governed surface answers "what are we
really good at", "where are we capacity constrained", "is this capability
concentrated in one person", "which capabilities does this initiative need"
and "can we take this on" — every claim derived from evidence (experts,
owners, teams, projects, knowledge, outcomes), never an opaque AI score.

Hard rules (from the 4F.6 directive):
  * Capability is what we CAN do; capacity is HOW MUCH is currently free.
    Both are derived from bounded indexed aggregates (the 4F.2
    CapabilityAggregate substrate is extended, never duplicated).
  * Lifecycle is deterministic and explainable: unknown -> emerging ->
    established -> strong -> strategic (and back: declining -> dormant),
    derived from evidence volume, strength, recency and monthly evolution
    markers — with history preserved (monthly CapabilityHistory rows).
  * Capacity is Potential minus Committed minus Reserved with observed /
    estimated / unknown states. No fake hour math: expert counts define
    potential; active project links define committed; open task load defines
    reserved. A person can be "potentially constrained", never "82% busy".
  * Demand is CURRENT bounded demand only: active projects whose work
    touches the capability (CapabilityProjectLink), never a forecast.
  * Concentration is advisory: a large share of capability evidence in one
    person surfaces a risk note ("consider secondary ownership or
    knowledge transfer"), never an automatic reassignment.
  * Analysis NEVER changes the organization: findings are signals that may
    only be acknowledged; no hire/fire/reassign/ownership/permission change
    is ever produced by this module.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# Capability lifecycle — deterministic state machine (evidence drives state,
# the state never invents evidence).
CAPABILITY_STATES: tuple[str, ...] = (
    "unknown",        # no evidence-backed experts yet
    "emerging",       # first evidence appears
    "established",    # proven, repeatable evidence
    "strong",         # deep, corroborated organizational strength
    "strategic",      # leadership-defining: many strong experts + heavy use
    "declining",      # current activity well below recent history
    "dormant",        # no fresh evidence for the dormancy window
)

# Capacity states — derived from the bounded Potential/Committed/Reserved
# model. "constrained" means no free experts remain, never a fake percentage.
CAPACITY_STATES: tuple[str, ...] = (
    "unknown",        # no experts -> nothing to commit
    "available",      # free experts remain
    "stretched",      # few free experts left
    "constrained",    # every expert is already committed
)

# Current demand states (active projects touching the capability).
DEMAND_STATES: tuple[str, ...] = (
    "none",
    "low",        # 1..2 active demanding projects
    "moderate",   # 3..5 active demanding projects
    "high",       # more than 5 active demanding projects
)

# Advisory signal kinds — analysis NEVER changes the organization.
SIGNAL_KINDS: tuple[str, ...] = (
    "concentration",                # one person carries a large evidence share
    "single_point_dependency",      # exactly one expert, and they are engaged
    "capacity_constraint",          # no free experts left relative to demand
    "capability_gap",               # demand exceeds free capacity
    "weakening",                    # capability activity declining
    "emerging_without_capacity",    # new capability with no free experts
    "expertise_without_capacity",   # proven expertise currently unused
    "capacity_without_expertise",   # active work needs a capability with no experts
    "declining",                    # capability entered the declining lifecycle
)

SIGNAL_SEVERITIES: tuple[str, ...] = ("info", "warning", "critical")

# Project-link statuses (derived from the project's own lifecycle).
LINK_STATUSES: tuple[str, ...] = ("active", "closed")


class OrgCapability(Base, TimestampMixin):
    """The canonical organizational capability row: one per (org x skill).

    A capability is the organization-level truth of a canonical skill: how
    many evidence-backed experts exist, how deep and current the evidence
    is, how much capacity is committed/reserved/free, what current demand
    looks like, how concentrated the evidence is, and which lifecycle state
    the capability is in. Every field is a bounded deterministic function
    of the underlying evidence ledger (Expertise, ExpertiseEvidence, 4F.2's
    CapabilityAggregate, ownership, projects, tasks, knowledge) — there is
    no magic number and no AI score.
    """

    __tablename__ = "org_capabilities"
    __table_args__ = (
        Index("ix_org_cap_org_state", "organization_id", "lifecycle"),
        Index("ix_org_cap_org_capacity", "organization_id", "capacity_state"),
        Index("ix_org_cap_org_evidence", "organization_id", "evidence_count"),
        # One canonical row per (org, capability).
        Index("uq_org_cap_skill", "organization_id", "skill_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    category: Mapped[Optional[str]] = mapped_column(String(120), default=None)

    # ---- capability strength (evidence-derived, explainable)
    # unknown|emerging|established|strong|strategic|declining|dormant
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    expert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_expert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corroborated_kinds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome_ratio: Mapped[Optional[float]] = mapped_column(Float, default=None)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latest_evidence_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # ---- capacity model (Potential - Committed - Reserved, no fake hours)
    capacity_potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # unknown|available|stretched|constrained
    capacity_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )

    # ---- current demand (bounded, no forecasts)
    demand_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # none|low|moderate|high
    demand_state: Mapped[str] = mapped_column(String(12), nullable=False, default="none")

    # ---- concentration (advisory)
    concentration_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    second_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ---- integration surfaces (bounded counts)
    owner_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ---- monthly evolution markers (history is never destroyed)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, default="")
    points_cur_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    points_prev_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ---- provenance of the current state (why do we believe this?)
    factors_json: Mapped[Optional[dict]] = mapped_column(Text, default=None)
    explain: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    last_event_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    last_event_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )

    @property
    def factors(self) -> dict:
        import json

        if not self.factors_json:
            return {}
        try:
            return json.loads(self.factors_json)
        except (TypeError, ValueError):
            return {}


class CapabilityProjectLink(Base, TimestampMixin):
    """Project <-> capability link, created ONLY where work shows it.

    A link is created when a task in a project is worked by an expert of a
    capability (or the project lifecycle touches a known capability), never
    by scanning. The (org, project, skill, source_event) key is unique, so
    a replayed event converge exactly-once. This is the bounded demand
    ledger: current demand = active links; committed capacity = distinct
    experts on active links.
    """

    __tablename__ = "capability_project_links"
    __table_args__ = (
        Index("ix_cap_link_org_skill", "organization_id", "skill_id"),
        Index("ix_cap_link_org_project", "organization_id", "project_id"),
        Index(
            "ix_cap_link_org_status", "organization_id", "status"
        ),
        # Exact-once law: one durable event creates a link at most once.
        Index(
            "uq_cap_link_event",
            "organization_id", "project_id", "skill_id", "source_event_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # active|closed (closed when the project completes or is cancelled)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class CapabilityHistory(Base, TimestampMixin):
    """Monthly snapshot of a capability — the preserved evolution timeline.

    One row per (org, capability, month). Recomputable from the evidence
    ledger, but kept so "how has our data-engineering capability changed
    since March" is a bounded indexed read, and lifecycle transitions
    (emerging -> strong -> declining) always have the numbers behind them.
    """

    __tablename__ = "capability_history"
    __table_args__ = (
        Index("ix_cap_history_org_skill", "organization_id", "skill_id", "month_key"),
        Index("uq_cap_history_month", "organization_id", "skill_id", "month_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    expert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_expert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capacity_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    demand_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class CapabilitySignal(Base, TimestampMixin):
    """Advisory findings from capability analysis — NEVER auto-fixes.

    A signal names a concentration risk, a single-person dependency, a
    capacity constraint or a capability gap with the evidence behind it.
    Signals are deduplicated per open finding and may only be acknowledged
    or resolved; they never mutate people, ownership, projects or work.
    """

    __tablename__ = "capability_signals"
    __table_args__ = (
        Index("ix_cap_signal_org_kind", "organization_id", "kind", "status"),
        Index("ix_cap_signal_org_skill", "organization_id", "skill_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="warning")
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    noted_by: Mapped[Optional[str]] = mapped_column(String(64), default=None)