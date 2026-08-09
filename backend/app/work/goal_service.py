"""Goal service â€” OKRs with key results and progress rollup (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.goal import Goal, KeyResult


class GoalService:
    async def _validate_ref(self, db: AsyncSession, organization_id: str, key: str, value: str):
        from app.models.department import Department
        from app.models.team import Team
        from app.models.project import Project

        model = {
            "owner_id": Employee,
            "department_id": Department,
            "team_id": Team,
            "project_id": Project,
            "parent_goal_id": Goal,
        }.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Goal:
        for key in ("owner_id", "department_id", "team_id", "project_id", "parent_goal_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        goal = Goal(
            organization_id=organization_id,
            parent_goal_id=data.get("parent_goal_id"),
            name=data["name"],
            description=data.get("description"),
            scope=data.get("scope", "team"),
            owner_id=data.get("owner_id"),
            department_id=data.get("department_id"),
            team_id=data.get("team_id"),
            project_id=data.get("project_id"),
            status=data.get("status", "planned"),
            priority=data.get("priority", "medium"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            progress=data.get("progress") or 0,
        )
        db.add(goal)
        await db.flush()
        for kr_data in data.get("key_results", []) or []:
            await self.add_key_result(
                db, organization_id=organization_id, goal_id=goal.id,
                data={**kr_data, "goal_id": goal.id},
            )
        await self.recompute_progress(db, organization_id=organization_id, goal=goal)
        await self._emit(db, "goal.created", organization_id, actor, ip_address, goal)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="goal.created",
            actor=actor, ip_address=ip_address,
            resource_type="goal", resource_id=goal.id,
            details={"name": goal.name, "scope": goal.scope},
        )
        return goal

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], goal: Goal):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id, payload={"goal_id": goal.id, "name": goal.name, "owner_id": goal.owner_id, "progress": goal.progress},
        )

    async def recompute_progress(self, db: AsyncSession, *, organization_id: str, goal: Goal) -> Goal:
        krs = await self.key_results(db, organization_id=organization_id, goal_id=goal.id)
        was_completed = goal.status == "completed"
        if krs:
            ratios = [
                min(1.0, (kr.current or 0) / kr.target)
                for kr in krs
                if kr.target and kr.target > 0
            ]
            goal.progress = round(sum(ratios) / len(ratios) * 100, 1) if ratios else round(goal.progress or 0, 1)
        if all(kr.status == "completed" for kr in krs) and krs:
            goal.status = "completed"
        elif goal.status != "completed" and goal.progress and goal.progress < 30 and goal.start_date and utcnow().date() > goal.start_date:
            goal.status = "at_risk"
        goal.updated_at = utcnow()
        await db.flush()
        if goal.status == "completed" and not was_completed:
            await self._emit(db, "goal.completed", organization_id, None, None, goal)
        return goal

    async def get(self, db: AsyncSession, *, organization_id: str, goal_id: str) -> Optional[Goal]:
        row = await db.execute(
            select(Goal).where(Goal.organization_id == organization_id, Goal.id == goal_id)
        )
        goal = row.scalar_one_or_none()
        if goal:
            goal.key_results = await self.key_results(db, organization_id=organization_id, goal_id=goal.id)
            goal.key_results_count = len(goal.key_results)
            goal.owner_name = None
            goal.parent_name = None
            if goal.owner_id:
                owner = await db.get(Employee, goal.owner_id)
                goal.owner_name = owner.full_name if owner else None
            if goal.parent_goal_id:
                parent = await db.get(Goal, goal.parent_goal_id)
                goal.parent_name = parent.name if parent else None
        return goal

    async def list_all(
        self, db: AsyncSession, *, organization_id: str, scope: Optional[str] = None,
        status: Optional[str] = None, owner_id: Optional[str] = None,
        team_id: Optional[str] = None, search: Optional[str] = None,
    ) -> list[Goal]:
        from sqlalchemy import or_

        stmt = select(Goal).where(Goal.organization_id == organization_id)
        if scope:
            stmt = stmt.where(Goal.scope == scope)
        if status:
            stmt = stmt.where(Goal.status == status)
        if owner_id:
            stmt = stmt.where(Goal.owner_id == owner_id)
        if team_id:
            stmt = stmt.where(Goal.team_id == team_id)
        if search:
            stmt = stmt.where(func.lower(Goal.name).like(f"%{search.lower()}%"))
        rows = await db.execute(stmt.order_by(desc(Goal.updated_at)))
        goals = list(rows.scalars().all())
        ids = [g.id for g in goals]
        kr_counts = {}
        if ids:
            kr_counts = dict(
                (await db.execute(
                    select(KeyResult.goal_id, func.count(KeyResult.id))
                    .where(KeyResult.organization_id == organization_id, KeyResult.goal_id.in_(ids))
                    .group_by(KeyResult.goal_id)
                )).all()
            )
        owner_ids = [g.owner_id for g in goals if g.owner_id]
        owners = {}
        if owner_ids:
            owners = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(owner_ids)))).scalars().all()}
        for g in goals:
            g.key_results_count = kr_counts.get(g.id, 0)
            g.owner_name = owners[g.owner_id].full_name if g.owner_id and owners.get(g.owner_id) else None
        return goals

    async def update(
        self, db: AsyncSession, *, organization_id: str, goal: Goal, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Goal:
        for key, value in data.items():
            if hasattr(goal, key) and key not in ("id", "organization_id", "created_at"):
                setattr(goal, key, value)
        goal.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "goal.updated", organization_id, actor, ip_address, goal)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="goal.updated",
            actor=actor, ip_address=ip_address,
            resource_type="goal", resource_id=goal.id,
            details={"name": goal.name},
        )
        return goal

    # ------------------------------------------------------------------ key results

    async def get_kr(self, db: AsyncSession, *, organization_id: str, kr_id: str) -> Optional[KeyResult]:
        kr = (
            await db.execute(
                select(KeyResult).where(KeyResult.organization_id == organization_id, KeyResult.id == kr_id)
            )
        ).scalar_one_or_none()
        if kr and kr.owner_id:
            owner = await db.get(Employee, kr.owner_id)
            kr.owner_name = owner.full_name if owner else None
        return kr

    async def _fetch_kr(self, db: AsyncSession, kr_id: str) -> Optional[KeyResult]:
        kr = await db.get(KeyResult, kr_id)
        if kr and kr.owner_id:
            owner = await db.get(Employee, kr.owner_id)
            kr.owner_name = owner.full_name if owner else None
        return kr

    async def key_results(self, db: AsyncSession, *, organization_id: str, goal_id: str) -> list[KeyResult]:
        rows = await db.execute(
            select(KeyResult)
            .where(KeyResult.organization_id == organization_id, KeyResult.goal_id == goal_id)
            .order_by(KeyResult.created_at.asc())
        )
        krs = list(rows.scalars().all())
        for kr in krs:
            kr.owner_name = None
            if kr.owner_id:
                owner = await db.get(Employee, kr.owner_id)
                kr.owner_name = owner.full_name if owner else None
        return krs

    async def add_key_result(
        self, db: AsyncSession, *, organization_id: str, goal_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> KeyResult:
        if data.get("owner_id"):
            emp = await db.get(Employee, data["owner_id"])
            if emp is None or emp.organization_id != organization_id:
                raise ValueError("Invalid owner_id reference")
        kr = KeyResult(
            organization_id=organization_id,
            goal_id=data.get("goal_id") or goal_id,
            title=data["title"],
            metric=data.get("metric"),
            unit=data.get("unit"),
            target=data.get("target"),
            current=data.get("current", 0),
            owner_id=data.get("owner_id"),
        )
        db.add(kr)
        await db.flush()
        goal = await db.get(Goal, goal_id)
        if goal and goal.organization_id == organization_id:
            await self.recompute_progress(db, organization_id=organization_id, goal=goal)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="key_result.created",
            actor=actor, ip_address=ip_address,
            resource_type="key_result", resource_id=kr.id,
            details={"title": kr.title, "goal_id": goal_id},
        )
        return kr

    async def update_key_result(
        self, db: AsyncSession, *, organization_id: str, goal_id: str, kr: KeyResult,
        data: dict[str, Any], actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> KeyResult:
        for key, value in data.items():
            if hasattr(kr, key) and key not in ("id", "organization_id", "goal_id"):
                setattr(kr, key, value)
        target = kr.target or 0
        current = kr.current or 0
        if target and current >= target:
            kr.status = "completed"
        elif target and current / target >= 0.7:
            kr.status = "on_track"
        elif target and current / target >= 0.4:
            kr.status = "behind"
        else:
            kr.status = "at_risk"
        kr.updated_at = utcnow()
        await db.flush()
        goal = await db.get(Goal, goal_id)
        if goal and goal.organization_id == organization_id:
            await self.recompute_progress(db, organization_id=organization_id, goal=goal)
            await self._emit(db, "goal.progress_updated", organization_id, actor, ip_address, goal)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="key_result.updated",
            actor=actor, ip_address=ip_address,
            resource_type="key_result", resource_id=kr.id,
            details={"title": kr.title, "goal_id": goal_id},
        )
        return kr

    async def delete_key_result(
        self, db: AsyncSession, *, organization_id: str, kr: KeyResult,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        goal_id = kr.goal_id
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="key_result.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="key_result", resource_id=kr.id,
            details={"title": kr.title, "goal_id": goal_id},
        )
        await db.delete(kr)
        await db.flush()
        goal = await db.get(Goal, goal_id)
        if goal and goal.organization_id == organization_id:
            await self.recompute_progress(db, organization_id=organization_id, goal=goal)

    async def delete(
        self, db: AsyncSession, *, organization_id: str, goal: Goal,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="goal.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="goal", resource_id=goal.id,
            details={"name": goal.name},
        )
        await db.delete(goal)


goal_service = GoalService()

