"""Organizational Forecasting (Phase 18.9) — growth, hiring, revenue and more.

The forecasting engine projects nine dimensions over a horizon (default 90
days) by extrapolating current twin aggregates with a simple compounding
trend. Every forecast carries a confidence score and evidence drivers.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow, ensure_aware
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.digital_twin import StrategicForecast

logger = logging.getLogger("vcos.digital_twin.forecast")

FORECAST_DIMENSIONS = [
    "growth",
    "hiring",
    "revenue",
    "knowledge",
    "learning",
    "projects",
    "community",
    "infrastructure",
    "capacity",
]


class ForecastingService:
    """Projects organizational dimensions into the future from the twin."""

    def _project(self, dimension: str, current: float, weekly_growth: float, horizon_days: int) -> tuple[list[dict], float, str]:
        series: list[dict] = []
        value = float(current)
        today = utcnow().date()
        weekly = weekly_growth / 7.0
        for day in range(0, horizon_days + 1, 7):
            series.append({"date": (today + timedelta(days=day)).isoformat(), "value": round(value, 2)})
            value *= 1 + weekly
        confidence = min(0.95, max(0.5, 0.85 - weekly_growth * 4))
        summary = f"{dimension.title()} projected from {current:,.0f} to {series[-1]['value']:,.0f} over {horizon_days} days."
        return series, confidence, summary

    async def generate(self, db: AsyncSession, organization_id: str, *, horizon_days: int = 90, commit: bool = False) -> list[dict[str, Any]]:
        twin = await digital_twin_service.get_twin(db, organization_id)
        if twin is None:
            payload = await digital_twin_service.build_twin(db, organization_id)
            counts = payload["entity_counts"]
        else:
            counts = json.loads(twin.entity_counts_json or "{}")

        employees = counts.get("active_employees", counts.get("employees", 0)) or 0
        projects = counts.get("projects", 0) or 0
        customers = counts.get("customers", 0) or 0
        knowledge = counts.get("knowledge_indexed", counts.get("documents", 0)) or 0
        enrollments = counts.get("course_enrollments", 0) or 0
        community = counts.get("community_posts", 0) or 0
        workflows = counts.get("workflow_executions", 0) or 0
        meetings = counts.get("meetings", 0) or 0
        open_tasks = counts.get("open_tasks", 0) or 0

        plans = [
            ("growth", employees * 1.0, 0.01),
            ("hiring", employees, 0.008),
            ("revenue", customers * 12000 if customers else 0, 0.015),
            ("knowledge", knowledge, 0.02),
            ("learning", enrollments, 0.02),
            ("projects", projects, 0.01),
            ("community", community, 0.015),
            ("infrastructure", workflows, 0.01),
            ("capacity", open_tasks, -0.005),
        ]

        rows = []
        for dimension, current, growth in plans:
            series, confidence, summary = self._project(dimension, current, growth, horizon_days)
            drivers = [
                {"metric": dimension, "value": current},
                {"note": "Extrapolated from digital twin entity counts"},
            ]
            row = StrategicForecast(
                organization_id=organization_id,
                dimension=dimension,
                horizon_days=horizon_days,
                series_json=json.dumps(series),
                summary=summary,
                confidence=confidence,
                drivers_json=json.dumps(drivers),
                generated_at=utcnow(),
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        created = [self.serialize(r) for r in rows]
        await publish_background_event(
            db,
            name="forecast.created",
            organization_id=organization_id,
            payload={"dimensions": [c["dimension"] for c in created], "horizon_days": horizon_days},
        )
        if commit:
            await db.commit()
        return created

    async def list(self, db: AsyncSession, organization_id: str, dimension: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        query = select(StrategicForecast).where(StrategicForecast.organization_id == organization_id)
        if dimension:
            query = query.where(StrategicForecast.dimension == dimension)
        query = query.order_by(StrategicForecast.generated_at.desc()).limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [self.serialize(r) for r in rows]

    def serialize(self, row: StrategicForecast) -> dict[str, Any]:
        series = []
        if row.series_json:
            try:
                series = json.loads(row.series_json)
            except (json.JSONDecodeError, TypeError):
                series = []
        drivers = []
        if row.drivers_json:
            try:
                drivers = json.loads(row.drivers_json)
            except (json.JSONDecodeError, TypeError):
                drivers = []
        def _trend() -> str:
            if len(series) < 2:
                return "flat"
            first = series[0].get("value", 0) or 0
            last = series[-1].get("value", 0) or 0
            delta = last - first
            if delta > first * 0.02:
                return "up"
            if delta < -first * 0.02:
                return "down"
            return "flat"

        return {
            "id": row.id,
            "dimension": row.dimension,
            "horizon_days": row.horizon_days,
            "series": series,
            "trend": _trend(),
            "summary": row.summary,
            "confidence": row.confidence,
            "drivers": drivers,
            "generated_at": ensure_aware(row.generated_at).isoformat() if row.generated_at else None,
        }


forecasting_service = ForecastingService()
