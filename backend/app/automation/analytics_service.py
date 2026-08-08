"""Workflow analytics (Phase 14) — dashboards, trends, materialized metrics.

The analytics worker materializes daily/monthly metrics; live endpoints
compute execution statistics on demand.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.workflow import Workflow, WorkflowExecution, WorkflowMetric, WorkflowSchedule

logger = logging.getLogger("vcos.automation.analytics")


class WorkflowAnalytics:
    async def dashboard(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        workflows = (
            await db.execute(select(Workflow).where(Workflow.organization_id == organization_id))
        ).scalars().all()
        executions = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.organization_id == organization_id)
            )
        ).scalars().all()
        schedules = (
            await db.execute(
                select(WorkflowSchedule).where(WorkflowSchedule.organization_id == organization_id)
            )
        ).scalars().all()

        status_counts = {"draft": 0, "active": 0, "paused": 0, "archived": 0}
        for workflow in workflows:
            status_counts[workflow.status] = status_counts.get(workflow.status, 0) + 1
        exec_counts = {"queued": 0, "running": 0, "waiting": 0, "completed": 0,
                       "failed": 0, "cancelled": 0, "timed_out": 0}
        durations = [execution.duration_ms for execution in executions if execution.duration_ms]
        for execution in executions:
            exec_counts[execution.status] = exec_counts.get(execution.status, 0) + 1
        completed = exec_counts.get("completed", 0)
        total = len(executions)
        return {
            "workflows": {
                "total": len(workflows),
                **status_counts,
            },
            "executions": {
                "total": total,
                **exec_counts,
            },
            "completion_rate": round(completed / total * 100, 1) if total else 0.0,
            "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "schedules": {"total": len(schedules),
                          "enabled": sum(1 for s in schedules if s.enabled)},
            "run_count": sum(w.run_count or 0 for w in workflows),
        }

    async def trends(self, db: AsyncSession, *, organization_id: str,
                     days: int = 30, workflow_id: Optional[str] = None) -> dict[str, Any]:
        since = utcnow() - timedelta(days=days)
        query = select(WorkflowExecution).where(
            WorkflowExecution.organization_id == organization_id,
            WorkflowExecution.started_at >= since,
        )
        if workflow_id:
            query = query.where(WorkflowExecution.workflow_id == workflow_id)
        rows = (await db.execute(query)).scalars().all()
        by_day: dict[str, dict[str, int]] = {}
        by_workflow: dict[str, dict[str, Any]] = {}
        for execution in rows:
            day = (execution.started_at or utcnow()).strftime("%Y-%m-%d")
            bucket = by_day.setdefault(day, {"runs": 0, "completed": 0, "failed": 0, "waiting": 0})
            bucket["runs"] += 1
            bucket[execution.status if execution.status in ("completed", "failed", "waiting") else "runs"] += 0
            if execution.status == "completed":
                bucket["completed"] += 1
            elif execution.status == "failed":
                bucket["failed"] += 1
            elif execution.status == "waiting":
                bucket["waiting"] += 1
            wf = by_workflow.setdefault(
                execution.workflow_id or "unknown",
                {"workflow_id": execution.workflow_id, "name": execution.workflow_name,
                 "runs": 0, "completed": 0, "failed": 0},
            )
            wf["runs"] += 1
            if execution.status == "completed":
                wf["completed"] += 1
            elif execution.status == "failed":
                wf["failed"] += 1
        return {
            "by_day": [{"date": day, **counts} for day, counts in sorted(by_day.items())],
            "by_workflow": sorted(by_workflow.values(), key=lambda row: -row["runs"]),
        }

    async def materialize(self, db: AsyncSession, *, organization_id: Optional[str] = None) -> int:
        """Materialize monthly metrics for the analytics worker."""
        filters = []
        if organization_id:
            filters.append(WorkflowExecution.organization_id == organization_id)
        rows = (
            await db.execute(
                select(WorkflowExecution).where(*filters)
            )
        ).scalars().all()
        period = utcnow().strftime("%Y-%m")
        from collections import defaultdict

        totals = defaultdict(lambda: {"count": 0, "duration": 0})
        for execution in rows:
            key = (execution.organization_id, execution.workflow_id)
            totals[(key, "executions")]["count"] += 1
            if execution.status == "completed":
                totals[(key, "completions")]["count"] += 1
                if execution.duration_ms:
                    totals[(key, "avg_duration_ms")]["duration"] += execution.duration_ms
            if execution.status == "failed":
                totals[(key, "failures")]["count"] += 1

        written = 0
        for (org_id, workflow_id), metric_type in totals.keys():
            data = totals[((org_id, workflow_id), metric_type)]
            existing = (
                await db.execute(
                    select(WorkflowMetric).where(
                        WorkflowMetric.organization_id == org_id,
                        WorkflowMetric.workflow_id == workflow_id,
                        WorkflowMetric.metric_type == metric_type,
                        WorkflowMetric.period == period,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    WorkflowMetric(
                        organization_id=org_id,
                        workflow_id=workflow_id,
                        metric_type=metric_type,
                        period=period,
                        value=data["duration"] / data["count"] if data["count"] and metric_type == "avg_duration_ms" else float(data["count"]),
                        count=data["count"],
                    )
                )
                written += 1
        await db.flush()
        return written

    async def metrics(self, db: AsyncSession, *, organization_id: str,
                      metric_type: Optional[str] = None, limit: int = 60) -> list[dict[str, Any]]:
        query = select(WorkflowMetric).where(WorkflowMetric.organization_id == organization_id)
        if metric_type:
            query = query.where(WorkflowMetric.metric_type == metric_type)
        rows = (
            await db.execute(query.order_by(WorkflowMetric.period.desc()).limit(limit))
        ).scalars().all()
        return [
            {
                "id": row.id,
                "workflow_id": row.workflow_id,
                "metric_type": row.metric_type,
                "period": row.period,
                "value": row.value,
                "count": row.count,
            }
            for row in rows
        ]


workflow_analytics = WorkflowAnalytics()
