"""Industry analytics engine (Phase 17.14).

Each pack ships KPIs (healthcare bed occupancy, manufacturing OEE, retail
sell-through, education graduation rate...). The analytics engine records KPI
values into IndustryMetric, compares them against pack benchmarks and returns
dashboard-ready summaries with trend and benchmark context — no per-industry
code in the core.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.industry.framework.registry import pack_kpis
from app.models.industry import IndustryMetric
from app.models.organization import gen_uuid

logger = logging.getLogger("vcos.industry.analytics")


class IndustryAnalyticsEngine:
    async def kpis(self, industry_key: str) -> list[dict[str, Any]]:
        return pack_kpis(industry_key)

    async def record(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        metric_key: str,
        value: float,
        period: str = "daily",
        tags: Optional[dict[str, Any]] = None,
        actor_id: Optional[str] = None,
    ) -> IndustryMetric:
        definition = next(
            (k for k in pack_kpis(industry_key) if k["key"] == metric_key), None
        )
        metric = IndustryMetric(
            id=gen_uuid(),
            organization_id=organization_id,
            industry_key=industry_key,
            metric_key=metric_key,
            name=(definition or {}).get("name"),
            value=value,
            unit=(definition or {}).get("unit"),
            period=period,
            tags=tags or {},
            recorded_at=utcnow(),
        )
        db.add(metric)
        await db.flush()
        await publish_event(
            db,
            name="industry.analytics.generated",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "industry_key": industry_key,
                "metric_key": metric_key,
                "value": value,
                "period": period,
            },
        )
        return metric

    async def record_many(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        values: list[dict[str, Any]],
        period: str = "daily",
        actor_id: Optional[str] = None,
    ) -> list[IndustryMetric]:
        recorded: list[IndustryMetric] = []
        for entry in values:
            metric = await self.record(
                db,
                organization_id=organization_id,
                industry_key=industry_key,
                metric_key=entry["metric_key"],
                value=float(entry["value"]),
                period=entry.get("period", period),
                tags=entry.get("tags"),
                actor_id=actor_id,
            )
            recorded.append(metric)
        return recorded

    async def timeseries(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        metric_key: Optional[str] = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        cutoff = utcnow() - timedelta(days=days)
        query = select(IndustryMetric).where(
            IndustryMetric.organization_id == organization_id,
            IndustryMetric.industry_key == industry_key,
            IndustryMetric.recorded_at >= cutoff,
        )
        if metric_key:
            query = query.where(IndustryMetric.metric_key == metric_key)
        query = query.order_by(IndustryMetric.recorded_at.asc())
        result = await db.execute(query)
        return [
            {
                "id": m.id,
                "metric_key": m.metric_key,
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "period": m.period,
                "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
            }
            for m in result.scalars().all()
        ]

    async def dashboard(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Benchmark comparison + latest values for every pack KPI."""
        definitions = pack_kpis(industry_key)
        series = await self.timeseries(
            db, organization_id=organization_id, industry_key=industry_key, days=days
        )
        latest_by_key: dict[str, dict[str, Any]] = {}
        for point in series:
            latest_by_key[point["metric_key"]] = point
        cards: list[dict[str, Any]] = []
        for kpi in definitions:
            latest = latest_by_key.get(kpi["key"])
            benchmark = kpi.get("benchmark")
            value = latest["value"] if latest else None
            cards.append(
                {
                    "metric_key": kpi["key"],
                    "name": latest.get("name") if latest else kpi["name"],
                    "unit": kpi.get("unit"),
                    "value": value,
                    "benchmark": benchmark,
                    "status": self._status(kpi, value),
                    "delta_pct": (
                        round(100 * (value - benchmark) / benchmark, 1)
                        if value is not None and benchmark
                        else None
                    ),
                    "points": sum(1 for p in series if p["metric_key"] == kpi["key"]),
                }
            )
        return {
            "industry_key": industry_key,
            "period_days": days,
            "metrics": cards,
            "tracked": len(series),
        }

    @staticmethod
    def _status(kpi: dict[str, Any], value: Optional[float]) -> str:
        if value is None:
            return "untracked"
        benchmark = kpi.get("benchmark")
        if benchmark is None:
            return "tracked"
        higher_is_better = bool(kpi.get("higher_is_better", True))
        if higher_is_better:
            return "above_benchmark" if value >= benchmark else "below_benchmark"
        return "above_benchmark" if value <= benchmark else "below_benchmark"

    async def best(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        metric_key: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = (
            select(IndustryMetric)
            .where(
                IndustryMetric.organization_id == organization_id,
                IndustryMetric.industry_key == industry_key,
                IndustryMetric.metric_key == metric_key,
            )
            .order_by(IndustryMetric.value.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        return [
            {
                "id": m.id,
                "value": m.value,
                "period": m.period,
                "tags": m.tags or {},
                "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
            }
            for m in result.scalars().all()
        ]


industry_analytics_engine = IndustryAnalyticsEngine()
