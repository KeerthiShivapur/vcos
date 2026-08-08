"""Phase 8.10 — Trend Analysis.

AI continuously detects growth, decline and improvement across the
organization: collaboration, knowledge, hiring, innovation, learning and
productivity trends — bucketed daily, weekly, monthly, quarterly and yearly,
and persisted as organization metrics for the executive dashboard.
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.communication import CommunityPost, InnovationIdea, Recognition
from app.models.employee import Employee
from app.models.executive import ExecutiveMetric
from app.models.knowledge import Decision, Document, WikiPage
from app.models.meeting import Meeting
from app.models.task import Task

logger = logging.getLogger("vcos.executive.analytics")

_METRIC_SOURCES: dict[str, tuple[Any, str]] = {
    "tasks_created": (Task, "created_at"),
    "tasks_completed": (Task, "completed_at"),
    "meetings_held": (Meeting, "start_at"),
    "knowledge_published": (Document, "created_at"),
    "wiki_published": (WikiPage, "created_at"),
    "decisions_made": (Decision, "created_at"),
    "employees_joined": (Employee, "created_at"),
    "posts_created": (CommunityPost, "created_at"),
    "ideas_submitted": (InnovationIdea, "created_at"),
    "recognitions_given": (Recognition, "created_at"),
}

_PERIOD_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}


def _bucket_key(ts: datetime | date | None, period: str) -> str:
    if ts is None:
        return "unknown"
    if isinstance(ts, date) and not isinstance(ts, datetime):
        ts = datetime(ts.year, ts.month, ts.day)
    if ts.tzinfo is not None:
        ts = ts.astimezone(utcnow().tzinfo)
    if period == "daily":
        return ts.strftime("%Y-%m-%d")
    if period == "weekly":
        iso = ts.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "monthly":
        return ts.strftime("%Y-%m")
    if period == "quarterly":
        return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"
    return str(ts.year)


class ExecutiveAnalytics:
    async def trends(self, db: AsyncSession, *, organization_id: str, period: str = "weekly") -> dict[str, Any]:
        if period not in _PERIOD_DAYS:
            raise ValueError("period must be one of daily|weekly|monthly|quarterly|yearly")
        days = _PERIOD_DAYS[period]
        now = utcnow()
        cutoff = now - timedelta(days=days * 26)

        series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for metric, (model, attr) in _METRIC_SOURCES.items():
            rows = (await db.execute(
                select(model, getattr(model, attr)).where(
                    model.organization_id == organization_id,
                    getattr(model, attr).isnot(None),
                )
            )).all()
            for _row, ts in rows:
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=now.tzinfo)
                if ts < cutoff:
                    continue
                series[metric][_bucket_key(ts, period)] += 1

        results: list[dict[str, Any]] = []
        for metric, buckets in series.items():
            ordered = sorted(buckets.items())
            values = [v for _, v in ordered]
            first = values[0] if values else 0
            last = values[-1] if values else 0
            if first > 0:
                change = round((last - first) / first * 100, 1)
            elif last > 0:
                change = 100.0
            else:
                change = 0.0
            direction = "growing" if change > 5 else ("declining" if change < -5 else "stable")
            results.append({
                "metric": metric,
                "period": period,
                "points": [{"period": k, "value": v} for k, v in ordered],
                "first": first,
                "last": last,
                "change_percent": change,
                "direction": direction,
            })
        results.sort(key=lambda r: r["metric"])
        return {"period": period, "trends": results}

    async def refresh(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        total = 0
        for metric, (model, attr) in _METRIC_SOURCES.items():
            count = (
                await db.execute(select(func.count(model.id)).where(
                    model.organization_id == organization_id,
                    getattr(model, attr) >= now - timedelta(days=_PERIOD_DAYS["weekly"]),
                ))
            ).scalar() or 0
            db.add(ExecutiveMetric(
                organization_id=organization_id,
                metric=metric,
                value=count,
                unit="count",
                period="weekly",
                period_start=now.strftime("%Y-%m-%d"),
            ))
            total += 1
        return {"refreshed": total, "as_of": now.isoformat()}

    async def history(self, db: AsyncSession, *, organization_id: str, limit: int = 200) -> dict[str, Any]:
        rows = (await db.execute(
            select(ExecutiveMetric).where(ExecutiveMetric.organization_id == organization_id)
            .order_by(ExecutiveMetric.created_at.desc()).limit(limit)
        )).scalars().all()
        return {
            "total": len(rows),
            "metrics": [
                {
                    "id": m.id,
                    "metric": m.metric,
                    "value": m.value,
                    "period": m.period,
                    "period_start": m.period_start,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in rows
            ],
        }


executive_analytics = ExecutiveAnalytics()
