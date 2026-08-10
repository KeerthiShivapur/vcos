"""Decision service — the Decision Registry (Phase 4.3).

Every important decision is recorded with context, alternatives, participants,
the chosen option and the reasoning, so the AI can later answer "why was this
decision made?" from the organization's own memory.

Slice 4A extends the registry into the execution loop: follow-up actions carry
an owner, goal, project and due date, convert into real tasks, and the decision
moves to `implemented` once every follow-up task is completed.
"""

from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.knowledge.crud_base import KnowledgeCrud
from app.models.employee import Employee
from app.models.knowledge import Decision, DecisionOption, DecisionParticipant
from app.schemas.knowledge import normalize_follow_up_actions

DECISION_STATUSES = ("proposed", "made", "implemented", "reviewed")
ACTION_STATUSES = ("pending", "in_progress", "completed", "skipped")


async def _validate_org_members(db: AsyncSession, organization_id: str, **refs: Optional[str]) -> None:
    """Every follow-up reference must resolve inside the same organization."""
    from app.models.goal import Goal
    from app.models.project import Project

    if refs.get("owner_id"):
        owner = await db.get(Employee, refs["owner_id"])
        if owner is None or owner.organization_id != organization_id:
            raise ValueError("Invalid owner reference (must be an employee of this organization)")
    if refs.get("project_id"):
        project = await db.get(Project, refs["project_id"])
        if project is None or project.organization_id != organization_id:
            raise ValueError("Invalid project reference (must belong to this organization)")
    if refs.get("goal_id"):
        goal = await db.get(Goal, refs["goal_id"])
        if goal is None or goal.organization_id != organization_id:
            raise ValueError("Invalid goal reference (must belong to this organization)")


