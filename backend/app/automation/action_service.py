"""Workflow action executor (Phase 14) â€” performs typed actions inside executions.

Actions reuse the existing module services (tasks, meetings, projects,
approvals, onboarding, notifications) so workflow-created entities behave
exactly like user-created ones, including events and alerts.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.workflow import AutomationIntegration, WorkflowAction

logger = logging.getLogger("vcos.automation.actions")

# node types that are executed (non-routing)
ACTION_NODE_TYPES = (
    "task",
    "meeting",
    "project",
    "notification",
    "approval",
    "onboarding",
    "integration",
    "webhook",
    "ai_summarize",
)


def render_template(value: Any, context: dict[str, Any]) -> Any:
    """Substitute {{ path }} tokens (context or trigger payload) in strings."""
    if isinstance(value, str) and "{{" in value:
        result = value
        for key, val in list(context.items()):
            if isinstance(val, (dict, list)):
                continue
            result = result.replace("{{" + key + "}}", str(val))
        return result
    if isinstance(value, list):
        return [render_template(item, context) for item in value]
    if isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}
    return value


async def _employee_id(db: AsyncSession, organization_id: str, ref: str) -> Optional[str]:
    """Resolve a user_id or employee_id reference to an employee id."""
    if not ref:
        return None
    if ref == "__OWNER__":
        from app.models.organization import Organization

        org = await db.get(Organization, organization_id)
        ref = (org.owner_id if org else None) or ""
    row = await db.execute(
        select(Employee).where(Employee.organization_id == organization_id)
    )
    for employee in row.scalars().all():
        if employee.id == ref or employee.user_id == ref:
            return employee.id
    return None


async def _actor_employee(db: AsyncSession, organization_id: str, actor_id: Optional[str]):
    """Resolve an acting user id to an Employee (None when absent)."""
    if not actor_id:
        return None
    from app.people.employee_service import employee_service

    try:
        return await employee_service.get_by_user(db, organization_id=organization_id, user_id=actor_id)
    except Exception:  # pragma: no cover - defensive
        return None


class ActionExecutor:
    """Executes a single action node and returns a serializable result."""

    async def execute(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action: WorkflowAction,
        context: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        action_type = action.action_type
        config = render_template(dict(action.config or {}), context)
        handler = getattr(self, f"_action_{action_type}", None)
        if handler is None:
            raise ValueError(f"Unsupported action type: {action_type}")
        return await handler(db, organization_id=organization_id, config=config,
                             context=context, actor_id=actor_id)

    # ------------------------------------------------------------- actions

    async def _action_create_task(self, db, *, organization_id, config, context, actor_id):
        from app.work.task_service import task_service

        data = {
            "title": config["title"],
            "description": config.get("description"),
            "status": config.get("status", "backlog"),
            "priority": config.get("priority", "medium"),
            "project_id": config.get("project_id"),
            "epic_id": config.get("epic_id"),
            "milestone_id": config.get("milestone_id"),
            "sprint_id": config.get("sprint_id"),
            "assignee_id": await _employee_id(db, organization_id, config.get("assignee_ref") or config.get("assignee_id")),
            "reporter_id": await _employee_id(db, organization_id, config.get("reporter_ref") or config.get("reporter_id")),
            "estimate_hours": config.get("estimate_hours"),
            "due_date": config.get("due_date"),
        }
        task = await task_service.create(
            db, organization_id=organization_id, data=data,
            actor=await _actor_employee(db, organization_id, actor_id),
        )
        return {"task_id": task.id, "title": task.title, "status": task.status}

    async def _action_create_meeting(self, db, *, organization_id, config, context, actor_id):
        from app.work.meeting_service import meeting_service

        data = {
            "title": config["title"],
            "description": config.get("description"),
            "meeting_type": config.get("meeting_type", "team"),
            "status": config.get("status", "scheduled"),
            "organizer_id": await _employee_id(db, organization_id, config.get("organizer_ref") or config.get("organizer_id")),
            "project_id": config.get("project_id"),
            "goal_id": config.get("goal_id"),
            "start_at": config.get("start_at"),
            "end_at": config.get("end_at"),
            "location": config.get("location"),
            "agenda": config.get("agenda", []),
            "attendee_ids": [
                emp_id for ref in (config.get("attendee_refs") or [])
                if (emp_id := await _employee_id(db, organization_id, ref))
            ],
        }
        meeting = await meeting_service.create(
            db, organization_id=organization_id, data=data,
            actor=await _actor_employee(db, organization_id, actor_id),
        )
        return {"meeting_id": meeting.id, "title": meeting.title, "status": meeting.status}

    async def _action_create_project(self, db, *, organization_id, config, context, actor_id):
        from app.work.project_service import project_service

        data = {
            "name": config["name"],
            "description": config.get("description"),
            "status": config.get("status", "planning"),
            "owner_id": await _employee_id(db, organization_id, config.get("owner_ref") or config.get("owner_id")),
            "department_id": config.get("department_id"),
            "team_id": config.get("team_id"),
            "start_date": config.get("start_date"),
            "due_date": config.get("due_date"),
        }
        project = await project_service.create(
            db, organization_id=organization_id, data=data,
            actor=await _actor_employee(db, organization_id, actor_id),
        )
        return {"project_id": project.id, "name": project.name, "status": project.status}

    async def _action_create_approval(self, db, *, organization_id, config, context, actor_id):
        from app.work.approval_service import approval_service

        data = {
            "approval_type": config.get("approval_type", "workflow"),
            "title": config["title"],
            "description": config.get("description"),
            "requester_id": await _employee_id(db, organization_id, config.get("requester_ref") or config.get("requester_id")),
            "approver_id": await _employee_id(db, organization_id, config.get("approver_ref") or config.get("approver_id")),
            "priority": config.get("priority", "medium"),
            "due_at": config.get("due_at"),
            "entity_type": "workflow_execution",
            "entity_id": context.get("execution_id"),
        }
        approval = await approval_service.create(
            db, organization_id=organization_id, data=data,
            actor=await _actor_employee(db, organization_id, actor_id),
        )
        return {"approval_id": approval.id, "title": approval.title, "status": approval.status}

    async def _action_create_onboarding(self, db, *, organization_id, config, context, actor_id):
        from app.learning.onboarding_service import onboarding_service

        employee_ref = config.get("employee_ref") or config.get("employee_id")
        employee_id = await _employee_id(db, organization_id, employee_ref)
        if not employee_id:
            raise ValueError("onboarding action requires an employee_ref")
        plan = await onboarding_service.create_plan(
            db, organization_id=organization_id, employee_id=employee_id,
            actor=await _actor_employee(db, organization_id, actor_id),
        )
        return {"plan_id": plan.id, "employee_id": employee_id, "status": plan.status}

    async def _action_send_notification(self, db, *, organization_id, config, context, actor_id):
        from app.services.notification_service import notification_service

        recipient_ref = config.get("recipient_ref") or config.get("recipient_id")
        employee = None
        if recipient_ref:
            employee = await _employee_id(db, organization_id, recipient_ref)
        recipient = employee or (actor_id if not recipient_ref else None)
        if not recipient and not recipient_ref:
            from app.models.workflow import Workflow

            owner = await db.execute(
                select(Workflow).where(
                    Workflow.id == context.get("workflow_id"),
                    Workflow.organization_id == organization_id,
                )
            )
            workflow = owner.scalar_one_or_none()
            if workflow and workflow.created_by:
                recipient = await _employee_id(db, organization_id, workflow.created_by)
        if not recipient:
            raise ValueError("notification action requires a recipient_ref")
        notification = await notification_service.create(
            db,
            organization_id=organization_id,
            recipient_id=recipient,
            type=config.get("type", "automation"),
            title=config["title"],
            body=config.get("body"),
            actor_id=actor_id,
            priority=config.get("priority", "normal"),
            channel=config.get("channel", "in_app"),
            link=config.get("link"),
            entity_type="workflow_execution",
            entity_id=context.get("execution_id"),
            metadata={"node_key": context.get("node_key"), "workflow_id": context.get("workflow_id")},
        )
        return {"notification_id": notification.id, "recipient_id": recipient}

    async def _action_send_message(self, db, *, organization_id, config, context, actor_id):
        from app.services.notification_service import notification_service

        broadcast_to = config.get("broadcast", False)
        if broadcast_to:
            from app.models.user import User

            users = (
                await db.execute(
                    select(User.id).where(User.id.in_(
                        select(Employee.user_id).where(Employee.organization_id == organization_id)
                    ))
                )
            ).scalars().all()
            sent = 0
            for user_id in users:
                await notification_service.create(
                    db,
                    organization_id=organization_id,
                    recipient_id=user_id,
                    type="automation",
                    title=config["title"],
                    body=config.get("body"),
                    actor_id=actor_id,
                    priority=config.get("priority", "normal"),
                    entity_type="workflow_execution",
                    entity_id=context.get("execution_id"),
                )
                sent += 1
            return {"sent": sent}
        return {"sent": 0}

    async def _action_integration(self, db, *, organization_id, config, context, actor_id):
        from app.automation.integration_service import automation_integration_service

        name = config.get("integration") or config.get("integration_name")
        if not name:
            raise ValueError("integration action requires an integration name")
        return await automation_integration_service.trigger_sync(
            db, organization_id=organization_id, integration_name=name,
            payload={"action": config.get("event", "workflow"), "context": context},
        )

    async def _action_webhook(self, db, *, organization_id, config, context, actor_id):
        url = config.get("url")
        if not url:
            raise ValueError("webhook action requires a url")
        payload = {
            "workflow": context.get("workflow_id"),
            "execution": context.get("execution_id"),
            "event": config.get("event", "workflow.completed"),
            "data": config.get("payload") or {},
        }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
            return {"status_code": response.status_code, "ok": response.status_code < 400}
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("webhook action failed: %s", exc)
            return {"status_code": 0, "ok": False, "error": str(exc)}

    async def _action_ai_summarize(self, db, *, organization_id, config, context, actor_id):
        text = str(config.get("text") or context.get("trigger") or "")
        summary = text[:500]
        return {"summary": summary, "characters": len(summary)}


action_executor = ActionExecutor()

