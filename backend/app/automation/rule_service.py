"""Business rules engine (Phase 14) — event-driven IF/THEN automation.

Rules match an event name plus conditions on the payload and fire a list of
actions through the same ActionExecutor used by workflow nodes. Rules run
from the event-bus hook alongside event triggers.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.workflow import AutomationIntegration, BusinessRule, WorkflowLog

logger = logging.getLogger("vcos.automation.rules")

OPERATORS = {"eq", "neq", "gt", "gte", "lt", "lte", "contains", "in", "is_null", "truthy"}


class RuleEngine:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        created_by: Optional[str] = None,
    ) -> BusinessRule:
        for condition in data.get("conditions", []):
            if condition.get("operator", "eq") not in OPERATORS:
                raise ValueError(f"Unsupported condition operator: {condition.get('operator')}")
        rule = BusinessRule(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            event_name=data["event_name"],
            conditions=data.get("conditions") or [],
            actions=data.get("actions") or [],
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
            created_by=created_by,
        )
        db.add(rule)
        await db.flush()
        return rule

    async def update(self, db: AsyncSession, rule: BusinessRule, data: dict[str, Any]) -> BusinessRule:
        for field in ("name", "description", "event_name", "conditions",
                      "actions", "enabled", "priority"):
            if field in data:
                setattr(rule, field, data[field])
        await db.flush()
        return rule

    async def on_event(self, db: AsyncSession, event_name: str, organization_id: Optional[str],
                       payload: dict[str, Any], actor_id: Optional[str] = None) -> int:
        """Evaluate matching enabled rules and fire their actions."""
        fired = 0
        if not organization_id:
            return fired
        rules = (
            await db.execute(
                select(BusinessRule)
                .where(
                    BusinessRule.organization_id == organization_id,
                    BusinessRule.event_name == event_name,
                    BusinessRule.enabled.is_(True),
                )
                .order_by(BusinessRule.priority.asc(), BusinessRule.created_at.asc())
            )
        ).scalars().all()
        for rule in rules:
            if not self._matches(rule.conditions or [], payload):
                continue
            try:
                await self._fire(db, rule, payload, actor_id)
                rule.hit_count += 1
                rule.last_triggered_at = utcnow()
                fired += 1
            except Exception as exc:  # noqa: BLE001 - one rule never blocks others
                logger.warning("rule %s failed: %s", rule.id, exc)
        await db.flush()
        return fired

    def _matches(self, conditions: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
        for condition in conditions:
            value = payload.get(condition.get("field")) if isinstance(payload, dict) else None
            operator = condition.get("operator", "eq")
            expected = condition.get("value")
            if operator == "eq" and value != expected:
                return False
            if operator == "neq" and value == expected:
                return False
            if operator == "truthy" and not value:
                return False
            if operator == "is_null" and value not in (None, "", []):
                return False
            if operator == "contains" and expected not in str(value or ""):
                return False
            if operator == "in" and value not in (expected or []):
                return False
            try:
                if operator in ("gt", "gte", "lt", "lte"):
                    left, right = float(value), float(expected)
                    checks = {"gt": left > right, "gte": left >= right,
                              "lt": left < right, "lte": left <= right}
                    if not checks[operator]:
                        return False
            except (TypeError, ValueError):
                return False
        return True

    async def _fire(self, db, rule: BusinessRule, payload: dict[str, Any],
                    actor_id: Optional[str]) -> None:
        from app.automation.action_service import action_executor
        from app.models.workflow import WorkflowAction

        context = {"trigger": dict(payload), "rule_id": rule.id, "rule_name": rule.name}
        for action in rule.actions or []:
            action_type = action.get("action", "send_notification")
            config = dict(action.get("config") or {})
            row = WorkflowAction(
                organization_id=rule.organization_id,
                workflow_id="",
                node_key=f"rule_{rule.id}_{action_type}",
                action_type=action_type,
                config=config,
            )
            await action_executor.execute(
                db, organization_id=rule.organization_id, action=row,
                context=context, actor_id=actor_id,
            )
        db.add(
            WorkflowLog(
                organization_id=rule.organization_id,
                level="info",
                message=f"Rule fired: {rule.name} on {rule.event_name}",
                data={"rule_id": rule.id, "event": rule.event_name},
            )
        )
        await db.flush()


rule_engine = RuleEngine()
