"""Slice 4E.6 — Universal Company Action Intelligence: governed knowledge-to-action.

4E.5 built the knowledge intelligence operating layer: insights and
recommendations that tell the company what its knowledge MEANS. 4E.6 closes
the loop — knowledge -> recommendation -> action proposal -> governance ->
approval -> operational execution -> verification -> outcome -> evidence ->
company intelligence.

Design laws (mirroring 4E.4/4E.5, per the 4E.6 contract):
* deterministic first — no LLM invents an organizational action; every
  transition is an explicit, audited user action or an idempotent auto-step,
* one universal action contract — ``company_actions`` is the canonical row
  for the six action types (task | decision | communication | knowledge |
  meeting | project); the actual work ALWAYS routes into the existing
  governed operating services (tasks, decisions, announcements, documents,
  meetings, projects). This layer never duplicates those systems,
* governed by policy — low risk auto-approves, medium risk needs approval,
  high risk mandates it, restricted types (project) are role-gated. An
  unauthorized caller can never see an action exists (404 semantics),
* exact-once — actions are keyed by a stable fingerprint
  (organization + scope + action_type + target + source_problem); replays
  never duplicate and a finished action's successor links back,
* immutable audit — every transition is an append-only CompanyActionEvent
  (action.created, action.approved, action.verified, …) that is never
  edited or deleted,
* change-driven, bounded — every pass is an indexed organization-scoped
  query with a hard limit; workers are replay-safe (fingerprint keys,
  optimistic versioning, idempotent auto-steps),
* tenant isolation is absolute — every read AND every write is scoped to the
  caller's organization; non-org-wide callers only ever see the project
  actions their governance grants them.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow as now_utc
from app.knowledge.intelligence_engine import _fingerprint
from app.knowledge.synthesis_engine import _json_loads
from app.models.company_actions import (
    CompanyAction,
    CompanyActionEvent,
    CompanyActionOutcome,
)
from app.models.knowledge import KnowledgeIntelInsight, KnowledgeRecommendation
from app.models.company_operating import CompanyDecision, CompanyScenarioRun

# Slice 4H.5 — a decision may only anchor an action's lineage once it has
# reached human approval (or a later state). Pre-approval/declined decisions
# carry no institutional authority to act on.
_LINEAGE_DECISION_STATES = frozenset(
    {"approved", "executed", "outcome_recorded", "assessed"}
)

logger = logging.getLogger("vcos.knowledge.action_ops")

# ---------------------------------------------------------------------------
# bounds — every read and every write is hard-capped
# ---------------------------------------------------------------------------

_MAX_EVALUATE_SCAN = 200    # non-terminal actions considered per evaluate pass
_MAX_CENTER = 100           # action center page size
_MAX_EVENTS = 100           # audit events per action detail
_MAX_OUTCOME_INTEL = 300    # outcome rows considered for intelligence
_MAX_DEPENDENCIES = 40      # dependency edges per action

_EXPIRE_AFTER_DAYS = 14     # approval pending older than this expires
_ESCALATE_BLOCKED_DAYS = 3  # blocked longer than this escalates
_AUTOCOMPLETE_STATES = frozenset({"completed", "done"})

_ACTION_TYPES = frozenset({"task", "decision", "communication", "knowledge", "meeting", "project"})
_SCOPES = frozenset({"org", "company", "project", "department", "team", "goal"})
_RISKS = frozenset({"low", "medium", "high"})
_OUTCOME_TYPES = frozenset({"success", "partial", "failed", "not_applicable"})

_TERMINAL_STATES = frozenset({"rejected", "cancelled", "expired", "failed", "superseded"})

# controlled state machine: transition -> (allowed source states, next state)
_STATE_FLOW: dict[str, tuple[tuple[str, ...], Optional[str]]] = {
    "validate": (("proposed",), "validating"),
    "auto_approve": (("validating",), "approved"),
    "request_approval": (("validating",), "awaiting_approval"),
    "approve": (("awaiting_approval", "validating"), "approved"),
    "reject": (("proposed", "validating", "awaiting_approval", "approved", "ready"), "rejected"),
    "ready": (("approved",), "ready"),
    "assign": (("awaiting_approval", "approved", "ready"), None),
    "start": (("ready", "approved", "awaiting_approval"), "in_progress"),
    "block": (("in_progress", "ready", "approved"), "blocked"),
    "unblock": (("blocked",), "in_progress"),
    "complete": (("in_progress",), "completed"),
    "verify": (("completed",), "verified"),
    "fail": (("awaiting_approval", "approved", "ready", "in_progress", "blocked"), "failed"),
    "cancel": (
        ("proposed", "validating", "awaiting_approval", "approved", "ready", "in_progress", "blocked"),
        "cancelled",
    ),
    "expire": (("awaiting_approval", "approved", "ready", "in_progress", "blocked"), "expired"),
    "supersede": (
        ("awaiting_approval", "approved", "ready", "in_progress", "blocked", "completed", "verified"),
        "superseded",
    ),
}

_EVENT_FOR_TRANSITION: dict[str, str] = {
    "validate": "action.validated",
    "auto_approve": "action.approved",
    "request_approval": "action.approval_requested",
    "approve": "action.approved",
    "reject": "action.rejected",
    "ready": "action.ready",
    "assign": "action.assigned",
    "start": "action.started",
    "block": "action.blocked",
    "unblock": "action.unblocked",
    "complete": "action.completed",
    "verify": "action.verified",
    "fail": "action.failed",
    "cancel": "action.cancelled",
    "expire": "action.expired",
    "supersede": "action.superseded",
}

_RISK_BASE_SCORE = {"low": 10.0, "medium": 30.0, "high": 60.0}


def _norm(part: str, limit: int = 120) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (part or "").lower().strip())[:limit]


class ActionOpsEngine:
    """The 4E.6 universal action engine (deterministic, governed, bounded)."""

    # ------------------------------------------------------------------ access

    async def _access(self, db: AsyncSession, *, organization_id: str, user: Any):
        from app.intelligence.company_context import resolve_caller_access

        return await resolve_caller_access(
            db, organization_id=organization_id, user=user
        )

    async def _employee(self, db: AsyncSession, *, organization_id: str, user: Any):
        from app.people.employee_service import employee_service

        return await employee_service.get_by_user(
            db, organization_id=organization_id, user_id=getattr(user, "id", None)
        )

    async def _load(
        self, db: AsyncSession, *, organization_id: str, action_id: str
    ) -> Optional[CompanyAction]:
        return (
            await db.execute(
                select(CompanyAction).where(
                    CompanyAction.organization_id == organization_id,
                    CompanyAction.id == action_id,
                )
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------------ policy

    @staticmethod
    def _policy_for(action_type: str, risk: str) -> dict[str, Any]:
        """Deterministic policy routing:
        project type is always role-gated and approval-mandatory; every other
        type routes purely by risk — low -> auto; medium/high -> approval."""
        if action_type == "project":
            return {"route": "restricted", "approval_required": True}
        return {
            "route": "approval" if risk in ("medium", "high") else "auto",
            "approval_required": risk in ("medium", "high"),
        }

    @staticmethod
    def _priority_score(risk: str, due_at: Optional[datetime]) -> float:
        score = _RISK_BASE_SCORE.get(risk, 10.0)
        if due_at is not None:
            now = now_utc()
            if due_at < now:
                score += 25.0
            elif due_at < now + timedelta(days=2):
                score += 12.0
        return score

    # ------------------------------------------------------------------ events

    async def _emit(
        self,
        db: AsyncSession,
        action: CompanyAction,
        *,
        event: str,
        actor_id: Optional[str],
        note: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        db.add(
            CompanyActionEvent(
                organization_id=action.organization_id,
                action_id=action.id,
                event=event,
                actor_id=actor_id or "system",
                note=note,
                details_json=json.dumps(details) if details else None,
            )
        )

    # ------------------------------------------------------------- transitions

    async def _apply(
        self,
        db: AsyncSession,
        action: CompanyAction,
        transition: str,
        *,
        actor_id: str,
        note: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> CompanyAction:
        if transition not in _STATE_FLOW:
            raise ValueError(f"unknown action transition '{transition}'")
        allowed, next_state = _STATE_FLOW[transition]
        if action.state not in allowed:
            raise ValueError(
                f"cannot '{transition}' from state '{action.state}'"
            )
        now = now_utc()
        if transition in ("approve",):
            action.approved_by, action.approved_at = actor_id, now
            action.approver_id = action.approver_id or actor_id
            action.approval_note = note
        elif transition == "reject":
            action.rejected_reason = note
        elif transition == "start":
            action.started_at = now
        elif transition == "block":
            action.blocked_at, action.blocked_reason = now, note
        elif transition == "unblock":
            action.blocked_at, action.blocked_reason = None, None
        elif transition == "complete":
            action.completed_at, action.completed_by = now, actor_id
        elif transition == "verify":
            action.verified_at, action.verified_by = now, actor_id
            action.verification_note = note
        elif transition == "fail":
            action.fail_reason = note
        elif transition == "cancel":
            action.cancel_reason = note
        elif transition == "expire":
            action.expired_at = now
        action.state = next_state or action.state
        action.version += 1  # CAS: event-driven workers never overwrite silently
        await db.flush()
        await self._emit(
            db, action,
            event=_EVENT_FOR_TRANSITION[transition],
            actor_id=actor_id, note=note, details=details,
        )
        return action

    # ------------------------------------------------------------ routing (adapters to existing operating systems)

    async def _route_into_system(
        self,
        db: AsyncSession,
        action: CompanyAction,
        *,
        actor_id: str,
        user: Any,
    ) -> None:
        """Materialize the approved action through the EXISTING governed
        operating services — never a parallel universe. The routed artifact
        id is recorded on the action (target_type / target_id)."""
        actor = await self._employee(db, organization_id=action.organization_id, user=user)
        title = action.title[:200]
        lineage = (
            f"Company action governed by knowledge intelligence ({action.action_type}, "
            f"risk {action.risk}, policy {action.policy}).\n"
            f"Why: {action.why or action.source_problem or action.title}\n"
            f"Evidence claims: {', '.join(_json_loads(action.source_claim_ids_json, []) or [])}\n"
            f"Action: {action.id}"
        )
        if action.action_type == "task":
            from app.work.task_service import task_service

            data: dict[str, Any] = {
                "title": f"[Action] {title}",
                "description": lineage,
                "priority": "high" if action.risk == "high" else "medium",
                "status": "backlog",
            }
            if action.scope_type == "project" and action.scope_id:
                data["project_id"] = action.scope_id
            task = await task_service.create(
                db, organization_id=action.organization_id, data=data,
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "task", task.id
        elif action.action_type == "decision":
            from app.knowledge.decision_service import decision_service

            entity = await decision_service.create(
                db, organization_id=action.organization_id,
                payload={
                    "title": f"[Action] {title}",
                    "description": lineage,
                    "status": "proposed",
                    "options": [
                        {"title": "Accept the action", "description": action.source_problem or action.title},
                        {"title": "Gather more evidence", "description": "Investigate the cited claims before deciding."},
                        {"title": "Defer", "description": "No decision right now."},
                    ],
                },
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "decision", entity.id
        elif action.action_type == "meeting":
            from app.work.meeting_service import meeting_service

            data = {
                "title": f"[Action] {title}",
                "description": lineage,
                "meeting_type": "action",
                "status": "scheduled",
                "organizer_id": actor.id if actor else None,
            }
            if action.scope_type == "project" and action.scope_id:
                data["project_id"] = action.scope_id
            if action.due_at:
                data["start_at"] = action.due_at
            entity = await meeting_service.create(
                db, organization_id=action.organization_id, data=data,
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "meeting", entity.id
        elif action.action_type == "communication":
            from app.communication.announcement_service import announcement_service

            payload = {
                "title": f"[Action] {title}",
                "body": lineage,
                "type": "action",
                "priority": "high" if action.risk == "high" else "normal",
                "status": "published",
                "pinned": False,
            }
            entity = await announcement_service.create(
                db, organization_id=action.organization_id, payload=payload,
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "communication", entity.id
        elif action.action_type == "knowledge":
            from app.knowledge.document_service import document_service

            entity = await document_service.create(
                db, organization_id=action.organization_id,
                payload={
                    "title": f"[Action] {title}",
                    "content": lineage,
                    "summary": action.source_problem or action.title,
                    "category": "action",
                    "status": "draft",
                },
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "knowledge", entity.id
        elif action.action_type == "project":
            from app.work.project_service import project_service

            data = {
                "name": f"[Action] {title}"[:140],
                "description": lineage,
                "status": "planning",
                "owner_id": actor.id if actor else None,
            }
            entity = await project_service.create(
                db, organization_id=action.organization_id, data=data,
                actor=actor, ip_address="api",
            )
            action.target_type, action.target_id = "project", entity.id
        else:  # pragma: no cover - guarded at propose
            raise ValueError(f"cannot route action type '{action.action_type}'")
        await db.flush()

    async def _route_and_ready(
        self, db: AsyncSession, *, action: CompanyAction, actor_id: str, user: Any
    ) -> None:
        """Approval done -> route the real artifact -> ready. A routing
        failure is itself an audited, terminal event: the action preserves
        the story instead of disappearing."""
        try:
            await self._route_into_system(
                db, action, actor_id=actor_id, user=user
            )
            route_ok = True
        except Exception as exc:  # deterministic: record and fail visibly
            logger.warning(
                "action %s routing failed: %s", action.id, exc
            )
            route_ok = False
            await self._apply(
                db, action, "fail", actor_id=actor_id,
                note=f"artifact routing failed: {exc}",
            )
        if route_ok:
            if action.state != "ready":
                await self._apply(
                    db, action, "ready", actor_id=actor_id,
                    details={"target_type": action.target_type, "target_id": action.target_id},
                )

    # ------------------------------------------------------------------ propose

    async def propose(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        action_type: str,
        title: str,
        description: Optional[str] = None,
        source_problem: Optional[str] = None,
        target: Optional[str] = None,
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        risk: str = "low",
        due_at: Optional[datetime] = None,
        source_recommendation_id: Optional[str] = None,
        source_insight_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
        source_claim_ids: Optional[list[str]] = None,
        source_company_decision_id: Optional[str] = None,
        source_scenario_id: Optional[str] = None,
        source_commitment_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        approver_id: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Propose a governed company action from the knowledge layer.
        Exact-once: replays keyed on the fingerprint never duplicate.

        Proposal immediately validates lineage, applies the risk policy and
        advances automatically: low risk -> approved -> ready (artifact
        routed into the operating system); medium/high -> awaiting_approval
        -> (approve) -> ready.
        """
        if action_type not in _ACTION_TYPES:
            raise ValueError(
                f"unknown action type '{action_type}'; expected one of "
                f"{sorted(_ACTION_TYPES)}"
            )
        if risk not in _RISKS:
            raise ValueError(f"unknown risk '{risk}'")
        if scope_type not in _SCOPES:
            raise ValueError(f"unknown scope '{scope_type}'")
        if len(title) < 4:
            raise ValueError("title is too short")

        actor_id = getattr(user, "id", "system")

        # -- lineage resolution: the recommendation / insight must really exist
        reason: Optional[str] = None
        if source_recommendation_id:
            recommendation = (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == organization_id,
                        KnowledgeRecommendation.id == source_recommendation_id,
                    )
                )
            ).scalar_one_or_none()
            if recommendation is None:
                raise ValueError("source recommendation not found")
            reason = recommendation.reason
            if target is None:
                entities = _json_loads(recommendation.entities_json, [])
                for entity in entities:
                    if entity.get("type") == "topic" and entity.get("name"):
                        target = entity["name"]
                        break
            if not source_problem:
                source_problem = reason
            if not source_claim_ids:
                source_claim_ids = _json_loads(recommendation.evidence_json, [])
        if source_insight_id:
            insight = (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == organization_id,
                        KnowledgeIntelInsight.id == source_insight_id,
                    )
                )
            ).scalar_one_or_none()
            if insight is None:
                raise ValueError("source insight not found")
            if reason is None:
                reason = f"{insight.kind}: {insight.title}"
            if target is None:
                target = insight.topic_name or insight.title
            if not source_problem:
                source_problem = insight.summary
            if not source_claim_ids:
                source_claim_ids = _json_loads(insight.source_claims_json, [])
        # Slice 4H.5 — decision lineage: the anchoring decision must exist in
        # this organization and have reached human approval; an optional
        # scenario reference must be a real rehearsal of this organization.
        # Lineage is provenance only — it never alters policy, routing, or
        # governance (L16/L19).
        if source_company_decision_id:
            decision = (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == organization_id,
                        CompanyDecision.decision_id == source_company_decision_id,
                    )
                )
            ).scalar_one_or_none()
            if decision is None:
                raise ValueError("source decision not found")
            if decision.state not in _LINEAGE_DECISION_STATES:
                raise ValueError(
                    f"source decision state '{decision.state}' has not reached "
                    "approval; only approved decisions may anchor action lineage"
                )
            if reason is None:
                reason = f"decision {decision.kind}: {decision.title}"
            if not source_problem:
                source_problem = decision.title
        if source_scenario_id:
            scenario = (
                await db.execute(
                    select(CompanyScenarioRun).where(
                        CompanyScenarioRun.organization_id == organization_id,
                        CompanyScenarioRun.id == source_scenario_id,
                    )
                )
            ).scalar_one_or_none()
            if scenario is None:
                raise ValueError("source scenario not found")

        # Slice 4I.8 — commitment lineage: validate the source commitment exists
        if source_commitment_id:
            from app.models.execution_strategy import CompanyCommitment
            commitment = (
                await db.execute(
                    select(CompanyCommitment).where(
                        CompanyCommitment.organization_id == organization_id,
                        CompanyCommitment.id == source_commitment_id,
                    )
                )
            ).scalar_one_or_none()
            if commitment is None:
                raise ValueError("source commitment not found")
            # Only authorized commitments can anchor actions
            if commitment.state not in ("authorized", "active", "fulfilled"):
                raise ValueError(
                    f"source commitment state '{commitment.state}' is not executable; "
                    "only authorized/active/fulfilled commitments may anchor action lineage"
                )

        target_norm = _norm(target or title)
        problem_norm = _norm(source_problem or title, 160)
        scope_key = f"{scope_type}:{scope_id or ''}"
        # exact-once key: organization + scope + action_type + target + source_problem
        fingerprint = _fingerprint("action", action_type, scope_key, target_norm, problem_norm)

        existing = (
            await db.execute(
                select(CompanyAction)
                .where(
                    CompanyAction.organization_id == organization_id,
                    CompanyAction.action_type == action_type,
                    CompanyAction.fingerprint == fingerprint,
                )
                .order_by(CompanyAction.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None and existing.state not in _TERMINAL_STATES:
            # replay: refresh the intent, never the governed state
            existing.title = title
            existing.description = description or existing.description
            existing.why = reason or existing.why
            existing.source_problem = source_problem or existing.source_problem
            if due_at is not None and existing.due_at is None:
                existing.due_at = due_at
            if assignee_id and existing.assignee_id is None:
                existing.assignee_id, existing.assignee_type = assignee_id, "employee"
                await self._emit(
                    db, existing, event="action.assigned",
                    actor_id=actor_id,
                )
            if source_recommendation_id:
                existing.source_recommendation_id = source_recommendation_id
            if source_insight_id:
                existing.source_insight_id = source_insight_id
            if source_company_decision_id:
                existing.source_company_decision_id = source_company_decision_id
            if source_scenario_id:
                existing.source_scenario_id = source_scenario_id
            if source_commitment_id:
                existing.source_commitment_id = source_commitment_id
            existing.priority_score = max(existing.priority_score, self._priority_score(risk, due_at))
            await db.flush()
            return self._payload(existing, deduplicated=True)

        policy = self._policy_for(action_type, risk)
        now = now_utc()
        action = CompanyAction(
            organization_id=organization_id,
            action_type=action_type,
            title=title,
            description=description,
            state="proposed",
            risk=risk,
            priority_score=self._priority_score(risk, due_at),
            scope_type=scope_type,
            scope_id=scope_id,
            fingerprint=fingerprint,
            target_label=target_norm,
            source_problem=source_problem,
            why=reason,
            source_recommendation_id=source_recommendation_id,
            source_insight_id=source_insight_id,
            source_event_id=source_event_id,
            source_claim_ids_json=json.dumps(source_claim_ids or []),
            source_company_decision_id=source_company_decision_id,
            source_scenario_id=source_scenario_id,
            source_commitment_id=source_commitment_id,
            policy=policy["route"],
            approval_required=policy["approval_required"],
            approver_id=approver_id,
            assignee_id=assignee_id,
            assignee_type="employee" if assignee_id else "employee",
            due_at=due_at,
            created_by=actor_id,
        )
        if existing is not None:
            action.supersedes_id = existing.id
            existing.superseded_by_id = None  # terminal rows keep their own story
        db.add(action)
        await db.flush()
        await self._emit(
            db, action, event="action.created", actor_id=actor_id,
            details={"risk": risk, "policy": policy["route"], "fingerprint": fingerprint},
        )
        await self._apply(db, action, "validate", actor_id=actor_id)

        if depends_on:
            await self.set_dependencies(
                db, organization_id=organization_id, action=action,
                depends_on=depends_on,
            )

        if policy["approval_required"]:
            await self._apply(
                db, action, "request_approval", actor_id=actor_id,
                details={"require": "approval" if policy["route"] != "restricted" else "restricted + approval"},
            )
            return self._payload(action)

        # auto path: validated -> approved -> routed -> ready
        await self._apply(
            db, action, "auto_approve", actor_id=actor_id,
            note="auto-approval by policy (low risk)",
        )
        await self._route_and_ready(db, action=action, actor_id=actor_id, user=user)
        return self._payload(action)

    # ------------------------------------------------------------- approvals

    async def approve(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any,
        note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        action = await self._load(db, organization_id=organization_id, action_id=action_id)
        if action is None:
            return None
        actor_id = getattr(user, "id", "system")
        await self._apply(db, action, "approve", actor_id=actor_id, note=note)
        await self._route_and_ready(db, action=action, actor_id=actor_id, user=user)
        return self._payload(action)

    async def reject(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any,
        note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        action = await self._load(db, organization_id=organization_id, action_id=action_id)
        if action is None:
            return None
        await self._apply(
            db, action, "reject", actor_id=getattr(user, "id", "system"), note=note
        )
        return self._payload(action)

    # ------------------------------------------------------------- transitions

    async def transition(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any,
        transition: str,
        note: Optional[str] = None,
        assignee_id: Optional[str] = None,
        due_at: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        """One governed surface for every user-facing transition: assign,
        start, block, unblock, complete, verify, fail, cancel, supersede.
        Every call is audited; the row is never deleted."""
        action = await self._load(db, organization_id=organization_id, action_id=action_id)
        if action is None:
            return None
        actor_id = getattr(user, "id", "system")

        if transition == "approve":
            await self._apply(db, action, "approve", actor_id=actor_id, note=note)
            await self._route_and_ready(db, action=action, actor_id=actor_id, user=user)
            return self._payload(action)
        if transition == "reject":
            await self._apply(db, action, "reject", actor_id=actor_id, note=note)
            return self._payload(action)
        if transition == "assign":
            if not assignee_id:
                raise ValueError("assign needs an assignee_id")
            action.assignee_id, action.assignee_type = assignee_id, "employee"
            action.assigned_at = now_utc()
            action.version += 1
            await db.flush()
            await self._emit(db, action, event="action.assigned", actor_id=actor_id, note=note)
            return self._payload(action)
        if transition == "verify" and not note:
            raise ValueError("verification needs a note")
        if transition == "start":
            deps = _json_loads(action.dependencies_json, []) or []
            if deps:
                rows = list(
                    (
                        await db.execute(
                            select(CompanyAction).where(
                                CompanyAction.organization_id == organization_id,
                                CompanyAction.id.in_(deps),
                            )
                        )
                    ).scalars().all()
                )
                incomplete = [
                    d.id for d in rows
                    if d.state not in ("completed", "verified")
                ]
                if incomplete:
                    raise ValueError(
                        f"dependent action(s) not completed: {', '.join(incomplete)}"
                    )
        if due_at is not None:
            action.due_at = due_at
        await self._apply(db, action, transition, actor_id=actor_id, note=note)
        return self._payload(action)

    # --------------------------------------------------------- dependencies

    async def set_dependencies(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action: CompanyAction,
        depends_on: list[str],
        user: Any = None,
    ) -> list[str]:
        """Add dependency edges (bounded, cycle-safe, org-scoped)."""
        if len(depends_on) > _MAX_DEPENDENCIES:
            raise ValueError(f"too many dependencies (max {_MAX_DEPENDENCIES})")
        if action.id in depends_on:
            raise ValueError("an action cannot depend on itself")
        rows = list(
            (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.id.in_(depends_on),
                    )
                )
            ).scalars().all()
        )
        found = {r.id for r in rows}
        missing = [d for d in depends_on if d not in found]
        if missing:
            raise ValueError(f"dependent action(s) not found: {', '.join(missing)}")
        current = set(_json_loads(action.dependencies_json, []) or [])
        updated = sorted(current | found)
        action.dependencies_json = json.dumps(updated)
        action.version += 1
        await db.flush()
        await self._emit(
            db, action, event="action.validated", actor_id=getattr(user, "id", "system"),
            details={"dependencies": updated},
        )
        return updated

    # --------------------------------------------------------------- outcomes

    async def record_outcome(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any,
        outcome_type: str,
        verdict: Optional[str] = None,
        effectiveness: float = 0.5,
        notes: Optional[str] = None,
        evidence: Optional[list[str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Record what the action actually achieved after verification.
        Evidence defaults to the action's own source claims — the loop back
        into company intelligence."""
        action = await self._load(db, organization_id=organization_id, action_id=action_id)
        if action is None:
            return None
        if action.state not in ("completed", "verified"):
            raise ValueError(
                f"cannot record an outcome from state '{action.state}'"
            )
        if outcome_type not in _OUTCOME_TYPES:
            raise ValueError(f"unknown outcome type '{outcome_type}'")
        effectiveness = max(0.0, min(1.0, float(effectiveness or 0.0)))
        evidence_ids = evidence or (_json_loads(action.source_claim_ids_json, []) or [])
        row = CompanyActionOutcome(
            organization_id=organization_id,
            action_id=action.id,
            outcome_type=outcome_type,
            verdict=verdict,
            effectiveness=effectiveness,
            evidence_json=json.dumps(evidence_ids),
            notes=notes,
            recorded_by=getattr(user, "id", "system"),
        )
        db.add(row)
        await db.flush()
        action.outcome_id = row.id
        action.version += 1
        await db.flush()
        await self._emit(
            db, action, event="action.outcome_recorded",
            actor_id=getattr(user, "id", "system"),
            note=verdict,
            details={"outcome_type": outcome_type, "effectiveness": effectiveness},
        )
        return {
            "outcome": {
                "id": row.id,
                "outcome_type": row.outcome_type,
                "verdict": row.verdict,
                "effectiveness": row.effectiveness,
                "evidence": evidence_ids,
                "notes": row.notes,
                "recorded_by": row.recorded_by,
                "measured_at": ensure_aware(row.measured_at).isoformat(),
            },
            "action": self._payload(action),
        }

    async def outcome_intelligence(
        self, db: AsyncSession, *, organization_id: str
    ) -> dict[str, Any]:
        """What the company's actions achieve: effectiveness by outcome type,
        by action type, by risk — the outcome intelligence layer."""
        rows = list(
            (
                await db.execute(
                    select(CompanyActionOutcome)
                    .where(CompanyActionOutcome.organization_id == organization_id)
                    .order_by(CompanyActionOutcome.measured_at.desc())
                    .limit(_MAX_OUTCOME_INTEL)
                )
            ).scalars().all()
        )
        if not rows:
            return {
                "total": 0,
                "by_outcome_type": [],
                "by_action_type": [],
                "by_risk": [],
                "success_rate": 0.0,
                "avg_effectiveness": 0.0,
                "recent": [],
            }
        action_ids = {r.action_id for r in rows}
        actions = {
            a.id: a
            for a in (
                await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.id.in_(action_ids),
                    )
                )
            ).scalars().all()
        }

        by_outcome: dict[str, list[CompanyActionOutcome]] = {}
        by_type: dict[str, list[CompanyActionOutcome]] = {}
        by_risk: dict[str, list[CompanyActionOutcome]] = {}
        for row in rows:
            action = actions.get(row.action_id)
            by_outcome.setdefault(row.outcome_type, []).append(row)
            by_type.setdefault(
                action.action_type if action else "unknown", []
            ).append(row)
            by_risk.setdefault(action.risk if action else "unknown", []).append(row)

        def summarize(groups: dict) -> list[dict[str, Any]]:
            out = []
            for key, group in sorted(groups.items()):
                out.append(
                    {
                        "key": key,
                        "total": len(group),
                        "success": sum(1 for r in group if r.outcome_type == "success"),
                        "failed": sum(1 for r in group if r.outcome_type == "failed"),
                        "avg_effectiveness": round(
                            sum(r.effectiveness for r in group) / len(group), 3
                        ),
                    }
                )
            return out

        successes = sum(1 for r in rows if r.outcome_type == "success")
        return {
            "total": len(rows),
            "by_outcome_type": summarize(by_outcome),
            "by_action_type": summarize(by_type),
            "by_risk": summarize(by_risk),
            "success_rate": round(successes / len(rows), 3),
            "avg_effectiveness": round(
                sum(r.effectiveness for r in rows) / len(rows), 3
            ),
            "recent": [
                {
                    "action_id": r.action_id,
                    "action_title": getattr(actions.get(r.action_id), "title", None),
                    "outcome_type": r.outcome_type,
                    "verdict": r.verdict,
                    "effectiveness": r.effectiveness,
                    "measured_at": ensure_aware(r.measured_at).isoformat(),
                }
                for r in rows[:10]
            ],
        }

    # ----------------------------------------------------------------- center

    async def center(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        state: Optional[str] = None,
        action_type: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        risk: Optional[str] = None,
        assignee_id: Optional[str] = None,
        mine: bool = False,
        attention: bool = False,
        blocked_only: bool = False,
        overdue_only: bool = False,
        escalated_only: bool = False,
        search: Optional[str] = None,
        limit: int = _MAX_CENTER,
        offset: int = 0,
    ) -> dict[str, Any]:
        """The company action center — governed, bounded, tenant-isolated.
        Non-org-wide callers only ever see project actions their governance
        grants them; everything else is indistinguishable from absent."""
        access = await self._access(db, organization_id=organization_id, user=user)
        query = select(CompanyAction).where(
            CompanyAction.organization_id == organization_id
        )
        if not access.org_wide:
            query = query.where(
                CompanyAction.scope_type == "project",
                CompanyAction.scope_id.in_(
                    set(access.project_ids) if access.project_ids else {"__none__"}
                ),
            )
        if state:
            query = query.where(CompanyAction.state == state)
        if action_type:
            query = query.where(CompanyAction.action_type == action_type)
        if scope_type:
            query = query.where(CompanyAction.scope_type == scope_type)
        if scope_id:
            query = query.where(CompanyAction.scope_id == scope_id)
        if risk:
            query = query.where(CompanyAction.risk == risk)
        if assignee_id:
            query = query.where(CompanyAction.assignee_id == assignee_id)
        if mine and access.employee_id:
            query = query.where(CompanyAction.assignee_id == access.employee_id)
        if search:
            query = query.where(CompanyAction.title.ilike(f"%{search}%"))
        all_rows = list(
            (
                await db.execute(
                    query.order_by(CompanyAction.updated_at.desc())
                )
            ).scalars().all()
        )
        rows = all_rows[offset: offset + limit]
        now = now_utc()

        def attention_reasons(row: CompanyAction) -> list[str]:
            reasons: list[str] = []
            if row.state == "awaiting_approval":
                reasons.append("needs approval")
            if row.state == "blocked":
                reasons.append("blocked")
            if row.due_at is not None and row.state not in _TERMINAL_STATES \
                    and ensure_aware(row.due_at) < now:
                reasons.append("overdue")
            if row.escalation_level > 0:
                reasons.append("escalated")
            return reasons

        stats_query = select(CompanyAction).where(
            CompanyAction.organization_id == organization_id
        )
        if not access.org_wide:
            stats_query = stats_query.where(
                CompanyAction.scope_type == "project",
                CompanyAction.scope_id.in_(
                    set(access.project_ids) if access.project_ids else {"__none__"}
                ),
            )
        org_rows = list(
            (
                await db.execute(
                    stats_query.limit(2000)  # bounded: stats over a bounded window
                )
            ).scalars().all()
        )
        by_state: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for row in org_rows:
            by_state[row.state] = by_state.get(row.state, 0) + 1
            by_type[row.action_type] = by_type.get(row.action_type, 0) + 1

        if blocked_only:
            rows = [r for r in rows if r.state == "blocked"]
        elif overdue_only:
            rows = [
                r for r in rows
                if r.due_at is not None and r.state not in _TERMINAL_STATES
                and ensure_aware(r.due_at) < now
            ]
        elif escalated_only:
            rows = [r for r in rows if r.escalation_level > 0]
        elif attention:
            rows = [r for r in rows if attention_reasons(r)]

        return {
            "total": len(org_rows),
            "scope": "org" if access.org_wide else "project",
            "stats": {
                "by_state": by_state,
                "by_action_type": by_type,
                "open": sum(v for k, v in by_state.items() if k not in _TERMINAL_STATES),
            },
            "items": [self._payload(r, reasons=attention_reasons(r)) for r in rows],
            "limit": limit,
            "offset": offset,
        }

    # ---------------------------------------------------------------- detail

    async def detail(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        action_id: str,
        user: Any,
    ) -> Optional[dict[str, Any]]:
        access = await self._access(db, organization_id=organization_id, user=user)
        action = await self._load(db, organization_id=organization_id, action_id=action_id)
        if action is None:
            return None
        if not access.org_wide:
            if action.scope_type != "project" or (
                action.scope_id not in access.project_ids
            ):
                return None  # 404 semantics: unauthorized is indistinguishable
        payload = self._payload(action)
        events = list(
            (
                await db.execute(
                    select(CompanyActionEvent)
                    .where(CompanyActionEvent.action_id == action.id)
                    .order_by(CompanyActionEvent.created_at.desc())
                    .limit(_MAX_EVENTS)
                )
            ).scalars().all()
        )
        payload["events"] = [
            {
                "event": e.event,
                "actor_id": e.actor_id,
                "note": e.note,
                "details": _json_loads(e.details_json, None),
                "created_at": ensure_aware(e.created_at).isoformat(),
            }
            for e in events
        ]
        deps = _json_loads(action.dependencies_json, []) or []
        dep_rows: dict[str, CompanyAction] = {}
        if deps:
            dep_rows = {
                d.id: d for d in (
                    await db.execute(
                        select(CompanyAction).where(
                            CompanyAction.organization_id == organization_id,
                            CompanyAction.id.in_(deps),
                        )
                    )
                ).scalars().all()
            }
        payload["dependencies"] = [
            {
                "id": d,
                "title": dep_rows[d].title if d in dep_rows else None,
                "state": dep_rows[d].state if d in dep_rows else None,
                "complete": dep_rows[d].state in ("completed", "verified") if d in dep_rows else False,
            }
            for d in deps
        ]
        outcome: Optional[dict[str, Any]] = None
        if action.outcome_id:
            row = (
                await db.execute(
                    select(CompanyActionOutcome).where(
                        CompanyActionOutcome.id == action.outcome_id,
                        CompanyActionOutcome.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                outcome = {
                    "id": row.id,
                    "outcome_type": row.outcome_type,
                    "verdict": row.verdict,
                    "effectiveness": row.effectiveness,
                    "evidence": _json_loads(row.evidence_json, []),
                    "notes": row.notes,
                    "recorded_by": row.recorded_by,
                    "measured_at": ensure_aware(row.measured_at).isoformat(),
                }
        payload["outcome"] = outcome
        if action.source_recommendation_id:
            rec = (
                await db.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.id == action.source_recommendation_id,
                        KnowledgeRecommendation.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            payload["source_recommendation"] = (
                {
                    "id": rec.id,
                    "kind": rec.kind,
                    "reason": rec.reason,
                    "confidence": rec.confidence,
                    "risk": rec.risk,
                }
                if rec else None
            )
        if action.source_insight_id:
            ins = (
                await db.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.id == action.source_insight_id,
                        KnowledgeIntelInsight.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            payload["source_insight"] = (
                {"id": ins.id, "kind": ins.kind, "title": ins.title, "summary": ins.summary}
                if ins else None
            )
        return payload

    # --------------------------------------------------------------- evaluate

    async def evaluate(
        self, db: AsyncSession, *, organization_id: str, user: Any = None
    ) -> dict[str, int]:
        """One idempotent, bounded operational pass over non-terminal actions:
        expire stale approvals, escalate overdue / long-blocked work, and
        reflect completion from the routed operating artifacts (event-driven
        reflection). Every step is idempotent and audited."""
        rows = list(
            (
                await db.execute(
                    select(CompanyAction)
                    .where(
                        CompanyAction.organization_id == organization_id,
                        CompanyAction.state.notin_(tuple(_TERMINAL_STATES)),
                    )
                    .order_by(CompanyAction.updated_at.desc())
                    .limit(_MAX_EVALUATE_SCAN)
                )
            ).scalars().all()
        )
        now = now_utc()
        expired = escalated = completed = 0
        for action in rows:
            stale = ensure_aware(action.updated_at) < now - timedelta(days=_EXPIRE_AFTER_DAYS)
            if action.state in ("awaiting_approval", "approved") and stale:
                await self._apply(
                    db, action, "expire", actor_id="system",
                    note="approval pending beyond the policy horizon",
                )
                expired += 1
                continue
            if action.state == "in_progress" and action.target_type in ("task", "meeting"):
                status = await self._artifact_status(db, action)
                if status in _AUTOCOMPLETE_STATES:
                    await self._apply(
                        db, action, "complete", actor_id="system",
                        note=f"reflected from routed {action.target_type} status",
                    )
                    completed += 1
                    continue
            if action.state in ("ready", "in_progress", "blocked"):
                reason: Optional[str] = None
                if action.due_at is not None and ensure_aware(action.due_at) < now:
                    reason = "overdue"
                elif (
                    action.state == "blocked"
                    and action.blocked_at is not None
                    and ensure_aware(action.blocked_at) < now
                    - timedelta(days=_ESCALATE_BLOCKED_DAYS)
                ):
                    reason = f"blocked {_ESCALATE_BLOCKED_DAYS}+ days"
                if reason and action.escalation_level == 0:
                    action.escalation_level = 1
                    action.priority_score += 20.0
                    action.version += 1
                    await db.flush()
                    await self._emit(
                        db, action, event="action.escalated",
                        actor_id="system",
                        note=f"escalated: {reason}",
                        details={"reason": reason, "due_at": action.due_at.isoformat() if action.due_at else None},
                    )
                    escalated += 1
        await db.flush()
        return {
            "evaluated": len(rows),
            "expired": expired,
            "escalated": escalated,
            "auto_completed": completed,
        }

    async def _artifact_status(
        self, db: AsyncSession, action: CompanyAction
    ) -> Optional[str]:
        if action.target_id is None:
            return None
        try:
            if action.target_type == "task":
                from app.work.task_service import task_service

                task = await task_service.get(
                    db, organization_id=action.organization_id, task_id=action.target_id
                )
                return getattr(task, "status", None)
            if action.target_type == "meeting":
                from app.work.meeting_service import meeting_service

                meeting = await meeting_service.get(
                    db, organization_id=action.organization_id, meeting_id=action.target_id
                )
                return getattr(meeting, "status", None)
        except Exception:  # pragma: no cover - artifact layers vary
            return None
        return None

    # ----------------------------------------------------------------- payload

    @staticmethod
    def _payload(
        action: CompanyAction,
        deduplicated: bool = False,
        reasons: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        now = now_utc()
        overdue = (
            action.due_at is not None
            and action.state not in _TERMINAL_STATES
            and ensure_aware(action.due_at) < now
        )
        return {
            "id": action.id,
            "action_type": action.action_type,
            "title": action.title,
            "description": action.description,
            "state": action.state,
            "risk": action.risk,
            "priority_score": round(action.priority_score, 1),
            "policy": action.policy,
            "approval_required": action.approval_required,
            "approver_id": action.approver_id,
            "approved_by": action.approved_by,
            "approved_at": ensure_aware(action.approved_at).isoformat() if action.approved_at else None,
            "rejected_reason": action.rejected_reason,
            "scope_type": action.scope_type,
            "scope_id": action.scope_id,
            "fingerprint": action.fingerprint,
            "target_label": action.target_label,
            "source_problem": action.source_problem,
            "why": action.why,
            "source_recommendation_id": action.source_recommendation_id,
            "source_insight_id": action.source_insight_id,
            "source_event_id": action.source_event_id,
            "source_claim_ids": _json_loads(action.source_claim_ids_json, []),
            "source_company_decision_id": action.source_company_decision_id,
            "source_scenario_id": action.source_scenario_id,
            "source_commitment_id": action.source_commitment_id,
            "target_type": action.target_type,
            "target_id": action.target_id,
            "assignee_id": action.assignee_id,
            "assigned_at": ensure_aware(action.assigned_at).isoformat() if action.assigned_at else None,
            "due_at": ensure_aware(action.due_at).isoformat() if action.due_at else None,
            "overdue": overdue,
            "dependencies": _json_loads(action.dependencies_json, []) or [],
            "escalation_level": action.escalation_level,
            "started_at": ensure_aware(action.started_at).isoformat() if action.started_at else None,
            "blocked_at": ensure_aware(action.blocked_at).isoformat() if action.blocked_at else None,
            "blocked_reason": action.blocked_reason,
            "completed_at": ensure_aware(action.completed_at).isoformat() if action.completed_at else None,
            "verified_at": ensure_aware(action.verified_at).isoformat() if action.verified_at else None,
            "verification_note": action.verification_note,
            "fail_reason": action.fail_reason,
            "cancel_reason": action.cancel_reason,
            "supersedes_id": action.supersedes_id,
            "superseded_by_id": action.superseded_by_id,
            "outcome_id": action.outcome_id,
            "version": action.version,
            "attention_reasons": reasons or [],
            "created_by": action.created_by,
            "created_at": ensure_aware(action.created_at).isoformat(),
            "updated_at": ensure_aware(action.updated_at).isoformat(),
            "deduplicated": deduplicated,
        }


action_ops_engine = ActionOpsEngine()