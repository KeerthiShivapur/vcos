"""Executive models for dashboards, insights, reports, and strategic planning."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import DateTime, Date, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CompanyHealth(Base, TimestampMixin):
    __tablename__ = "company_health"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    health_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    health_status: Mapped[str] = mapped_column(String(24), default="good", nullable=False)  # excellent, good, fair, poor, critical
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    trends: Mapped[dict] = mapped_column(JSON, default=dict)
    alerts: Mapped[List[dict]] = mapped_column(JSON, default=list)
    recommendations: Mapped[List[dict]] = mapped_column(JSON, default=list)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "period_end", name="uq_company_health_org_period"),
        Index("ix_company_health_org_period", "organization_id", "period_end"),
    )


class ExecutiveInsight(Base, TimestampMixin):
    __tablename__ = "executive_insights"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)  # info, warning, critical
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    impact_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    affected_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    actionable_recommendations: Mapped[List[dict]] = mapped_column(JSON, default=list)
    source_data_refs: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="new", nullable=False)  # new, acknowledged, actioned, dismissed
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_executive_insights_org_type", "organization_id", "insight_type"),
        Index("ix_executive_insights_org_severity", "organization_id", "severity"),
        Index("ix_executive_insights_org_status", "organization_id", "status"),
    )


class ExecutiveMetric(Base, TimestampMixin):
    __tablename__ = "executive_metrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    previous_value: Mapped[Optional[float]] = mapped_column(default=None)
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)  # up, down, stable, volatile
    change_percent: Mapped[float] = mapped_column(default=0.0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)  # daily, weekly, monthly, quarterly, yearly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    data_source: Mapped[Optional[str]] = mapped_column(String(100))
    companyhealth_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "metric_key", "period", "period_end", name="uq_exec_metrics_org_key_period"),
        Index("ix_executive_metrics_org_category", "organization_id", "category"),
        Index("ix_executive_metrics_org_period", "organization_id", "period_end"),
    )


class ExecutiveRecommendation(Base, TimestampMixin):
    __tablename__ = "executive_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    impact_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    effort_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    roi_estimate: Mapped[Optional[float]] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)  # proposed, approved, in_progress, completed, rejected
    assigned_to: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    supporting_data: Mapped[dict] = mapped_column(JSON, default=dict)
    related_insights: Mapped[List[str]] = mapped_column(JSON, default=list)
    companyhealth_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_exec_recs_org_category", "organization_id", "category"),
        Index("ix_executive_recs_org_priority", "organization_id", "priority"),
        Index("ix_executive_recs_org_status", "organization_id", "status"),
    )


class ExecutiveReport(Base, TimestampMixin):
    __tablename__ = "executive_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # weekly, monthly, quarterly, annual, custom
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft, generating, completed, distributed
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sections: Mapped[List[dict]] = mapped_column(JSON, default=list)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    insights: Mapped[List[str]] = mapped_column(JSON, default=list)
    recommendations: Mapped[List[str]] = mapped_column(JSON, default=list)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    distributed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recipients: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_executive_reports_org_period", "organization_id", "period_end"),
        Index("ix_executive_reports_org_type", "organization_id", "report_type"),
    )


class OrganizationSnapshot(Base, TimestampMixin):
    __tablename__ = "organization_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(24), default="daily", nullable=False)  # daily, weekly, monthly, quarterly, annual
    headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    departments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    teams_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    projects_active: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    projects_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[Optional[float]] = mapped_column(default=None)
    expenses: Mapped[Optional[float]] = mapped_column(default=None)
    profit: Mapped[Optional[float]] = mapped_column(default=None)
    cash_balance: Mapped[Optional[float]] = mapped_column(default=None)
    runway_months: Mapped[Optional[float]] = mapped_column(default=None)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    health_score: Mapped[Optional[float]] = mapped_column(default=None)
    companyhealth_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", "snapshot_type", name="uq_org_snapshots_org_date_type"),
        Index("ix_org_snapshots_org_type", "organization_id", "snapshot_type"),
    )


class Simulation(Base, TimestampMixin):
    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    simulation_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # scenario, forecast, what-if, stress-test
    scenario_params: Mapped[dict] = mapped_column(JSON, default=dict)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, running, completed, failed
    results: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence_interval: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_simulations_org_status", "organization_id", "status"),
        Index("ix_simulations_org_type", "organization_id", "simulation_type"),
    )


class StrategicRisk(Base, TimestampMixin):
    __tablename__ = "strategic_risks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    risk_category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    likelihood: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    impact: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mitigation_strategy: Mapped[Optional[str]] = mapped_column(Text)
    contingency_plan: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="identified", nullable=False)  # identified, monitoring, mitigating, resolved
    identified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_strategic_risks_org_status", "organization_id", "status"),
        Index("ix_strategic_risks_org_category", "organization_id", "risk_category"),
    )


class StrategicGoal(Base, TimestampMixin):
    __tablename__ = "strategic_goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    time_horizon: Mapped[str] = mapped_column(String(24), default="yearly", nullable=False)  # quarterly, yearly, 3_year, 5_year
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="planning", nullable=False)  # planning, active, on_track, at_risk, completed, cancelled
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    parent_goal_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    success_criteria: Mapped[List[str]] = mapped_column(JSON, default=list)
    key_results: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    companyhealth_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_strategic_goals_org_status", "organization_id", "status"),
        Index("ix_strategic_goals_org_owner", "organization_id", "owner_id"),
    )