"""Workflow trigger engine (Phase 14) — manual, event, schedule, webhook.

The event-bus hook (on_event) is called from the event worker after regular
handlers run, so event-driven workflows react with zero extra latency.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.execution_service import execution_engine
from app.models.workflow import Workflow, WorkflowTrigger

logger = logging.getLogger("vcos.automation.triggers")

TRIGGER_TYPES = ("manual", "event", "schedule", "webhook")


class TriggerEngine:
    # ------------------------------------------------------------- manual

    async def run_manual(
        self, db: AsyncSession, *, organization_id: str, workflow_id: str,
        triggered_by: Optional[str] = None, context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        if workflow.trigger_type not in ("manual", "webhook", "event", "schedule"):
            raise ValueError(f"Workflow cannot be run manually with trigger type {workflow.trigger_type}")
        execution = await execution_engine.start(
            db, organization_id=organization_id, workflow_id=workflow.id,
            trigger_source="manual", triggered_by=triggered_by, context=context or {},
        )
        await db.flush()
        detail = await execution_engine.execution_detail(db, execution)
        db.expunge(execution)
        return detail

    # -------------------------------------------------------------- event

    async def on_event(self, db: AsyncSession, event_name: str, organization_id: Optional[str],
                       payload: dict[str, Any], actor_id: Optional[str] = None) -> int:
        """Event-bus hook: start executions for matching event triggers and
        evaluate business rules. Returns executions started."""
        started = 0
        if not organization_id:
            return started
        filters = {
            "event_name": event_name,
            "enabled": True,
        }
        triggers = (
            await db.execute(
                select(WorkflowTrigger).where(
                    WorkflowTrigger.organization_id == organization_id,
                    WorkflowTrigger.trigger_type == "event",
                    WorkflowTrigger.event_name == event_name,
                    WorkflowTrigger.enabled.is_(True),
                )
            )
        ).scalars().all()
        for trigger in triggers:
            workflow = await db.get(Workflow, trigger.workflow_id)
            if workflow is None or workflow.status != "active":
                continue
            if not self._matches_filters(trigger.config or {}, payload):
                continue
            try:
                execution = await execution_engine.start(
                    db, organization_id=organization_id, workflow_id=workflow.id,
                    trigger_source="event", trigger_event=event_name,
                    triggered_by=actor_id, context=payload,
                )
                trigger.fire_count += 1
                trigger.last_fired_at = execution.started_at
                started += 1
            except Exception as exc:  # noqa: BLE001 - one bad trigger never blocks others
                logger.warning("event trigger %s failed for %s: %s",
                               trigger.id, event_name, exc)
        await db.flush()
        return started

    def _matches_filters(self, config: dict[str, Any], payload: dict[str, Any]) -> bool:
        filters = config.get("filters") or []
        for condition in filters:
            value = payload.get(condition.get("field")) if isinstance(payload, dict) else None
            operator = condition.get("operator", "eq")
            expected = condition.get("value")
            if operator == "eq" and value != expected:
                return False
            if operator == "neq" and value == expected:
                return False
            if operator == "contains" and expected not in str(value or ""):
                return False
            if operator == "in" and value not in (expected or []):
                return False
        return True

    # ------------------------------------------------------------ webhook

    async def run_webhook(
        self, db: AsyncSession, *, organization_id: str, workflow_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        if workflow.status != "active":
            raise ValueError("Workflow is not active")
        config = workflow.trigger_config or {}
        if config.get("token") and config.get("token") != payload.get("token"):
            raise PermissionError("Invalid webhook token")
        execution = await execution_engine.start(
            db, organization_id=organization_id, workflow_id=workflow.id,
            trigger_source="webhook", context=payload,
        )
        await db.flush()
        detail = await execution_engine.execution_detail(db, execution)
        db.expunge(execution)
        return detail

    # ----------------------------------------------------------- triggers

    async def list(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(WorkflowTrigger).where(WorkflowTrigger.organization_id == organization_id)
            )
        ).scalars().all()
        result = []
        for trigger in rows:
            workflow = await db.get(Workflow, trigger.workflow_id)
            result.append({
                "id": trigger.id,
                "workflow_id": trigger.workflow_id,
                "workflow_name": workflow.name if workflow else None,
                "trigger_type": trigger.trigger_type,
                "event_name": trigger.event_name,
                "config": trigger.config,
                "enabled": trigger.enabled,
                "last_fired_at": trigger.last_fired_at.isoformat() if trigger.last_fired_at else None,
                "fire_count": trigger.fire_count,
            })
        return result

    async def create(self, db: AsyncSession, *, organization_id: str, workflow_id: str,
                     trigger_type: str, event_name: Optional[str] = None,
                     config: Optional[dict[str, Any]] = None) -> WorkflowTrigger:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"Invalid trigger type: {trigger_type}")
        if trigger_type == "event" and not event_name:
            raise ValueError("Event triggers require an event_name")
        existing = (
            await db.execute(
                select(WorkflowTrigger).where(
                    WorkflowTrigger.workflow_id == workflow_id,
                    WorkflowTrigger.trigger_type == trigger_type,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.event_name = event_name or existing.event_name
            existing.config = config or {}
            await db.flush()
            return existing
        trigger = WorkflowTrigger(
            organization_id=organization_id,
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            event_name=event_name,
            config=config or {},
        )
        db.add(trigger)
        await db.flush()
        return trigger

    async def update(self, db: AsyncSession, trigger: WorkflowTrigger,
                     data: dict[str, Any]) -> WorkflowTrigger:
        for field in ("event_name", "config", "enabled"):
            if field in data:
                setattr(trigger, field, data[field])
        await db.flush()
        return trigger

    async def delete(self, db: AsyncSession, trigger: WorkflowTrigger) -> None:
        await db.delete(trigger)
        await db.flush()

    async def check_token(self, db: AsyncSession, workflow_id: str, token: str) -> bool:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None:
            return False
        return (workflow.trigger_config or {}).get("token") == token


trigger_engine = TriggerEngine()
