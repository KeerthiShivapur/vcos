"""Slice 4F.7 — People Decision Intelligence (the 4F capstone).

Turns 4F.1..4F.6 into evidence-backed, human-controlled organizational
decision support. "Given all that evidence, what people/organizational
decision should we consider, and why?"

Central principle (from the 4F.7 directive): decision intelligence, NOT
automatic employee management. VCOS reasons and recommends; a human decides;
the outcome becomes evidence for the next decision. The canonical chain:

    Observe -> Reason -> Recommend -> Explain -> Human decision
        -> Authorized action -> Outcome -> (evidence for the next decision)

Hard rules:
  * Candidates are compared with decision-specific evidence (skill match,
    trusted expertise, availability, ownership, collaboration, capability,
    prior outcomes, scope) — NEVER with an opaque employee score. There is
    no "Alice = 93" ranking anywhere; the Why is a list of evidence bullets.
  * Every recommendation carries alternatives, trade-offs, unknowns, a
    confidence and a full provenance trail (request, context, evidence,
    constraints, alternatives, recommendation, timestamp) so "why did VCOS
    recommend this?" is always reconstructable.
  * The decision lifecycle is a human-governed state machine:
    detected -> evaluated -> recommended -> reviewed -> approved | rejected
    -> executed -> verified -> outcome. Outcome (successful / unsuccessful /
    partial / unknown) feeds the next evaluation -> Decision -> Outcome ->
    Learning moat. Negative evidence is never hidden ("5 successful outcomes,
    1 unsuccessful outcome" is shown honestly).
  * Governance risk tiers: LOW (information retrieval, expertise discovery,
    stakeholder suggestions) and MEDIUM (staffing, ownership, collaboration,
    capacity, team composition) recommendations may be produced by VCOS.
    HIGH (hiring, promotion, termination, compensation, disciplinary) is
    refused: those decisions remain entirely under human governance.
  * Privacy pipeline is LOCKED in order: Identity -> Authorization ->
    Governance scope -> Accessible evidence -> Decision reasoning -> Answer.
    Reasoning never runs before permission checks. Scoped callers only ever
    see people and evidence inside their anchored scope.
  * "What if?" is a BOUNDED decision simulation: deltas are computed against
    the decision's own context (capacity, ownership, concentration,
    collaboration, workload for the recommended vs the alternative). It is
    NOT the 4P prediction engine.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# ---------------------------------------------------------------------------
# Decision types — the framework of organizational people decisions.
# ---------------------------------------------------------------------------
DECISION_TYPES: tuple[str, ...] = (
    "staffing",            # who should take this responsibility / this task
    "ownership",           # who should own this project / capability / system
    "backup_ownership",    # who should be the secondary (bus-factor) owner
    "expertise",           # who has the strongest trusted expertise (info)
    "capacity",            # who can take this on without breaking availability
    "collaboration",       # who should be involved / who works best together
    "capability_gap",      # what capability gap prevents us from doing this
    "succession",          # who is the continuity path for a key role
    "team_composition",    # which team can absorb this work
    "stakeholders",        # who should be consulted / informed (info)
)

# Governance risk tiers (from the directive): HIGH-impact people decisions
# stay under human governance; VCOS never automates them.
RISK_TIERS: tuple[str, ...] = (
    "low",      # information retrieval, expertise discovery, stakeholders
    "medium",   # staffing, ownership, collaboration, capacity, composition
    "high",     # hiring, promotion, termination, compensation, disciplinary
)

# Bounded recommendation model: one primary, a small honest set of
# alternatives with trade-offs, everyone else excluded with a why_not.
ROLE_RECOMMENDED = "recommended"
ROLE_ALTERNATIVE = "alternative"
ROLE_EXCLUDED = "excluded"

# Human-controlled lifecycle state machine.
LIFECYCLE_STATES: tuple[str, ...] = (
    "detected",     # an organizational signal surfaced a candidate decision
    "evaluated",    # evidence gathered, candidates reasoned over
    "recommended",  # primary + alternatives + trade-offs + confidence ready
    "reviewed",     # a human reviewed the recommendation
    "approved",     # human approved the recommendation
    "rejected",     # human rejected the recommendation
    "executed",     # human authorized action was taken
    "verified",     # the action was verified as taken
    "outcome",      # the outcome was recorded and becomes future evidence
)

# Outcome statuses — the learning feedback. Honest: unsuccessful is kept.
OUTCOME_STATUSES: tuple[str, ...] = (
    "successful",
    "unsuccessful",
    "partial",
    "unknown",
)


class PeopleDecision(TimestampMixin, Base):
    """Canonical organizational decision record — one per decision.

    The decision itself, its context, requirements, lifecycle position,
    recommendation and provenance. Never contains employee scores: the
    recommendation is evidence (DecisionCandidate rows + evidence items).
    """

    __tablename__ = "people_decisions"
    __table_args__ = (
        Index(
            "ix_people_decisions_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_people_decisions_ctx",
            "organization_id",
            "context_type",
            "context_id",
        ),
        Index(
            "ix_people_decisions_lifecycle",
            "organization_id",
            "lifecycle",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # What kind of decision and how heavy its governance is.
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)

    # Context: what the decision is about (a project, a capability, a team,
    # a system, or the whole organization).
    context_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    context_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    context_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # The request in the requester's own words (the decision context).
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    # Requirements extracted / declared for the decision (skill ids).
    requirements_json: Mapped[str] = mapped_column(Text, default="[]")

    # Lifecycle (human-controlled state machine).
    lifecycle: Mapped[str] = mapped_column(String(20), default="detected")

    # Recommendation (evidence-backed, never a score).
    recommended_person_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    recommended_person_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Full provenance — "why did VCOS recommend this?" is reconstructable.
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")

    # Human decision record (who decided what, when).
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Outcome — the learning feedback for future decisions.
    outcome_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    outcome_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome_recorded_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    outcome_recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Exact-once wiring for change-driven creation (the triggering event).
    last_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class DecisionCandidate(Base):
    """One evaluated person for a decision — with WHY, not a score.

    role=recommended for the primary choice, alternative for the honest
    runner-ups (with trade_off vs the primary), excluded otherwise (with
    why_not explaining what disqualified them).
    """

    __tablename__ = "decision_candidates"
    __table_args__ = (
        Index("ix_decision_candidates_decision", "decision_id", "rank"),
        Index("ix_decision_candidates_person", "organization_id", "person_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("people_decisions.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_label: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    # The evidence-backed verdict per dimension (JSON of dimension -> grade).
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    # Human-readable bullets: what speaks FOR this person.
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # For alternatives: trade-off vs the primary. For excluded: why not.
    trade_off: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    why_not: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionEvidenceItem(Base):
    """One discrete evidence fact behind a decision's reasoning.

    dimension in {expertise, trust, ownership, collaboration, capacity,
    capability, scope, outcome, workload, context}. source_* records where
    the fact came from so every claim is traceable.
    """

    __tablename__ = "decision_evidence_items"
    __table_args__ = (
        Index("ix_decision_evidence_items_decision", "decision_id", "dimension"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("people_decisions.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dimension: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionSimulation(Base):
    """A bounded "what if?" run — deltas of assigning a specific person.

    Deltas are computed against the decision's own context only (capacity,
    ownership, concentration, collaboration, workload), never an org-wide
    prediction. Bounded per decision (the engine prunes old runs).
    """

    __tablename__ = "decision_simulations"
    __table_args__ = (
        Index("ix_decision_simulations_decision", "decision_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("people_decisions.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Baseline (primary) vs this person: JSON of dimension -> (baseline, delta).
    deltas_json: Mapped[str] = mapped_column(Text, default="{}")
    verdict: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionAudit(Base):
    """Append-only human-governance trail for a decision lifecycle.

    Every transition (created/evaluated/reviewed/approved/rejected/executed/
    verified/outcome) is recorded with its actor and timestamp so the human
    control record is never lost.
    """

    __tablename__ = "decision_audit"
    __table_args__ = (
        Index("ix_decision_audit_decision", "decision_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("people_decisions.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
