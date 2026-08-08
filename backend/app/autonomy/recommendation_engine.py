"""Organization recommendation engine — continuous, evidence-backed suggestions.

Every recommendation carries evidence, confidence, business impact and
estimated benefit, and sensitive ones require human approval. Recommendations
are emitted as events and feed the executive dashboard, AI memory and graph.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.course import CourseEnrollment
from app.models.customer import CustomerHealth, Customer
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.goal import Goal
from app.models.knowledge import Document
from app.models.meeting import Meeting, MeetingActionItem
from app.models.project import Project
from app.models.recommendation import Recommendation, RECOMMENDATION_CATEGORIES
from app.models.task import Task
from app.models.workflow import WorkflowApproval


class RecommendationEngine:
    async def generate(
        self, db: AsyncSession, organization_id: str, *, commit: bool = False
    ) -> dict[str, Any]:
        now = utcnow()
        candidates = await self._candidates(db, organization_id, now)
        rows: list[Recommendation] = []
        for candidate in candidates:
            row = Recommendation(
                organization_id=organization_id,
                category=candidate["category"],
                title=candidate["title"],
                description=candidate.get("description"),
                rationale=candidate.get("rationale"),
                evidence=candidate.get("evidence", []),
                confidence=candidate.get("confidence", 0.6),
                impact=candidate.get("impact", "medium"),
                estimated_benefit=candidate.get("estimated_benefit"),
                approval_required=candidate.get("approval_required", True),
                status="pending",
                source_event="recommendation.created",
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        created = [{"id": r.id, **candidate} for r, candidate in zip(rows, candidates)]
        for row in created:
            await publish_background_event(
                db, name="recommendation.created", organization_id=organization_id,
                payload={"recommendation_id": row["id"], "category": row["category"],
                         "confidence": row.get("confidence", 0.6)},
            )
        if commit:
            await db.commit()
        return {"total": len(created), "recommendations": created}

    async def _candidates(
        self, db: AsyncSession, organization_id: str, now: Any
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        async def _count(model, **filters):
            stmt = select(func.count(model.id)).where(model.organization_id == organization_id)
            for key, value in filters.items():
                stmt = stmt.where(getattr(model, key) == value)
            return (await db.execute(stmt)).scalar() or 0

        employees = await _count(Employee)
        projects = await _count(Project)
        docs = await _count(Document)

        # team structure: tiny teams / solo projects
        solo_projects = (
            await db.execute(
                select(func.count(Project.id)).where(
                    Project.organization_id == organization_id, Project.status == "active"
                )
            )
        ).scalar() or 0
        if employees >= 3 and solo_projects >= 3:
            out.append({
                "category": "team_structure",
                "title": "Merge teams working on overlapping projects",
                "description": "Several active projects suggest siloed work.",
                "rationale": "Consolidation reduces coordination overhead and duplicate effort.",
                "evidence": [{"metric": "active_projects", "value": solo_projects}],
                "confidence": 0.55, "impact": "medium",
                "estimated_benefit": "Lower coordination overhead",
            })

        # meetings: overloaded calendar
        meetings_week = (
            await db.execute(
                select(func.count(Meeting.id)).where(
                    Meeting.organization_id == organization_id,
                    Meeting.start_at >= now - timedelta(days=7),
                )
            )
        ).scalar() or 0
        if meetings_week >= 8:
            out.append({
                "category": "meetings",
                "title": "Reduce meeting load",
                "description": "High weekly meeting volume burns focus time.",
                "rationale": "Focused async work replaces low-value meetings.",
                "evidence": [{"metric": "meetings_this_week", "value": meetings_week}],
                "confidence": 0.6, "impact": "medium",
                "estimated_benefit": "Recovered focus hours",
            })

        # documentation: projects without documents
        projects_without_docs = 0
        project_rows = (
            await db.execute(
                select(Project.id).where(Project.organization_id == organization_id).limit(100)
            )
        ).scalars().all()
        for pid in project_rows:
            doc_count = (
                await db.execute(
                    select(func.count(Document.id)).where(Document.project_id == pid)
                )
            ).scalar() or 0
            if doc_count == 0:
                projects_without_docs += 1
        if projects_without_docs >= 2:
            out.append({
                "category": "documentation",
                "title": "Generate missing documentation for under-documented projects",
                "description": f"{projects_without_docs} project(s) have no documents.",
                "rationale": "Documentation prevents knowledge loss and onboarding delays.",
                "evidence": [{"metric": "projects_without_docs", "value": projects_without_docs}],
                "confidence": 0.7, "impact": "medium",
                "estimated_benefit": "Protected institutional knowledge",
            })

        # learning: low completion
        enrollments = await _count(CourseEnrollment)
        completed = await _count(CourseEnrollment, status="completed")
        if enrollments >= 1 and enrollments > completed and employees >= 3:
            out.append({
                "category": "learning",
                "title": "Increase training completion",
                "description": f"Only {completed} of {enrollments} enrollments are completed.",
                "rationale": "Higher completion builds the skills the org needs.",
                "evidence": [{"metric": "completed_enrollments", "value": completed}],
                "confidence": 0.6, "impact": "medium",
                "estimated_benefit": "Stronger skill base",
            })

        # mentorship: no mentors, many juniors
        if employees >= 6 and await _count(Employee, title="Junior") >= 3:
            out.append({
                "category": "mentorship",
                "title": "Assign mentors to junior employees",
                "description": "Several junior employees would benefit from mentorship.",
                "rationale": "Mentorship accelerates growth and retention.",
                "evidence": [{"metric": "junior_employees", "value": await _count(Employee, title="Junior")}],
                "confidence": 0.65, "impact": "medium",
                "estimated_benefit": "Faster ramp + higher retention",
            })

        # hiring: overloaded teams
        overloaded = (
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
        if overloaded:
            out.append({
                "category": "hiring",
                "title": "Hire additional engineers to relieve overload",
                "description": f"{len(overloaded)} employee(s) each carry 8+ open tasks.",
                "rationale": "Sustained overload predicts burnout and attrition.",
                "evidence": [{"metric": "overloaded_employees", "value": len(overloaded)}],
                "confidence": 0.6, "impact": "high",
                "estimated_benefit": "Reduced burnout + faster delivery",
            })

        # budget: reallocate underused budgets
        budgets = (
            await db.execute(
                select(Budget).where(Budget.organization_id == organization_id, Budget.status == "active")
            )
        ).scalars().all()
        underused = [b for b in budgets if (b.allocated_amount or 0) > 0 and (b.used_amount or 0) / b.allocated_amount < 0.3]
        if underused:
            out.append({
                "category": "budget",
                "title": "Reallocate underused budget",
                "description": f"{len(underused)} active budget(s) are under 30% utilized.",
                "rationale": "Capital should follow activity.",
                "evidence": [{"metric": "underused_budgets", "value": len(underused)}],
                "confidence": 0.55, "impact": "medium",
                "estimated_benefit": "Better capital efficiency",
            })

        # automation: slow approvals
        slow_approvals = (
            await db.execute(
                select(func.count(WorkflowApproval.id)).where(
                    WorkflowApproval.organization_id == organization_id,
                    WorkflowApproval.status == "pending",
                )
            )
        ).scalar() or 0
        if slow_approvals >= 3:
            out.append({
                "category": "automation",
                "title": "Automate or escalate slow approvals",
                "description": f"{slow_approvals} approval(s) are waiting.",
                "rationale": "Waiting approvals stall dependent work.",
                "evidence": [{"metric": "pending_approvals", "value": slow_approvals}],
                "confidence": 0.6, "impact": "medium",
                "estimated_benefit": "Faster decision flow",
            })

        # promotion: long-tenured high performers
        long_tenure = (
            await db.execute(
                select(func.count(Employee.id)).where(
                    Employee.organization_id == organization_id,
                    Employee.created_at <= now - timedelta(days=730),
                )
            )
        ).scalar() or 0
        if long_tenure >= 2:
            out.append({
                "category": "promotion",
                "title": "Review long-tenured employees for promotion",
                "description": f"{long_tenure} employee(s) have 2+ years of tenure.",
                "rationale": "Recognition retains top performers.",
                "evidence": [{"metric": "employees_2y_tenure", "value": long_tenure}],
                "confidence": 0.4, "impact": "medium",
                "estimated_benefit": "Retention + motivation",
                "approval_required": True,
            })

        # risk mitigation: low customer health
        low_health = (
            await db.execute(
                select(func.count(CustomerHealth.id))
                .join(Customer, Customer.id == CustomerHealth.customer_id)
                .where(Customer.organization_id == organization_id, CustomerHealth.score < 50)
            )
        ).scalar() or 0
        if low_health:
            out.append({
                "category": "risk_mitigation",
                "title": "Proactively address declining customer health",
                "description": f"{low_health} customer(s) scored below 50.",
                "rationale": "Early intervention prevents churn.",
                "evidence": [{"metric": "customers_below_50", "value": low_health}],
                "confidence": 0.65, "impact": "high",
                "estimated_benefit": "Retained revenue",
            })

        # knowledge: stale documentation
        stale_docs = (
            await db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id,
                    Document.updated_at <= now - timedelta(days=90),
                )
            )
        ).scalar() or 0
        if stale_docs >= 3:
            out.append({
                "category": "knowledge",
                "title": "Refresh stale documentation",
                "description": f"{stale_docs} document(s) are 90+ days old.",
                "rationale": "Outdated knowledge misleads decisions.",
                "evidence": [{"metric": "stale_documents", "value": stale_docs}],
                "confidence": 0.6, "impact": "low",
                "estimated_benefit": "Accurate knowledge base",
            })

        # action items -> tasks
        open_items = await _count(MeetingActionItem, status="open")
        if open_items >= 2:
            out.append({
                "category": "workflow",
                "title": "Convert meeting action items into tracked tasks",
                "description": f"{open_items} action items are not yet tracked.",
                "rationale": "Untracked items fall through the cracks.",
                "evidence": [{"metric": "open_action_items", "value": open_items}],
                "confidence": 0.7, "impact": "low",
                "estimated_benefit": "Nothing falls through",
            })

        if docs == 0 and projects >= 1:
            out.append({
                "category": "documentation",
                "title": "Create the organization knowledge base",
                "description": "No knowledge documents exist yet.",
                "rationale": "Every organization needs durable knowledge.",
                "evidence": [{"metric": "documents", "value": 0}],
                "confidence": 0.8, "impact": "medium",
                "estimated_benefit": "Foundational knowledge",
            })

        return out

    async def list(
        self, db: AsyncSession, organization_id: str, *, category: str | None = None,
        status: str | None = None, limit: int = 100,
    ) -> dict[str, Any]:
        stmt = select(Recommendation).where(Recommendation.organization_id == organization_id)
        if category:
            stmt = stmt.where(Recommendation.category == category)
        if status:
            stmt = stmt.where(Recommendation.status == status)
        rows = (
            await db.execute(stmt.order_by(Recommendation.created_at.desc()).limit(limit))
        ).scalars().all()
        return {"total": len(rows), "recommendations": [self._serialize(r) for r in rows]}

    async def set_status(
        self, db: AsyncSession, organization_id: str, recommendation_id: str, status: str,
        *, user_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == organization_id,
                    Recommendation.id == recommendation_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        if status not in ("pending", "approved", "rejected", "applied", "dismissed"):
            raise ValueError("invalid status")
        row.status = status
        row.resolved_by = user_id
        row.resolved_at = utcnow()
        await db.flush()
        return self._serialize(row)


recommendation_engine = RecommendationEngine()
