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

from app.models.base import Base, TimestampMixin, gen_uuid, utcnow


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Slice 4D.4 — universal organizational pattern intelligence --------------

# Pattern lifecycle (canonical ``PatternDetection.status`` values).
PATTERN_LIFECYCLE = ("candidate", "emerging", "confirmed", "persistent", "fading", "resolved")
# Lifecycle values that still represent an active, observable pattern.
ACTIVE_PATTERN_STATUSES = ("candidate", "emerging", "confirmed", "persistent", "fading")
# Legacy Phase 9 statuses still accepted for read/write compatibility.
LEGACY_PATTERN_STATUSES = ("open", "acknowledged", "dismissed")

# Pattern families (from the 4D.4 registry).
PATTERN_FAMILIES = (
    "execution",
    "decision",
    "governance",
    "communication",
    "knowledge",
    "organization",
)


class BackgroundJob(Base, TimestampMixin):
    """A background job with retry + idempotency bookkeeping.

    status: queued | running | done | failed | retry
    """

    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_bg_jobs_org_status", "organization_id", "status"),
        Index("ix_bg_jobs_org_created", "organization_id", "created_at"),
        UniqueConstraint("name", "event_id", name="uq_background_jobs_name_event"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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


class CompanyInsight(Base, TimestampMixin):
    """Per-entity company intelligence freshness (Slice 4D.1).

    One row per (organization, entity_type, entity_id): a bounded summary kept
    fresh by change-driven consumers. The brain reads live evidence from the
    underlying tables; this table only marks what changed, why, and when, so
    consumers can show a knowledge-staleness signal without a full rescan.
    """

    __tablename__ = "company_insights"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id",
            name="uq_company_insight_entity",
        ),
        Index("ix_company_insight_refresh", "organization_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="context", nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(300))
    status: Mapped[Optional[str]] = mapped_column(String(40))
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200))
    detail: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    touched_by: Mapped[Optional[str]] = mapped_column(String(32))


class GraphUpdate(Base, TimestampMixin):
    """Audit trail of graph mutations made by the graph worker."""

    __tablename__ = "graph_updates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
    """Repeated organizational patterns turned into insights.

    Slice 4D.4 — universal organizational pattern intelligence. Patterns are
    change-driven (one ``pattern.evaluate`` job per significant event), carry
    first-class evidence lineage (``evidence_json`` / ``supporting_event_ids``),
    a configurable lifecycle (``status``: candidate -> emerging -> confirmed ->
    persistent -> fading -> resolved), bounded confidence in [0, 1], governance
    scope inheritance (``scope_id`` / ``scope_type`` / ``auth_project_id``) and
    a natural key (``organization_id``, ``pattern_type``, ``key``) for
    idempotent upsert.
    """

    __tablename__ = "pattern_detections"
    __table_args__ = (
        Index("ix_patterns_org_type", "organization_id", "pattern_type"),
        Index("ix_patterns_org_lifecycle", "organization_id", "status"),
        Index("ix_patterns_org_last_seen", "organization_id", "last_seen"),
        Index("ix_patterns_org_updated", "organization_id", "updated_at"),
        UniqueConstraint("organization_id", "pattern_type", "key", name="uq_pattern_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    pattern_type: Mapped[str] = mapped_column(String(60), nullable=False)  # repeated_delay | decision_reversal | approval_bottleneck | knowledge_gap | ...
    key: Mapped[str] = mapped_column(String(300), nullable=False)  # natural key for idempotent upsert
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    # --- Slice 4D.4 canonical fields ----------------------------------------
    # Pattern family: execution | decision | governance | communication |
    # knowledge | organization
    family: Mapped[str] = mapped_column(String(20), default="execution", nullable=False)
    # Human explanation of why VCOS believes this is a pattern.
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Lifecycle: candidate | emerging | confirmed | persistent | fading | resolved
    # (legacy Phase 9 values open | acknowledged | resolved are still readable)
    status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False)
    # Observed occurrences of the pattern (the pattern's repetition count).
    count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.3)
    evidence: Mapped[Optional[str]] = mapped_column(Text)  # legacy flat evidence string
    # Evidence lineage: [{"type": "event", "id": ..., "relationship": "occurrence"}, ...]
    # Real VCOS objects only (task/project/decision/message/memory/event) — a
    # pattern can always answer "why does VCOS believe this?".
    evidence_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # Affected entities: [{"type": "project", "id": ..., "title": ...}, ...]
    entities_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # Supporting organizational memory ids (Slice 4D.3 CompanyMemory).
    supporting_memory_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # Origin events that produced the occurrences (deduplicated).
    supporting_event_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # Organization graph edges that corroborate the pattern.
    supporting_relationships: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # Confidence component breakdown (evidence quality, temporal, support...).
    detail_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # Governance scope inherited from the pattern's evidence (project-anchored).
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(16), default="org", nullable=False)  # org | project
    auth_project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    # Temporal: observation window and recurrence behaviour.
    time_window_days: Mapped[int] = mapped_column(Integer, default=30)
    trend: Mapped[str] = mapped_column(String(20), default="stable")  # rising | stable | fading
    avg_interval_days: Mapped[Optional[float]] = mapped_column(Float)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def pattern_key(self) -> str:
        return self.key

    @property
    def occurrence_count(self) -> int:
        return self.count


