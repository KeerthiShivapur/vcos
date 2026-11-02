"""Organizational Learning models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class OutcomeAssessment(Base, TimestampMixin):
    __tablename__ = "outcome_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    variance: Mapped[Optional[str]] = mapped_column(Text)
    success_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    lessons: Mapped[List[str]] = mapped_column(JSON, default=list)
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_outcome_assessments_org_entity", "organization_id", "entity_type", "entity_id"),
    )


class OrganizationalLearning(Base, TimestampMixin):
    __tablename__ = "organizational_learning"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    learning_type: Mapped[str] = mapped_column(String(40), nullable=False)  # success, failure, pattern, anti-pattern
    domain: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    source_entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    key_insight: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    applicability: Mapped[List[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="validated", nullable=False)
    validated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    applicable_contexts: Mapped[List[dict]] = mapped_column(JSON, default=list)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    __table_args__ = (
        Index("ix_org_learning_org_domain", "organization_id", "domain"),
        Index("ix_org_learning_org_status", "organization_id", "status"),
    )


class LearningEvidence(Base, TimestampMixin):
    __tablename__ = "learning_evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    learning_id: Mapped[str] = mapped_column(
        ForeignKey("organizational_learning.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_supporting: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_learning_evidence_learning", "learning_id"),
    )


class DecisionOutcome(Base, TimestampMixin):
    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    actual_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    variance: Mapped[Optional[str]] = mapped_column(Text)
    success_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    contributing_factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    lessons_learned: Mapped[List[str]] = mapped_column(JSON, default=list)
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_decision_outcomes_org_decision", "organization_id", "decision_id"),
    )


class RecommendationOutcome(Base, TimestampMixin):
    __tablename__ = "recommendation_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    was_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[Optional[str]] = mapped_column(Text)
    actual_impact: Mapped[Optional[float]] = mapped_column(default=None)
    expected_impact: Mapped[Optional[float]] = mapped_column(default=None)
    variance: Mapped[Optional[float]] = mapped_column(default=None)
    satisfaction_score: Mapped[Optional[int]] = mapped_column(Integer)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    assessed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_recommendation_outcomes_org_rec", "organization_id", "recommendation_id"),
    )


class CompanyChange(Base, TimestampMixin):
    __tablename__ = "company_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    change_scope: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)
    affected_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    driver: Mapped[Optional[str]] = mapped_column(Text)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, in_progress, completed, rolled_back
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    implemented_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    rollback_plan: Mapped[Optional[str]] = mapped_column(Text)
    rollback_executed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_changes_org_status", "organization_id", "status"),
        Index("ix_company_changes_org_type", "organization_id", "change_type"),
    )


class CompanyHealthSignal(Base, TimestampMixin):
    __tablename__ = "company_health_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    value: Mapped[Optional[float]] = mapped_column(default=None)
    threshold: Mapped[Optional[float]] = mapped_column(default=None)
    trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_health_signals_org_active", "organization_id", "is_active"),
        Index("ix_company_health_signals_org_type", "organization_id", "signal_type"),
    )


class ImpactAssessment(Base, TimestampMixin):
    __tablename__ = "impact_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    impact_areas: Mapped[List[str]] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    quantitative_impact: Mapped[dict] = mapped_column(JSON, default=dict)
    qualitative_impact: Mapped[Optional[str]] = mapped_column(Text)
    mitigation_measures: Mapped[List[str]] = mapped_column(JSON, default=list)
    assessed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_impact_assessments_org_entity", "organization_id", "entity_type", "entity_id"),
    )


class KnowledgeClaimLifecycle(Base, TimestampMixin):
    __tablename__ = "knowledge_claim_lifecycles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    claim_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # proposed, supported, authoritative, contested, superseded
    previous_stage: Mapped[Optional[str]] = mapped_column(String(40))
    changed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    outcomeassessment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_knowledge_claim_lifecycles_org_claim", "organization_id", "claim_id"),
    )


class OperatingInsight(Base, TimestampMixin):
    __tablename__ = "operating_insights"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    impact_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    source_data: Mapped[List[dict]] = mapped_column(JSON, default=list)
    related_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    actionable_recommendations: Mapped[List[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_operating_insights_org_type", "organization_id", "insight_type"),
        Index("ix_operating_insights_org_status", "organization_id", "status"),
    )