"""Observability service (Phase 15) — structured logs and traces.

A lightweight structured-log store with trace correlation. Log lines are
ingested by the API process or agents and queried from the observability
console; a trace_id groups spans of a single request/flow.
"""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.enterprise import ObservabilityLog

VALID_LEVELS = ("debug", "info", "warn", "error", "critical")


class ObservabilityService:
    async def ingest(
        self,
        db: AsyncSession,
        *,
        organization_id: Optional[str],
        message: str,
        level: str = "info",
        source: str = "app",
        details: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> ObservabilityLog:
        if level not in VALID_LEVELS:
            level = "info"
        log = ObservabilityLog(
            organization_id=organization_id,
            level=level,
            source=source,
            message=message,
            details=details or {},
            trace_id=trace_id,
            span_id=span_id,
            recorded_at=utcnow(),
        )
        db.add(log)
        await db.flush()
        return log

    async def query(
        self,
        db: AsyncSession,
        *,
        organization_id: Optional[str],
        level: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> list[ObservabilityLog]:
        query = select(ObservabilityLog)
        if organization_id is not None:
            query = query.where(ObservabilityLog.organization_id == organization_id)
        if level:
            query = query.where(ObservabilityLog.level == level)
        if source:
            query = query.where(ObservabilityLog.source == source)
        if search:
            pattern = f"%{search.lower()}%"
            from sqlalchemy import func

            query = query.where(func.lower(ObservabilityLog.message).like(pattern))
        result = await db.execute(
            query.order_by(ObservabilityLog.recorded_at.desc()).limit(min(limit, 200))
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, log_id: str) -> Optional[ObservabilityLog]:
        return await db.get(ObservabilityLog, log_id)

    async def trace(self, db: AsyncSession, trace_id: str) -> list[ObservabilityLog]:
        result = await db.execute(
            select(ObservabilityLog)
            .where(ObservabilityLog.trace_id == trace_id)
            .order_by(ObservabilityLog.recorded_at)
        )
        return list(result.scalars().all())

    async def prune(self, db: AsyncSession, *, older_than_days: int = 30) -> int:
        cutoff = utcnow() - timedelta(days=older_than_days)
        ids = list(
            (await db.execute(
                select(ObservabilityLog.id).where(ObservabilityLog.recorded_at < cutoff)
            )).scalars().all()
        )
        for log_id in ids:
            log = await db.get(ObservabilityLog, log_id)
            if log:
                await db.delete(log)
        return len(ids)


observability_service = ObservabilityService()
