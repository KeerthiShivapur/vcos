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
