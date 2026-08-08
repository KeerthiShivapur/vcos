"""Infrastructure observability: health & service metrics, dashboards (Phase 16.23)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.infrastructure import HealthMetric, ServiceMetric
from app.models.organization import gen_uuid

HEALTH_STATUSES = ("ok", "warn", "critical")


class ObservabilityService:
    """Collect and query health and service metrics at platform scale."""

    async def record_health(
        self,
        db: AsyncSession,
        *,
        region: Optional[str],
        service: str,
        status: str,
        metric_name: str = "availability",
        value: float = 100.0,
        unit: str = "percent",
        actor_id: Optional[str] = None,
    ) -> HealthMetric:
        if status not in HEALTH_STATUSES:
            raise ValueError(f"status must be one of {', '.join(HEALTH_STATUSES)}")
        metric = HealthMetric(
            id=gen_uuid(),
            region=region,
            service=service,
            status=status,
            metric_name=metric_name,
            value=value,
            unit=unit,
            recorded_at=utcnow(),
        )
        db.add(metric)
        await db.flush()
        return metric

    async def record_service_metric(
        self,
        db: AsyncSession,
        *,
        service: str,
        metric_name: str,
        value: float,
        unit: str = "count",
        region: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> ServiceMetric:
        metric = ServiceMetric(
            id=gen_uuid(),
            service=service,
            region=region,
            metric_name=metric_name,
            value=value,
            unit=unit,
            recorded_at=utcnow(),
            details=details or {},
        )
        db.add(metric)
        await db.flush()
        return metric

    async def record_metric(
        self,
        db: AsyncSession,
        *,
        service: str,
        metric_name: str,
        value: float,
        unit: str = "count",
        region: Optional[str] = None,
        status: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> ServiceMetric:
        """Unified ingestion used by probes (health checks, schedulers)."""
        return await self.record_service_metric(
            db, service=service, metric_name=metric_name, value=value, unit=unit, region=region, details=details
        )

    async def query_service_metric(
        self,
        db: AsyncSession,
        *,
        service: Optional[str] = None,
        metric_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[ServiceMetric]:
        query = select(ServiceMetric)
        if service:
            query = query.where(ServiceMetric.service == service)
        if metric_name:
            query = query.where(ServiceMetric.metric_name == metric_name)
        result = await db.execute(query.order_by(ServiceMetric.recorded_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def query_health(
        self, db: AsyncSession, *, service: Optional[str] = None, region: Optional[str] = None, limit: int = 100
    ) -> list[HealthMetric]:
        query = select(HealthMetric)
        if service:
            query = query.where(HealthMetric.service == service)
        if region:
            query = query.where(HealthMetric.region == region)
        result = await db.execute(query.order_by(HealthMetric.recorded_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def dashboard(self, db: AsyncSession) -> dict[str, Any]:
        health = await self.query_health(db, limit=1000)
        by_status: dict[str, int] = {"ok": 0, "warn": 0, "critical": 0}
        for row in health:
            by_status[row.status] = by_status.get(row.status, 0) + 1
        metrics = await self.query_service_metric(db, limit=1000)
        by_service: dict[str, dict[str, Any]] = {}
        for row in metrics:
            entry = by_service.setdefault(row.service, {"samples": 0, "last": None})
            entry["samples"] += 1
            entry["last"] = {"metric": row.metric_name, "value": row.value, "unit": row.unit, "at": row.recorded_at.isoformat()}
        warn_services = sorted({row.service for row in health if row.status == "warn"})
        critical_services = sorted({row.service for row in health if row.status == "critical"})
        return {
            "health": {
                "total": len(health),
                **by_status,
                "healthy_percent": round(100 * by_status["ok"] / max(1, len(health)), 2),
            },
            "metrics_total": len(metrics),
            "services": by_service,
            "warn_services": warn_services,
            "critical_services": critical_services,
        }


observability_service = ObservabilityService()
