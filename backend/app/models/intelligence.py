"""Phase 9 — Background Intelligence & Autonomous Organization models.

Every background computation is observable: events feed handlers, handlers
update intelligence tables, and every mutation leaves a trace. These tables
are written by the background workers / event handlers, never by API request
handlers (unless a worker is triggered manually for a live refresh).
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundJob(Base, TimestampMixin):
    """A background job with retry + idempotency bookkeeping.

    status: queued | running | done | failed | retry
    """

    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_bg_jobs_org_status", "organization_id", "status"),
        Index("ix_bg_jobs_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def payload(self) -> Optional[dict]:
        import json

        if not self.payload_json:
            return None
        try:
            return json.loads(self.payload_json)
        except (json.JSONDecodeError, TypeError):
            return None


class ExpertiseHistory(Base, TimestampMixin):
    """Every expertise score change, with the event that caused it."""

    __tablename__ = "expertise_history"
    __table_args__ = (
        Index("ix_expertise_history_org_emp", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    skill_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    skill_name: Mapped[Optional[str]] = mapped_column(String(120))
    before: Mapped[float] = mapped_column(Float, default=0.0)
    after: Mapped[float] = mapped_column(Float, default=0.0)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    source_event: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)


class OrgGraphEdge(Base, TimestampMixin):
    """An organization graph relationship (employee <-> employee/entity)."""

    __tablename__ = "org_graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id", "target_type", "target_id", "relation",
            name="uq_org_graph_edge",
        ),
        Index("ix_org_graph_source", "organization_id", "source_type", "source_id"),
        Index("ix_org_graph_target", "organization_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # employee | project | department | team | knowledge | community
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation: Mapped[str] = mapped_column(String(60), nullable=False)  # works_on | collaborates_with | authored | member_of | depends_on | manages
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[Optional[str]] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GraphUpdate(Base, TimestampMixin):
    """Audit trail of graph mutations made by the graph worker."""

    __tablename__ = "graph_updates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)  # edge_added | edge_updated | edge_deactivated
    relation: Mapped[str] = mapped_column(String(60), index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(32))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(32))
    detail: Mapped[Optional[str]] = mapped_column(String(500))


class KnowledgeInsight(Base, TimestampMixin):
    """Automatically detected knowledge problems and improvement suggestions."""

    __tablename__ = "knowledge_insights"
    __table_args__ = (
        Index("ix_knowledge_insights_org_kind", "organization_id", "kind"),
        Index("ix_knowledge_insights_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # outdated | duplicate | missing | unused | conflict | gap
    entity_type: Mapped[Optional[str]] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    related_type: Mapped[Optional[str]] = mapped_column(String(32))
    related_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    recommendation: Mapped[Optional[str]] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | accepted | dismissed
    source: Mapped[str] = mapped_column(String(60), default="knowledge_worker")


class CollaborationMetric(Base, TimestampMixin):
    """Collaboration network metrics computed by the collaboration worker."""

    __tablename__ = "collaboration_metrics"
    __table_args__ = (
        Index("ix_collab_metrics_org_type", "organization_id", "metric_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(60), nullable=False)  # dept_pair_interactions | team_engagement | cross_functional | silo
    value: Mapped[float] = mapped_column(Float, default=0.0)
    detail_json: Mapped[Optional[str]] = mapped_column(Text)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def detail(self) -> Optional[dict]:
        import json

        if not self.detail_json:
            return None
        try:
            return json.loads(self.detail_json)
        except (json.JSONDecodeError, TypeError):
            return None


class BurnoutSignal(Base, TimestampMixin):
    """Workload-pattern signals that may warrant manager review.

    AI never diagnoses medical conditions. A high score means the workload
    pattern matches known overload patterns and a manager may want to look.
    """

    __tablename__ = "burnout_signals"
    __table_args__ = (
        Index("ix_burnout_org_status", "organization_id", "status"),
        UniqueConstraint("organization_id", "employee_id", "period_start", name="uq_burnout_emp_period"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[str] = mapped_column(String(20), default="low")  # low | moderate | elevated | high
    signals_json: Mapped[Optional[str]] = mapped_column(Text)
    suggestions_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | acknowledged | resolved
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def signals(self) -> Optional[dict]:
        import json

        if not self.signals_json:
            return None
        try:
            return json.loads(self.signals_json)
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def suggestions(self) -> list[str]:
        import json

        if not self.suggestions_json:
            return []
        try:
            return json.loads(self.suggestions_json)
        except (json.JSONDecodeError, TypeError):
            return []


class DuplicateDetection(Base, TimestampMixin):
    """Duplicate work or knowledge detected across any entity kind."""

    __tablename__ = "duplicate_detections"
    __table_args__ = (
        Index("ix_duplicates_org_status", "organization_id", "status"),
        UniqueConstraint("kind", "entity_type_a", "entity_id_a", "entity_type_b", "entity_id_b", name="uq_duplicate_pair"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # project | task | document | meeting | policy | idea
    entity_type_a: Mapped[str] = mapped_column(String(32))
    entity_id_a: Mapped[str] = mapped_column(String(32))
    title_a: Mapped[Optional[str]] = mapped_column(String(300))
    entity_type_b: Mapped[str] = mapped_column(String(32))
    entity_id_b: Mapped[str] = mapped_column(String(32))
    title_b: Mapped[Optional[str]] = mapped_column(String(300))
    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | resolved | dismissed


class PatternDetection(Base, TimestampMixin):
    """Repeated organizational patterns turned into insights."""

    __tablename__ = "pattern_detections"
    __table_args__ = (
        Index("ix_patterns_org_type", "organization_id", "pattern_type"),
        UniqueConstraint("organization_id", "pattern_type", "key", name="uq_pattern_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pattern_type: Mapped[str] = mapped_column(String(60), nullable=False)  # repeated_delay | repeated_incident | approval_bottleneck | knowledge_gap | onboarding
    key: Mapped[str] = mapped_column(String(300), nullable=False)  # natural key for idempotent upsert
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | acknowledged | resolved
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LearningEvent(Base, TimestampMixin):
    """Lessons learned — the organization's growing memory of what works."""

    __tablename__ = "learning_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)  # project_completed | project_failed | lesson
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    lesson: Mapped[Optional[str]] = mapped_column(Text)
    entity_type: Mapped[Optional[str]] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    tags_json: Mapped[Optional[str]] = mapped_column(Text)

    @property
    def tags(self) -> list[str]:
        import json

        if not self.tags_json:
            return []
        try:
            return json.loads(self.tags_json)
        except (json.JSONDecodeError, TypeError):
            return []


