from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

metadata = MetaData()

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata

    def dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


def _make_engine(database_url: str | None = None):
    settings = get_settings()
    url = database_url or settings.DATABASE_URL
    kwargs: dict[str, Any] = {"echo": settings.DB_ECHO, "pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
        )
    return create_async_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def init_db() -> None:
    """Create tables if they do not exist (dev bootstrap; production uses Alembic)."""
    from app import models  # noqa: F401  (register all models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _run_postgres_alter_migrations()


_POSTGRES_ALTERS: list[str] = [
    # Phase 6: collaboration columns on the existing Phase 3 `meetings` table.
    # `ADD COLUMN IF NOT EXISTS` makes each statement idempotent.
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS department_id VARCHAR(32) REFERENCES departments(id) ON DELETE SET NULL",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS team_id VARCHAR(32) REFERENCES teams(id) ON DELETE SET NULL",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS calendar_event_id VARCHAR(32) REFERENCES calendar_events(id) ON DELETE SET NULL",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS room_id VARCHAR(32) REFERENCES meeting_rooms(id) ON DELETE SET NULL",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS meeting_code VARCHAR(16)",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)",
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS duration_minutes INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_meetings_meeting_code ON meetings (meeting_code)",
    # Slice 3: event bus hardening — dispatch claim columns on background_jobs.
    "ALTER TABLE background_jobs ADD COLUMN IF NOT EXISTS event_id VARCHAR(32)",
    "ALTER TABLE background_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_name_event ON background_jobs (name, event_id)",
    # Slice 3 Step 6: task collaboration — tags column on the existing tasks table.
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS tags JSON",
    # Slice 3 Step 8: project & roadmap management — progress on roadmaps.
    "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0",
    # Slice 3 Step 10: project/sprint execution — progress on sprints.
    "ALTER TABLE sprints ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0",
    "ALTER TABLE sprints ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
    # Slice 4A: decision → execution lineage — tasks trace back to the
    # originating decision and the goal they support.
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS decision_id VARCHAR(32) REFERENCES decisions(id) ON DELETE SET NULL",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS goal_id VARCHAR(32) REFERENCES goals(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_tasks_decision_id ON tasks (decision_id)",
    "CREATE INDEX IF NOT EXISTS ix_tasks_goal_id ON tasks (goal_id)",
    "ALTER TABLE decisions ADD COLUMN IF NOT EXISTS goal_id VARCHAR(32)",
    "CREATE INDEX IF NOT EXISTS ix_decisions_goal_id ON decisions (goal_id)",
    # Slice 4B: messaging loop — edited timestamp on messages.
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ",
    # Slice 4C: governance kernel — scoped role assignments + approval policies.
    "ALTER TABLE user_roles ADD COLUMN IF NOT EXISTS scope_id VARCHAR(32)",
    "CREATE INDEX IF NOT EXISTS ix_user_roles_scope_id ON user_roles (scope_id)",
    "ALTER TABLE approvals ADD COLUMN IF NOT EXISTS policy_id VARCHAR(32)",
    "CREATE INDEX IF NOT EXISTS ix_approvals_policy_id ON approvals (policy_id)",
    # Slice 4D.1: change-driven company intelligence — recency index on the
    # graph edges so the bounded sweep is proportional to recent change volume.
    "CREATE INDEX IF NOT EXISTS ix_org_graph_edge_updated ON org_graph_edges (updated_at)",
    # Slice 4D.3: organizational memory automation — evidence-backed memory
    # semantics on the existing Phase 19 company_memory table (new tables
    # memory_events / memory_outcomes are created by create_all at bootstrap).
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS memory_category VARCHAR(16) DEFAULT 'event'",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS domain VARCHAR(30) DEFAULT 'event'",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS summary TEXT",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS context_json JSON",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS evidence_json JSON",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS lesson TEXT",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS outcome TEXT",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS outcome_type VARCHAR(16)",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 0.3",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS fact_kind VARCHAR(16) DEFAULT 'fact'",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS source_event_ids JSON",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(255)",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS auth_scope VARCHAR(16) DEFAULT 'org'",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS auth_project_id VARCHAR(32)",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS auth_scope_id VARCHAR(32)",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'active'",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS supersedes_id VARCHAR(32)",
    "ALTER TABLE company_memory ADD COLUMN IF NOT EXISTS related_memory_ids JSON",
    "CREATE INDEX IF NOT EXISTS ix_company_memory_org_category ON company_memory (organization_id, memory_category)",
    "CREATE INDEX IF NOT EXISTS ix_company_memory_org_dedupe ON company_memory (organization_id, dedupe_key)",
    "CREATE INDEX IF NOT EXISTS ix_company_memory_org_auth ON company_memory (organization_id, auth_scope, auth_project_id)",
    # Slice 4D.4: universal organizational pattern intelligence — canonical
    # evidence-backed fields on the existing Phase 9 pattern_detections table.
    # (pattern_events is a new table and is created by create_all at bootstrap.)
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS family VARCHAR(20) DEFAULT 'execution'",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS description TEXT",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS evidence_json JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS entities_json JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS supporting_memory_ids JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS supporting_event_ids JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS supporting_relationships JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS detail_json JSON",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS scope_id VARCHAR(32)",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS scope_type VARCHAR(16) DEFAULT 'org'",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS auth_project_id VARCHAR(32)",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS time_window_days INTEGER DEFAULT 30",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS trend VARCHAR(20) DEFAULT 'stable'",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS avg_interval_days FLOAT",
    "ALTER TABLE pattern_detections ADD COLUMN IF NOT EXISTS last_evaluated_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_patterns_org_lifecycle ON pattern_detections (organization_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_patterns_org_last_seen ON pattern_detections (organization_id, last_seen)",
    "CREATE INDEX IF NOT EXISTS ix_patterns_org_updated ON pattern_detections (organization_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_pattern_detections_scope_id ON pattern_detections (scope_id)",
    "CREATE INDEX IF NOT EXISTS ix_pattern_detections_auth_project_id ON pattern_detections (auth_project_id)",
    # Slice 4E.3: universal knowledge understanding — cross-source relationship
    # columns on the existing 4E.1 knowledge_claims table (synthesis claims are
    # topic-anchored claims with supporting/contradicting claim links).
    "ALTER TABLE knowledge_claims ADD COLUMN IF NOT EXISTS topic_id VARCHAR(32)",
    "ALTER TABLE knowledge_claims ADD COLUMN IF NOT EXISTS supporting_claim_ids_json TEXT",
    "ALTER TABLE knowledge_claims ADD COLUMN IF NOT EXISTS contradicting_claim_ids_json TEXT",
    "ALTER TABLE knowledge_claims ADD COLUMN IF NOT EXISTS related_entities_json TEXT",
    "ALTER TABLE knowledge_claims ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_claims_topic ON knowledge_claims (organization_id, topic_id)",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_claims_last_seen ON knowledge_claims (organization_id, last_seen)",
    # Slice 4E.5: knowledge-to-action — recommendation lifecycle columns on
    # the existing 4E.4 knowledge_recommendations table (new tables
    # knowledge_intel_insights / knowledge_intel_insight_events are created by create_all).
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS lifecycle VARCHAR(20) DEFAULT 'detected'",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS lifecycle_audit_json TEXT",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS review_note TEXT",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS decided_by VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS decision_note TEXT",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS decision_id VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS task_id VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS converted_at TIMESTAMPTZ",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS executed_by VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS verified_by VARCHAR(32)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS verification_outcome VARCHAR(24)",
    "ALTER TABLE knowledge_recommendations ADD COLUMN IF NOT EXISTS verification_note TEXT",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_recommendations_lifecycle ON knowledge_recommendations (lifecycle)",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_recommendations_task_id ON knowledge_recommendations (task_id)",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_recommendations_decision_id ON knowledge_recommendations (decision_id)",
    # Slice 4E.6: universal company actions — bounded replay-safe dispatch.
    # Every worker pass reaps stale 'running' jobs, re-picks queued dispatch
    # jobs, and re-adopts orphan events.  At scale those scans walked the whole
    # background_jobs / events history on every pass; the composite indexes
    # keep each pass bounded by the *active* queue instead of the full log.
    "CREATE INDEX IF NOT EXISTS ix_bg_jobs_dispatch_reap ON background_jobs (name, status, started_at)",
    "CREATE INDEX IF NOT EXISTS ix_bg_jobs_dispatch_pick ON background_jobs (name, status, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_events_processed_occurred ON events (processed_at, occurred_at)",
    # Slice 4F.3: expertise evidence & trust — provenance/outcome/lineage on
    # the canonical evidence, trust facets + freshness on the expertise state.
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS evidence_kind VARCHAR(20) DEFAULT 'work'",
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS outcome VARCHAR(12) DEFAULT 'neutral'",
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ",
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ",
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS lineage_key VARCHAR(64)",
    "ALTER TABLE expertise_evidence ADD COLUMN IF NOT EXISTS origin_event_id VARCHAR(32)",
    "CREATE INDEX IF NOT EXISTS ix_expertise_evidence_lineage ON expertise_evidence (organization_id, lineage_key)",
    "CREATE INDEX IF NOT EXISTS ix_expertise_evidence_origin ON expertise_evidence (origin_event_id)",
    # 4F.3 outcome history: one action's success/failure/rollback must all
    # remain visible; the old source-unique constraint (one row per source)
    # collapsed that history, so it is dropped in favour of the event key.
    "ALTER TABLE expertise_evidence DROP CONSTRAINT IF EXISTS uq_expertise_evidence_source",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS successful_count INTEGER DEFAULT 0",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS failed_count INTEGER DEFAULT 0",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS outcome_ratio FLOAT",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS distinct_lineages INTEGER DEFAULT 0",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS corroborated_kinds INTEGER DEFAULT 0",
    "ALTER TABLE expertise ADD COLUMN IF NOT EXISTS freshness VARCHAR(12) DEFAULT 'historical'",
]


async def _run_postgres_alter_migrations() -> None:
    """Idempotent column additions for databases created before Phase 6."""
    try:
        async with engine.connect() as conn:
            if conn.dialect.name != "postgresql":
                return
            for statement in _POSTGRES_ALTERS:
                await conn.execute(text(statement))
            await conn.commit()
    except Exception:  # pragma: no cover - dev bootstrap robustness
        import logging

        logging.getLogger("vcos.db").warning(
            "Postgres ALTER migrations skipped (tables may be mid-bootstrap)", exc_info=True
        )


async def dispose_engine() -> None:
    await engine.dispose()