class PatternEvent(Base, TimestampMixin):
    """Lineage link between a pattern and the events that fed it (Slice 4D.4).

    An event may feed multiple patterns (e.g. ``task.blocked`` contributes to
    the project's repeated-delay pattern and the task's dependency-failure
    pattern), so the uniqueness is per ``(pattern_id, event_id)``. The pipeline
    checks these links before counting an occurrence, making evaluation
    idempotent and replay-safe under the durable ``(name, event_id)`` job
    constraint.
    """

    __tablename__ = "pattern_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "pattern_id", "event_id", name="uq_pattern_events_link"
        ),
        Index("ix_pattern_events_org", "organization_id"),
        Index("ix_pattern_events_pattern", "pattern_id"),
        Index("ix_pattern_events_event", "event_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    pattern_id: Mapped[str] = mapped_column(
        ForeignKey("pattern_detections.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # how the event relates to the pattern, e.g. "occurrence" | "context"
    relationship: Mapped[str] = mapped_column(String(20), default="occurrence")


# --- Slice 4D.5 — universal company insight intelligence ---------------------

# Insight severity (deterministic, derived from confidence + impact).
INSIGHT_SEVERITIES = ("info", "warning", "critical")
# Insight lifecycle (auto-managed by the insight worker, observational only).
INSIGHT_STATUSES = ("active", "faded", "resolved")
# Domains the insight registry can compose across.
INSIGHT_DOMAINS = (
    "execution",
    "decision",
    "governance",
    "communication",
    "knowledge",
    "organization",
    "people",
    "cross_domain",
)


class UniversalInsight(Base, TimestampMixin):
    """Canonical company-level insight (Slice 4D.5).

    The composition layer above the 4D.1-4D.4 primitives: one canonical insight
    representation that connects patterns, memories, graph relationships,
    decisions, approvals, dependencies, tasks and projects into a single
    evidence-backed, governance-scoped statement about the company.

    ``claim`` + ``evidence`` + ``confidence`` + ``scope`` + affected entities
    + timestamps. No unsupported AI statements: every field is derived from
    real rows by deterministic registry rules; ``confidence_components``
    explains exactly why the bounded score is what it is.

    Observational-only: written by the insight pipeline / worker, never by
    API request handlers, and no operating table is ever mutated.
    """

    __tablename__ = "universal_insights"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "insight_type", "key", name="uq_universal_insight_key"
        ),
        Index("ix_universal_insights_org_status", "organization_id", "status"),
        Index("ix_universal_insights_org_type", "organization_id", "insight_type"),
        Index("ix_universal_insights_scope", "scope_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # registry key, e.g. "execution_bottleneck"
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False)
    # natural deduplication key within (organization_id, insight_type),
    # e.g. "project:8793b1..." — the same underlying situation always maps to
    # the same insight row (deduplication, replay-safe).
    key: Mapped[str] = mapped_column(String(240), nullable=False)
    domain: Mapped[str] = mapped_column(String(30), default="cross_domain", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # the core, defensible statement
    claim: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # compositional confidence explanation: component -> value
    confidence_components: Mapped[Optional[dict]] = mapped_column(JSON)
    # resolved evidence refs: [{type, id, title, relationship, occurred_at}]
    evidence_json: Mapped[Optional[list]] = mapped_column(JSON)
    # graph relationships consumed: [{source_type, source_id, relation, target_type, target_id}]
    relationships_json: Mapped[Optional[list]] = mapped_column(JSON)
    supporting_pattern_ids: Mapped[Optional[list]] = mapped_column(JSON)
    supporting_memory_ids: Mapped[Optional[list]] = mapped_column(JSON)
    # entities this insight is about: [{type, id, title}]
    affected_entities: Mapped[Optional[list]] = mapped_column(JSON)
    # governance inheritance (mirrors patterns / memories)
    scope_type: Mapped[str] = mapped_column(String(16), default="org")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    auth_project_id: Mapped[Optional[str]] = mapped_column(String(32))
    # active | faded | resolved (auto lifecycle)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    first_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # human lifecycle notes are NOT part of 4D.5 (observation only)


class InsightEvent(Base, TimestampMixin):
    """Lineage link between an insight and the events that fed it (Slice 4D.5).

    Exactly-once: an event may feed multiple insights, so uniqueness is per
    ``(insight_id, event_id)``; the pipeline checks these links before
    refreshing an insight, making evaluation idempotent and replay-safe.
    """

    __tablename__ = "insight_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "insight_id", "event_id", name="uq_insight_events_link"
        ),
        Index("ix_insight_events_org", "organization_id"),
        Index("ix_insight_events_insight", "insight_id"),
        Index("ix_insight_events_event", "event_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    insight_id: Mapped[str] = mapped_column(
        ForeignKey("universal_insights.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # how the event relates to the insight, e.g. "pattern.updated" | "seed"
    relationship: Mapped[str] = mapped_column(String(40), default="seed")


class LearningEvent(Base, TimestampMixin):
    """Lessons learned — the organization's growing memory of what works."""

    __tablename__ = "learning_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
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
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False)  # approval_bottleneck | slow_approval | automation | duplicate_work | manual_work
    entity_type: Mapped[Optional[str]] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info | warning | critical
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open | acknowledged | resolved
    recommendation: Mapped[Optional[str]] = mapped_column(String(300))


# --- Slice 4E.3+ --- ML Models for Forecasting & Anomaly Detection ---


class MLModel(Base, TimestampMixin):
    """Stored ML model metadata."""

    __tablename__ = "ml_models"
    __table_args__ = (
        Index("ix_ml_models_org_type", "organization_id", "model_type"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecasting, anomaly
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False)  # prophet, isolation_forest, etc.
    version: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[Optional[str]] = mapped_column(Text)  # JSON config
    metrics: Mapped[Optional[str]] = mapped_column(Text)  # JSON metrics
    model_data: Mapped[Optional[str]] = mapped_column(Text)  # Pickled model (base64)
    status: Mapped[str] = mapped_column(String(24), default="training")  # training, ready, failed
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MLPrediction(Base, TimestampMixin):
    """Stored predictions for audit/history."""

    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_ml_predictions_org_model", "organization_id", "model_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prediction_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecast, anomaly
    input_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON input
    output_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON output


# --- Knowledge Vector/Search Models ---


class KnowledgeVector(Base, TimestampMixin):
    """Slice 4D.2 - persisted semantic vector per deterministic chunk.

    One row per (tenant, source, chunk) holding the embedding produced by the
    configured embedding provider. The row is the evidence lineage for
    semantic retrieval: every chunk knows its canonical source row
    (source_type + source_id), when that source last changed
    (source_updated_at) and when the vector was (re)indexed
    (indexed_at). Deletes remove the rows, so removed content can never
    resurface through search.
    """

    __tablename__ = "knowledge_vectors"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text)  # JSON float list
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id", "chunk_index",
            name="uq_knowledge_vector_chunk",
        ),
    )


