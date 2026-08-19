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

# Lifecycle of a governed decision artifact. approved -> executed ->
# outcome_recorded; declined is terminal and is itself remembered.
DECISION_STATES = (
    "approved",
    "declined",
    "executed",
    "outcome_recorded",
)

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


class CompanyHealthHistory(Base, TimestampMixin):
    """Append-only temporal trail of the composed company health assessment.

    One row per recomputing event (exact-once on the source event), so the
    company-level "What changed?" and the "Why?" layer stay answerable over
    any period. The live assessment is simply the latest row.
    """

    __tablename__ = "company_health_history"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_event_id",
            name="uq_chh_exact_once",
        ),
        Index(
            "ix_chh_org_time",
            "organization_id", "occurred_at",
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
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
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
    # approved | declined | executed | outcome_recorded
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
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
