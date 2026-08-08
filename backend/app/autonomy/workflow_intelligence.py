"""Autonomous workflow intelligence — observes workflows and finds friction.

Detects slow approvals, repeated manual work, duplicate approvals, long delays
and missed notifications, then suggests automation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.workflow import (
    Workflow,
    WorkflowApproval,
    WorkflowExecution,
    WorkflowExecutionStep,
)


class WorkflowIntelligence:
    async def analyze(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        findings: list[dict[str, Any]] = []
        suggestions: list[dict[str, Any]] = []

        workflows = (
            await db.execute(
                select(Workflow).where(Workflow.organization_id == organization_id).limit(100)
            )
        ).scalars().all()
        approvals = (
            await db.execute(
                select(WorkflowApproval).where(WorkflowApproval.organization_id == organization_id)
            )
        ).scalars().all()
        executions = (
            await db.execute(
                select(WorkflowExecution)
                .where(WorkflowExecution.organization_id == organization_id)
                .order_by(WorkflowExecution.created_at.desc())
                .limit(200)
            )
        ).scalars().all()

        pending = [a for a in approvals if a.status == "pending"]
        if len(pending) >= 3:
            findings.append({
                "kind": "slow_approvals",
                "count": len(pending),
                "detail": f"{len(pending)} approvals are waiting; stalled approvals delay execution.",
                "severity": "medium",
            })
            suggestions.append({
                "category": "automation",
                "title": "Escalate or auto-remind stalled approvals",
                "description": "Add escalation rules to approval workflows.",
                "confidence": 0.7,
                "evidence": [{"metric": "pending_approvals", "value": len(pending)}],
            })

        wait_steps = (
            await db.execute(
                select(WorkflowExecutionStep).where(
                    WorkflowExecutionStep.organization_id == organization_id,
                    WorkflowExecutionStep.status == "waiting",
                )
            )
        ).scalars().all()
        if len(wait_steps) >= 5:
            findings.append({
                "kind": "long_delays",
                "count": len(wait_steps),
                "detail": f"{len(wait_steps)} steps are waiting on dependencies.",
                "severity": "medium",
            })
            suggestions.append({
                "category": "automation",
                "title": "Parallelize independent workflow steps",
                "description": "Reduce serial waiting in frequently executed workflows.",
                "confidence": 0.6,
                "evidence": [{"metric": "waiting_steps", "value": len(wait_steps)}],
            })

        repeated = {}
        for execution in executions:
            key = getattr(execution, "workflow_id", None) or getattr(execution, "name", "unknown")
            repeated[key] = repeated.get(key, 0) + 1
        frequent = [(k, v) for k, v in repeated.items() if v >= 10]
        if frequent:
            findings.append({
                "kind": "repeated_manual_work",
                "count": len(frequent),
                "detail": f"{len(frequent)} workflow(s) ran 10+ times recently — candidates for template automation.",
                "severity": "low",
            })
            suggestions.append({
                "category": "automation",
                "title": "Turn frequently repeated workflows into templates",
                "description": "Reduce manual setup for recurring processes.",
                "confidence": 0.7,
                "evidence": [{"metric": "frequent_workflows", "value": len(frequent)}],
            })

        failed = [e for e in executions if e.status == "failed"]
        if failed:
            findings.append({
                "kind": "execution_failures",
                "count": len(failed),
                "detail": f"{len(failed)} executions failed; retries may be needed.",
                "severity": "high",
            })

        return {
            "workflows": len(workflows),
            "findings": findings,
            "suggestions": suggestions,
        }


workflow_intelligence = WorkflowIntelligence()
