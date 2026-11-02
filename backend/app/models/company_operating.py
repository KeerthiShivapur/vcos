"""Slice 4G.7 — Universal Company Operating Intelligence models.

The company operating layer NEVER parallel-copies the canonical records of
4G.1-4G.6. It composes them deterministically on read (state, health,
root-cause chains, impact propagation, the universal recommendation queue,
bounded what-if scenarios) and persists only what cannot be derived:

  1. CompanyHealthHistory — the exact-once temporal trail of the composed
     company-level health assessment (the basis of "What changed?" and the
     "Why?" layer for company-level findings).
  2. CompanyDecision — the governed human artifact that closes the loop
     decision -> reason -> action -> outcome -> learning. A company
     recommendation only becomes an action after a human approves it, and the
     outcome plus the lesson are recorded so the organization learns.

Everything else (projects, goals, capacity, customers, business performance,
people, knowledge) lives in its canonical system of record; this layer is a
synthesis over those systems, advisory-only, bounded, and one canonical
architecture for every company size (5 to 50,000+ people).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# --- canonical vocabularies ------------------------------------------------

# The eight company-level health domains. Strategy and execution (4G.1/4G.3),
# capacity and people (4G.4), customers (4G.5), financial (4G.6),
# coordination (4G.2) and knowledge (4E/4D). Same health language as the
# rest of the platform: healthy / concerned / at_risk (plus critical for
# company-level constraints that must be seen by leadership).
HEALTH_STATES = ("healthy", "concerned", "at_risk", "critical")

# Company-level health domains in deterministic display order.
COMPANY_HEALTH_DOMAINS: tuple[str, ...] = (
    "strategy",
    "execution",
    "people",
    "capacity",
    "customers",
    "financial",
    "coordination",
    "knowledge",
)

# Weight of each domain in the composed company health score (sums to 1.0).
DOMAIN_WEIGHTS: dict[str, float] = {
    "strategy": 0.20,
    "execution": 0.20,
    "capacity": 0.15,
    "customers": 0.15,
    "financial": 0.15,
    "coordination": 0.05,
    "people": 0.05,
    "knowledge": 0.05,
}

# What a governed company decision is allowed to be. The engine only records
# what a HUMAN approves; the decision record carries the reason (why), the
# expected impact, and later the outcome and the lesson.
DECISION_KINDS = (
    "reallocate_capacity",
    "delay_project",
    "hire",
    "change_priority",
    "resolve_conflict",
    "improve_coordination",
    "customer_mitigation",
    "commercial_action",
    "other",
)

# Lifecycle of a governed decision artifact. 4G.7/4H.1: approved ->
# executed -> outcome_recorded; declined is terminal and is itself remembered.
# 4H.2 extends the FRONT of the lifecycle with advisory pre-approval stages
# (proposed -> evaluated -> recommended). These pre-approval states are
# NEVER executable; only approved -> executed is. `assessed` is the terminal
# post-reconciliation state. Consumers must not assume the old four-state
# constant, its length, or positional ordering (contract §4 law).
DECISION_STATES = (
    "proposed",
    "evaluated",
    "recommended",
    "approved",
    "declined",
    "executed",
    "outcome_recorded",
    "assessed",
)

# Stage vocabulary of the quality snapshots (§3.4) — one exact-once snapshot
# per stage a decision reaches.
QUALITY_STAGES = (
    "proposed",
    "evaluated",
    "recommended",
    "approved",
    "outcome_recorded",
)

# Evidence lineage types (§3.2) — constraints and stakeholders are first-class
# lineage so the canonical model question -> company state -> evidence +
# constraints + stakeholders -> alternatives is fully supported.
DECISION_EVIDENCE_TYPES = (
    "event",
    "metric",
    "insight",
    "pattern",
    "memory",
    "decision",
    "constraint",
    "stakeholder",
)

# Contradiction row lifecycle (§3.6): surfaced open, acknowledged by a human,
# resolved by a human — transitions are audited lifecycle events.
CONTRADICTION_STATUSES = ("open", "acknowledged", "resolved")

# Outcome vocabulary of an executed action — the same language execution
# (4G.1) uses for project outcomes.
OUTCOME_KINDS = ("successful", "partial", "unsuccessful")

# Bounded what-if scenarios the company layer can evaluate deterministically.
WHATIF_SCENARIOS = ("reallocate", "delay", "hire")

# Cap on recommendation queue and what-if consequences (bounded queries).
MAX_COMPANY_RECOMMENDATIONS = 20
MAX_WHATIF_CONSEQUENCES = 5
MAX_CHANGES_SHOWN = 10
MAX_MEMORY_SHOWN = 20

# Cross-org scopes the multi-level company state can be parameterized by.
COMPANY_SCOPE_TYPES = ("org", "business_unit", "department", "team", "person")

# Derived causality kinds (Slice 4H.1) — every edge is derived from tables the
# canonical engines already expose; kinds with no derivable join simply carry
# no rows (the snapshot stays evidence-driven, never faked).
CAUSAL_EDGE_KINDS = (
    "person->capability", "capability->project", "project->milestone",
    "project->customer", "milestone->customer", "customer->revenue",
    "revenue->objective", "objective->outcome", "decision->task",
    "task->execution", "execution->outcome", "outcome->customer",
    "customer->business", "dependency->project", "capacity->project",
    # Slice 4H.3 — additive kinds only (no new edge table, no new engine).
    # Derived from existing canonical rows; kinds with no derivable join
    # today ("decision->process") legitimately carry no rows — the snapshot
    # stays evidence-driven, never faked.
    "risk->project", "constraint->project", "opportunity->decision",
    "decision->process",
)
CAUSAL_EDGE_CONFIDENCES = ("high", "medium", "low")

# Bounds for the derived causality snapshot and walk.
MAX_CAUSAL_EDGES = 60
MAX_CAUSAL_DEPTH = 5
MAX_NARRATIVE_STEPS = 5
MAX_SCOPED_DEVIATIONS = 3

# 4H.2 decision-intelligence bounds (§5.4, §9): precedent recall is top-N and
# per-decision evidence is capped so every query stays bounded from 5 to
# 50,000+ employees.
MAX_PRECEDENTS = 10
MAX_DECISION_EVIDENCE = 40
MAX_ALTERNATIVES = 5

# Slice 4H.3 — Living Company State. The eight fixed state dimensions of the
# composed living-company snapshot (deterministic display order); each is
# typed observed (from a canonical health domain) or derived (composed from
# decision/outcome rows).
STATE_DIMENSIONS = (
    "people", "work", "resources", "processes", "outcomes",
    "knowledge", "customers", "finance",
)

# 4H.3 bounds (§5.5): every surface block is top-N bounded, identical shape
# 5 -> 50,000+.
MAX_STATE_DELTA = 30
MAX_STATE_RISKS = 10
MAX_STATE_OPPORTUNITIES = 10
MAX_STATE_DECISIONS = 20
MAX_STATE_SIGNALS = 30
# §10: the state surface is re-composed on read only when the latest
# composed snapshot is older than this (seconds).
STATE_TTL = 60

# --- Slice 4H.4 — Decision-Rehearsal Intelligence (§3, §7.1, §12).
# Sanctioned scenario kinds: the 4G.7 what-if kinds (same derivation
# functions) plus three contract-sanctioned rehearsal kinds. No new engine.
SCENARIO_KINDS = (
    "reallocate", "delay", "hire",
    "resource_loss", "dependency_break", "decision_reconsider",
)
# Whitelisted scenario parameter keys (reuse the what-if vocabulary).
SCENARIO_PARAM_KEYS = (
    "project_id", "days", "capability", "from_project_id", "to_project_id",
    "units", "people", "ramp_days", "duration_days", "resource_id",
    "customer_id", "decision_id",
)
# §12 bounds: history list cap and assumption list cap.
MAX_SCENARIOS_SHOWN = 10
MAX_SCENARIO_ASSUMPTIONS = 20


class CompanyHealthHistory(Base, TimestampMixin):
    """Append-only temporal trail of the composed company health assessment.

    One row per recomputing event (exact-once on the source event), so the
    company-level "What changed?" and the "Why?" layer stay answerable over
    any period. The live assessment is simply the latest row.
    """

    __tablename__ = "company_health_history"
    __table_args__ = (
        # 4H.1: the exact-once key grew the scope so per-event scoped rows
        # coexist with the org row (one row per scope per event, replays
        # converge on the same key).
        UniqueConstraint(
            "organization_id", "source_event_id", "scope_type", "scope_id",
            name="uq_chh_exact_once",
        ),
        Index(
            "ix_chh_org_time",
            "organization_id", "occurred_at",
        ),
        Index(
            "ix_chh_org_scope_time",
            "organization_id", "scope_type", "scope_id", "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    company_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # healthy | concerned | at_risk | critical
    company_state: Mapped[str] = mapped_column(
        String(12), nullable=False, default="concerned"
    )
    # the single biggest company-level constraint:
    # {"domain","label","detail","affected","root_cause","interventions"}
    primary_constraint_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # [{"key","label","score","state","reasons","affected","constraint",
    #   "root_cause","interventions","evidence_count"}]
    domains_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # attention items: [{"priority","kind","title","why"}]
    attention_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    summary_narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 4H.1: multi-level parameterization. "org" rows are the canonical
    # per-event trail; scoped rows (scope_type != "org") are written by the
    # engine only for attention-worthy deviations, bounded per event.
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False, default="org")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CompanyStateHistory(Base, TimestampMixin):
    """Slice 4H.3 — append-only temporal trail of the composed living company
    state.

    One row per source event (exact-once on ``source_event_id``), written
    ONLY when the composed surface differs from the previous snapshot (no-op
    compositions stay unwritten — no false trail entries). The state at any
    instant is stable forever and replays converge: the same composition
    path over the same canonical rows yields the identical surface.
    """

    __tablename__ = "company_state_history"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope_type", "scope_id", "source_event_id",
            name="uq_csh_state",
        ),
        Index(
            "ix_csh_org_time",
            "organization_id", "occurred_at",
        ),
        Index(
            "ix_csh_org_scope_time",
            "organization_id", "scope_type", "scope_id", "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # `st:<org>:<scope>:<seq>` — deterministic display key
    state_key: Mapped[str] = mapped_column(String(140), nullable=False)
    # org | business_unit | department | team | person (COMPANY_SCOPE_TYPES);
    # scoped rows only for attention-worthy deviations
    scope_type: Mapped[str] = mapped_column(String(12), nullable=False, default="org")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    # 8 fixed dimensions (STATE_DIMENSIONS), each:
    #   {"op","signal_count","state","type":"observed/derived"}
    dimensions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # what changed vs the previous snapshot:
    #   [{"op","entity","id","label","kind","signal":"event/pattern/insight/
    #     memory","signal_ids":[],"evidence_count"}]
    delta_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # contributing signals behind this snapshot (event ids, pattern/insight
    # ids, refreshed causal-edge refs, memory ids) — the "why"
    signals_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # top-N dependency edges visible from this state (entity pairs + kind +
    # confidence), bounded
    dependencies_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # open-risk exposure composition:
    #   [{"risk_id","title","band","probability","impact",
    #     "affected":[{"entity","id","kind"}]}]
    risks_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # derived opportunity surface:
    #   [{"source":"pattern/insight/recommendation","source_id","kind",
    #     "signal_count","evidence_count"}]
    opportunities_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # decision ids/state/kind for pre-approval and active decisions
    # intersecting the delta (bounded, deterministic)
    affected_decisions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # what humans should consider — 4H.1 attention language
    # (priority/kind/title/why)
    attention_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # advisory what-if consequences:
    #   [{"scenario_type","consequences_count","not_a_prediction":true}]
    next_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # exact-once key
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # when composed
    snapshot_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # event time (the as-of anchor)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CompanyDecision(Base, TimestampMixin):
    """A governed human decision artifact closing the operating loop.

    decision -> reason -> action -> outcome -> learning. Created only when a
    human approves (or declines) a company recommendation; transitions are
    idempotent on the decision state machine. The lesson is the
    organizational-learning payload that future recommendations cite.
    """

    __tablename__ = "company_decisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id",
            name="uq_cd_canonical",
        ),
        UniqueConstraint(
            "organization_id", "source_event_id",
            name="uq_cd_exact_once",
        ),
        Index(
            "ix_cd_org_state",
            "organization_id", "state", "updated_at",
        ),
        Index(
            "ix_cd_org_scope",
            "organization_id", "scope_type", "scope_id",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # canonical decision key (stable across replays)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # reallocate_capacity | delay_project | hire | change_priority |
    # resolve_conflict | improve_coordination | customer_mitigation |
    # commercial_action | other
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    # the recommendation the decision answers (or "" for free decisions)
    recommendation_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # WHY this decision is being taken (evidence-backed rationale)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # alternative courses considered: [{"title","impact_label","confidence"}]
    alternatives_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    impact_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    expected_improvement: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    owner_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # proposed | evaluated | recommended | approved | declined | executed |
    # outcome_recorded | assessed (see DECISION_STATES)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="approved")
    approver_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    executed_by_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # successful | partial | unsuccessful
    outcome_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # 0..1 observed effectiveness of the action
    effectiveness: Mapped[Optional[float]] = mapped_column(Float)
    outcome_evidence_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # the learning payload future recommendations cite
    lesson: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 4H.1: prediction at approve-time + reconcile on outcome. Existing
    # vocabularies unchanged.
    predicted_outcome: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    prediction_confidence: Mapped[Optional[float]] = mapped_column(Float)
    actual_outcome_compare: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # 4H.2 additive-only columns (§3.7) — never remove, rename, or
    # reinterpret any existing column.
    # The CompanyHealthHistory snapshot refs (source_event_ids) known at
    # decide-time: the temporal as-of anchor for "state of the company when
    # we decided" (§5.1).
    as_of_context_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    # 4H.3 additive-only (§3.2): the decide-time state anchor — the
    # company_state_history snapshot refs (source_event_ids) plus bounded
    # dependency/risk/opportunity summaries known when the decision was
    # evaluated or recommended. Mirrors and extends as_of_context_json; a
    # decision may carry both.
    state_context_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    # Denormalized display of the §3.4 quality evidence count.
    quality_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional multi-level scoping (org / business_unit / department / team /
    # person, from COMPANY_SCOPE_TYPES); None = org-wide decision.
    scope_type: Mapped[Optional[str]] = mapped_column(String(12), default=None)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Gate 6-F: Epistemic integrity - track the epistemic status of the decision
    epistemic_status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    # Gate 6-F: Provenance chain for epistemic transitions
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


class CompanyCausalEdge(Base, TimestampMixin):
    """Slice 4H.1 — derived company causality snapshot.

    One row per (source event, hop): the engine derives bounded edges from
    tables the canonical engines already expose and prunes older events so
    the graph stays a recent window. Exact-once on the (event, hop) key —
    replays converge on the same rows.
    """

    __tablename__ = "company_causal_edges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_event_id", "kind",
            "source_type", "source_id", "target_type", "target_id",
            name="uq_cce_hops",
        ),
        Index(
            "ix_cce_org_subject",
            "organization_id", "source_type", "source_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # entity labels: person | project | capability | milestone | customer |
    # goal | objective | outcome | decision | task | execution | dependency
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # one of CAUSAL_EDGE_KINDS (validated by the engine on derivation)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # high | medium | low — from evidence strength of the derivation
    confidence: Mapped[str] = mapped_column(String(12), nullable=False, default="medium")
    # canonical entity refs behind the hop: [{"entity","id","label","kind"}]
    evidence_ref: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


# --- Slice 4H.2 — Universal Organizational Decision Intelligence -----------
# Exactly six new tables (contract §3.1-§3.6), all child rows of the ONE
# canonical CompanyDecision store, all organization-scoped, all exact-once
# keyed. No seventh table may be added without a contract amendment.


class CompanyDecisionAlternative(Base, TimestampMixin):
    """§3.1 — first-class alternatives considered for a decision.

    At least two alternatives per evaluated/recommended decision; exactly one
    `chosen=True` per decision (enforced at write time + partial unique
    index); every rejected alternative MUST carry `why_not` and SHOULD carry
    `preferable_if` (the reversibility condition).
    """

    __tablename__ = "company_decision_alternatives"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # `alt:<decision_id>:<n>` — deterministic exact-once key
    alternative_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # per-alternative expectation (mirrors predicted_outcome shape)
    expected_outcome: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    chosen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # required iff chosen
    why_chosen: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # required for every rejected alternative — the why-not record
    why_not: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # what would need to change for this rejected alternative to become
    # preferable (deadline, capacity, dependency, market condition...)
    preferable_if: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # evidence ids behind this alternative
    evidence_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)


class CompanyDecisionEvidence(Base, TimestampMixin):
    """§3.2 — evidence lineage rows answering "why did we decide this".

    Every row carries the evidence's OWN timestamp (`captured_at`), never
    write-time — it is the as-of anchor (§5.1). Constraints and stakeholders
    are first-class evidence types.
    """

    __tablename__ = "company_decision_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id", "evidence_key",
            name="uq_cdev_key",
        ),
        Index(
            "ix_cdev_org_decision",
            "organization_id", "decision_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decision_id"],
            ["company_decisions.organization_id", "company_decisions.decision_id"],
            name="fk_cdev_decision",
            ondelete="CASCADE",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # optional per-alternative evidence
    alternative_key: Mapped[Optional[str]] = mapped_column(String(80), default=None)
    # `ev:<decision_id>:<n>` — exact-once
    evidence_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # event | metric | insight | pattern | memory | decision | constraint |
    # stakeholder (DECISION_EVIDENCE_TYPES)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # link into the event fabric
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    # e.g. business.metric.updated, insight.detected
    source_kind: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # what this evidence said
    source_summary: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    # the evidence's own timestamp — the as-of anchor
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 0..1
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class CompanyDecisionPrecedent(Base, TimestampMixin):
    """§3.3 — precedent citations: this decision cites a past decision.

    `context_signature` is the deterministic linker (kind + scopes +
    metric/domain keys present in evidence); `cited_lesson` is a SNAPSHOT of
    the past lesson as-of the precedent's outcome (never later edits).
    """

    __tablename__ = "company_decision_precedents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id", "source_event_id",
            name="uq_cdp_exact_once",
        ),
        Index(
            "ix_cdp_org_signature",
            "organization_id", "context_signature",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decision_id"],
            ["company_decisions.organization_id", "company_decisions.decision_id"],
            name="fk_cdp_decision",
            ondelete="CASCADE",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # the new decision citing the precedent
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # the past decision cited
    precedent_decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # canonicalized context tokens (kind + scopes + metric/domain keys)
    context_signature: Mapped[str] = mapped_column(String(240), nullable=False)
    # 0..1, computed, stored
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # evidence items the precedent carries (confidence-with-counts rule)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # snapshot of the lesson as-of the precedent's outcome
    cited_lesson: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # event that created the link (exact-once)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)


class CompanyDecisionQuality(Base, TimestampMixin):
    """§3.4 — quality snapshots (per stage transition, additive, exact-once).

    Quality is composed only from recorded evidence and is an attribute of
    the DECISION, never of a person (§5.3). `prediction_alignment` is None
    until reconciliation exists = "not yet measurable", never a fake 0.
    """

    __tablename__ = "company_decision_quality"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id", "quality_key",
            name="uq_cdq_key",
        ),
        Index(
            "ix_cdq_org_decision",
            "organization_id", "decision_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decision_id"],
            ["company_decisions.organization_id", "company_decisions.decision_id"],
            name="fk_cdq_decision",
            ondelete="CASCADE",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # `q:<decision_id>:<stage>:<n>` — exact-once per recompute
    quality_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # proposed | evaluated | recommended | approved | outcome_recorded
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    # evidence rows at that stage
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # recorded confidence + evidence count (never naked)
    confidence_support: Mapped[Optional[float]] = mapped_column(Float)
    # 0..1 when reconciliation exists; None = "not yet measurable"
    prediction_alignment: Mapped[Optional[float]] = mapped_column(Float)
    # LOW / MEDIUM / HIGH
    risk_band: Mapped[str] = mapped_column(String(10), nullable=False, default="MEDIUM")
    # count surfaced for this decision
    contradictions_surfaced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # the atomic assessment (§5.3) — decision/evidence/event ids, never persons
    assess_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # exact-once
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)


class CompanyDecisionTrack(Base, TimestampMixin):
    """§3.5 — prediction track-record rollups (cohort, advisory, append-only).

    Temporal law: one snapshot row PER source event, never an update — a
    later outcome NEVER rewrites a previous snapshot. An as_of read returns
    the latest snapshot with snapshot_ts <= as_of, byte-identical on replay.
    """

    __tablename__ = "company_decision_tracks"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "cohort_key", "source_event_id",
            name="uq_cdt_snapshot",
        ),
        Index(
            "ix_cdt_org_cohort_time",
            "organization_id", "cohort_key", "snapshot_ts",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # `kind:<kind>` | `kind:<kind>:scope:<type>:<id>` | `period:<YYYY-MM>`
    cohort_key: Mapped[str] = mapped_column(String(160), nullable=False)
    decisions_measured: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictions_recorded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # from actual_outcome_compare.aligned
    aligned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    misaligned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_effectiveness: Mapped[Optional[float]] = mapped_column(Float)
    # the exact-once key — one snapshot row per source event
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # when this snapshot was composed
    snapshot_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CompanyDecisionContradiction(Base, TimestampMixin):
    """§3.6 — surfaced conflicting evidence (append-only, never deleted).

    Both sides are preserved with provenance; status transitions
    (open -> acknowledged -> resolved) are human acts recorded as normal
    lifecycle events. Contradictions count into quality.
    """

    __tablename__ = "company_decision_contradictions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "decision_id", "contradiction_key",
            name="uq_cdc_key",
        ),
        Index(
            "ix_cdc_org_decision_status",
            "organization_id", "decision_id", "status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "decision_id"],
            ["company_decisions.organization_id", "company_decisions.decision_id"],
            name="fk_cdc_decision",
            ondelete="CASCADE",
        ),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # the pending (recommended-stage) decision with the conflict
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # `cx:<decision_id>:<n>` — deterministic exact-once key
    contradiction_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # the contradicting CompanyMemory lesson, when present
    lesson_memory_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    # the contradicting precedent decision, when present
    precedent_decision_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    # the pending decision side: claims + evidence ids + timestamps
    side_a_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # the recorded lesson/precedent side: claims + evidence ids + timestamps
    side_b_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # open | acknowledged | resolved (resolution is a human act)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # event that surfaced the contradiction (exact-once)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # supersedes relationship for contradiction lineage preservation
    supersedes_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_decision_contradictions.id", ondelete="SET NULL"), default=None
    )
    supersedes: Mapped[Optional["CompanyDecisionContradiction"]] = relationship(
        "CompanyDecisionContradiction", remote_side=[id], backref="superseded_by"
    )


class CompanyScenarioRun(Base, TimestampMixin):
    """Slice 4H.4 — Decision-Rehearsal Intelligence (contract §3.1, "no"
    branch of §0.2): append-only institutional memory of recorded rehearsals.

    One row per deterministic rehearsal, exact-once on
    ``(organization_id, scope_type, scope_id, scenario_kind, input_hash,
    snapshot_ref)`` — same hypothetical against the same baseline snapshot is
    the SAME rehearsal (replayed, zero events); the same hypothetical against
    a changed company state is a DIFFERENT rehearsal (new append-only row).
    Rows are time-anchored to their baseline 4H.3 state snapshot and carry
    every identifier a future slice consumes (scenario/snapshot/subject/
    decision/risk/opportunity/causal-edge ids — inside the JSON payloads).

    The scenario NEVER writes the canonical stores (no ``company_causal_edges``
    write, no ``company_decisions`` mutation) and NEVER pretends to predict:
    every row carries ``honesty_json`` asserting advisory-only, not-a-prediction.
    """

    __tablename__ = "company_scenario_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope_type", "scope_id", "scenario_kind",
            "input_hash", "snapshot_ref",
            name="uq_c4h4_exact_once",
        ),
        Index(
            "ix_c4h4_org_time",
            "organization_id", "scope_type", "scope_id", "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # resolved company scope level (COMPANY_SCOPE_TYPES, L14) — the caller's
    # governance-resolved scope, stored on the row, drives row-level surfaces
    scope_type: Mapped[str] = mapped_column(String(24), nullable=False, default="org")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    # `st:<org>:<scope>:<seq>` of the baseline 4H.3 snapshot
    state_key: Mapped[str] = mapped_column(String(140), nullable=False, default="")
    # source_event_id of the baseline 4H.3 snapshot (temporal anchor)
    snapshot_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    # sanctioned SCENARIO_KINDS
    scenario_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # normalized scenario inputs — the single canonical scenario structure
    # {scenario_kind, subject_type, subject_id, params{whitelisted},
    #  assumptions[], organization_scope, as_of}
    input_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # deterministic hash of (scenario_kind, input_json) — exact-once identity
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # human-declared assumptions echoed verbatim, never invented
    assumptions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # bounded hops walk (MAX_CAUSAL_DEPTH/MAX_CAUSAL_EDGES); each hop carries
    # {edge_id, source_type, source_id, target_type, target_id, kind,
    #  confidence, label}
    propagation_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # bounded merged consequence surface with per-item
    # basis {edge_id, source_id, target_id, relation}
    consequences_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # affected decisions → {decision_id, state, why: needs_reconsideration,
    # advisory} — read-only bridge (L12)
    decision_suggestions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # {"advisory_only": true, "not_a_prediction": true, "mode": "bounded-scenario"}
    honesty_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # exact-once key (event-anchored write)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    # event time (the as-of anchor)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
