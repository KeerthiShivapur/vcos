"""Organization health engine — 14 domain health dimensions + overall score.

Dimensions: employees, teams, departments, knowledge, learning, community,
finance, customers, infrastructure, projects, innovation, workflow,
collaboration, leadership. Every refresh persists an OrganizationHealth row and
emits ``organization.health.updated``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import CompanyMemory
from app.models.communication import Community, CommunityPost, Recognition
from app.models.course import Course, CourseEnrollment
from app.models.customer import Customer, CustomerHealth
from app.models.department import Department
from app.models.employee import Employee, EmployeePresence
from app.models.finance import Budget
from app.models.goal import Goal
from app.models.infrastructure import ClusterStatus, DeploymentRecord
from app.models.innovation import Innovation
from app.models.knowledge import Document, KnowledgeQuality, WikiPage
from app.models.meeting import Meeting
from app.models.organization_health import OrganizationHealth
from app.models.project import Project
from app.models.task import Task
from app.models.workflow import WorkflowExecution, WorkflowMetric


def _pct(done: int, total: int) -> float:
    return round(done / total * 100, 1) if total else 100.0


class HealthEngine:
    async def compute(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        now = utcnow()
        month_ago = now - timedelta(days=30)

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        async def _count_global(model, **filters):
            stmt = select(func.count(model.id))
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        employees = await _count(Employee)
        online = await _count(EmployeePresence, is_online=True)
        projects_total = await _count(Project)
        projects_active = await _count(Project, status="active")
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
        wiki = await _count(WikiPage)
        docs_quality = 0.0
        quality_rows = (
            await db.execute(
                select(KnowledgeQuality.score).join(
                    Document, Document.id == KnowledgeQuality.entity_id
                ).where(
                    Document.organization_id == organization_id,
                    KnowledgeQuality.entity_type == "document",
                )
            )
        ).scalars().all()
        if quality_rows:
            docs_quality = round(sum(quality_rows) / len(quality_rows) * 100, 1)

        meetings_30d = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id, Meeting.start_at >= month_ago
                )
            )
        ).scalar() or 0
        courses = await _count(Course)
        completed = (
            await db.execute(
                select(func.count(CourseEnrollment.id))
                .join(Course, Course.id == CourseEnrollment.course_id)
                .where(Course.organization_id == organization_id, CourseEnrollment.status == "completed")
            )
        ).scalar() or 0
        posts_30d = (
            await db.execute(
                select(func.count(CommunityPost.id))
                .join(Community, Community.id == CommunityPost.community_id)
                .where(Community.organization_id == organization_id, CommunityPost.created_at >= month_ago)
            )
        ).scalar() or 0
        recognitions = await _count(Recognition)

        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        allocated = sum(b.allocated_amount or 0 for b in budgets)
        used = sum(b.used_amount or 0 for b in budgets)
        finance_score = 100.0 if not allocated else max(0.0, 100 - round(used / allocated * 100, 1) - 20)

        customers_total = await _count(Customer)
        customer_scores = (
            await db.execute(
                select(CustomerHealth.score)
                .join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id)
            )
        ).scalars().all()
        customer_health = round(sum(customer_scores) / len(customer_scores) * 100, 1) if customer_scores else 100.0

        clusters = await _count_global(ClusterStatus)
        healthy_clusters = await _count_global(ClusterStatus, status="healthy")
        deployments_30d = (
            await db.execute(
                select(func.count(DeploymentRecord.id)).where(
                    DeploymentRecord.created_at >= month_ago,
                )
            )
        ).scalar() or 0
        infra_score = _pct(healthy_clusters, clusters) if clusters else 90.0

        goals = await _count(Goal)
        innovations = await _count(Innovation)
        active_innovations = await _count(Innovation, status="active")
        memories = await _count(CompanyMemory)
        workflow_rows = (
            await db.execute(
                select(WorkflowMetric).where(WorkflowMetric.organization_id == organization_id).limit(20)
            )
        ).scalars().all()
        workflow_health = 100.0
        if workflow_rows:
            values = [m.health_score for m in workflow_rows if getattr(m, "health_score", None) is not None]
            if values:
                workflow_health = round(sum(values) / len(values), 1)

        departments = await _count(Department)
        dimensions = {
            "employees": round(_pct(online, employees), 1) if employees else 90.0,
            "teams": round(_pct(projects_active, projects_total), 1) if projects_total else 90.0,
            "departments": 100.0 if departments else 80.0,
            "knowledge": round((docs_quality + _pct(docs + wiki, docs + wiki + 1)) / 2, 1),
            "learning": _pct(completed, courses + completed + 1),
            "community": round((_pct(posts_30d, posts_30d + 1) * 2 + _pct(recognitions, 1)) / 3, 1),
            "finance": finance_score,
            "customers": customer_health,
            "infrastructure": infra_score,
            "projects": _pct(projects_total - overdue, projects_total + 1),
            "innovation": _pct(active_innovations, innovations + 1) if innovations else 80.0,
            "workflow": workflow_health,
            "collaboration": round(_pct(meetings_30d, meetings_30d + 1) * 0.7 + _pct(employees, 1) * 0.3, 1),
            "leadership": round((memories / 5) * 100, 1) if memories < 5 else 95.0,
        }
        return {"score": round(sum(dimensions.values()) / len(dimensions), 1), "dimensions": dimensions}

    async def refresh(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        computed = await self.compute(db, organization_id)
        score = computed["score"]
        status = "excellent" if score >= 85 else "good" if score >= 70 else "watch" if score >= 50 else "at_risk"
        previous = (
            await db.execute(
                select(OrganizationHealth.computed_at)
                .where(OrganizationHealth.organization_id == organization_id)
                .order_by(OrganizationHealth.computed_at.desc())
                .limit(1)
            )
        ).scalars().first()
        trend = {"direction": "flat", "delta": 0.0}
        if previous is not None:
            earlier = (
                await db.execute(
                    select(OrganizationHealth.score)
                    .where(
                        OrganizationHealth.organization_id == organization_id,
                        OrganizationHealth.computed_at < previous,
                    )
                    .order_by(OrganizationHealth.computed_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if earlier is not None:
                delta = round(score - earlier, 1)
                trend = {"direction": "up" if delta > 0 else "down" if delta < 0 else "flat", "delta": delta}
        row = OrganizationHealth(
            organization_id=organization_id,
            score=score,
            status=status,
            dimensions=computed["dimensions"],
            trend=trend,
            computed_at=utcnow(),
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="company.health.updated", organization_id=organization_id,
            payload={"health_id": row.id, "score": score, "status": status},
        )
        if commit:
            await db.commit()
        return {"id": row.id, "score": score, "status": status, "dimensions": computed["dimensions"]}

    async def latest(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        row = (
            await db.execute(
                select(OrganizationHealth)
                .where(OrganizationHealth.organization_id == organization_id)
                .order_by(OrganizationHealth.computed_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if row is None:
            return await self.refresh(db, organization_id, commit=True)
        return {
            "id": row.id, "score": row.score, "status": row.status,
            "dimensions": row.dimensions or {}, "trend": row.trend or {},
            "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        }

    async def history(
        self, db: AsyncSession, organization_id: str, *, limit: int = 30
    ) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(OrganizationHealth)
                .where(OrganizationHealth.organization_id == organization_id)
                .order_by(OrganizationHealth.computed_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            "total": len(rows),
            "history": [
                {
                    "id": r.id, "score": r.score, "status": r.status,
                    "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                }
                for r in rows
            ],
        }


health_engine = HealthEngine()