class DailyBrief(Base, TimestampMixin):
    """Autonomous daily brief generated for executives and employees."""

    __tablename__ = "daily_briefs"
    __table_args__ = (
        Index("ix_briefs_org_recipient", "organization_id", "recipient_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    brief_type: Mapped[str] = mapped_column(String(30), nullable=False)  # executive | employee
    recipient_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sections_json: Mapped[Optional[str]] = mapped_column(Text)
    brief_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    @property
    def sections(self) -> list[dict]:
        import json

        if not self.sections_json:
            return []
        try:
            return json.loads(self.sections_json)
        except (json.JSONDecodeError, TypeError):
            return []


class RecommendationItem(Base, TimestampMixin):
    """Personalized recommendation feed items."""

    __tablename__ = "recommendation_items"
    __table_args__ = (
        Index("ix_rec_items_org_user", "organization_id", "recipient_id"),
        Index("ix_rec_items_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recipient_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)  # None = org-wide
    kind: Mapped[str] = mapped_column(String(60), nullable=False)  # expert | document | mentor | training | community | project | meeting | career | knowledge
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    entity_type: Mapped[Optional[str]] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reasons_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active | accepted | dismissed

    @property
    def reasons(self) -> list[str]:
        import json

        if not self.reasons_json:
            return []
        try:
            return json.loads(self.reasons_json)
        except (json.JSONDecodeError, TypeError):
            return []


class SearchMetric(Base, TimestampMixin):
    """Search behavior — queries, success, and the documents people click."""

    __tablename__ = "search_metrics"
    __table_args__ = (
        Index("ix_search_metrics_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    query: Mapped[str] = mapped_column(String(300), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    clicked_type: Mapped[Optional[str]] = mapped_column(String(32))
    clicked_id: Mapped[Optional[str]] = mapped_column(String(32))
    clicked_title: Mapped[Optional[str]] = mapped_column(String(300))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)


class SearchInsight(Base, TimestampMixin):
    """Aggregated search intelligence (failed searches, popular topics)."""

    __tablename__ = "search_insights"
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "key", name="uq_search_insight_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # failed_search | popular_query | popular_document | rising_topic
    key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)


class WorkflowInsight(Base, TimestampMixin):
    """Workflow intelligence: bottlenecks, duplicate work, automation chances."""

    __tablename__ = "workflow_insights"
    __table_args__ = (
        Index("ix_workflow_insights_org", "organization_id", "insight_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False)  # approval_bottleneck | slow_approval | automation | duplicate_work | manual_work
    entity_type: Mapped[Optional[str]] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info | warning | critical
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | acknowledged | resolved
    recommendation: Mapped[Optional[str]] = mapped_column(String(300))
