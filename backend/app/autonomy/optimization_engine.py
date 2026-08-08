"""Continuous optimization engine — constant small improvements.

Optimizations target team structure, project allocation, documentation,
meeting schedules, learning plans, budget usage and automation. Applied
optimizations are recorded in optimization_history.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.course import CourseEnrollment
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.meeting import Meeting
from app.models.optimization import OptimizationHistory
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.task import Task


class OptimizationEngine:
    async def generate(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        now = utcnow()
        suggestions: list[dict[str, Any]] = []

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        employees = await _count(Employee)
        tasks_open = await _count(Task, status="todo") + await _count(Task, status="in_progress")

        # allocation: rebalance overloaded assignees
        heavy = (
            await db.execute(
                select(Task.assignee_id, func.count(Task.id))
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id.isnot(None),
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
                .group_by(Task.assignee_id)
                .having(func.count(Task.id) >= 8)
            )
        ).all()
        if heavy:
            suggestions.append({
                "category": "project_allocation",
                "title": "Rebalance task allocation",
                "description": f"Redistribute work from {len(heavy)} overloaded assignees.",
                "savings": {"hours_per_week": len(heavy) * 3},
                "expected_benefit": "Balanced workload, fewer delays",
            })

        # meetings: consolidate recurring meetings
        meetings_week = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id,
                    Meeting.start_at >= now - timedelta(days=7),
                )
            )
        ).scalar() or 0
        if meetings_week >= 10:
            suggestions.append({
                "category": "meeting_schedule",
                "title": "Consolidate recurring meetings",
                "description": "Reduce weekly meeting count by merging status updates.",
                "savings": {"hours_per_week": meetings_week // 2},
                "expected_benefit": "Recovered focus time",
            })

        # learning plans: target low completion
        enrollments = await _count(CourseEnrollment)
        completed = await _count(CourseEnrollment, status="completed")
        if enrollments >= 1 and enrollments > completed:
            suggestions.append({
                "category": "learning_plan",
                "title": "Adjust learning plans to boost completion",
                "description": f"Improve {enrollments - completed} incomplete enrollments.",
                "savings": {"completion_rate": round(completed / enrollments * 100, 1)},
                "expected_benefit": "Higher skill growth",
            })

        # budget: shift underused funds
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        underused = [b for b in budgets if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount < 0.3]
        if underused:
            suggestions.append({
                "category": "budget_usage",
                "title": "Reallocate underused budget lines",
                "description": "Move funds from underused budgets to constrained ones.",
                "savings": {"reallocated": round(sum(b.allocated_amount or 0 for b in underused), 2)},
                "expected_benefit": "Better capital efficiency",
            })

        # documentation: unify document structure
        if await _count(__import__("app.models.knowledge", fromlist=["Document"]).Document) >= 5 and await _count(Project) >= 2:
            suggestions.append({
                "category": "documentation",
                "title": "Standardize documentation structure",
                "description": "Apply a consistent template across project docs.",
                "savings": {"search_time_pct": 10},
                "expected_benefit": "Faster information retrieval",
            })

        # automation: automate repeated manual steps
        if tasks_open >= 10 and employees >= 3:
            suggestions.append({
                "category": "automation",
                "title": "Automate routine task transitions",
                "description": "Automate status updates and reminders for recurring work.",
                "savings": {"hours_per_week": 2},
                "expected_benefit": "Less manual overhead",
            })

        # team structure: balance team sizes
        if await _count(Project) >= 4:
            suggestions.append({
                "category": "team_structure",
                "title": "Balance team sizes across projects",
                "description": "Equalize membership so no team is overloaded.",
                "savings": {"throughput_pct": 5},
                "expected_benefit": "Consistent delivery pace",
            })

        rows: list[OptimizationHistory] = []
        for suggestion in suggestions:
            row = OptimizationHistory(
                organization_id=organization_id,
                category=suggestion["category"],
                title=suggestion["title"],
                expected_benefit=suggestion["expected_benefit"],
                savings=suggestion["savings"],
                status="proposed",
                applied_at=None,
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        created = [{"id": r.id, **suggestion} for r, suggestion in zip(rows, suggestions)]
        if commit:
            await db.commit()
        return {"total": len(created), "optimizations": created}

    async def list(
        self, db: AsyncSession, organization_id: str, *, limit: int = 100
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(OptimizationHistory)
                .where(OptimizationHistory.organization_id == organization_id)
                .order_by(OptimizationHistory.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total": len(rows),
            "optimizations": [
                {
                    "id": r.id, "category": r.category, "title": r.title,
                    "expected_benefit": r.expected_benefit, "savings": r.savings or {},
                    "status": r.status,
                    "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }

    async def apply(
        self, db: AsyncSession, organization_id: str, optimization_id: str, *,
        user_id: str | None = None, commit: bool = False,
    ) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(OptimizationHistory).where(
                    OptimizationHistory.organization_id == organization_id,
                    OptimizationHistory.id == optimization_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "applied"
        row.applied_by = user_id
        row.applied_at = utcnow()
        await db.flush()
        await publish_background_event(
            db, name="optimization.completed", organization_id=organization_id,
            payload={"optimization_id": row.id, "category": row.category},
        )
        if commit:
            await db.commit()
        return {
            "id": row.id, "category": row.category, "title": row.title,
            "status": row.status, "applied_at": row.applied_at.isoformat(),
        }


optimization_engine = OptimizationEngine()
