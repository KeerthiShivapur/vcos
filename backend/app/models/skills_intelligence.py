"""Slice 4F.2 — Universal Skills & Expertise Intelligence: the canonical
capability substrate of the company.

4F.1 answered WHO people are and how they are structurally connected. 4F.2
answers WHAT each person can actually do, HOW WELL they can do it, and WHAT
EVIDENCE supports that belief — never from profile keywords alone.

The pipeline is strictly change-driven and evidence-backed:

    company activity -> canonical evidence -> deterministic scoring ->
    expertise state -> governed surfaces (brain)

    * ``CanonicalSkill``      the one canonical skill taxonomy per tenant
                              (name, category, parents, related skills,
                              status, provenance) — no module invents skills
                              independently; aliases resolve deterministically
                              (Postgres / PostgreSQL / PG -> PostgreSQL);
                              ambiguous concepts stay unresolved until
                              governed confirmation, they are never merged,
    * ``SkillAlias``          normalized alias rows (tenant-scoped) giving
                              deterministic 1:1 term -> skill resolution;
                              a claimed alias that already belongs to another
                              skill is flagged ``ambiguous`` for both owners
                              instead of silently assigning either one,
    * ``PersonSkill``         a skill ASSOCIATION (skills are not expertise):
                              source, declared_level, first_seen, last_seen,
                              status. Declaring a skill never grants expertise,
    * ``Expertise``           the evidence-derived expert state per
                              (person x skill): score, confidence, evidence
                              counts, breadth, depth, recency, frequency,
                              span, lifecycle (observed -> emerging ->
                              established -> strong -> authoritative, and
                              dormant on inactivity — never deleted),
                              historical_peak preserved so decayed expertise
                              stays company memory,
    * ``ExpertiseEvidence``   every expertise claim is explainable: one
                              evidence row per (person, skill, event/source)
                              with an explicit strength class (strong /
                              medium / weak) and weight. Replay is exact-once
                              via (event_id) / (source_type, source_id) keys.
                              Weak mentions alone can never drive a person to
                              authoritative expertise,
    * ``CapabilityAggregate`` bounded indexed team / department / business
                              unit / organization aggregates refreshed only
                              for the affected scope when a cell changes —
                              complexity scales with change volume, never
                              company size.

Architecture laws preserved from 4F.1 / 4D / 4E: tenant-scoped rows,
stable unique keys (replay exact-once), no destructive deletes (dormant is a
state, never a deletion), dimensions are deterministic and explainable, and
no AI ever writes an expertise claim — the authority chain is activity ->
canonical evidence -> deterministic scoring -> state.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- canonical lifecycle (deterministic thresholds live in the expertise
# engine; these are the state machine's states) --------------------------------

SKILL_STATUSES = ("candidate", "active", "deprecated")
PROVENANCES = ("system_seed", "governed", "declared", "legacy_bridge", "signal")

PERSON_SKILL_SOURCES = ("declared", "activity", "learning", "certification", "signaled")
PERSON_SKILL_STATUSES = ("active", "inactive", "removed")

EXPERTISE_LIFECYCLE = (
    "observed",
    "emerging",
    "established",
    "strong",
    "authoritative",
    "dormant",
)

EVIDENCE_STRENGTHS = ("strong", "medium", "weak")

# Slice 4F.3 — the canonical evidence KIND taxonomy (source classification for
# corroboration; the user-facing hierarchy is documented in the 4F.3 report):
# work / knowledge / decision / communication / recognition / learning /
# operations. Corroboration counts DISTINCT kinds, and an assessment is
# "corroborated" when multiple INDEPENDENT source classes agree.
EVIDENCE_KINDS = (
    "work", "knowledge", "decision", "communication", "recognition",
    "learning", "operations",
)

# Outcome signals: successful (proven by outcome), failed (contradicting),
# neutral (mentions / participation — no outcome either way). Failed evidence
# is negative evidence: it deflates score/confidence deterministically and is
# never hidden from the trust profile.
EVIDENCE_OUTCOMES = ("successful", "failed", "neutral")

# Evidence source types (canonical source ids are stored alongside so every
# claim can answer "why does VCOS believe this?").
EVIDENCE_SOURCE_TYPES = (
    "task", "project", "milestone", "document", "wiki", "decision", "meeting",
    "community", "recognition", "goal", "template", "approval", "innovation",
    "course", "certificate", "assessment", "learning_path", "knowledge",
    "message", "review", "event",
)

AGGREGATE_SCOPE_TYPES = ("organization", "business_unit", "department", "team")


class CanonicalSkill(Base):
    """The one canonical skill taxonomy of a tenant.

    Tenants own their taxonomy (aliases are tenant-scoped isolation); a
    deterministic seed provides the starter taxonomy and modules can only
    extend it through the governed skill engine. ``canonical_name`` is the
    single agreed name; aliases live in ``SkillAlias``, parents and related
    skills are deterministic graph references.
    """

    __tablename__ = "canonical_skills"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "canonical_name", name="uq_canonical_skill_name"
        ),
        Index("ix_canonical_skills_org_category", "organization_id", "category"),
        Index("ix_canonical_skills_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    parent_skill_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="SET NULL"), index=True
    )
    related_skill_ids_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # candidate | active | deprecated
    status: Mapped[str] = mapped_column(String(16), default="candidate", nullable=False)
    # system_seed | governed | declared | legacy_bridge | signal
    provenance: Mapped[str] = mapped_column(String(20), default="signal", nullable=False)
    # taxonomy depth (root skills = 0)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def related_skill_ids(self) -> list[str]:
        return list(self.related_skill_ids_json or [])


class SkillAlias(Base):
    """Deterministic alias -> canonical skill resolution (tenant-scoped).

    An alias is a normalized lowercase term owned by exactly one skill. If a
    second skill claims a term that already resolves to another skill, both
    rows are flagged ``ambiguous`` — the ambiguity is surfaced, never merged
    by heuristics; governed confirmation is required to reassign.
    """

    __tablename__ = "skill_aliases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "alias_lower", name="uq_skill_alias_term"
        ),
        Index("ix_skill_aliases_org_skill", "organization_id", "skill_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alias_lower: Mapped[str] = mapped_column(String(120), nullable=False)
    # active | ambiguous
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PersonSkill(Base):
    """A skill ASSOCIATION for a person — never expertise by itself.

    Declaring "Python 5/5" in a profile means the person is associated with
    Python; it does not move any expertise dimension. Expertise requires
    canonical evidence (completed work, authored knowledge, decisions,
    validated certification). ``last_seen`` advances whenever canonical
    evidence for (person, skill) is observed.
    """

    __tablename__ = "person_skills"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "person_id", "skill_id", name="uq_person_skill"
        ),
        Index("ix_person_skills_org_skill", "organization_id", "skill_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # declared | activity | learning | certification | signaled
    source: Mapped[str] = mapped_column(String(20), default="declared", nullable=False)
    declared_level: Mapped[int] = mapped_column(Integer, default=2)  # 1..5
    # active | inactive | removed
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Expertise(Base):
    """Evidence-derived expertise state for one (person x skill).

    The user-facing ``score`` is a derived display value; the defensible
    truth lives in the dimension fields and ``factors_json`` breakdown plus
    the linked ``ExpertiseEvidence`` rows. Historical expertise is preserved:
    decay sets lifecycle to ``dormant`` and recency collapses, but score,
    peak and evidence counts stay readable as company memory.
    """

    __tablename__ = "expertise"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "person_id", "skill_id", name="uq_expertise_cell"
        ),
        Index("ix_expertise_org_skill", "organization_id", "skill_id"),
        Index("ix_expertise_state_org_score", "organization_id", "score"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # derived display score 0..100 (see factors_json for the breakdown)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # bounded confidence in [0, 1]
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strong_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    medium_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weak_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Slice 4F.3 — trust facets:
    #   successful_count / failed_count   outcome signals (effective evidence)
    #   outcome_ratio                     successful/(successful+failed) or None
    #   distinct_lineages                 INDEPENDENT underlying actions (one
    #                                     action counted once per kind) — the
    #                                     double-count guard
    #   corroborated_kinds                distinct evidence kinds present
    #                                     (work/knowledge/decision/...)
    #   freshness                         active (<=90d) | recent (<=365d) |
    #                                     historical (>365d) since last evidence
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome_ratio: Mapped[Optional[float]] = mapped_column(Float)
    distinct_lineages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    corroborated_kinds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    freshness: Mapped[str] = mapped_column(String(12), default="historical", nullable=False)
    # breadth: distinct evidence source types
    breadth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # depth: quality-weighted strong+medium evidence mass (0..1)
    depth: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # recency: days since the last observed evidence (None before any)
    recency_days: Mapped[Optional[int]] = mapped_column(Integer)
    # activity frequency: evidence items observed in the last 90 days
    frequency_90d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # span: months between first and last observed evidence
    span_months: Mapped[Optional[int]] = mapped_column(Integer)
    lifecycle: Mapped[str] = mapped_column(String(16), default="observed", nullable=False)
    # the highest score this cell ever reached (never lowered)
    historical_peak: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    first_observed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_observed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    # deterministic component breakdown (the "no single magic number" answer)
    factors_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(16), default="4f3.1", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def factors(self) -> dict:
        return dict(self.factors_json or {})


class ExpertiseEvidence(Base):
    """One canonical expertise evidence item.

    Every evidence item carries its canonical source id (task/document/
    decision/certificate id or, when the source is only the event itself, the
    event id), an explicit strength class and weight, and the 4E topic the
    item speaks to when applicable. Two natural keys make replay exact-once:

      (organization_id, person_id, event_id, skill_id)   event-driven items
      (organization_id, person_id, source_type, source_id, skill_id)
                                                        non-event / manual items

    Never edited, never deleted — the timeline of a capability is
    reconstructable exactly like the 4F.1 people timeline.
    """

    __tablename__ = "expertise_evidence"
    __table_args__ = (
        # Replay exact-once by EVENT: one canonical event -> one row per skill.
        # Slice 4F.3: a single ACTION with several outcomes (deployment.completed
        # -> deployment.failed -> deployment.rolled_back) must keep ALL its
        # history rows — success/contradiction/expiry are never collapsed, so
        # there is no source-unique constraint (distinct events, distinct rows).
        UniqueConstraint(
            "organization_id", "person_id", "event_id", "skill_id",
            name="uq_expertise_evidence_event",
        ),
        Index("ix_expertise_evidence_org_skill", "organization_id", "skill_id"),
        Index("ix_expertise_evidence_org_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # strong | medium | weak
    strength: Mapped[str] = mapped_column(String(12), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    # Slice 4F.3 — provenance & trust:
    #   evidence_kind   the canonical source class (work / knowledge /
    #                   decision / communication / recognition / learning /
    #                   operations) used for corroboration,
    #   outcome         successful (proven) | failed (contradicting) |
    #                   neutral (mention / participation),
    #   valid_from/to   the validity window of this claim (a rolled-back
    #                   deployment EXPIRES its earlier successful evidence);
    #                   expired items stay visible in lineage as history but
    #                   never feed current scoring,
    #   lineage_key     the underlying ACTION identity (origin event id or a
    #                   canonical action id like a deployment id) — one action
    #                   counted once per kind, so derived cascades can never
    #                   inflate evidence (independent sources only),
    #   origin_event_id the event this evidence derives from when ancestry is
    #                   known (double-count prevention).
    evidence_kind: Mapped[str] = mapped_column(String(20), default="work", nullable=False)
    outcome: Mapped[str] = mapped_column(String(12), default="neutral", nullable=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lineage_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    origin_event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_title: Mapped[Optional[str]] = mapped_column(String(300))
    # canonical 4E topic the evidence speaks to (when resolvable)
    topic_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CapabilityAggregate(Base):
    """Bounded, indexed capability rollup for one scope x skill.

    Refreshed by the capability engine for exactly the scopes that contain
    the changed person (team -> department -> business unit -> organization),
    never by scanning an organization. ``member_count`` counts distinct
    persons with score > 0 in the scope; it is only served to callers whose
    governance scope includes the whole aggregate scope (hidden people never
    leak through counts or rankings).
    """

    __tablename__ = "capability_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope_type", "scope_id", "skill_id",
            name="uq_capability_aggregate",
        ),
        Index("ix_capability_aggregates_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_capability_aggregates_skill", "organization_id", "skill_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # organization | business_unit | department | team
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # scope id; for organization scope this is the organization id
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False)
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    strong_member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)