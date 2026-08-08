"""Workflow execution engine (Phase 14) — walks the node graph.

Each run creates a WorkflowExecution plus one step per node. The engine
advances the graph one pass at a time: routing nodes (condition, ai_decision)
choose branches, blocking nodes (approval, delay, parallel_join) park the
execution in `waiting`, and action nodes execute through the ActionExecutor.
Failures are retried (per-node max_retries) by the retry worker; stale
executions are resumed by the workflow worker (crash recovery).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.action_service import action_executor
from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import event_bus
from app.models.workflow import (
    Workflow,
    WorkflowAction,
    WorkflowApproval,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowExecutionStep,
    WorkflowLog,
    WorkflowNode,
)

logger = logging.getLogger("vcos.automation.execution")

BLOCKING_STATUSES = {"pending", "running", "blocked", "waiting_approval", "waiting_delay"}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class ExecutionEngine:
    """Graph interpreter for workflow executions."""

    async def start(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        workflow_id: str,
        trigger_source: str = "manual",
        trigger_event: Optional[str] = None,
        triggered_by: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> WorkflowExecution:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        if workflow.status != "active":
            raise ValueError(f"Workflow is {workflow.status}, not active")

        now = utcnow()
        execution = WorkflowExecution(
            organization_id=organization_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status="running",
            trigger_source=trigger_source,
            trigger_event=trigger_event,
            triggered_by=triggered_by,
            context={
                "trigger": dict(context or {}),
                "trigger_source": trigger_source,
                "trigger_event": trigger_event,
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
            },
            started_at=now,
        )
        db.add(execution)
        await db.flush()

        nodes = (
            await db.execute(
                select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id)
            )
        ).scalars().all()
        for node in nodes:
            db.add(
                WorkflowExecutionStep(
                    execution_id=execution.id,
                    node_key=node.node_key,
                    node_type=node.node_type,
                    node_name=node.name,
                    status="pending",
                    input_data=dict(node.config or {}),
                )
            )
        workflow.run_count += 1
        workflow.last_run_at = now
        await db.flush()

        await event_bus.publish(
            db, name="workflow.started", organization_id=organization_id,
            actor_id=triggered_by,
            payload={"workflow_id": workflow.id, "workflow_name": workflow.name,
                     "execution_id": execution.id, "trigger_source": trigger_source},
        )
        await self.advance(db, execution)
        return execution

    # ------------------------------------------------------------------ graph

    async def _load_graph(
        self, db: AsyncSession, workflow_id: str, execution_id: str
    ) -> tuple[dict[str, WorkflowNode], dict[str, list[WorkflowEdge]], dict[str, WorkflowExecutionStep]]:
        nodes = {
            node.node_key: node
            for node in (
                await db.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id))
            ).scalars().all()
        }
        edges_by_source: dict[str, list[WorkflowEdge]] = {}
        for edge in (
            await db.execute(select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow_id))
        ).scalars().all():
            edges_by_source.setdefault(edge.source_key, []).append(edge)
        steps = {
            step.node_key: step
            for step in (
                await db.execute(
                    select(WorkflowExecutionStep).where(
                        WorkflowExecutionStep.execution_id == execution_id
                    )
                )
            ).scalars().all()
        }
        return nodes, edges_by_source, steps

    async def _load_actions(
        self, db: AsyncSession, workflow_id: str
    ) -> dict[str, WorkflowAction]:
        return {
            action.node_key: action
            for action in (
                await db.execute(
                    select(WorkflowAction).where(WorkflowAction.workflow_id == workflow_id)
                )
            ).scalars().all()
        }

    async def advance(self, db: AsyncSession, execution: WorkflowExecution) -> None:
        """Walk the graph from the entry nodes, one worklist pass."""
        if execution.status in ("completed", "failed", "cancelled", "timed_out"):
            return
        nodes, edges_by_source, steps = await self._load_graph(
            db, execution.workflow_id, execution.id
        )
        if not nodes:
            await self._finish(db, execution, "failed", error="Workflow has no nodes")
            return
        actions = await self._load_actions(db, execution.workflow_id)
        context = dict(execution.context or {})

        entry_keys = [
            key for key, node in nodes.items()
            if not any(edge.target_key == key for edges in edges_by_source.values() for edge in edges)
        ]
        if not entry_keys:
            entry_keys = [key for key, node in nodes.items() if node.node_type in ("start", "trigger")]
        if not entry_keys:
            await self._finish(db, execution, "failed", error="Workflow has no entry node")
            return

        resume_key = execution.current_node_key if execution.status == "waiting" else None
        worklist = (
            [resume_key] if resume_key and steps.get(resume_key)
            else [key for key in entry_keys if steps.get(key)]
        )
        execution.current_node_key = None
        visited: set[str] = set()
        guard = 0
        max_nodes = max(200, len(nodes) * 4)
        while worklist and guard < max_nodes:
            guard += 1
            key = worklist.pop(0)
            node = nodes.get(key)
            if node is None or key in visited:
                continue
            step = steps.get(key)
            if step is None:
                continue
            if step.status == "succeeded":
                visited.add(key)
                for edge in edges_by_source.get(key, []):
                    if await self._edge_matches(db, execution, edge, step):
                        worklist.append(edge.target_key)
                continue
            visited.add(key)

            outcome = await self._run_node(
                db, execution, node, step, actions, context,
                edges_by_source.get(key, []), steps,
            )
            if outcome == "wait":
                execution.status = "waiting"
                execution.current_node_key = key
                await db.flush()
                return
            if outcome == "failed":
                await self._finish(
                    db, execution, "failed",
                    error=f"Step {node.name or key} failed: {step.error or 'unknown error'}",
                )
                return
            if outcome == "blocked_join":
                execution.status = "waiting"
                execution.current_node_key = key
                step.status = "blocked"
                await db.flush()
                return

            for edge in edges_by_source.get(key, []):
                if await self._edge_matches(db, execution, edge, step):
                    worklist.append(edge.target_key)

        pending = [
            s for s in steps.values()
            if s.status in BLOCKING_STATUSES and s.node_key not in visited
        ]
        for step in pending:
            step.status = "skipped"  # unreached branch
        await self._finish(db, execution, "completed")

    # ------------------------------------------------------------- node run

    async def _run_node(
        self, db, execution, node, step, actions, context, out_edges, steps,
    ) -> str:
        now = utcnow()
        step.status = "running"
        step.started_at = now
        await db.flush()
        node_type = node.node_type
        config = node.config or {}

        try:
            if node_type in ("start", "trigger", "end"):
                result: dict[str, Any] = {}
                if node_type == "end":
                    result = {"result": "completed"}
            elif node_type == "condition":
                result = {"result": await self._eval_condition(config, context)}
            elif node_type == "ai_decision":
                from app.automation.ai_workflow_service import ai_workflow_service

                result = {
                    "result": await ai_workflow_service.decide(
                        db, organization_id=execution.organization_id,
                        prompt=config.get("prompt", ""), context=context,
                    )
                }
            elif node_type == "delay":
                seconds = max(0, int(config.get("seconds", 0)))
                if execution.resume_at is not None and ensure_aware(execution.resume_at) <= now:
                    step.output_data = {"result": "delay_done", "seconds": seconds}
                    step.status = "succeeded"
                    step.finished_at = now
                    execution.resume_at = None
                    await db.flush()
                    return "ok"
                step.status = "waiting_delay"
                execution.resume_at = now + timedelta(seconds=seconds)
                step.output_data = {"result": "delay", "seconds": seconds,
                                    "resume_at": _iso(execution.resume_at)}
                await db.flush()
                return "wait"
            elif node_type == "approval":
                return await self._run_approval(db, execution, node, step, config)
            elif node_type == "parallel_split":
                result = {"result": "split"}
            elif node_type == "parallel_join":
                inbound = (
                    await db.execute(
                        select(WorkflowEdge).where(
                            WorkflowEdge.workflow_id == execution.workflow_id,
                            WorkflowEdge.target_key == node.node_key,
                        )
                    )
                ).scalars().all()
                sources = {edge.source_key for edge in inbound}
                siblings = [
                    s for k, s in steps.items() if k in sources
                ]
                if any(s.status in BLOCKING_STATUSES for s in siblings):
                    return "blocked_join"
                result = {"result": "joined"}
            elif node_type == "script":
                computed = config.get("compute") or {}
                for key, value in computed.items():
                    context[key] = value
                result = {"result": "executed", "computed": list(computed.keys())}
            elif node_type in ("task", "meeting", "project", "notification",
                               "approval_action", "onboarding", "integration",
                               "webhook", "ai_summarize"):
                action = actions.get(node.node_key)
                if action is None or not action.enabled:
                    raise ValueError(f"no enabled action configured for node {node.node_key}")
                result = await action_executor.execute(
                    db,
                    organization_id=execution.organization_id,
                    action=action,
                    context={**context, "execution_id": execution.id,
                             "node_key": node.node_key, "workflow_id": execution.workflow_id},
                    actor_id=execution.triggered_by,
                )
            else:
                result = {"result": "executed", "node_type": node_type}

            step.status = "succeeded"
            step.output_data = result
            step.finished_at = now
            for key, value in (result or {}).items():
                if key != "result":
                    context[key] = value
            execution.context = context
            await db.flush()
            return "ok"
        except Exception as exc:  # noqa: BLE001 - retry semantics
            step.attempts += 1
            step.error = str(exc)[:2000]
            max_retries = max(0, int(config.get("max_retries", 0)))
            if step.attempts > max_retries:
                step.status = "failed"
                step.finished_at = now
                await db.flush()
                return "failed"
            step.status = "pending"
            step.finished_at = now
            await db.flush()
            logger.warning("step %s attempt %s failed, will retry: %s",
                           node.node_key, step.attempts, exc)
            return "wait"

    async def _run_approval(self, db, execution, node, step, config) -> str:
        from app.services.notification_service import notification_service

        approver_user_id = config.get("approver_user_id") or config.get("approver_ref")
        approver_role = config.get("approver_role")
        title = config.get("title") or node.name or "Approval required"
        approval = WorkflowApproval(
            organization_id=execution.organization_id,
            workflow_id=execution.workflow_id,
            execution_id=execution.id,
            node_key=node.node_key,
            title=title,
            description=config.get("description"),
            status="pending",
            approver_type="role" if approver_role and not approver_user_id else "user",
            approver_user_id=approver_user_id,
            approver_role=approver_role,
            requested_by=execution.triggered_by,
            due_at=utcnow() + timedelta(hours=int(config.get("due_hours", 24))),
            entity_type="workflow_execution",
            entity_id=execution.id,
        )
        db.add(approval)
        await db.flush()
        step.status = "waiting_approval"
        step.output_data = {"result": "pending", "approval_id": approval.id,
                            "title": title}
        await db.flush()

        recipient = approver_user_id
        if not recipient and config.get("approver_role"):
            recipient = None  # role-based: notified by approval worker scan
        if recipient:
            await notification_service.create(
                db,
                organization_id=execution.organization_id,
                recipient_id=recipient,
                type="automation",
                title=f"Workflow approval: {title}",
                body=config.get("description"),
                actor_id=execution.triggered_by,
                priority="high",
                link=f"/automation?tab=approvals",
                entity_type="workflow_approval",
                entity_id=approval.id,
            )
        await event_bus.publish(
            db, name="workflow.approval_requested", organization_id=execution.organization_id,
            payload={"approval_id": approval.id, "execution_id": execution.id,
                     "workflow_id": execution.workflow_id, "title": title},
        )
        return "wait"

    async def _eval_condition(self, config: dict[str, Any], context: dict[str, Any]) -> str:
        value = self._lookup(context, config.get("field"))
        operator = config.get("operator", "truthy")
        expected = config.get("value")
        if operator == "truthy":
            return "true" if value else "false"
        if operator == "falsy":
            return "true" if not value else "false"
        if operator == "eq":
            return "true" if value == expected else "false"
        if operator == "neq":
            return "true" if value != expected else "false"
        if operator in ("gt", "gte", "lt", "lte"):
            try:
                left, right = float(value), float(expected)
                return "true" if {
                    "gt": left > right, "gte": left >= right,
                    "lt": left < right, "lte": left <= right,
                }[operator] else "false"
            except (TypeError, ValueError):
                return "false"
        if operator == "contains":
            return "true" if expected and expected in str(value or "") else "false"
        if operator == "in":
            return "true" if value in (expected or []) else "false"
        if operator == "is_null":
            return "true" if value in (None, "", []) else "false"
        return "false"

    async def _edge_matches(self, db, execution, edge, step) -> bool:
        condition = edge.condition or {}
        if not condition:
            return True
        branch = condition.get("branch") or condition.get("value")
        if branch is not None:
            step_result = (step.output_data or {}).get("result")
            if isinstance(step_result, list):
                return branch in step_result
            return str(step_result) == str(branch)
        operator = condition.get("operator")
        if operator:
            check = dict(condition)
            check.pop("target", None)
            return await self._eval_condition(
                {**check, "field": check.get("field", ""), "operator": operator},
                dict(execution.context or {}),
            ) == "true"
        return True

    def _lookup(self, context: dict[str, Any], path: Optional[str]) -> Any:
        if not path:
            return None
        current: Any = context
        for part in str(path).split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    # ------------------------------------------------------------ lifecycle

    async def _finish(self, db, execution, status: str, *, error: Optional[str] = None) -> None:
        now = utcnow()
        execution.status = status
        execution.error = error
        execution.finished_at = now
        execution.current_node_key = None
        execution.resume_at = None
        if execution.started_at:
            execution.duration_ms = int(
                (now - ensure_aware(execution.started_at)).total_seconds() * 1000
            )
        await db.flush()
        await event_bus.publish(
            db, name=f"workflow.{status}", organization_id=execution.organization_id,
            actor_id=execution.triggered_by,
            payload={"workflow_id": execution.workflow_id,
                     "workflow_name": execution.workflow_name,
                     "execution_id": execution.id, "status": status, "error": error},
        )
        await self._log(db, execution, "error" if error else "info",
                        f"Execution {status}: {error or ''}".strip())

    async def cancel(self, db: AsyncSession, execution: WorkflowExecution, *, reason: str = "cancelled") -> None:
        if execution.status in ("completed", "failed", "cancelled", "timed_out"):
            return
        steps = (
            await db.execute(
                select(WorkflowExecutionStep).where(
                    WorkflowExecutionStep.execution_id == execution.id
                )
            )
        ).scalars().all()
        for step in steps:
            if step.status in BLOCKING_STATUSES:
                step.status = "skipped"
        approval_rows = (
            await db.execute(
                select(WorkflowApproval).where(
                    WorkflowApproval.execution_id == execution.id,
                    WorkflowApproval.status == "pending",
                )
            )
        ).scalars().all()
        for approval in approval_rows:
            approval.status = "cancelled"
            approval.comment = reason
            approval.decided_at = utcnow()
        await self._finish(db, execution, "cancelled")

    async def resume(self, db: AsyncSession, execution: WorkflowExecution) -> None:
        """Resume a waiting execution (approval decided, delay elapsed, join ready)."""
        if execution.status != "waiting":
            return
        if execution.resume_at and ensure_aware(execution.resume_at) > utcnow():
            return
        # re-open the blocking step so it can finish (delay) or be re-checked (join)
        if execution.current_node_key:
            step = (
                await db.execute(
                    select(WorkflowExecutionStep).where(
                        WorkflowExecutionStep.execution_id == execution.id,
                        WorkflowExecutionStep.node_key == execution.current_node_key,
                    )
                )
            ).scalar_one_or_none()
            if step is not None and step.status in ("waiting_delay", "blocked"):
                step.status = "pending"
                step.started_at = None
        execution.status = "running"
        await db.flush()
        await self.advance(db, execution)

    async def retry_failed_steps(self, db: AsyncSession, *, limit: int = 50,
                                 min_age_minutes: float = 0) -> int:
        """Reset failed steps so their executions can be re-run. The optional
        age guard prevents worker retry loops on hot failures."""
        cutoff = utcnow() - timedelta(minutes=min_age_minutes)
        steps = (
            await db.execute(
                select(WorkflowExecutionStep)
                .where(WorkflowExecutionStep.status == "failed")
                .order_by(WorkflowExecutionStep.updated_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        reset = 0
        for step in steps:
            if min_age_minutes and (step.updated_at or utcnow()) > cutoff:
                continue
            execution = await db.get(WorkflowExecution, step.execution_id)
            if execution is None or execution.status not in ("failed", "waiting", "running"):
                continue
            step.status = "pending"
            step.error = None
            step.started_at = None
            if execution.status == "failed":
                execution.status = "waiting"
                execution.error = None
                execution.finished_at = None
                execution.duration_ms = None
            reset += 1
        await db.flush()
        return reset

    async def resume_stale(self, db: AsyncSession, *, limit: int = 50) -> int:
        """Crash recovery: resume waiting executions whose delay elapsed, and
        re-open pending steps of executions that were interrupted mid-pass."""
        rows = (
            await db.execute(
                select(WorkflowExecution)
                .where(WorkflowExecution.status == "waiting")
                .order_by(WorkflowExecution.updated_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        resumed = 0
        for execution in rows:
            if execution.resume_at and ensure_aware(execution.resume_at) > utcnow():
                continue
            await self.resume(db, execution)
            resumed += 1
        return resumed

    async def timeout_stuck(self, db: AsyncSession, *, hours: float = 72) -> int:
        """Mark executions stuck in running for too long as timed_out."""
        cutoff = utcnow() - timedelta(hours=hours)
        rows = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.status == "running",
                    WorkflowExecution.started_at < cutoff,
                )
            )
        ).scalars().all()
        for execution in rows:
            await self._finish(db, execution, "timed_out", error="Execution timed out")
        return len(rows)

    async def _log(self, db, execution, level: str, message: str) -> None:
        db.add(
            WorkflowLog(
                organization_id=execution.organization_id,
                workflow_id=execution.workflow_id,
                execution_id=execution.id,
                level=level,
                message=message[:2000],
                data={"status": execution.status},
            )
        )
        await db.flush()

    # ------------------------------------------------------------- queries

    async def execution_detail(self, db: AsyncSession, execution: WorkflowExecution) -> dict[str, Any]:
        steps = (
            await db.execute(
                select(WorkflowExecutionStep)
                .where(WorkflowExecutionStep.execution_id == execution.id)
                .order_by(WorkflowExecutionStep.created_at.asc())
            )
        ).scalars().all()
        approvals = (
            await db.execute(
                select(WorkflowApproval).where(WorkflowApproval.execution_id == execution.id)
            )
        ).scalars().all()
        return {
            "id": execution.id,
            "workflow_id": execution.workflow_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "trigger_source": execution.trigger_source,
            "trigger_event": execution.trigger_event,
            "triggered_by": execution.triggered_by,
            "context": execution.context,
            "current_node_key": execution.current_node_key,
            "resume_at": _iso(execution.resume_at),
            "started_at": _iso(execution.started_at),
            "finished_at": _iso(execution.finished_at),
            "duration_ms": execution.duration_ms,
            "error": execution.error,
            "steps": [
                {
                    "node_key": s.node_key,
                    "node_type": s.node_type,
                    "node_name": s.node_name,
                    "status": s.status,
                    "input": s.input_data,
                    "output": s.output_data,
                    "error": s.error,
                    "attempts": s.attempts,
                    "started_at": _iso(s.started_at),
                    "finished_at": _iso(s.finished_at),
                }
                for s in steps
            ],
            "approvals": [
                {
                    "id": a.id,
                    "node_key": a.node_key,
                    "title": a.title,
                    "status": a.status,
                    "approver_user_id": a.approver_user_id,
                    "approver_role": a.approver_role,
                    "comment": a.comment,
                    "decided_at": _iso(a.decided_at),
                }
                for a in approvals
            ],
        }


execution_engine = ExecutionEngine()
