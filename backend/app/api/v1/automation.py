"""Workflow Automation & Business Process OS API (Phase 14).

Workflows (graph editor), executions (monitor), triggers, workflow approvals,
business rules, schedules, templates (marketplace), integrations, analytics
and the AI workflow assistant. Reads require automation:read; writes require
automation:manage. The webhook endpoint is deliberately unauthenticated —
runs are guarded by a per-workflow token.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.automation.ai_workflow_service import ai_workflow_service
from app.automation.analytics_service import workflow_analytics
from app.automation.approval_service import workflow_approval_service
from app.automation.execution_service import execution_engine
from app.automation.integration_service import automation_integration_service
from app.automation.rule_service import rule_engine
from app.automation.scheduler_service import scheduler_service
from app.automation.template_service import template_service
from app.automation.trigger_service import trigger_engine
from app.automation.workflow_service import workflow_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.workflow import (
    AutomationIntegration,
    BusinessRule,
    Workflow,
    WorkflowApproval,
    WorkflowExecution,
    WorkflowExecutionStep,
    WorkflowSchedule,
    WorkflowTemplate,
    WorkflowTrigger,
)

router = APIRouter(prefix="/automation", tags=["Automation"])


def _not_found(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{name} not found")


async def _get_workflow(db: AsyncSession, organization_id: str, workflow_id: str) -> Workflow:
    workflow = await db.get(Workflow, workflow_id)
    if workflow is None or workflow.organization_id != organization_id:
        raise _not_found("Workflow")
    return workflow


async def _get_execution(db: AsyncSession, organization_id: str, execution_id: str) -> WorkflowExecution:
    execution = await db.get(WorkflowExecution, execution_id)
    if execution is None or execution.organization_id != organization_id:
        raise _not_found("Execution")
    return execution


# ----------------------------------------------------------------- workflows

@router.get("/workflows")
async def list_workflows(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workflow_service.list(
        db, organization_id=org.id, status=status, category=category, search=search
    )


@router.post("/workflows", status_code=201)
async def create_workflow(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow = await workflow_service.create(
            db, organization_id=org.id, data=payload, created_by=user.id
        )
        await db.commit()
        return await workflow_service.payload(db, workflow)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    return await workflow_service.payload(db, workflow)


@router.patch("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    try:
        await workflow_service.update(db, workflow, payload)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await workflow_service.payload(db, workflow)


@router.post("/workflows/{workflow_id}/graph")
async def save_graph(
    workflow_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    try:
        await workflow_service.save_graph(
            db, workflow, nodes=payload.get("nodes", []),
            edges=payload.get("edges", []), actor_id=user.id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await workflow_service.payload(db, workflow)


@router.post("/workflows/{workflow_id}/transition")
async def transition_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    try:
        await workflow_service.transition(db, workflow, payload.get("status", "draft"))
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await workflow_service.payload(db, workflow)


@router.post("/workflows/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    copy = await workflow_service.duplicate(
        db, workflow, name=payload.get("name", f"{workflow.name} (copy)")
    )
    await db.commit()
    return await workflow_service.payload(db, copy)


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    try:
        detail = await trigger_engine.run_manual(
            db, organization_id=org.id, workflow_id=workflow.id,
            triggered_by=user.id, context=payload.get("context") or {},
        )
        await db.commit()
        return detail
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    workflow = await _get_workflow(db, org.id, workflow_id)
    await db.delete(workflow)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- executions

@router.get("/executions")
async def list_executions(
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    query = select(WorkflowExecution).where(WorkflowExecution.organization_id == org.id)
    if status:
        query = query.where(WorkflowExecution.status == status)
    if workflow_id:
        query = query.where(WorkflowExecution.workflow_id == workflow_id)
    rows = (
        await db.execute(query.order_by(WorkflowExecution.started_at.desc()).limit(limit))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "workflow_id": row.workflow_id,
            "workflow_name": row.workflow_name,
            "status": row.status,
            "trigger_source": row.trigger_source,
            "trigger_event": row.trigger_event,
            "triggered_by": row.triggered_by,
            "context": row.context or {},
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "duration_ms": row.duration_ms,
            "error": row.error,
            "resume_at": row.resume_at.isoformat() if row.resume_at else None,
        }
        for row in rows
    ]


@router.get("/executions/{execution_id}")
async def execution_detail(
    execution_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    execution = await _get_execution(db, org.id, execution_id)
    return await execution_engine.execution_detail(db, execution)


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    execution = await _get_execution(db, org.id, execution_id)
    await execution_engine.cancel(db, execution, reason="cancelled by user")
    await db.commit()
    return {"ok": True, "status": "cancelled"}


@router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    execution = await _get_execution(db, org.id, execution_id)
    await execution_engine.resume(db, execution)
    await db.commit()
    return {"ok": True, "status": execution.status}


@router.post("/executions/{execution_id}/retry")
async def retry_execution(
    execution_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    execution = await _get_execution(db, org.id, execution_id)
    steps = (
        await db.execute(
            select(WorkflowExecutionStep).where(
                WorkflowExecutionStep.execution_id == execution.id,
                WorkflowExecutionStep.status == "failed",
            )
        )
    ).scalars().all()

    for step in steps:
        step.status = "pending"
        step.error = None
        step.started_at = None
    if steps:
        execution.status = "waiting"
        execution.error = None
        execution.finished_at = None
        execution.duration_ms = None
    await db.flush()
    await execution_engine.resume(db, execution)
    await db.commit()
    return {"ok": True, "status": execution.status, "reset": len(steps)}


# ------------------------------------------------------------------ triggers

@router.get("/triggers")
async def list_triggers(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await trigger_engine.list(db, organization_id=org.id)


@router.post("/triggers", status_code=201)
async def create_trigger(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        trigger = await trigger_engine.create(
            db, organization_id=org.id, workflow_id=payload["workflow_id"],
            trigger_type=payload.get("trigger_type", "event"),
            event_name=payload.get("event_name"),
            config=payload.get("config") or {},
        )
        await db.commit()
        return {"id": trigger.id, "workflow_id": trigger.workflow_id,
                "trigger_type": trigger.trigger_type,
                "event_name": trigger.event_name, "enabled": trigger.enabled}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    trigger = await db.get(WorkflowTrigger, trigger_id)
    if trigger is None or trigger.organization_id != org.id:
        raise _not_found("Trigger")
    await trigger_engine.update(db, trigger, payload)
    await db.commit()
    return {"id": trigger.id, "enabled": trigger.enabled,
            "event_name": trigger.event_name, "config": trigger.config}


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    trigger = await db.get(WorkflowTrigger, trigger_id)
    if trigger is None or trigger.organization_id != org.id:
        raise _not_found("Trigger")
    await trigger_engine.delete(db, trigger)
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ approvals

@router.get("/approvals")
async def list_workflow_approvals(
    status: Optional[str] = None,
    mine: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workflow_approval_service.list(
        db, organization_id=org.id, status=status,
        as_user=user.id if mine else None,
    )


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    approval = await db.get(WorkflowApproval, approval_id)
    if approval is None or approval.organization_id != org.id:
        raise _not_found("Approval")
    try:
        await workflow_approval_service.decide(
            db, approval, decision=payload.get("decision", "approved"),
            decided_by=user.id, comment=payload.get("comment"),
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": approval.id, "status": approval.status,
            "escalation_level": approval.escalation_level}


# ---------------------------------------------------------------------- rules

@router.get("/rules")
async def list_rules(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(BusinessRule).where(BusinessRule.organization_id == org.id)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "event_name": row.event_name,
            "conditions": row.conditions,
            "actions": row.actions,
            "enabled": row.enabled,
            "priority": row.priority,
            "hit_count": row.hit_count,
            "last_triggered_at": row.last_triggered_at.isoformat() if row.last_triggered_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.post("/rules", status_code=201)
async def create_rule(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rule = await rule_engine.create(db, organization_id=org.id, data=payload, created_by=user.id)
        await db.commit()
        return {"id": rule.id, "name": rule.name, "event_name": rule.event_name,
                "enabled": rule.enabled}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(BusinessRule, rule_id)
    if rule is None or rule.organization_id != org.id:
        raise _not_found("Rule")
    await rule_engine.update(db, rule, payload)
    await db.commit()
    return {"id": rule.id, "enabled": rule.enabled}


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(BusinessRule, rule_id)
    if rule is None or rule.organization_id != org.id:
        raise _not_found("Rule")
    await db.delete(rule)
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ schedules

@router.get("/schedules")
async def list_schedules(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await scheduler_service.list(db, organization_id=org.id)


@router.post("/schedules", status_code=201)
async def create_schedule(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        schedule = await scheduler_service.create(db, organization_id=org.id, data=payload)
        await db.commit()
        return {"id": schedule.id, "name": schedule.name, "cron": schedule.cron,
                "enabled": schedule.enabled,
                "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    schedule = await db.get(WorkflowSchedule, schedule_id)
    if schedule is None or schedule.organization_id != org.id:
        raise _not_found("Schedule")
    try:
        await scheduler_service.update(db, schedule, payload)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": schedule.id, "enabled": schedule.enabled,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    schedule = await db.get(WorkflowSchedule, schedule_id)
    if schedule is None or schedule.organization_id != org.id:
        raise _not_found("Schedule")
    await scheduler_service.delete(db, schedule)
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ templates

@router.get("/templates")
async def list_templates(
    category: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    await template_service.seed(db)
    await db.commit()
    return await template_service.list(db, organization_id=org.id, category=category)


@router.post("/templates", status_code=201)
async def create_org_template(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        template = await template_service.create_org_template(
            db, data={**payload, "created_by": user.id}
        )
        await db.commit()
        return {"id": template.id, "name": template.name, "is_system": False}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/templates/instantiate")
async def instantiate_template(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await template_service.instantiate(
            db, template_id=payload["template_id"], organization_id=org.id,
            name=payload.get("name", "New workflow"), created_by=user.id,
        )
        await db.commit()
        return result
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------- integrations

@router.get("/integrations")
async def list_integrations(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await automation_integration_service.list(db, organization_id=org.id)


@router.post("/integrations", status_code=201)
async def create_integration(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        integration = await automation_integration_service.create(
            db, organization_id=org.id, data=payload, created_by=user.id
        )
        await db.commit()
        return {"id": integration.id, "name": integration.name,
                "platform": integration.platform, "enabled": integration.enabled}
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/integrations/{integration_id}")
async def update_integration(
    integration_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    integration = await db.get(AutomationIntegration, integration_id)
    if integration is None or integration.organization_id != org.id:
        raise _not_found("Integration")
    await automation_integration_service.update(db, integration, payload)
    await db.commit()
    return {"id": integration.id, "enabled": integration.enabled,
            "status": integration.status}


@router.delete("/integrations/{integration_id}")
async def delete_integration(
    integration_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    integration = await db.get(AutomationIntegration, integration_id)
    if integration is None or integration.organization_id != org.id:
        raise _not_found("Integration")
    await automation_integration_service.delete(db, integration)
    await db.commit()
    return {"ok": True}


@router.post("/integrations/{integration_id}/sync")
async def sync_integration(
    integration_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    integration = await db.get(AutomationIntegration, integration_id)
    if integration is None or integration.organization_id != org.id:
        raise _not_found("Integration")
    result = await automation_integration_service.trigger_sync(
        db, organization_id=org.id, integration_name=integration.name
    )
    await db.commit()
    return result


# ------------------------------------------------------------------ analytics

@router.get("/analytics/dashboard")
async def analytics_dashboard(
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workflow_analytics.dashboard(db, organization_id=org.id)


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = Query(30, ge=1, le=365),
    workflow_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workflow_analytics.trends(
        db, organization_id=org.id, days=days, workflow_id=workflow_id
    )


@router.get("/analytics/metrics")
async def analytics_metrics(
    metric_type: Optional[str] = None,
    limit: int = Query(60, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workflow_analytics.metrics(
        db, organization_id=org.id, metric_type=metric_type, limit=limit
    )


# -------------------------------------------------------------------- AI

@router.post("/ai/generate")
async def ai_generate(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    prompt = payload.get("prompt", "")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    try:
        result = await ai_workflow_service.generate(
            db, organization_id=org.id, prompt=prompt,
            name=payload.get("name") or "AI-generated workflow",
            category=payload.get("category", "general"),
            created_by=user.id, persist=payload.get("persist", True),
        )
        await db.commit()
        return result
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ai/rules/suggest")
async def ai_suggest_rule(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:manage")),
    db: AsyncSession = Depends(get_db),
):
    return await ai_workflow_service.suggest_rule(
        db, organization_id=org.id, prompt=payload.get("prompt", "")
    )


@router.get("/ai/explain/{workflow_id}")
async def ai_explain(
    workflow_id: str,
    org: Organization = Depends(get_current_organization),
    _user: User = Depends(require_permission("automation:read")),
    db: AsyncSession = Depends(get_db),
):
    return await ai_workflow_service.explain(db, workflow_id=workflow_id, organization_id=org.id)


# ------------------------------------------------------------------- webhook

@router.post("/webhooks/{workflow_id}")
async def webhook_trigger(
    workflow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Unauthenticated webhook entry: guarded by the workflow's token."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - tolerate non-JSON webhooks
        payload = {}
    token = payload.get("token")
    workflow = await db.get(Workflow, workflow_id)
    if workflow is None or workflow.organization_id is None:
        raise _not_found("Workflow")
    config = workflow.trigger_config or {}
    if config.get("token") and config.get("token") != token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    try:
        detail = await trigger_engine.run_webhook(
            db, organization_id=workflow.organization_id, workflow_id=workflow.id,
            payload=payload,
        )
        await db.commit()
        return {"ok": True, "execution_id": detail["id"], "status": detail["status"]}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
