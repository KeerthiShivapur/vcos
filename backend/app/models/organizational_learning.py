"""Slice 4E.7 — Universal Knowledge Operating Loop: the learning, evolution and
feedback entities that close the company loop.

4E.6 gave knowledge a governed action life; 4E.7 gives the company a MEMORY
that learns from what actually happened. This model file holds the durable
entities of the Organizational Learning Engine and its companions:

* ``OutcomeAssessment``   expected vs actual for a verified action/decision,
* ``OrganizationalLearning``  a lesson the company learned (exact-once), with
  ``LearningEvidence`` links to the sources that support it,
* ``DecisionOutcome`` / ``RecommendationOutcome``  the decision- and
  recommendation-feedback loops (deterministic, explainable quality),
* ``CompanyChange``  a materialized "what changed?" signal (critical /
  important / normal) with evidence and impact,
* ``CompanyHealthSignal``  an explainable 0-100 health signal per company
  dimension (never a fake black-box score),
* ``ImpactAssessment``  the persisted company-wide impact analysis (if we do
  X, what does it reach?),
* ``OperatingInsight``  the Universal Action Center consolidation (critical
  issues, pending approvals, emerging risks, learning opportunities, …).

Architecture law (established in 4E.1-4E.6, preserved here): rows are
tenant-scoped, keyed by a stable ``fingerprint``/unique constraint so replay is
exact-once, carry their lineage and actor, and are never deleted — state moves
forward, history is retained. Learning NEVER silently rewrites company rules:
it writes audited evidence + an explainable confidence adjustment into the
existing canonical knowledge model (``KnowledgeClaim`` lifecycle stages), it
does not replace the deterministic governance core.
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutcomeAssessment(Base):
    """One expected-vs-actual assessment of a verified action or a decision:
    what was expected, what actually happened, the variance, and the detected
    causal factors — the raw material the Learning Engine turns into lessons.
    Keyed (subject_type, subject_id) so a re-record is an in-place refresh,
    never a duplicate."""

    __tablename__ = "outcome_assessments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "subject_type", "subject_id",
            name="uq_outcome_assessments_subject",
        ),
        Index("ix_outcome_assessments_org_subject", "organization_id", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # action | decision
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_metric: Mapped[Optional[str]] = mapped_column(String(120))
    expected_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_units: Mapped[Optional[str]] = mapped_column(String(60))
    actual_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    variance_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    assessment: Mapped[str] = mapped_column(String(16), default="met", nullable=False, index=True)  # outperformed | met | underperformed
    factors_json: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    assessed_by: Mapped[Optional[str]] = mapped_column(String(32))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class OrganizationalLearning(Base):
    """A lesson the company learned. Exact-once by (kind, fingerprint): the same
    outcome replayed never spawns a second lesson. The lesson can update the
    canonical knowledge lifecycle (TESTED/CONFIRMED/SUPERSEDED) and is always
    backed by ``LearningEvidence`` rows — learning is never invented, only
    evidenced."""

    __tablename__ = "organizational_learning"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "kind", "fingerprint",
            name="uq_organizational_learning_fingerprint",
        ),
        Index("ix_organizational_learning_org_kind", "organization_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # outcome_learning | decision_learning | recommendation_learning |
    # contradiction_resolution | knowledge_confirmation
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    lesson: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)  # active | applied | archived
    lifecycle: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False)
    # discovered -> candidate -> supported -> authoritative -> confirmed ->
    # superseded -> archived
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String(32))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    topic_id: Mapped[Optional[str]] = mapped_column(String(32))
    topic_name: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    claims_updated_json: Mapped[Optional[str]] = mapped_column(Text)
    observation: Mapped[Optional[str]] = mapped_column(Text)  # what actually happened
    expectation: Mapped[Optional[str]] = mapped_column(Text)  # what was expected
    recorded_by: Mapped[Optional[str]] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class LearningEvidence(Base):
    """One source that evidences a lesson. Rows are immutable and keyed
    (learning_id, source_type, source_id) so a replay never duplicates."""

    __tablename__ = "learning_evidence"
    __table_args__ = (
        UniqueConstraint(
            "learning_id", "source_type", "source_id",
            name="uq_learning_evidence_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    learning_id: Mapped[str] = mapped_column(
        ForeignKey("organizational_learning.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), default="primary", nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DecisionOutcome(Base):
    """Decision feedback loop: a decision's expected vs actual result, so the
    company builds a historical record of decision performance."""

    __tablename__ = "decision_outcomes"
    __table_args__ = (
        UniqueConstraint("organization_id", "decision_id", name="uq_decision_outcomes_decision"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expected_metric: Mapped[Optional[str]] = mapped_column(String(120))
    expected_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_units: Mapped[Optional[str]] = mapped_column(String(60))
    actual_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    variance_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    assessment: Mapped[str] = mapped_column(String(16), default="met", nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(16), default="success", nullable=False)  # success | partial | failure
    factors_json: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    measured_by: Mapped[Optional[str]] = mapped_column(String(32))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class RecommendationOutcome(Base):
    """Recommendation feedback loop: whether a materialized recommendation's
    action succeeded, so per-kind recommendation quality is measured
    deterministically (never a silent model rewrite)."""

    __tablename__ = "recommendation_outcomes"
    __table_args__ = (
        UniqueConstraint("organization_id", "recommendation_id", name="uq_recommendation_outcomes_rec"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_recommendations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    action_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    outcome_type: Mapped[str] = mapped_column(String(16), default="success", nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effectiveness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    measured_by: Mapped[Optional[str]] = mapped_column(String(32))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CompanyChange(Base):
    """A materialized company "what changed?" signal. Computed deterministically
    from governed activity (escalations, overdue/blocked actions, superseded
    knowledge, finalized decisions, learned lessons) and keyed exact-once by
    (kind, fingerprint) so replays never duplicate. Nothing is invented: each
    change carries its evidence and impact."""

    __tablename__ = "company_changes"
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "fingerprint", name="uq_company_changes_fingerprint"),
        Index("ix_company_changes_org_type", "organization_id", "change_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # critical | important | normal
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    what_changed: Mapped[Optional[str]] = mapped_column(Text)
    why_changed: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    impact_json: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(32))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(32))
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CompanyHealthSignal(Base):
    """An explainable health signal (0-100) for one company dimension. Every
    signal carries its metric, evidence counts, time window, confidence and a
    plain-language explanation — there are no black-box AI scores."""

    __tablename__ = "company_health_signals"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "dimension", "metric", name="uq_company_health_signal_metric"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trend: Mapped[Optional[str]] = mapped_column(String(16))  # up | flat | down
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    time_window_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImpactAssessment(Base):
    """A persisted company-wide impact analysis. Bounded BFS over the knowledge
    graph, knowledge claims and governed action dependencies, collecting
    direct/indirect reach, risks, owners, customers, deadlines, financial
    assumptions and recommended mitigations. Refreshed idempotently per
    (subject_type, subject_id)."""

    __tablename__ = "impact_assessments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "subject_type", "subject_id",
            name="uq_impact_assessments_subject",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_title: Mapped[Optional[str]] = mapped_column(String(240))
    direct_json: Mapped[Optional[str]] = mapped_column(Text)
    indirect_json: Mapped[Optional[str]] = mapped_column(Text)
    risks_json: Mapped[Optional[str]] = mapped_column(Text)
    owners_json: Mapped[Optional[str]] = mapped_column(Text)
    customers_json: Mapped[Optional[str]] = mapped_column(Text)
    deadlines_json: Mapped[Optional[str]] = mapped_column(Text)
    financial_json: Mapped[Optional[str]] = mapped_column(Text)
    mitigations_json: Mapped[Optional[str]] = mapped_column(Text)
    total_direct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_indirect: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_by: Mapped[Optional[str]] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class KnowledgeClaimLifecycle(Base):
    """4E.7 knowledge lifecycle ledger — an append-only companion to the
    canonical 4E.1 ``KnowledgeClaim`` (the canonical table itself is never
    broken). Each row records one governed stage transition of a claim:
    discovered -> candidate -> supported -> authoritative -> used -> tested ->
    confirmed -> superseded -> archived, with the reason, the evidence and the
    actor. The current stage of a claim is the latest row; history is never
    deleted, so "what did the company believe and when was it last validated"
    is always answerable."""

    __tablename__ = "knowledge_claim_lifecycle"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "claim_id", "stage", "reason",
            name="uq_knowledge_claim_lifecycle_step",
        ),
        Index("ix_knowledge_claim_lifecycle_claim", "organization_id", "claim_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_claims.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    learning_id: Mapped[Optional[str]] = mapped_column(String(32))
    actor_id: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OperatingInsight(Base):
    """The Universal Action Center: one consolidated, governed surface that
    turns otherwise disconnected signals into an operating board. Categories —
    critical_issue, recommended_action, pending_approval, knowledge_gap,
    contradiction, emerging_risk, overdue_action, decision_attention,
    customer_impact, learning_opportunity — are keyed exact-once and can be
    resolved (never deleted), each carrying why/what/impact/evidence/owner/
    risk/approval/status/outcome."""

    __tablename__ = "operating_insights"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "category", "fingerprint",
            name="uq_operating_insights_fingerprint",
        ),
        Index("ix_operating_insights_org_cat", "organization_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    why: Mapped[Optional[str]] = mapped_column(Text)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    risk: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    authorization_level: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)  # auto | approval | human
    owner_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(32))
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    reference_status: Mapped[Optional[str]] = mapped_column(String(32))
    reference_outcome: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(String(32))