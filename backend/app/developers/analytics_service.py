from __future__ import annotations

"""Developer usage analytics service (Phase 18.14) â€” usage records & summaries.

Usage is recorded per application/day/unit (requests | errors | latency_ms |
installs). Summaries roll up over a lookback window for developer dashboards
and the analytics.generated event feeds.
"""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import DeveloperUsage

UNITS = ("requests", "errors", "latency_ms", "installs")


class DeveloperAnalyticsService:
    async def record(
        self,
        db: AsyncSession,
        *,
        developer_id: str,
        application_id: str,
        usage_date: str,
        unit: str,
        value: float,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if unit not in UNITS:
            raise ValueError(f"unit must be one of {UNITS}")
        existing = (
            await db.execute(
                select(DeveloperUsage).where(
                    DeveloperUsage.application_id == application_id,
                    DeveloperUsage.usage_date == usage_date,
                    DeveloperUsage.unit == unit,
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.value = float(existing.value or 0.0) + value
            row = existing
        else:
            row = DeveloperUsage(
                developer_id=developer_id,
                application_id=application_id,
                usage_date=usage_date,
                unit=unit,
                value=value,
            )
            db.add(row)
            await db.flush()
        await publish_background_event(
            db, name="usage.recorded", organization_id=organization_id or developer_id,
            payload={
                "application_id": application_id,
                "usage_date": usage_date,
                "unit": unit,
                "value": row.value,
            },
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def summary(
        self,
        db: AsyncSession,
        developer_id: str,
        *,
        days: int = 30,
    ) -> dict[str, Any]:
        from datetime import timedelta

        period_end = utcnow().date()
        since = (period_end - timedelta(days=days - 1)).isoformat()
        rows = (
            await db.execute(
                select(
                    DeveloperUsage.unit,
                    DeveloperUsage.usage_date,
                    func.sum(DeveloperUsage.value).label("total"),
                )
                .where(
                    DeveloperUsage.developer_id == developer_id,
                    DeveloperUsage.usage_date >= since,
                )
                .group_by(DeveloperUsage.unit, DeveloperUsage.usage_date)
            )
        ).all()
        totals: dict[str, float] = {}
        by_day: dict[str, dict[str, float]] = {}
        for unit, usage_date, total in rows:
            totals[unit] = totals.get(unit, 0.0) + (total or 0.0)
            by_day.setdefault(usage_date, {})[unit] = float(total or 0.0)
        return {
            "developer_id": developer_id,
            "days": days,
            "period_end": period_end.isoformat(),
            "totals": {u: round(totals.get(u, 0.0), 1) for u in UNITS},
            "by_day": by_day,
        }

    async def list_records(
        self,
        db: AsyncSession,
        developer_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DeveloperUsage)
                .where(DeveloperUsage.developer_id == developer_id)
                .order_by(DeveloperUsage.usage_date.desc(), DeveloperUsage.unit.asc())
                .limit(limit)
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    def serialize(self, row: DeveloperUsage) -> dict[str, Any]:
        return {
            "id": row.id,
            "developer_id": row.developer_id,
            "application_id": row.application_id,
            "usage_date": row.usage_date,
            "unit": row.unit,
            "value": float(row.value or 0.0),
        }


developer_analytics_service = DeveloperAnalyticsService()