class KnowledgeSource(Base, TimestampMixin):
    """4E.1 - the universal ingestion contract: one canonical registry row per
    (tenant, source object).

    Every knowledge object - internal (document, wiki, policy, sop, template,
    decision) or future external (4N adapters: Drive, Slack, Jira, ...) - is
    ingested through this single contract and then consumed identically by
    claims, topics, authority and freshness. Lifecycle follows the knowledge
    model: discovered - extracted - validated - active - updated - superseded
    - archived. Temporal truth: rows are never deleted; archival and
    supersession keep history and provenance.
    """

    __tablename__ = "knowledge_sources"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="internal", nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), default="discovered", nullable=False, index=True)
    source_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    freshness_label: Mapped[str] = mapped_column(String(16), default="stale", nullable=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    provenance_json: Mapped[Optional[str]] = mapped_column(Text)
    external_ref: Mapped[Optional[str]] = mapped_column(String(240))
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source_type", "source_id",
            name="uq_knowledge_sources_entity",
        ),
    )


class KnowledgeClaim(Base, TimestampMixin):
    """4E.1 - a canonical claim about an organizational knowledge object.

    Claims carry the authority of their source and follow their own lifecycle:
    candidate - supported - authoritative - contested - superseded. Superseded
    claims are never deleted: valid_to + superseded_by keep the
    temporal truth ("what was true, what is true now").
    """

    __tablename__ = "knowledge_claims"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    predicate: Mapped[str] = mapped_column(String(80), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), default="fact", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="supported", nullable=False)
    authority_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    context_type: Mapped[Optional[str]] = mapped_column(String(32))
    context_id: Mapped[Optional[str]] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL")
    )
    supporting_claim_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    contradicting_claim_ids_json: Mapped[Optional[str]] = mapped_column(Text)
    related_entities_json: Mapped[Optional[str]] = mapped_column(Text)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "subject_type", "subject_id", "predicate",
            name="uq_knowledge_claims_unique",
        ),
    )


class KnowledgeTopic(Base, TimestampMixin):
    """4E.3 - a canonical topic that groups related claims and entities."""

    __tablename__ = "knowledge_topics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("knowledge_topics.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name",
            name="uq_knowledge_topics_org_name",
        ),
        {"extend_existing": True},
    )