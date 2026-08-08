"""Autonomous planning engine — plans generated every morning for review.

Daily, weekly, sprint, department, hiring, infrastructure, learning and
executive plans. Managers approve before execution; approved plan items are
surfaced as recommendations so they become actionable.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.autonomous_plan import AutonomousPlan, PLAN_KINDS
from app.models.course import CourseEnrollment
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.knowledge import Document
from app.models.project import Project
from app.models.task import Task


class PlanningEngine:
    async def generate(
        self, db: AsyncSession, organization_id: str, *, kinds: list[str] | None = None,
        created_by: str | None = None, commit: bool = False,
    ) -> dict[str, Any]:
        selected = [k for k in (kinds or PLAN_KINDS) if k in PLAN_KINDS]
        rows: list[AutonomousPlan] = []
        for kind in selected:
            plan = await self._plan_for(db, organization_id, kind)
            row = AutonomousPlan(
                organization_id=organization_id,
                kind=kind,
                title=plan["title"],
                summary=plan["summary"],
                items=plan["items"],
                focus=plan["focus"],
                status="pending",
                created_by=created_by,
                source_event="planning.generated",
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        plans = [{"id": r.id, "kind": r.kind, "title": r.title, "summary": r.summary,
                  "items": r.items or [], "focus": r.focus or {}, "status": r.status}
                 for r in rows]
        if commit:
            await db.commit()
        return {"total": len(plans), "plans": plans}

    async def _plan_for(
        self, db: AsyncSession, organization_id: str, kind: str
    ) -> dict[str, Any]:
        now = utcnow()

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        employees = await _count(Employee)
        projects_active = await _count(Project, status="active")
        tasks_open = await _count(Task, status="todo") + await _count(Task, status="in_progress")
        overdue = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).scalar() or 0
        docs = await _count(Document)
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        underused = [b for b in budgets if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount < 0.3]
        enrollments = await _count(CourseEnrollment)
        completed = await _count(CourseEnrollment, status="completed")

        def _items(*rows: tuple[str, str, str]) -> list[dict[str, Any]]:
            return [
                {"action": action, "target": target, "owner_hint": owner_hint}
                for action, target, owner_hint in rows
            ]

        if kind == "daily":
            title = f"Daily plan — {now.strftime('%Y-%m-%d')}"
            summary = f"{tasks_open} open tasks, {overdue} overdue."
            items = _items(
                ("Clear overdue tasks", "Backlog", "Task owners"),
                ("Progress top 3 active projects", "Projects", "Project leads"),
                ("Review pending approvals", "Approvals", "Managers"),
                ("Capture lessons from yesterday", "Memory", "Team"),
            )
        elif kind == "weekly":
            title = f"Weekly plan — week of {now.strftime('%Y-%m-%d')}"
            summary = f"{projects_active} active projects, {employees} employees, {docs} documents."
            items = _items(
                ("Deliver sprint commitments", "Active projects", "Sprint leads"),
                ("Reduce overdue task count", "Tasks", "Managers"),
                ("Refresh stale knowledge", "Knowledge base", "Documentation owners"),
                ("Review team health", "Health dashboard", "Managers"),
            )
        elif kind == "sprint":
            title = f"Sprint plan — {now.strftime('%Y-%m-%d')}"
            summary = f"Capacity for {max(1, employees * 3)} task points."
            items = _items(
                ("Commit top-priority backlog items", "Backlog", "Scrum master"),
                ("Assign tasks within capacity", "Sprint board", "Managers"),
                ("Schedule reviews for completed work", "Sprint", "Team"),
            )
        elif kind == "department":
            title = "Department plan"
            summary = "Balanced focus across departments."
            items = _items(
                ("Review department workload", "All departments", "Heads"),
                ("Address underused budget lines", "Budget", "Finance"),
                ("Close knowledge gaps per department", "Knowledge", "Heads"),
            )
        elif kind == "hiring":
            title = "Hiring plan"
            summary = f"Employees: {employees}; capacity pressure: {tasks_open / max(employees * 3, 1):.0%}."
            items = _items(
                ("Open roles for overloaded teams", "Hiring pipeline", "Recruiting"),
                ("Prioritize critical skill gaps", "Skills", "Talent lead"),
                ("Prepare onboarding plan for new hires", "Onboarding", "HR"),
            )
        elif kind == "infrastructure":
            title = "Infrastructure plan"
            summary = "Growth-aligned capacity and reliability."
            items = _items(
                ("Review cluster health", "Infrastructure", "Platform"),
                ("Plan capacity for next quarter", "Capacity", "Platform"),
                ("Audit backup and recovery", "Backups", "Platform"),
            )
        elif kind == "learning":
            title = "Learning plan"
            summary = f"Enrollments: {enrollments}, completed: {completed}."
            items = _items(
                ("Enroll employees in gap courses", "Learning catalog", "Managers"),
                ("Assign mentors to juniors", "Mentorship", "HR"),
                ("Certify critical skills", "Certifications", "Team"),
            )
        else:  # executive
            title = f"Executive plan — {now.strftime('%Y-%m-%d')}"
            summary = "Strategic focus for the week."
            items = _items(
                ("Review company health score", "Health", "CEO"),
                ("Decide on strategic recommendations", "Recommendations", "Executives"),
                ("Review forecasts and risks", "Strategy", "CEO"),
                ("Approve budget reallocation", "Budget", "CFO"),
            )

        focus = {
            "overdue_tasks": overdue,
            "active_projects": projects_active,
            "underused_budgets": len(underused),
        }
        return {"title": title, "summary": summary, "items": items, "focus": focus}

    async def list(
        self, db: AsyncSession, organization_id: str, *, kind: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        stmt = select(AutonomousPlan).where(AutonomousPlan.organization_id == organization_id)
        if kind:
            stmt = stmt.where(AutonomousPlan.kind == kind)
        rows = (
            await db.execute(stmt.order_by(AutonomousPlan.created_at.desc()).limit(limit))
        ).scalars().all()
        return {
            "total": len(rows),
            "plans": [
                {
                    "id": r.id, "kind": r.kind, "title": r.title, "summary": r.summary,
                    "items": r.items or [], "focus": r.focus or {}, "status": r.status,
                    "approved_by": r.approved_by,
                    "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }

    async def set_status(
        self, db: AsyncSession, organization_id: str, plan_id: str, status: str,
        *, user_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(AutonomousPlan).where(
                    AutonomousPlan.organization_id == organization_id,
                    AutonomousPlan.id == plan_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        if status not in ("pending", "approved", "applied", "rejected"):
            raise ValueError("invalid plan status")
        row.status = status
        if status in ("approved", "applied"):
            row.approved_by = user_id
            row.approved_at = utcnow()
        await db.flush()
        return {
            "id": row.id, "kind": row.kind, "title": row.title, "status": row.status,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        }


planning_engine = PlanningEngine()