class DecisionService(KnowledgeCrud):
    model = Decision
    kind = "decision"

    async def create(self, db: AsyncSession, *, organization_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Any:
        options = payload.pop("options", None) or []
        participants = payload.pop("participants", None) or []
        actions = normalize_follow_up_actions(payload.pop("follow_up_actions", None))
        for action in actions or []:
            await _validate_org_members(
                db, organization_id,
                owner_id=action.get("owner_id"),
                project_id=action.get("project_id"),
                goal_id=action.get("goal_id"),
            )
        data = dict(payload)
        data.setdefault("status", "proposed")
        if actions:
            data["follow_up_actions"] = actions
        entity = await super().create(db, organization_id=organization_id, payload=data, actor=actor, ip_address=ip_address)
        for i, opt in enumerate(options):
            db.add(
                DecisionOption(
                    organization_id=organization_id,
                    decision_id=entity.id,
                    title=opt.get("title", f"Option {i + 1}"),
                    description=opt.get("description"),
                    pros=opt.get("pros"),
                    cons=opt.get("cons"),
                    sort_order=opt.get("sort_order", i),
                )
            )
        for p in participants:
            db.add(
                DecisionParticipant(
                    organization_id=organization_id,
                    decision_id=entity.id,
                    employee_id=p["employee_id"],
                    role=p.get("role", "consulted"),
                )
            )
        await db.flush()
        return entity

    async def update(self, db: AsyncSession, *, organization_id: str, entity_id: str, payload: dict[str, Any], actor: Optional[Employee], ip_address: Optional[str]) -> Optional[Any]:
        options = payload.pop("options", None)
        participants = payload.pop("participants", None)
        actions = payload.pop("follow_up_actions", None)
        if actions is not None:
            actions = normalize_follow_up_actions(actions)
            for action in actions or []:
                await _validate_org_members(
                    db, organization_id,
                    owner_id=action.get("owner_id"),
                    project_id=action.get("project_id"),
                    goal_id=action.get("goal_id"),
                )
            payload["follow_up_actions"] = actions or []
        entity = await super().update(db, organization_id=organization_id, entity_id=entity_id, payload=payload, actor=actor, ip_address=ip_address)
        if entity is None:
            return None
        if options is not None:
            existing = (
                await db.execute(
                    select(DecisionOption).where(
                        DecisionOption.organization_id == organization_id, DecisionOption.decision_id == entity.id
                    )
                )
            ).scalars().all()
            for row in existing:
                await db.delete(row)
            for i, opt in enumerate(options):
                db.add(
                    DecisionOption(
                        organization_id=organization_id,
                        decision_id=entity.id,
                        title=opt.get("title", f"Option {i + 1}"),
                        description=opt.get("description"),
                        pros=opt.get("pros"),
                        cons=opt.get("cons"),
                        sort_order=opt.get("sort_order", i),
                    )
                )
        if participants is not None:
            existing = (
                await db.execute(
                    select(DecisionParticipant).where(
                        DecisionParticipant.organization_id == organization_id, DecisionParticipant.decision_id == entity.id
                    )
                )
            ).scalars().all()
            for row in existing:
                await db.delete(row)
            for p in participants:
                db.add(
                    DecisionParticipant(
                        organization_id=organization_id,
                        decision_id=entity.id,
                        employee_id=p["employee_id"],
                        role=p.get("role", "consulted"),
                    )
                )
        await db.flush()
        return entity

    async def options(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> list[DecisionOption]:
        rows = (
            await db.execute(
                select(DecisionOption)
                .where(DecisionOption.organization_id == organization_id, DecisionOption.decision_id == decision_id)
                .order_by(DecisionOption.sort_order.asc())
            )
        ).scalars().all()
        return list(rows)

    async def participants(self, db: AsyncSession, *, organization_id: str, decision_id: str) -> list[DecisionParticipant]:
        rows = (
            await db.execute(
                select(DecisionParticipant)
                .where(DecisionParticipant.organization_id == organization_id, DecisionParticipant.decision_id == decision_id)
            )
        ).scalars().all()
        return list(rows)

    async def choose(
        self, db: AsyncSession, *, organization_id: str, decision_id: str, option_id: str, reason: Optional[str] = None,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Optional[Any]:
        """Record the chosen option, make the decision, persist the reason."""
        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None:
            return None
        option = (
            await db.execute(
                select(DecisionOption).where(
                    DecisionOption.organization_id == organization_id,
                    DecisionOption.decision_id == decision_id,
                    DecisionOption.id == option_id,
                )
            )
        ).scalar_one_or_none()
        if option is None:
            return None
        all_options = await self.options(db, organization_id=organization_id, decision_id=decision_id)
        for opt in all_options:
            opt.chosen = False
            opt.chosen_reason = None
        option.chosen = True
        option.chosen_reason = reason
        decision.status = "made"
        decision.decided_at = utcnow()
        decision.decision_date = decision.decision_date or date.today()
        decision.updated_at = utcnow()
        await kb.emit_and_audit(
            db, organization_id=organization_id, name="decision.made", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={
                "entity_id": decision.id, "decision_id": decision.id,
                "title": decision.title, "option": option.title, "reason": reason,
                "project_id": decision.project_id,
                "decision_maker_id": decision.decision_maker_id,
            },
            resource_type="decision", resource_id=decision.id,
        )
        await db.flush()
        return decision

    async def transition(
        self, db: AsyncSession, *, organization_id: str, decision_id: str, status: str, note: Optional[str] = None,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Optional[Any]:
        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None or status not in DECISION_STATUSES:
            return None
        decision.status = status
        if status == "made" and not decision.decided_at:
            decision.decided_at = utcnow()
            decision.decision_date = decision.decision_date or date.today()
        if status in ("implemented", "reviewed") and not decision.lessons_learned:
            decision.lessons_learned = decision.lessons_learned
        decision.updated_at = utcnow()
        await kb.emit_and_audit(
            db, organization_id=organization_id, name=f"decision.{status}", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={
                "entity_id": decision.id, "decision_id": decision.id,
                "title": decision.title, "note": note,
                "project_id": decision.project_id,
            },
            resource_type="decision", resource_id=decision.id,
        )
        await db.flush()
        return decision

    # ------------------------------------------------------------------ 4A

    async def tasks_for(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
    ) -> list[Any]:
        """Every task this decision produced."""
        from app.models.task import Task

        rows = (
            await db.execute(
                select(Task)
                .where(Task.organization_id == organization_id, Task.decision_id == decision_id)
                .order_by(Task.created_at.asc())
            )
        ).scalars().all()
        tasks = list(rows)
        from app.work.task_service import task_service

        for task in tasks:
            await task_service._hydrate_one(db, organization_id, task)
        return tasks

    async def execute_action(
        self, db: AsyncSession, *, organization_id: str, decision_id: str, action_index: int,
        actor: Optional[Employee], ip_address: Optional[str],
    ) -> Optional[tuple[Any, Any]]:
        """Convert a follow-up action into a real task (the 4A conversion).

        Reuses the canonical task engine: the task is tenanted, validated
        against the same organization, emits task.created + audit, notifies
        the assigned owner, and gets linked to the decision.
        """
        from app.work.task_service import task_service

        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None:
            return None
        actions = normalize_follow_up_actions(decision.follow_up_actions) or []
        if action_index < 0 or action_index >= len(actions):
            return None
        action = actions[action_index]
        if action.get("task_id"):
            return None
        if not action.get("text"):
            return None
        await _validate_org_members(
            db, organization_id,
            owner_id=action.get("owner_id"),
            project_id=action.get("project_id"),
            goal_id=action.get("goal_id"),
        )
        project_id = action.get("project_id") or decision.project_id
        due_date = None
        if action.get("due_date"):
            raw = action["due_date"]
            if isinstance(raw, date):
                due_date = raw
            else:
                try:
                    due_date = date.fromisoformat(str(raw)[:10])
                except ValueError:
                    due_date = None
        context_lines = []
        if decision.title:
            context_lines.append(f"Decision: {decision.title}")
        if decision.context:
            context_lines.append(f"Context: {decision.context}")
        if decision.summary:
            context_lines.append(f"Reason: {decision.summary}")
        description = "\n".join(context_lines) if context_lines else f"Follow-up action from decision '{decision.title or decision_id}'"
        task = await task_service.create(
            db,
            organization_id=organization_id,
            data={
                "title": action["text"],
                "description": description,
                "project_id": project_id,
                "goal_id": action.get("goal_id"),
                "assignee_id": action.get("owner_id"),
                "reporter_id": decision.decision_maker_id,
                "due_date": due_date,
                "status": "todo",
                "priority": "medium",
                "tags": ["decision"],
                "decision_id": decision.id,
            },
            actor=actor,
            ip_address=ip_address,
        )
        action["task_id"] = task.id
        action["status"] = "in_progress"
        decision.follow_up_actions = actions
        decision.updated_at = utcnow()
        from app.knowledge.relation_service import relation_service

        await relation_service.add(
            db, organization_id=organization_id,
            source_type="decision", source_id=decision.id,
            target_type="task", target_id=task.id,
            relation_type="produces",
            created_by=actor.id if actor else None,
        )
        await kb.emit_and_audit(
            db, organization_id=organization_id, name="decision.executed", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={
                "entity_id": decision.id, "decision_id": decision.id,
                "title": decision.title, "action": action["text"],
                "task_id": task.id, "task_title": task.title,
                "assignee_id": action.get("owner_id"),
                "project_id": project_id, "goal_id": action.get("goal_id"),
            },
            resource_type="decision", resource_id=decision.id,
        )
        await db.flush()
        return decision, task

    async def refresh_status(
        self, db: AsyncSession, *, organization_id: str, decision_id: str,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Optional[Any]:
        """Completion loop: when every executed follow-up task is completed,
        the decision automatically becomes `implemented`."""
        from app.models.task import Task

        decision = await self.get(db, organization_id=organization_id, entity_id=decision_id)
        if decision is None or decision.status not in ("made", "implemented"):
            return None
        if decision.status == "implemented":
            return decision
        tasks = await self.tasks_for(db, organization_id=organization_id, decision_id=decision_id)
        if not tasks:
            return decision
        if not all(t.status == "completed" for t in tasks):
            return decision
        decision.status = "implemented"
        decision.updated_at = utcnow()
        if not decision.decided_at:
            decision.decided_at = utcnow()
            decision.decision_date = decision.decision_date or date.today()
        actions = normalize_follow_up_actions(decision.follow_up_actions)
        if actions:
            for action in actions:
                if action.get("task_id") in {t.id for t in tasks}:
                    action["status"] = "completed"
            decision.follow_up_actions = actions
        await kb.emit_and_audit(
            db, organization_id=organization_id, name="decision.implemented", actor=actor,
            actor_user_id=actor.user_id if actor else None, ip_address=ip_address,
            payload={
                "entity_id": decision.id, "decision_id": decision.id,
                "title": decision.title, "tasks": [t.id for t in tasks],
                "project_id": decision.project_id,
            },
            resource_type="decision", resource_id=decision.id,
        )
        await self._notify_participants(db, organization_id, decision, actor)
        await db.flush()
        return decision

    async def _notify_participants(
        self, db: AsyncSession, organization_id: str, decision: Any, actor: Optional[Employee],
    ) -> None:
        from app.services.work_alerts import notify_employees

        rows = await self.participants(db, organization_id=organization_id, decision_id=decision.id)
        employee_ids = [p.employee_id for p in rows if p.employee_id]
        if decision.decision_maker_id:
            employee_ids.append(decision.decision_maker_id)
        await notify_employees(
            db,
            organization_id=organization_id,
            employee_ids=list(dict.fromkeys(employee_ids)),
            type="decision.implemented",
            title=f"Decision implemented: {decision.title}",
            body="Every follow-up task from this decision is now complete.",
            actor_id=actor.user_id if actor else None,
            entity_type="decision",
            entity_id=decision.id,
            link=f"/decisions/{decision.id}",
            priority="high",
        )


decision_service = DecisionService()
