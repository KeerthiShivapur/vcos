"""Slice 4F.5 — Work Collaboration Intelligence.

The canonical, change-driven record of how work flows between people, teams
and projects: one governed surface answers "who works most closely with X",
"who connects Sales and Engineering", "why is collaboration between these
two teams weak", "is this project overdependent on one person" and "what
collaboration risks exist" — always from evidence, never from a social
graph.

Hard rules (from the 4F.5 directive):
  * Evidence is mandatory: every claim carries lineage back to a durable
    event (CollaborationEvidence, exact-once via a unique org+event key).
  * Change-driven and bounded: an event touches ONLY the pairs it evidences;
    there is no full rescan and no O(N²) all-pairs pass. Edges exist only
    where evidence exists.
  * Strength is a bounded deterministic function of weighted positive and
    negative evidence; failed/negative signals deflate it deterministically
    and are never hidden.
  * Temporal history is retained: evidence is append-only, monthly point
    markers roll, first/last seen are preserved, and evolution states
    (emerging/strengthening/stable/weakening/dormant/blocked) are derived
    from the markers with evidence behind every transition.
  * Advisory only: concentration risk, bottleneck and gap findings are
    signals — analysis NEVER changes the organization. A gap names a
    missing relationship, never a failing team.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# Relationship kinds between two people (derived from their units, stored for
# bounded reads). "bridge" marks a pair whose ONLY common work path runs
# through a third person — a derived, evidence-backed signal.
RELATIONSHIP_KINDS: tuple[str, ...] = (
    "same_team",         # both people in the same team
    "same_department",   # both people in the same department (different teams)
    "cross_department",  # different departments
    "project_partner",   # paired evidence on a shared project scope only
)

# Scope vocabulary of a collaboration edge.
SCOPES: tuple[str, ...] = ("org", "project")

# Health states — one label per relationship at any moment, derived from
# evidence and monthly markers (bounded deterministic derivation).
HEALTH_STATES: tuple[str, ...] = (
    "blocked",       # recent evidence dominated by failed outcomes
    "at_risk",       # meaningful failed outcomes, not yet blocking
    "dormant",       # no activity for the dormancy window
    "emerging",      # first evidence within the emergence window
    "weakening",     # current month well below the previous month
    "strengthening",  # current month well above the previous month
    "strong",        # high strength with real successful evidence
    "healthy",       # solid strength, no open issues
    "low_evidence",  # some evidence, not enough to claim more
)

# Quality labels — separate from strength: volume is not quality.
QUALITY_LABELS: tuple[str, ...] = (
    "problematic",   # failures dominate recent interaction quality
    "high_quality",  # high success ratio, real joint outcomes
    "high_volume",   # high evidence volume without quality flags
)

# Advisory signal kinds (analysis NEVER changes the org — only surfaces).
SIGNAL_KINDS: tuple[str, ...] = (
    "concentration",     # a person carries a large share of collaboration flow
    "slowdown",          # a previously strong pair/unit pair went quiet
    "gap",               # required (project-anchored) work with no evidence
    "negative_shift",    # collaboration experienced failed outcomes
)

SIGNAL_SEVERITIES: tuple[str, ...] = ("info", "warning", "critical")


class CollaborationRelationship(Base, TimestampMixin):
    """One canonical work-collaboration edge: person A ↔ person B.

    The pair key is canonical (person_a_id < person_b_id) so replays converge
    on the same row. Rows are org-level by default (scope_type "org"); a
    project-scoped row exists only when a pair has joint evidence inside that
    project AND a project-scoped view is warranted — edges are created only
    where evidence exists, never as an all-pairs pass.

    History is never destroyed: evidence is append-only; monthly point
    markers roll forward; first_seen/last_seen and created/updated times
    reconstruct evolution. Strength is bounded (0..1) and deterministic.
    """

    __tablename__ = "collaboration_relationships"
    __table_args__ = (
        Index("ix_collab_rel_org_person", "organization_id", "person_a_id"),
        Index("ix_collab_rel_person_b", "organization_id", "person_b_id"),
        Index("ix_collab_rel_org_status", "organization_id", "status"),
        Index("ix_collab_rel_scope", "organization_id", "scope_type", "scope_id"),
        # Canonical determinism: one row per (org, ordered pair, scope).
        Index(
            "uq_collab_rel_pair",
            "organization_id", "person_a_id", "person_b_id", "scope_type", "scope_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    person_a_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_a_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    person_b_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_b_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    relationship_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="cross_department"
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="org")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # Evidence counters (denormalized, increment-only, recomputable from the
    # evidence ledger — never edited in place by analysis).
    shared_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shared_decisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shared_meetings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meaningful_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Derived truth (deterministic functions of the counters + monotonic
    # decay of cold relationships).
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    health_state: Mapped[str] = mapped_column(String(24), nullable=False, default="low_evidence")
    quality: Mapped[Optional[str]] = mapped_column(String(24), default=None)

    # Monthly markers for evolution detection (bounded: two counters + a key).
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, default="")
    points_cur_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    points_prev_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Last-evidence provenance (the most recent thing that anchored this pair).
    source_type: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    last_source_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    last_source_title: Mapped[Optional[str]] = mapped_column(String(300), default=None)

    # Temporal envelope.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|dormant
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class CollaborationEvidence(Base, TimestampMixin):
    """Append-only lineage of every collaboration event (exact-once).

    (organization_id, source_event_id) is unique — a replayed event can never
    double-count. Every relationship counter and signal is recomputable from
    this ledger; it IS the provenance trail.
    """

    __tablename__ = "collaboration_evidence"
    __table_args__ = (
        Index("ix_collab_evidence_org_rel", "organization_id", "relationship_id"),
        Index("ix_collab_evidence_pair", "organization_id", "person_a_id", "person_b_id"),
        Index("ix_collab_evidence_org_event", "organization_id", "event_name"),
        Index("ix_collab_evidence_project", "organization_id", "project_id"),
        # Exact-once law: one durable event applies at most once per pair. The
        # engine pre-checks this constraint; the index enforces it atomically
        # under concurrent replays (event worker + drain).
        Index(
            "uq_collab_evidence_event",
            "organization_id", "source_event_id", "person_a_id", "person_b_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    relationship_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    person_a_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_a_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    person_b_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_b_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="org")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    source_type: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    source_title: Mapped[Optional[str]] = mapped_column(String(300), default=None)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    outcome: Mapped[str] = mapped_column(String(12), nullable=False, default="neutral")  # success|failure|neutral
    points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CollaborationUnitPair(Base, TimestampMixin):
    """Team↔team (or department↔department) collaboration window.

    Rolled up from the same evidence (unit resolution of each person), so the
    pair's numbers are exact, bounded and always consistent with the
    person-level ledger — never a separate scan.
    """

    __tablename__ = "collaboration_unit_pairs"
    __table_args__ = (
        Index("ix_collab_unit_org_type", "organization_id", "unit_type"),
        Index(
            "uq_collab_unit_pair",
            "organization_id", "unit_type", "unit_a_id", "unit_b_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    unit_type: Mapped[str] = mapped_column(String(16), nullable=False)  # team|department
    unit_a_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_a_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    unit_b_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_b_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    shared_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shared_decisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shared_meetings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meaningful_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_interactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    health_state: Mapped[str] = mapped_column(String(24), nullable=False, default="low_evidence")
    quality: Mapped[Optional[str]] = mapped_column(String(24), default=None)

    month_key: Mapped[str] = mapped_column(String(7), nullable=False, default="")
    points_cur_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    points_prev_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|dormant
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CollaborationPersonRollup(Base, TimestampMixin):
    """Bounded per-person collaboration accumulation (one row per person).

    Kept incrementally (O(1) per evidence event) so concentration analysis
    never needs a graph rescan: every share is exact-by-construction instead
    of computed over the org.
    """

    __tablename__ = "collaboration_person_rollups"
    __table_args__ = (
        Index("ix_collab_rollup_org_person", "organization_id", "person_id"),
        Index("uq_collab_rollup_person", "organization_id", "person_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    active_relationships: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_evidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, default="")
    total_points_cur_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_points_prev_month: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CollaborationOrgRollup(Base, TimestampMixin):
    """One bounded org-level accumulator row for concentration shares."""

    __tablename__ = "collaboration_org_rollups"
    __table_args__ = (
        Index("uq_collab_org_rollup", "organization_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    active_relationships: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_evidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CollaborationSignal(Base, TimestampMixin):
    """Advisory findings from collaboration analysis — NEVER auto-fixes.

    A signal names a potential concentration risk, a slowdown, a required
    collaboration gap or a negative shift with the evidence behind it.
    Signals are deduplicated per open finding and may only be acknowledged or
    resolved; they never mutate relationships, units or people.
    """

    __tablename__ = "collaboration_signals"
    __table_args__ = (
        Index("ix_collab_signal_org_kind", "organization_id", "kind", "status"),
        Index("ix_collab_signal_subject", "organization_id", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(24), nullable=False)  # person|unit_pair|relationship|project
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="warning")
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open|acknowledged|resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    noted_by: Mapped[Optional[str]] = mapped_column(String(64), default=None)