"""Workflow scheduler (Phase 14) — cron-driven runs.

Schedules hold a 5-field cron expression (minute hour day-of-month month
day-of-week) plus a payload template. The scheduler worker computes due
schedules and starts executions with the rendered payload as context.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.execution_service import execution_engine
from app.core.timeutils import utcnow
from app.models.workflow import Workflow, WorkflowSchedule

logger = logging.getLogger("vcos.automation.scheduler")

_SHORTHANDS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}

MAX_RUNS_PER_PASS = 200


class SchedulerService:
    # ---------------------------------------------------------------- CRUD

    async def create(self, db: AsyncSession, *, organization_id: str,
                     data: dict[str, Any]) -> WorkflowSchedule:
        workflow = await db.get(Workflow, data["workflow_id"])
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        cron = data.get("cron", "")
        cron = _SHORTHANDS.get(cron.strip(), cron.strip())
        if not self._valid_cron(cron):
            raise ValueError(f"Invalid cron expression: {cron}")
        schedule = WorkflowSchedule(
            organization_id=organization_id,
            workflow_id=data["workflow_id"],
            name=data.get("name", workflow.name),
            cron=cron,
            timezone=data.get("timezone", "UTC"),
            enabled=data.get("enabled", True),
            payload_template=data.get("payload_template") or {},
            next_run_at=utcnow() + timedelta(minutes=1),
        )
        db.add(schedule)
        await db.flush()
        schedule.next_run_at = self._next_run(cron, after=utcnow())
        await db.flush()
        return schedule

    async def update(self, db: AsyncSession, schedule: WorkflowSchedule,
                     data: dict[str, Any]) -> WorkflowSchedule:
        for field in ("name", "cron", "timezone", "enabled", "payload_template"):
            if field in data:
                setattr(schedule, field, data[field])
        schedule.cron = _SHORTHANDS.get(schedule.cron.strip(), schedule.cron.strip())
        if not self._valid_cron(schedule.cron):
            raise ValueError(f"Invalid cron expression: {schedule.cron}")
        if data.get("enabled") is not None or "cron" in data:
            schedule.next_run_at = self._next_run(schedule.cron, after=utcnow())
        await db.flush()
        return schedule

    async def list(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WorkflowSchedule).where(WorkflowSchedule.organization_id == organization_id)
            )
        ).scalars().all()
        result = []
        for schedule in rows:
            workflow = await db.get(Workflow, schedule.workflow_id)
            result.append({
                "id": schedule.id,
                "workflow_id": schedule.workflow_id,
                "workflow_name": workflow.name if workflow else None,
                "name": schedule.name,
                "cron": schedule.cron,
                "timezone": schedule.timezone,
                "enabled": schedule.enabled,
                "payload_template": schedule.payload_template,
                "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                "run_count": schedule.run_count,
            })
        return result

    async def delete(self, db: AsyncSession, schedule: WorkflowSchedule) -> None:
        await db.delete(schedule)
        await db.flush()

    # ------------------------------------------------------------- running

    async def run_due(self, db: AsyncSession, *, limit: int = 50) -> int:
        """Fire schedules whose next_run_at has passed (scheduler worker)."""
        now = utcnow()
        rows = (
            await db.execute(
                select(WorkflowSchedule)
                .where(
                    WorkflowSchedule.enabled.is_(True),
                    WorkflowSchedule.next_run_at.isnot(None),
                    WorkflowSchedule.next_run_at <= now,
                )
                .order_by(WorkflowSchedule.next_run_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        started = 0
        for schedule in rows:
            workflow = await db.get(Workflow, schedule.workflow_id)
            if workflow is None or workflow.status != "active":
                continue
            try:
                await execution_engine.start(
                    db,
                    organization_id=schedule.organization_id,
                    workflow_id=schedule.workflow_id,
                    trigger_source="schedule",
                    context=dict(schedule.payload_template or {}),
                )
                schedule.run_count += 1
                schedule.last_run_at = now
                schedule.next_run_at = self._next_run(schedule.cron, after=now)
                started += 1
            except Exception as exc:  # noqa: BLE001 - one schedule never blocks others
                logger.warning("schedule %s failed: %s", schedule.id, exc)
                schedule.next_run_at = now + timedelta(minutes=5)
            if started >= MAX_RUNS_PER_PASS:
                break
        await db.flush()
        return started

    # --------------------------------------------------------------- cron

    def _valid_cron(self, cron: str) -> bool:
        parts = cron.split()
        if len(parts) != 5:
            return False
        try:
            for idx, part in enumerate(parts):
                limits = (0, 59), (0, 23), (1, 31), (1, 12), (0, 6)
                lo, hi = limits[idx]
                for token in part.split(","):
                    if token in ("*", "?"):
                        continue
                    if "/" in token:
                        token = token.split("/")[0]
                    if token == "*":
                        continue
                    if "-" in token:
                        start, end = token.split("-")
                        if int(start) < lo or int(end) > hi:
                            return False
                    else:
                        if int(token) < lo or int(token) > hi:
                            return False
        except ValueError:
            return False
        return True

    def _next_run(self, cron: str, after: datetime) -> datetime:
        """Find the next moment matching the cron expression after `after`."""
        try:
            cron = _SHORTHANDS.get(cron.strip(), cron.strip())
            minute_field, hour_field, dom_field, month_field, dow_field = cron.split()
            candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
            for _ in range(48 * 30):  # look up to 30 days ahead
                if self._matches(candidate, minute_field, hour_field,
                                 dom_field, month_field, dow_field):
                    return candidate
                candidate += timedelta(minutes=1)
        except Exception:  # pragma: no cover - defensive fallback
            logger.warning("cron compute failed for %s", cron)
        return after + timedelta(days=1)

    def _matches(self, moment: datetime, minute_field: str, hour_field: str,
                 dom_field: str, month_field: str, dow_field: str) -> bool:
        return (
            self._field_matches(moment.minute, minute_field)
            and self._field_matches(moment.hour, hour_field)
            and self._field_matches(moment.day, dom_field)
            and self._field_matches(moment.month, month_field)
            and self._field_matches(moment.weekday(), dow_field)
        )

    def _field_matches(self, value: int, field: str) -> bool:
        if field in ("*", "?"):
            return True
        for token in field.split(","):
            step = 1
            if "/" in token:
                token, step_str = token.split("/")
                step = int(step_str)
            base = token
            if "-" in token:
                start, end = token.split("-")
                if value < int(start) or value > int(end):
                    continue
                if (value - int(start)) % step != 0:
                    continue
                return True
            if base == "*":
                if value % step != 0:
                    continue
                return True
            if value == int(base) and step == 1:
                return True
        return False


scheduler_service = SchedulerService()
