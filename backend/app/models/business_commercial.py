"""Business Commercial models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class BusinessNeedKind(str):
    PROBLEM = "problem"
    OPPORTUNITY = "opportunity"
    REQUIREMENT = "requirement"
    IDEA = "idea"
    COMPLAINT = "complaint"
    REQUEST = "request"


class BusinessNeedStatus(str):
    NEW = "new"
    TRIAGED = "triaged"
    ANALYZING = "analyzing"
    PRIORITIZED = "prioritized"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BusinessNeed(Base, TimestampMixin):
    __tablename__ = "business_needs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), default=BusinessNeedKind.PROBLEM, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=BusinessNeedStatus.NEW, nullable=False, index=True)
    submitter_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    assignee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    impact_estimate: Mapped[Optional[str]] = mapped_column(Text)
    effort_estimate: Mapped[Optional[str]] = mapped_column(String(50))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    businessneedkind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_business_needs_org_status", "organization_id", "status"),
        Index("ix_business_needs_org_submitter", "organization_id", "submitter_id"),
    )


BUSINESS_NEED_KINDS = [BusinessNeedKind.PROBLEM, BusinessNeedKind.OPPORTUNITY, BusinessNeedKind.REQUIREMENT, BusinessNeedKind.IDEA, BusinessNeedKind.COMPLAINT, BusinessNeedKind.REQUEST]
BUSINESS_NEED_STATES = [BusinessNeedStatus.NEW, BusinessNeedStatus.TRIAGED, BusinessNeedStatus.ANALYZING, BusinessNeedStatus.PRIORITIZED, BusinessNeedStatus.APPROVED, BusinessNeedStatus.REJECTED, BusinessNeedStatus.IN_PROGRESS, BusinessNeedStatus.COMPLETED, BusinessNeedStatus.CANCELLED]


class CommercialIntentKind(str):
    PURCHASE = "purchase"
    RENEWAL = "renewal"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    EXPANSION = "expansion"
    CROSS_SELL = "cross_sell"
    UPSELL = "upsell"
    CROSS_SELL = "cross_sell"
    CHURN_PREVENTION = "churn_prevention"
    PARTNERSHIP = "partnership"


class CommercialIntentState(str):
    IDENTIFIED = "identified"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATING = "negotiating"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    ON_HOLD = "on_hold"


class CommercialIntent(Base, TimestampMixin):
    __tablename__ = "commercial_intents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), default=CommercialIntentKind.PURCHASE, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=CommercialIntentState.IDENTIFIED, nullable=False, index=True)
    value_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    value_amount: Mapped[Optional[float]] = mapped_column(default=None)
    probability: Mapped[float] = mapped_column(default=0.0, nullable=False)
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[Optional[str]] = mapped_column(String(60))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    businessneedkind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_commercial_intents_org_customer", "organization_id", "customer_id"),
        Index("ix_commercial_intents_org_status", "organization_id", "status"),
    )


COMMERCIAL_INTENT_KINDS = [CommercialIntentKind.PURCHASE, CommercialIntentKind.RENEWAL, CommercialIntentKind.UPGRADE, CommercialIntentKind.DOWNGRADE, CommercialIntentKind.EXPANSION, CommercialIntentKind.CROSS_SELL, CommercialIntentKind.UPSELL, CommercialIntentKind.CHURN_PREVENTION, CommercialIntentKind.PARTNERSHIP]
COMMERCIAL_INTENT_STATES = [CommercialIntentState.IDENTIFIED, CommercialIntentState.QUALIFIED, CommercialIntentState.PROPOSAL, CommercialIntentState.NEGOTIATING, CommercialIntentState.CLOSED_WON, CommercialIntentState.CLOSED_LOST, CommercialIntentState.ON_HOLD]


class BusinessOutcomeKind(str):
    REVENUE = "revenue"
    COST_SAVINGS = "cost_savings"
    EFFICIENCY = "efficiency"
    CUSTOMER_SATISFACTION = "customer_satisfaction"
    EMPLOYEE_ENGAGEMENT = "employee_engagement"
    INNOVATION = "innovation"
    COMPLIANCE = "compliance"
    RISK_REDUCTION = "risk_reduction"


class BusinessOutcomeState(str):
    PROJECTED = "projected"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    EXCEEDED = "exceeded"
    MISSED = "missed"
    ABANDONED = "abandoned"


class BusinessOutcome(Base, TimestampMixin):
    __tablename__ = "business_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), default=BusinessOutcomeKind.REVENUE, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=BusinessOutcomeState.PROJECTED, nullable=False, index=True)
    value_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    value_amount: Mapped[Optional[float]] = mapped_column(default=None)
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    achieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    related_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    businessneedkind_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_business_outcomes_org_status", "organization_id", "status"),
        Index("ix_business_outcomes_org_kind", "organization_id", "kind"),
    )


BUSINESS_OUTCOME_KINDS = [BusinessOutcomeKind.REVENUE, BusinessOutcomeKind.COST_SAVINGS, BusinessOutcomeKind.EFFICIENCY, BusinessOutcomeKind.CUSTOMER_SATISFACTION, BusinessOutcomeKind.EMPLOYEE_ENGAGEMENT, BusinessOutcomeKind.INNOVATION, BusinessOutcomeKind.COMPLIANCE, BusinessOutcomeKind.RISK_REDUCTION]
BUSINESS_OUTCOME_STATES = [BusinessOutcomeState.PROJECTED, BusinessOutcomeState.IN_PROGRESS, BusinessOutcomeState.ACHIEVED, BusinessOutcomeState.EXCEEDED, BusinessOutcomeState.MISSED, BusinessOutcomeState.ABANDONED]


class CustomerRisk(Base, TimestampMixin):
    """Customer risk assessment."""
    __tablename__ = "customer_risks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    risk_type: Mapped[str] = mapped_column(String(40), nullable=False)  # churn, credit, operational, reputational
    severity: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # low, medium, high, critical
    probability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    impact: Mapped[str] = mapped_column(String(24), default="medium", nullable=False)  # low, medium, high, critical
    description: Mapped[str] = mapped_column(Text, nullable=False)
    indicators: Mapped[List[str]] = mapped_column(JSON, default=list)
    mitigation: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="identified", nullable=False)  # identified, monitoring, mitigating, resolved, accepted
    identified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    businesscommercial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_customer_risks_org_customer", "organization_id", "customer_id"),
        Index("ix_customer_risks_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )


class CustomerOperatingSlice(Base, TimestampMixin):
    """Customer operating slice - customer-specific operating context."""
    __tablename__ = "customer_operating_slices"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    slice_type: Mapped[str] = mapped_column(String(40), nullable=False)  # strategic, tactical, operational
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)  # active, paused, completed, archived
    scope_data: Mapped[dict] = mapped_column(JSON, default=dict)
    businesscommercial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_cust_ops_org_customer", "organization_id", "customer_id"),
        Index("ix_cust_ops_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )


class CustomerImpactAnalysis(Base, TimestampMixin):
    """Customer impact analysis for business decisions."""
    __tablename__ = "customer_impact_analyses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(40), nullable=False)  # churn_risk, upsell_potential, health_score
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    recommendations: Mapped[List[str]] = mapped_column(JSON, default=list)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    businesscommercial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_cust_impact_org_customer", "organization_id", "customer_id"),
        Index("ix_cust_impact_org_type", "organization_id", "analysis_type"),
        {"extend_existing": True},
    )


class CustomerOperatingContext(Base, TimestampMixin):
    """Customer operating context - the customer's view of the company."""
    __tablename__ = "customer_operating_contexts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    context_type: Mapped[str] = mapped_column(String(40), nullable=False)  # strategic, tactical, operational, relationship
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)  # active, paused, completed, archived
    context_data: Mapped[dict] = mapped_column(JSON, default=dict)
    businesscommercial_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_cust_op_ctx_org_customer", "organization_id", "customer_id"),
        Index("ix_cust_op_ctx_org_status", "organization_id", "status"),
        {"extend_existing": True},
    )