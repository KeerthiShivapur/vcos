"""Phase 8 — Executive Intelligence & Digital Twin data models.

The executive layer is the organization's living digital model: company
health, strategic risks, executive recommendations, predictions, simulations,
strategic goals, reports, snapshots of the digital twin and metric history all
persist per organization with the standard multi-tenancy columns so every
insight is traceable to underlying organizational data.
"""

from typing import Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class CompanyHealth(Base, TimestampMixin):
    """A computed company health score (Phase 8.2)."""

    __tablename__ = "company_health"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="stable")  # excellent | good | watch | at_risk
    breakdown_json: Mapped[Optional[str]] = mapped_column(Text)  # dimension -> score
    period_start: Mapped[Optional[str]] = mapped_column(String(40))
    period_end: Mapped[Optional[str]] = mapped_column(String(40))

    @property
    def breakdown(self) -> dict[str, Any]:
        import json

        if not self.breakdown_json:
            return {}
        try:
            return json.loads(self.breakdown_json)
        except (json.JSONDecodeError, TypeError):
            return {}


class ExecutiveInsight(Base, TimestampMixin):
    """A single explainable executive insight (Phase 8.1/8.12)."""

    __tablename__ = "executive_insights"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(60), index=True)  # growth | decline | risk | achievement | attention
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)  # traceable evidence chain
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | warning | critical
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | acknowledged | resolved


class ExecutiveMetric(Base, TimestampMixin):
    """A time-bucketed organizational metric for trend analysis (Phase 8.10)."""

    __tablename__ = "organization_metrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(80), index=True)  # tasks_completed | meetings_held | knowledge_published | ...
    value: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(30), default="count")
    period: Mapped[str] = mapped_column(String(10), index=True)  # daily | weekly | monthly | quarterly | yearly
    period_start: Mapped[str] = mapped_column(String(40), index=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text)


class ExecutiveRecommendation(Base, TimestampMixin):
    """An evidence-grounded strategic recommendation (Phase 8.5)."""

    __tablename__ = "executive_recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(60), index=True)  # hire | assign | document | reduce_meetings | review | ...
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)  # why
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)  # evidence
    expected_outcome: Mapped[Optional[str]] = mapped_column(Text)  # expected result
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    impact: Mapped[str] = mapped_column(String(20), default="medium")  # high | medium | low
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | accepted | dismissed


class StrategicRisk(Base, TimestampMixin):
    """A proactively detected strategic risk (Phase 8.4)."""

    __tablename__ = "strategic_risks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(60), index=True)  # project_delay | key_dependency | overload | ...
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float, default=0.5)
    impact: Mapped[float] = mapped_column(Float, default=0.5)
    score: Mapped[float] = mapped_column(Float, default=0.25)
    level: Mapped[str] = mapped_column(String(10), default="low")  # low | medium | high | critical
    subject_type: Mapped[Optional[str]] = mapped_column(String(40))  # project | team | employee | organization
    subject_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    subject_name: Mapped[Optional[str]] = mapped_column(String(300))
    affected_teams_json: Mapped[Optional[str]] = mapped_column(Text)
    recommended_actions_json: Mapped[Optional[str]] = mapped_column(Text)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | accepted | mitigated


class OrganizationSnapshot(Base, TimestampMixin):
    """A persisted snapshot of the digital twin (Phase 8.6)."""

    __tablename__ = "organization_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    twin_json: Mapped[Optional[str]] = mapped_column(Text)  # full twin payload
    entity_counts_json: Mapped[Optional[str]] = mapped_column(Text)
    captured_at: Mapped[Optional[str]] = mapped_column(String(40))


class Simulation(Base, TimestampMixin):
    """A scenario simulation run and its results (Phase 8.7)."""

    __tablename__ = "simulations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario: Mapped[str] = mapped_column(String(60), index=True)  # hire_engineers | delay_release | lose_specialist | ...
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    assumptions_json: Mapped[Optional[str]] = mapped_column(Text)
    results_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="completed")


class ExecutiveReport(Base, TimestampMixin):
    """An automatically generated executive report (Phase 8.13)."""

    __tablename__ = "executive_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(40), index=True)  # daily | weekly | monthly | quarterly | board | annual | department | hiring | innovation | knowledge | compliance
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    period_start: Mapped[Optional[str]] = mapped_column(String(40))
    period_end: Mapped[Optional[str]] = mapped_column(String(40))
    export_format: Mapped[str] = mapped_column(String(10), default="text")  # text | markdown | csv
    status: Mapped[str] = mapped_column(String(20), default="generated")


class StrategicGoal(Base, TimestampMixin):
    """A strategic goal tracked by the executive strategy layer (Phase 8.4/8.15)."""

    __tablename__ = "strategic_goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    timeframe: Mapped[str] = mapped_column(String(30), default="quarter")  # quarter | half | year | multi_year
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned | in_progress | completed | at_risk
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    focus: Mapped[str] = mapped_column(String(40), default="growth")  # growth | retention | innovation | efficiency | expansion | learning
    links_json: Mapped[Optional[str]] = mapped_column(Text)  # linked projects/departments/initiatives
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
