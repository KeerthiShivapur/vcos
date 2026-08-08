"""Workflow approval service (Phase 14) — approvals gate executions.

A decision (approve/reject/escalate) updates the approval row, feeds the
result back into the execution step and resumes the waiting execution so
the graph continues down the matching branch.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.execution_service import execution_engine
from app.core.timeutils import utcnow
from app.models.workflow import Workflow, WorkflowApproval, WorkflowExecution, WorkflowExecutionStep

logger = logging.getLogger("vcos.automation.approvals")


class WorkflowApprovalService:
    async def list(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, as_user: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(WorkflowApproval).where(WorkflowApproval.organization_id == organization_id)
        if status:
            query = query.where(WorkflowApproval.status == status)
        if as_user:
            query = query.where(WorkflowApproval.approver_user_id == as_user)
        rows = (
            await db.execute(query.order_by(WorkflowApproval.created_at.desc()).limit(limit))
        ).scalars().all()
        result = []
        for approval in rows:
            execution = (
                await db.get(WorkflowExecution, approval.execution_id)
                if approval.execution_id else None
            )
            result.append({
                "id": approval.id,
                "workflow_id": approval.workflow_id,
                "workflow_name": (
                    (await db.get(Workflow, approval.workflow_id)).name
                    if approval.workflow_id and await db.get(Workflow, approval.workflow_id) else None
                ),
                "execution_id": approval.execution_id,
                "execution_status": execution.status if execution else None,
                "node_key": approval.node_key,
                "title": approval.title,
                "description": approval.description,
                "status": approval.status,
                "approver_type": approval.approver_type,
                "approver_user_id": approval.approver_user_id,
                "approver_role": approval.approver_role,
                "requested_by": approval.requested_by,
                "decided_by": approval.decided_by,
                "comment": approval.comment,
                "due_at": approval.due_at.isoformat() if approval.due_at else None,
                "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
                "escalation_level": approval.escalation_level,
                "created_at": approval.created_at.isoformat() if approval.created_at else None,
            })
        return result

    async def decide(
        self, db: AsyncSession, approval: WorkflowApproval, *, decision: str,
        decided_by: Optional[str] = None, comment: Optional[str] = None,
    ) -> WorkflowApproval:
        if approval.status != "pending":
            raise ValueError(f"Approval already decided: {approval.status}")
        if decision not in ("approved", "rejected", "escalated"):
            raise ValueError(f"Invalid decision: {decision}")
        approval.status = decision
        approval.decided_by = decided_by
        approval.comment = comment
        approval.decided_at = utcnow()
        if decision == "escalated":
            approval.escalation_level += 1
        await db.flush()

        execution = await db.get(WorkflowExecution, approval.execution_id) if approval.execution_id else None
        if execution is not None and execution.status == "waiting":
            step = (
                await db.execute(
                    select(WorkflowExecutionStep).where(
                        WorkflowExecutionStep.execution_id == execution.id,
                        WorkflowExecutionStep.node_key == approval.node_key,
                    )
                )
            ).scalar_one_or_none()
            if step is not None:
                step.status = "succeeded"
                step.output_data = {"result": decision, "approval_id": approval.id,
                                    "decided_by": decided_by, "comment": comment}
                step.finished_at = utcnow()
            execution.context = dict(execution.context or {})
            execution.context["approval_result"] = decision
            await db.flush()
            await execution_engine.resume(db, execution)
        await db.flush()
        return approval

    async def escalate_due(self, db: AsyncSession, *, hours: float = 24, limit: int = 50) -> int:
        """Auto-escalate pending approvals past their due date (approval worker)."""
        from datetime import timedelta

        cutoff = utcnow() - timedelta(hours=hours)
        rows = (
            await db.execute(
                select(WorkflowApproval)
                .where(
                    WorkflowApproval.status == "pending",
                    WorkflowApproval.due_at.isnot(None),
                    WorkflowApproval.due_at < cutoff,
                )
                .order_by(WorkflowApproval.due_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        escalated = 0
        for approval in rows:
            approval.escalation_level += 1
            approval.due_at = (approval.due_at or utcnow()) + timedelta(hours=hours * (approval.escalation_level))
            await db.flush()
            escalated += 1
        return escalated


workflow_approval_service = WorkflowApprovalService()
