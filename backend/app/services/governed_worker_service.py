"""Governed AI Worker service (Slice 4).

Runs AI-assisted work through the canonical operation spine:

- every task is a CanonicalOperation (exact-once fingerprint, attempts,
  checkpoints, UNKNOWN semantics) — no parallel task system;
- context is retrieved from canonical services under the caller's tenant,
  and retrieval failures are surfaced, never hidden;
- model output is untrusted until strictly validated; malformed output is a
  failure, not a silent downgrade;
- observed facts, model claims, inferences, uncertainties and proposals are
  stored separately — epistemic provenance is never blended;
- consequential actions never execute from the analysis itself: a
  recommendation creates a proposed Decision + a pending Approval + a
  queued child action operation that executes only after the approval is
  revalidated at the execution boundary.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ai_gateway
from app.ai.provider import ChatMessage
from app.core.timeutils import utcnow
from app.intelligence.company_operating_engine import company_operating_engine
from app.knowledge.decision_service import decision_service
from app.models.approval import Approval
from app.models.canonical_reliability import CanonicalOperation
from app.models.employee import Employee
from app.schemas.governed_worker import WorkerModelOutput, WorkerTaskCreate
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.event_service import event_service
from app.work.approval_service import approval_service
from app.work.project_service import project_service
from app.work.risk_service import risk_service
from app.work.task_service import task_service

logger = logging.getLogger(__name__)

TASK_OPERATION_TYPE = "governed_worker.task"
ACTION_OPERATION_TYPE = "governed_worker.action"

MODEL_TIMEOUT_SECONDS = 60
MAX_CONTEXT_ITEMS = 25
_RUNNABLE_STATES = ("queued", "retrying")
_CANCELLABLE_STATES = ("queued", "attempting", "retrying", "unknown")

SYSTEM_PROMPT = (
    "You are a governed company analyst inside VCOS. You produce strictly valid JSON only.\n"
    "Rules:\n"
    "- Facts may only come from the provided authorized_context; never invent facts, ids, "
    "names, numbers or events.\n"
    "- Put facts you found in the context into observed_facts, each grounded by an evidence "
    "entry {claim, source, source_ref}.\n"
    "- Put interpretations in inferences; put anything uncertain in uncertainties; never "
    "present an inference as a fact.\n"
    "- Recommendations are proposals only: the company requires human authorization before "
    "any consequential action. Set requires_approval=true for every proposed action.\n"
    "- Return exactly this JSON shape and nothing else:\n"
    '{"summary": "...", "observed_facts": ["..."], '
    '"evidence": [{"claim": "...", "source": "...", "source_ref": "..."}], '
    '"inferences": ["..."], "uncertainties": ["..."], "recommendations": ["..."], '
    '"proposed_actions": [{"action_type": "create_task", "title": "...", '
    '"description": "...", "requires_approval": true}]}'
)


class WorkerError(Exception):
    """Base governed-worker error surfaced as an HTTP 4xx."""


class WorkerNotFound(WorkerError):
    pass


class WorkerNotRunnable(WorkerError):
    pass


class WorkerNotExecutable(WorkerError):
    pass


class GovernedWorkerService:
    # ------------------------------------------------------------------ create

    async def create_task(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: WorkerTaskCreate,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> CanonicalOperation:
        if data.scope_type == "project":
            if not data.scope_id:
                raise WorkerError("scope_id is required when scope_type is 'project'")
            project = await project_service.get(
                db, organization_id=organization_id, project_id=data.scope_id
            )
            if project is None:
                raise WorkerError("scope project not found")

        key_fields: dict[str, Any] = {
            "task_kind": data.task_kind,
            "scope_type": data.scope_type,
            "scope_id": data.scope_id or "",
            "idempotency_key": data.idempotency_key or f"nonce:{utcnow().isoformat()}",
        }
        operation = await canonical_reliability_service.create_operation(
            db,
            organization_id=organization_id,
            operation_type=TASK_OPERATION_TYPE,
            title=data.title,
            description=data.instruction,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            actor_id=actor.id if actor else None,
            actor_type="agent",
            is_external=False,
            max_attempts=1,
            key_fields=key_fields,
        )
        if operation.payload is None:
            operation.payload = {
                "task_kind": data.task_kind,
                "instruction": data.instruction,
                "requested_by": actor.id if actor else None,
                "idempotency_key": data.idempotency_key,
            }
            await db.flush()

        await self._emit(
            db,
            "governed_worker.task.created",
            organization_id,
            actor,
            {
                "operation_id": operation.id,
                "task_kind": data.task_kind,
                "scope_type": data.scope_type,
                "scope_id": data.scope_id,
            },
        )
        await self._audit(
            db,
            organization_id=organization_id,
            action="governed_worker.task.created",
            actor=actor,
            ip_address=ip_address,
            resource_id=operation.id,
            details={"task_kind": data.task_kind, "scope_type": data.scope_type},
        )
        return operation

    # -------------------------------------------------------------------- run

    async def run_task(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_id: str,
        actor: Optional[Employee] = None,
    ) -> CanonicalOperation:
        operation = await self._get_operation(
            db,
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type=TASK_OPERATION_TYPE,
        )
        if operation.state not in _RUNNABLE_STATES:
            raise WorkerNotRunnable(
                f"Task is not runnable in state '{operation.state}'"
            )

        payload = operation.payload or {}
        task_kind = payload.get("task_kind", "research")
        instruction = payload.get("instruction") or operation.description or ""

        attempt = await canonical_reliability_service.start_attempt(
            db,
            operation,
            worker_id=f"governed-worker:{actor.id if actor else 'system'}",
        )

        # Stage 1 — authorized context retrieval (facts from canonical services).
        try:
            context = await self._retrieve_context(
                db, organization_id=organization_id, operation=operation
            )
        except Exception as exc:
            logger.warning("Governed worker context retrieval failed: %s", exc)
            await canonical_reliability_service.complete_attempt(
                db, operation, attempt, outcome="failure",
                error=f"context_retrieval_failed: {exc}",
            )
            await self._emit(
                db, "governed_worker.task.failed", organization_id, actor,
                {"operation_id": operation.id, "stage": "context_retrieval"},
            )
            return operation

        await self._emit(
            db,
            "governed_worker.context.retrieved",
            organization_id,
            actor,
            {
                "operation_id": operation.id,
                "sources": [
                    {"source": s["source"], "status": s["status"], "count": s["count"]}
                    for s in context["sections"]
                ],
            },
        )

        # Stage 2 — model invocation through the existing AI gateway.
        try:
            model_state = await self._invoke_model(
                instruction=instruction, task_kind=task_kind, context=context
            )
        except Exception as exc:
            logger.warning("Governed worker model invocation failed: %s", exc)
            await canonical_reliability_service.complete_attempt(
                db, operation, attempt, outcome="failure",
                error=f"model_invocation_failed: {exc}",
            )
            await self._emit(
                db, "governed_worker.task.failed", organization_id, actor,
                {"operation_id": operation.id, "stage": "model_invocation"},
            )
            return operation

        model_meta: dict[str, Any] = {
            "provider": model_state["provider"],
            "model": model_state["model"],
            "available": model_state["available"],
            "assisted": False,
            "validation_errors": [],
        }
        structured: Optional[dict] = None
        if model_state["available"]:
            structured, errors = self._validate_model_output(model_state["content"])
            model_meta["validation_errors"] = errors
            if structured is None:
                # Untrusted output is never persisted as a result.
                await canonical_reliability_service.complete_attempt(
                    db, operation, attempt, outcome="failure",
                    error=f"model_output_invalid: {'; '.join(errors)[:500]}",
                )
                await self._emit(
                    db, "governed_worker.task.failed", organization_id, actor,
                    {"operation_id": operation.id, "stage": "output_validation",
                     "errors": errors},
                )
                return operation
            model_meta["assisted"] = True

        result = self._build_result(task_kind, instruction, context, structured, model_meta)

        # Stage 3 — governance persistence (proposal + approval + child action).
        if task_kind == "recommendation":
            try:
                await self._persist_recommendation_governance(
                    db, organization_id=organization_id, operation=operation,
                    result=result, actor=actor,
                )
            except Exception as exc:
                logger.warning("Governed worker governance persistence failed: %s", exc)
                await canonical_reliability_service.complete_attempt(
                    db, operation, attempt, outcome="failure",
                    error=f"governance_persistence_failed: {exc}",
                )
                await self._emit(
                    db, "governed_worker.task.failed", organization_id, actor,
                    {"operation_id": operation.id, "stage": "governance_persistence"},
                )
                return operation

        result["completed_at"] = utcnow().isoformat()
        await canonical_reliability_service.complete_attempt(
            db, operation, attempt, outcome="success", result_json=result
        )
        await self._emit(
            db, "governed_worker.task.completed", organization_id, actor,
            {"operation_id": operation.id, "task_kind": task_kind,
             "model_assisted": model_meta["assisted"],
             "approval_id": (result.get("approval") or {}).get("id")},
        )
        return operation

    # ---------------------------------------------------------------- action

    async def execute_action(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_id: str,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> CanonicalOperation:
        operation = await self._get_operation(
            db,
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type=ACTION_OPERATION_TYPE,
        )
        if operation.state != "queued":
            raise WorkerNotExecutable(
                f"Action is not executable in state '{operation.state}'"
            )

        approval: Optional[Approval] = None
        if operation.authorization_id:
            approval = await approval_service.get(
                db, organization_id=organization_id,
                approval_id=operation.authorization_id,
            )
        if approval is None or approval.status != "approved":
            # Revalidation at the execution boundary: revoked or missing
            # authorization must stop execution.
            raise WorkerNotExecutable(
                "Authorization not granted: the linked approval is missing or not approved"
            )

        attempt = await canonical_reliability_service.start_attempt(
            db,
            operation,
            worker_id=f"governed-worker:{actor.id if actor else 'system'}",
        )
        action = (operation.payload or {}).get("action") or {}
        try:
            task = await task_service.create(
                db,
                organization_id=organization_id,
                data={
                    "title": (action.get("title") or operation.title)[:300],
                    "description": action.get("description") or (
                        f"Authorized action from governed worker approval {approval.id}."
                    ),
                    "status": "backlog",
                    "priority": "medium",
                    "project_id": (
                        operation.scope_id
                        if operation.scope_type == "project" else None
                    ),
                    "decision_id": operation.decision_id,
                    "reporter_id": actor.id if actor else None,
                    "tags": ["governed-worker", "authorized-action"],
                },
                actor=actor,
                ip_address=ip_address,
            )
        except Exception as exc:
            logger.warning("Governed worker action execution failed: %s", exc)
            await canonical_reliability_service.complete_attempt(
                db, operation, attempt, outcome="failure",
                error=f"action_execution_failed: {exc}",
            )
            await self._emit(
                db, "governed_worker.execution.failed", organization_id, actor,
                {"operation_id": operation.id, "approval_id": approval.id},
            )
            return operation

        result = {
            "action": "task_created",
            "task_id": task.id,
            "task_title": task.title,
            "approval_id": approval.id,
            "executed_by": actor.id if actor else None,
            "executed_at": utcnow().isoformat(),
        }
        await canonical_reliability_service.complete_attempt(
            db, operation, attempt, outcome="success", result_json=result
        )
        await self._emit(
            db, "governed_worker.execution.completed", organization_id, actor,
            {"operation_id": operation.id, "task_id": task.id,
             "approval_id": approval.id},
        )
        await self._audit(
            db,
            organization_id=organization_id,
            action="governed_worker.execution.completed",
            actor=actor,
            ip_address=ip_address,
            resource_id=operation.id,
            details={"task_id": task.id, "approval_id": approval.id},
            resource_type="governed_worker_action",
        )
        return operation

    # ---------------------------------------------------------------- cancel

    async def cancel_task(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_id: str,
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> CanonicalOperation:
        operation = await self._get_operation(
            db,
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type=TASK_OPERATION_TYPE,
        )
        if operation.state not in _CANCELLABLE_STATES:
            raise WorkerNotRunnable(
                f"Task cannot be cancelled in state '{operation.state}'"
            )
        operation.state = "cancelled"
        operation.outcome = "cancelled"
        operation.completed_at = utcnow()

        # Cancel any child action operation and its pending approval.
        child = await self._find_child_action(
            db, organization_id=organization_id, parent_operation_id=operation.id
        )
        if child is not None and child.state in ("queued",):
            child.state = "cancelled"
            child.outcome = "cancelled"
            child.completed_at = utcnow()
            if child.authorization_id:
                approval = await approval_service.get(
                    db, organization_id=organization_id,
                    approval_id=child.authorization_id,
                )
                if approval is not None and approval.status == "pending":
                    approval.status = "cancelled"
                    await db.flush()

        await self._emit(
            db, "governed_worker.task.cancelled", organization_id, actor,
            {"operation_id": operation.id},
        )
        await self._audit(
            db,
            organization_id=organization_id,
            action="governed_worker.task.cancelled",
            actor=actor,
            ip_address=ip_address,
            resource_id=operation.id,
            details={},
        )
        return operation

    # ------------------------------------------------------------------ views

    async def list_tasks(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50
    ) -> list[dict]:
        rows = (
            await db.execute(
                select(CanonicalOperation)
                .where(
                    CanonicalOperation.organization_id == organization_id,
                    CanonicalOperation.operation_type == TASK_OPERATION_TYPE,
                )
                .order_by(desc(CanonicalOperation.created_at))
                .limit(limit)
            )
        ).scalars().all()
        return await self._build_views(db, organization_id=organization_id, tasks=list(rows))

    async def get_task_detail(
        self, db: AsyncSession, *, organization_id: str, operation_id: str
    ) -> dict:
        operation = await self._get_operation(
            db,
            organization_id=organization_id,
            operation_id=operation_id,
            operation_type=TASK_OPERATION_TYPE,
        )
        views = await self._build_views(db, organization_id=organization_id, tasks=[operation])
        detail = views[0]
        detail["result"] = operation.result_json
        child = await self._find_child_action(
            db, organization_id=organization_id, parent_operation_id=operation.id
        )
        detail["action_result"] = child.result_json if child is not None else None
        detail["error"] = operation.error
        return detail

    async def _build_views(
        self, db: AsyncSession, *, organization_id: str, tasks: list[CanonicalOperation]
    ) -> list[dict]:
        task_ids = {t.id for t in tasks}
        actions: dict[str, CanonicalOperation] = {}
        if task_ids:
            action_rows = (
                await db.execute(
                    select(CanonicalOperation)
                    .where(
                        CanonicalOperation.organization_id == organization_id,
                        CanonicalOperation.operation_type == ACTION_OPERATION_TYPE,
                    )
                    .order_by(desc(CanonicalOperation.created_at))
                    .limit(500)
                )
            ).scalars().all()
            for op in action_rows:
                parent = (op.payload or {}).get("parent_operation_id")
                if parent in task_ids and parent not in actions:
                    actions[parent] = op

        approval_ids = {
            op.authorization_id for op in actions.values() if op.authorization_id
        }
        approvals: dict[str, Approval] = {}
        if approval_ids:
            rows = (
                await db.execute(
                    select(Approval).where(
                        Approval.organization_id == organization_id,
                        Approval.id.in_(approval_ids),
                    )
                )
            ).scalars().all()
            approvals = {a.id: a for a in rows}

        return [
            self._task_view(task, actions.get(task.id), approvals)
            for task in tasks
        ]

    def _task_view(
        self,
        task: CanonicalOperation,
        action_op: Optional[CanonicalOperation],
        approvals: dict[str, Approval],
    ) -> dict:
        payload = task.payload or {}
        result = task.result_json or {}
        approval_view = None
        if action_op is not None and action_op.authorization_id:
            approval = approvals.get(action_op.authorization_id)
            if approval is not None:
                approval_view = {
                    "id": approval.id,
                    "status": approval.status,
                    "title": approval.title,
                }
        return {
            "id": task.id,
            "title": task.title,
            "instruction": payload.get("instruction") or task.description or "",
            "task_kind": payload.get("task_kind", "research"),
            "scope_type": task.scope_type,
            "scope_id": task.scope_id,
            "state": task.state,
            "phase": self._derive_phase(task, action_op, approval_view),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "summary": result.get("summary"),
            "model": result.get("model"),
            "approval": approval_view,
            "proposal_decision": result.get("proposal_decision"),
            "action_operation": (
                {
                    "id": action_op.id,
                    "state": action_op.state,
                    "title": action_op.title,
                }
                if action_op is not None else None
            ),
            "has_result": bool(task.result_json),
        }

    @staticmethod
    def _derive_phase(
        task: CanonicalOperation,
        action_op: Optional[CanonicalOperation],
        approval_view: Optional[dict],
    ) -> str:
        if task.state == "completed" and action_op is not None:
            if action_op.state == "completed":
                return "executed"
            if action_op.state == "cancelled":
                return "action_cancelled"
            if action_op.state == "failed":
                return "action_failed"
            status = (approval_view or {}).get("status")
            if status == "pending":
                return "awaiting_approval"
            if status == "approved":
                return "ready_to_execute"
            if status in ("rejected", "cancelled"):
                return "action_rejected"
            return "completed"
        return {
            "queued": "queued",
            "attempting": "running",
            "executing": "running",
            "retrying": "queued",
            "recovering": "recovering",
            "unknown": "unknown",
            "failed": "failed",
            "cancelled": "cancelled",
            "reconciled": "completed",
            "expired": "failed",
        }.get(task.state, task.state)

    # --------------------------------------------------------- context/model

    async def _retrieve_context(
        self, db: AsyncSession, *, organization_id: str, operation: CanonicalOperation
    ) -> dict:
        sections: list[dict] = []
        model_context: dict[str, Any] = {}
        observed: list[str] = []
        evidence: list[dict] = []

        if operation.scope_type == "project" and operation.scope_id:
            project = await project_service.get(
                db, organization_id=organization_id, project_id=operation.scope_id
            )
            if project is None:
                raise WorkerError("scope project not found")
            sections.append({"source": "projects", "status": "retrieved", "count": 1})
            model_context["project"] = {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "description": project.description,
            }
            observed.append(
                f"Project '{project.name}' is in status '{project.status}'."
            )
            evidence.append({
                "claim": f"Project '{project.name}' status is '{project.status}'",
                "source": "projects",
                "source_ref": project.id,
            })

            risks = await risk_service.list_all(
                db, organization_id=organization_id,
                project_id=operation.scope_id, limit=MAX_CONTEXT_ITEMS,
            )
            sections.append({"source": "risks", "status": "retrieved", "count": len(risks)})
            model_context["risks"] = [
                {"id": r.id, "title": r.title, "status": r.status,
                 "risk_score": r.risk_score, "severity": getattr(r, "severity", None)}
                for r in risks
            ]
            observed.append(f"{len(risks)} risks are registered for this project.")
            if risks:
                top = risks[0]
                observed.append(
                    f"Highest-scoring risk: '{top.title}' "
                    f"(score {top.risk_score}, status '{top.status}')."
                )
                evidence.append({
                    "claim": f"Top risk '{top.title}' has score {top.risk_score}",
                    "source": "risks",
                    "source_ref": top.id,
                })

            decisions = await decision_service.list_all(
                db, organization_id=organization_id,
                project_id=operation.scope_id, limit=10,
            )
            sections.append({"source": "decisions", "status": "retrieved", "count": len(decisions)})
            model_context["decisions"] = [
                {"id": d.id, "title": d.title, "status": d.status,
                 "created_at": str(d.created_at)}
                for d in decisions
            ]
            observed.append(f"{len(decisions)} decisions are recorded for this project.")

            tasks = await task_service.list_all(
                db, organization_id=organization_id,
                project_id=operation.scope_id, limit=MAX_CONTEXT_ITEMS,
            )
            open_tasks = [
                t for t in tasks
                if t.status not in ("done", "completed", "cancelled", "archived")
            ]
            sections.append({"source": "tasks", "status": "retrieved", "count": len(tasks)})
            model_context["open_tasks"] = [
                {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority}
                for t in open_tasks[:15]
            ]
            observed.append(f"{len(open_tasks)} of {len(tasks)} tasks are open.")
        else:
            state = await company_operating_engine.company_state(
                db, organization_id=organization_id
            )
            dimensions = state.get("dimensions") or {}
            attention = state.get("attention") or []
            sections.append(
                {"source": "company_state", "status": "retrieved", "count": len(dimensions)}
            )
            model_context["company_dimensions"] = {
                key: {"state": value.get("state"), "headline": value.get("headline")}
                for key, value in dimensions.items()
            }
            for key, value in dimensions.items():
                observed.append(
                    f"{value.get('label', key)}: {value.get('headline', '')} "
                    f"(state: {value.get('state')})"
                )
            model_context["attention"] = [
                {
                    "title": a.get("title") if isinstance(a, dict) else str(a),
                    "kind": (a.get("kind") or a.get("source")) if isinstance(a, dict) else None,
                    "severity": a.get("severity") if isinstance(a, dict) else None,
                }
                for a in attention[:10]
            ]
            for item in attention[:10]:
                title = item.get("title") if isinstance(item, dict) else str(item)
                if title:
                    observed.append(f"Attention item: {title}")
            evidence.append({
                "claim": "Company operating state retrieved from the canonical operating engine",
                "source": "company_operating_engine",
                "source_ref": organization_id,
            })

        return {
            "sections": sections,
            "observed_facts": observed,
            "evidence": evidence,
            "model_context": model_context,
        }

    async def _invoke_model(
        self, *, instruction: str, task_kind: str, context: dict
    ) -> dict:
        provider = ai_gateway.provider()
        if provider.name in ("local", "none"):
            # No external model configured: degrade honestly, never fabricate
            # reasoning. Retrieval still produced real canonical facts.
            return {
                "provider": provider.name,
                "model": None,
                "available": False,
                "content": "",
                "usage": None,
            }

        user_prompt = json.dumps(
            {
                "task_kind": task_kind,
                "instruction": instruction,
                "authorized_context": context["model_context"],
            },
            default=str,
        )
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_prompt),
        ]
        response = await asyncio.wait_for(
            ai_gateway.chat(messages), timeout=MODEL_TIMEOUT_SECONDS
        )
        content = (response.get("content") or "").strip()
        available = bool(response.get("available")) and bool(content)
        return {
            "provider": response.get("provider") or provider.name,
            "model": response.get("model"),
            "available": available,
            "content": content,
            "usage": response.get("usage"),
        }

    def _validate_model_output(self, content: str) -> tuple[Optional[dict], list[str]]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, [f"invalid_json: {exc.msg}"]
        if not isinstance(raw, dict):
            return None, ["top_level_not_object"]
        try:
            parsed = WorkerModelOutput.model_validate(raw)
        except ValidationError as exc:
            return None, [
                f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"
                for err in exc.errors()
            ][:5]
        return parsed.model_dump(), []

    def _build_result(
        self,
        task_kind: str,
        instruction: str,
        context: dict,
        structured: Optional[dict],
        model_meta: dict,
    ) -> dict:
        result: dict[str, Any] = {
            "task_kind": task_kind,
            "instruction": instruction,
            "model": model_meta,
            "summary": None,
            "observed_facts": context["observed_facts"],
            "evidence": context["evidence"],
            "model_observed_facts": [],
            "model_evidence": [],
            "inferences": [],
            "uncertainties": [],
            "recommendations": [],
            "proposed_actions": [],
            "context_sources": context["sections"],
            "epistemic": {
                "observed_facts": "retrieved_from_canonical_services",
                "model_observed_facts": "model_claimed_grounded_in_context",
                "inferences": "model_interpretation",
                "recommendations": "proposal_only_requires_human_authorization",
            },
            "approval": None,
            "proposal_decision": None,
            "action_operation_id": None,
            "completed_at": None,
        }
        if structured is not None:
            result["summary"] = structured.get("summary")
            result["model_observed_facts"] = structured.get("observed_facts", [])
            result["model_evidence"] = structured.get("evidence", [])
            result["inferences"] = structured.get("inferences", [])
            result["uncertainties"] = structured.get("uncertainties", [])
            result["recommendations"] = structured.get("recommendations", [])
            result["proposed_actions"] = structured.get("proposed_actions", [])
        else:
            result["uncertainties"] = [
                "AI model provider unavailable: this analysis contains only "
                "canonical facts retrieved from company services, with no "
                "model-generated reasoning."
            ]
        return result

    async def _persist_recommendation_governance(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation: CanonicalOperation,
        result: dict,
        actor: Optional[Employee],
    ) -> None:
        title = f"Recommendation: {result['instruction'][:180]}"
        decision = await decision_service.create(
            db,
            organization_id=organization_id,
            payload={
                "title": title[:300],
                "description": self._render_recommendation_markdown(result)[:6000],
                "status": "proposed",
                "project_id": (
                    operation.scope_id if operation.scope_type == "project" else None
                ),
                "tags": ["governed-worker", "ai-proposal"],
            },
            actor=actor,
            ip_address=None,
        )
        result["proposal_decision"] = {
            "id": decision.id,
            "status": decision.status,
            "title": decision.title,
        }

        action = next(
            (
                a for a in result.get("proposed_actions") or []
                if isinstance(a, dict) and a.get("action_type") == "create_task"
            ),
            None,
        )
        if action is None:
            action = {
                "action_type": "create_task",
                "title": f"Follow-up: {result['instruction'][:180]}",
                "description": result.get("summary") or result["instruction"],
                "requires_approval": True,
            }

        approval = await approval_service.create(
            db,
            organization_id=organization_id,
            data={
                "approval_type": "governed_worker_action",
                "title": f"Authorize action: {action['title'][:220]}",
                "description": (
                    "Requested by the governed AI worker. The proposed action "
                    "executes only if this approval is granted."
                ),
                "priority": "high",
                "entity_type": "governed_worker.task",
                "entity_id": operation.id,
                "requester_id": actor.id if actor else None,
            },
            actor=actor,
        )

        action_op = await canonical_reliability_service.create_operation(
            db,
            organization_id=organization_id,
            operation_type=ACTION_OPERATION_TYPE,
            title=action["title"][:300],
            description=action.get("description") or "",
            scope_type=operation.scope_type,
            scope_id=operation.scope_id,
            authorization_id=approval.id,
            decision_id=decision.id,
            actor_id=actor.id if actor else None,
            actor_type="agent",
            is_external=False,
            max_attempts=1,
            key_fields={
                "parent_operation_id": operation.id,
                "action_title": action["title"][:200],
            },
        )
        action_op.payload = {
            "parent_operation_id": operation.id,
            "analysis_operation_id": operation.id,
            "action": action,
        }
        await db.flush()

        result["approval"] = {
            "id": approval.id,
            "status": approval.status,
            "title": approval.title,
        }
        result["action_operation_id"] = action_op.id
        await self._emit(
            db,
            "governed_worker.approval.requested",
            organization_id,
            actor,
            {
                "operation_id": operation.id,
                "action_operation_id": action_op.id,
                "approval_id": approval.id,
                "decision_id": decision.id,
            },
        )

    @staticmethod
    def _render_recommendation_markdown(result: dict) -> str:
        lines = [
            "**AI-assisted recommendation — proposed, pending human authorization.**",
            "",
        ]
        if result.get("summary"):
            lines += ["## Summary", result["summary"], ""]
        blocks = (
            ("observed_facts", "Observed facts (canonical services)"),
            ("model_observed_facts", "Observed facts (model, grounded in context)"),
            ("inferences", "Inferences (model interpretation)"),
            ("uncertainties", "Uncertainties"),
            ("recommendations", "Recommendations (proposal only)"),
        )
        for key, heading in blocks:
            items = result.get(key) or []
            if items:
                lines.append(f"## {heading}")
                lines += [f"- {item}" for item in items]
                lines.append("")
        evidence = result.get("evidence") or []
        if evidence:
            lines.append("## Evidence")
            for item in evidence:
                suffix = (
                    f" ({item.get('source_ref')})" if item.get("source_ref") else ""
                )
                lines.append(f"- {item.get('claim')} — {item.get('source')}{suffix}")
            lines.append("")
        model = result.get("model") or {}
        lines.append(
            f"> Model: {model.get('provider') or 'none'} / "
            f"{model.get('model') or 'n/a'} · assisted: {model.get('assisted')}"
        )
        return "\n".join(lines)

    # ----------------------------------------------------------------- helpers

    async def _get_operation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_id: str,
        operation_type: str,
    ) -> CanonicalOperation:
        row = await db.execute(
            select(CanonicalOperation).where(
                CanonicalOperation.organization_id == organization_id,
                CanonicalOperation.id == operation_id,
                CanonicalOperation.operation_type == operation_type,
            )
        )
        operation = row.scalar_one_or_none()
        if operation is None:
            raise WorkerNotFound("Task not found")
        return operation

    async def _find_child_action(
        self, db: AsyncSession, *, organization_id: str, parent_operation_id: str
    ) -> Optional[CanonicalOperation]:
        rows = (
            await db.execute(
                select(CanonicalOperation)
                .where(
                    CanonicalOperation.organization_id == organization_id,
                    CanonicalOperation.operation_type == ACTION_OPERATION_TYPE,
                )
                .order_by(desc(CanonicalOperation.created_at))
                .limit(500)
            )
        ).scalars().all()
        for op in rows:
            if (op.payload or {}).get("parent_operation_id") == parent_operation_id:
                return op
        return None

    async def _emit(
        self,
        db: AsyncSession,
        name: str,
        organization_id: str,
        actor: Optional[Employee],
        payload: dict,
    ) -> None:
        await event_service.emit(
            db,
            name=name,
            actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload=payload,
        )

    async def _audit(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action: str,
        actor: Optional[Employee],
        ip_address: Optional[str],
        resource_id: str,
        details: dict,
        resource_type: str = "governed_worker_task",
    ) -> None:
        from app.services.work_audit import record

        await record(
            db,
            organization_id=organization_id,
            action=action,
            actor=actor,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )


governed_worker_service = GovernedWorkerService()
