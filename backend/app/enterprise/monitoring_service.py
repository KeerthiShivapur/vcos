"""Monitoring service (Phase 15) — health, metrics and alerts.

Metrics are ingested as time series (system_metrics rows) by agents or the
API process; health derives a single posture (healthy|degraded|critical)
from recent samples and emits alerts when thresholds are crossed.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.enterprise import SystemMetric

ERROR_RATE_DEGRADED = 5.0
ERROR_RATE_CRITICAL = 20.0


class MonitoringService:
    async def record_metric(
        self,
        db: AsyncSession,
        *,
        organization_id: Optional[str],
        name: str,
        value: float,
        unit: Optional[str] = None,
        tags: Optional[dict[str, Any]] = None,
        actor_id: Optional[str] = None,
    ) -> SystemMetric:
        metric = SystemMetric(
            organization_id=organization_id,
            name=name,
            value=value,
            unit=unit,
            tags=tags or {},
            recorded_at=utcnow(),
        )
        db.add(metric)
        await db.flush()
        await publish_event(
            db,
            name="monitoring.metric.recorded",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"metric": name, "value": value, "unit": unit},
        )
        return metric

    async def recent(
        self,
        db: AsyncSession,
        *,
        organization_id: Optional[str],
        name: Optional[str] = None,
        limit: int = 100,
    ) -> list[SystemMetric]:
        query = select(SystemMetric)
        if organization_id is not None:
            query = query.where(SystemMetric.organization_id == organization_id)
        if name:
            query = query.where(SystemMetric.name == name)
        result = await db.execute(
            query.order_by(SystemMetric.recorded_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def _last_value(
        self, db: AsyncSession, organization_id: Optional[str], name: str
    ) -> Optional[float]:
        result = await db.execute(
            select(SystemMetric.value)
            .where(SystemMetric.organization_id == organization_id, SystemMetric.name == name)
            .order_by(SystemMetric.recorded_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def health(
        self, db: AsyncSession, *, organization_id: Optional[str]
    ) -> dict[str, Any]:
        error_rate = await self._last_value(db, organization_id, "http_error_rate") or 0.0
        latency = await self._last_value(db, organization_id, "latency_ms")
        uptime = await self._last_value(db, organization_id, "uptime_percent")
        status = "healthy"
        if error_rate >= ERROR_RATE_CRITICAL:
            status = "critical"
        elif error_rate >= ERROR_RATE_DEGRADED:
            status = "degraded"
        return {
            "status": status,
            "checks": {
                "http_error_rate": {"value": error_rate, "threshold": ERROR_RATE_DEGRADED},
                "latency_ms": {"value": latency},
                "uptime_percent": {"value": uptime},
            },
            "recorded_at": utcnow().isoformat(),
        }

    async def alerts(
        self, db: AsyncSession, *, organization_id: Optional[str]
    ) -> list[dict[str, Any]]:
        health = await self.health(db, organization_id=organization_id)
        alerts: list[dict[str, Any]] = []
        error_rate = health["checks"]["http_error_rate"]["value"]
        if error_rate >= ERROR_RATE_CRITICAL:
            alerts.append({"severity": "critical", "name": "http_error_rate",
                           "value": error_rate, "message": "Error rate is critical"})
        elif error_rate >= ERROR_RATE_DEGRADED:
            alerts.append({"severity": "warning", "name": "http_error_rate",
                           "value": error_rate, "message": "Error rate is elevated"})
        latency = health["checks"]["latency_ms"]["value"]
        if latency and latency > 2000:
            alerts.append({"severity": "warning", "name": "latency_ms",
                           "value": latency, "message": "Latency exceeds 2000ms"})
        return alerts

    async def prune(self, db: AsyncSession, *, organization_id: Optional[str] = None,
                    older_than_days: int = 30) -> int:
        """Delete metrics older than the retention window (worker hook)."""
        cutoff = utcnow()
        cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        cutoff = cutoff - timedelta(days=older_than_days)
        query = select(SystemMetric.id).where(SystemMetric.recorded_at < cutoff)
        if organization_id is not None:
            query = query.where(SystemMetric.organization_id == organization_id)
        ids = list((await db.execute(query)).scalars().all())
        for metric_id in ids:
            metric = await db.get(SystemMetric, metric_id)
            if metric:
                await db.delete(metric)
        return len(ids)


monitoring_service = MonitoringService()
