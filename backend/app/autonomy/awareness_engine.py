"""Organizational awareness engine — VCOS always knows the current company status.

Live status across projects, employees, knowledge, meetings, customers, budget,
hiring, learning and community. Snapshot into ``company_state`` + materialize
``organization_metrics`` for trends.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_state import CompanyState, OrganizationMetric
from app.models.course import CourseEnrollment, Course
from app.models.customer import Customer
from app.models.employee import Employee, EmployeePresence
from app.models.finance import Budget, Invoice
from app.models.goal import Goal
from app.models.knowledge import Document, Policy, WikiPage
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.task import Task


class AwarenessEngine:
    async def compute_state(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Compute the live company state (no persistence)."""
        now = utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        employees = (
            await db.execute(
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            )
        ).scalar() or 0
        online = (
            await db.execute(
                select(func.count(EmployeePresence.id))
                .join(Employee, Employee.id == EmployeePresence.employee_id)
                .where(Employee.organization_id == organization_id, EmployeePresence.is_online.is_(True))
            )
        ).scalar() or 0

        projects_total = (
            await db.execute(
                select(func.count(Project.id)).where(Project.organization_id == organization_id)
            )
        ).scalar() or 0
        projects_active = (
            await db.execute(
                select(func.count(Project.id)).where(
                    Project.organization_id == organization_id,
                    Project.status.in_(["active", "in_progress", "on_track"]),
                )
            )
        ).scalar() or 0
        overdue_tasks = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_(["done", "completed", "cancelled"]),
                )
            )
        ).scalar() or 0

        docs = (
            await db.execute(
                select(func.count(Document.id)).where(Document.organization_id == organization_id)
            )
        ).scalar() or 0
        wiki = (
            await db.execute(
                select(func.count(WikiPage.id)).where(WikiPage.organization_id == organization_id)
            )
        ).scalar() or 0
        policies = (
            await db.execute(
                select(func.count(Policy.id)).where(Policy.organization_id == organization_id)
            )
        ).scalar() or 0
        docs_week = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id, Document.created_at >= week_ago
                )
            )
        ).scalar() or 0

        meetings_total = (
            await db.execute(
                select(func.count(Meeting.id)).where(Meeting.organization_id == organization_id)
            )
        ).scalar() or 0
        meetings_week = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id, Meeting.start_at >= week_ago
                )
            )
        ).scalar() or 0

        customers_total = (
            await db.execute(
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            )
        ).scalar() or 0
        goals = (
            await db.execute(
                select(func.count(Goal.id)).where(Goal.organization_id == organization_id)
            )
        ).scalar() or 0

        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        budget_allocated = sum(b.allocated_amount or 0 for b in budgets)
        budget_used = sum(b.used_amount or 0 for b in budgets)
        budget_pct = round(budget_used / budget_allocated * 100, 1) if budget_allocated else 0.0

        invoices = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id,
                    Invoice.status.in_(["pending", "overdue"]),
                )
            )
        ).scalars().all()
        outstanding = sum(getattr(i, "amount_due", 0) or getattr(i, "amount", 0) or 0 for i in invoices)

        enrollments = (
            await db.execute(
                select(func.count(CourseEnrollment.id))
                .join(Course, Course.id == CourseEnrollment.course_id)
                .where(Course.organization_id == organization_id, CourseEnrollment.status == "completed")
            )
        ).scalar() or 0
        courses = (
            await db.execute(
                select(func.count(Course.id)).where(Course.organization_id == organization_id)
            )
        ).scalar() or 0

        hired_30d = (
            await db.execute(
                select(func.count(Employee.id)).where(
                    Employee.organization_id == organization_id, Employee.created_at >= month_ago
                )
            )
        ).scalar() or 0

        state = {
            "projects": {"total": projects_total, "active": projects_active},
            "employees": {"total": employees, "online": online},
            "knowledge": {"documents": docs, "wiki_pages": wiki, "policies": policies,
                          "added_7d": docs_week},
            "meetings": {"total": meetings_total, "this_week": meetings_week},
            "customers": {"total": customers_total},
            "goals": {"total": goals},
            "budget": {"allocated": budget_allocated, "used": budget_used,
                       "usage_percent": budget_pct, "outstanding_invoices": outstanding},
            "hiring": {"hired_30d": hired_30d},
            "learning": {"completed_enrollments": enrollments, "courses": courses},
            "tasks": {"overdue": overdue_tasks},
            "snapshot_at": now.isoformat(),
        }
        return state

    async def snapshot(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        """Persist a company-state snapshot + materialize metrics."""
        state = await self.compute_state(db, organization_id)
        snapshot = CompanyState(
            organization_id=organization_id,
            state=state,
            score=round(state["projects"]["active"] / max(state["projects"]["total"], 1) * 100, 1)
            if state["projects"]["total"]
            else 100.0,
            source="awareness",
            snapshot_at=utcnow(),
        )
        db.add(snapshot)
        metrics = [
            ("projects_total", state["projects"]["total"]),
            ("projects_active", state["projects"]["active"]),
            ("employees_total", state["employees"]["total"]),
            ("employees_online", state["employees"]["online"]),
            ("knowledge_documents", state["knowledge"]["documents"]),
            ("meetings_this_week", state["meetings"]["this_week"]),
            ("customers_total", state["customers"]["total"]),
            ("budget_usage_percent", state["budget"]["usage_percent"]),
            ("overdue_tasks", state["tasks"]["overdue"]),
            ("learning_completed", state["learning"]["completed_enrollments"]),
            ("hired_30d", state["hiring"]["hired_30d"]),
        ]
        now = utcnow()
        for name, value in metrics:
            db.add(
                OrganizationMetric(
                    organization_id=organization_id, name=name, value=float(value),
                    unit="count", period="daily", source="awareness", recorded_at=now,
                )
            )
        if commit:
            await db.commit()
        return {"snapshot_id": snapshot.id, "state": state, "score": snapshot.score}

    async def latest(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        row = (
            await db.execute(
                select(CompanyState)
                .where(CompanyState.organization_id == organization_id)
                .order_by(CompanyState.snapshot_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None:
            return await self.snapshot(db, organization_id, commit=True)
        return {
            "id": row.id,
            "state": row.state or {},
            "score": row.score,
            "source": row.source,
            "snapshot_at": row.snapshot_at.isoformat() if row.snapshot_at else None,
        }

    async def metrics(
        self, db: AsyncSession, organization_id: str, *, name: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        stmt = select(OrganizationMetric).where(OrganizationMetric.organization_id == organization_id)
        if name:
            stmt = stmt.where(OrganizationMetric.name == name)
        rows = (
            await db.execute(
                stmt.order_by(OrganizationMetric.recorded_at.desc()).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id, "name": r.name, "value": r.value, "unit": r.unit,
                "period": r.period, "source": r.source,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in rows
        ]


awareness_engine = AwarenessEngine()
