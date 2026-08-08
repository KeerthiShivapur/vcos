"""Phase 20 — Universal search engine.

One search across everything: employees, projects, tasks, meetings,
knowledge, learning, finance, customers, assets, ideas, community, AI
memory, graph nodes, workflows and decisions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.customer import Customer
from app.models.decision_history import DecisionHistory
from app.models.department import Department
from app.models.employee import Employee
from app.models.finance import Budget
from app.models.innovation import Innovation
from app.models.knowledge import Document, Policy, WikiPage
from app.models.meeting import Meeting
from app.models.organization_node import OrganizationNode
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.workflow import Workflow
from app.models.company_memory import CompanyMemory, OrganizationTimeline

_DOMAINS = (
    "employees", "departments", "teams", "projects", "tasks", "meetings",
    "documents", "wiki", "policies", "courses", "customers", "budgets",
    "workflows", "innovations", "memories", "timeline", "decisions",
)


class SearchEngine:
    """Universal search across every organizational module."""

    async def search(
        self, db: AsyncSession, organization_id: str, q: str, *, limit: int = 20
    ) -> dict[str, Any]:
        needle = q.strip()
        if not needle:
            return {"query": q, "total": 0, "results": [], "domains": list(_DOMAINS)}
        pattern = f"%{needle}%"
        results: list[dict[str, Any]] = []

        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    or_(
                        Employee.first_name.ilike(pattern),
                        Employee.last_name.ilike(pattern),
                        Employee.display_name.ilike(pattern),
                        Employee.email.ilike(pattern),
                    ),
                ).limit(limit)
            )
        ).scalars().all()
        for r in employees:
            results.append({"domain": "employees", "entity_type": "employee",
                            "id": r.id, "name": r.full_name, "match": "employee"})

        departments = (
            await db.execute(
                select(Department).where(
                    Department.organization_id == organization_id,
                    Department.name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in departments:
            results.append({"domain": "departments", "entity_type": "department",
                            "id": r.id, "name": r.name, "match": "department"})

        teams = (
            await db.execute(
                select(Team).where(
                    Team.organization_id == organization_id,
                    Team.name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in teams:
            results.append({"domain": "teams", "entity_type": "team",
                            "id": r.id, "name": r.name, "match": "team"})

        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in projects:
            results.append({"domain": "projects", "entity_type": "project",
                            "id": r.id, "name": r.name, "match": "project"})

        tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in tasks:
            results.append({"domain": "tasks", "entity_type": "task",
                            "id": r.id, "name": r.title, "match": "task"})

        meetings = (
            await db.execute(
                select(Meeting).where(
                    Meeting.organization_id == organization_id,
                    Meeting.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in meetings:
            results.append({"domain": "meetings", "entity_type": "meeting",
                            "id": r.id, "name": r.title, "match": "meeting"})

        documents = (
            await db.execute(
                select(Document).where(
                    Document.organization_id == organization_id,
                    Document.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in documents:
            results.append({"domain": "documents", "entity_type": "document",
                            "id": r.id, "name": r.title, "match": "document"})

        wiki = (
            await db.execute(
                select(WikiPage).where(
                    WikiPage.organization_id == organization_id,
                    WikiPage.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in wiki:
            results.append({"domain": "wiki", "entity_type": "wiki",
                            "id": r.id, "name": r.title, "match": "wiki"})

        policies = (
            await db.execute(
                select(Policy).where(
                    Policy.organization_id == organization_id,
                    Policy.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in policies:
            results.append({"domain": "policies", "entity_type": "policy",
                            "id": r.id, "name": r.title, "match": "policy"})

        courses = (
            await db.execute(
                select(Course).where(
                    Course.organization_id == organization_id,
                    Course.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in courses:
            results.append({"domain": "courses", "entity_type": "course",
                            "id": r.id, "name": r.title, "match": "course"})

        customers = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    Customer.company_name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in customers:
            results.append({"domain": "customers", "entity_type": "customer",
                            "id": r.id, "name": r.company_name, "match": "customer"})

        budgets = (
            await db.execute(
                select(Budget).where(
                    Budget.organization_id == organization_id,
                    Budget.name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in budgets:
            results.append({"domain": "budgets", "entity_type": "budget",
                            "id": r.id, "name": r.name, "match": "budget"})

        workflows = (
            await db.execute(
                select(Workflow).where(
                    Workflow.organization_id == organization_id,
                    Workflow.name.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in workflows:
            results.append({"domain": "workflows", "entity_type": "workflow",
                            "id": r.id, "name": r.name, "match": "workflow"})

        innovations = (
            await db.execute(
                select(Innovation).where(
                    Innovation.organization_id == organization_id,
                    Innovation.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in innovations:
            results.append({"domain": "innovations", "entity_type": "innovation",
                            "id": r.id, "name": r.title, "match": "innovation"})

        memories = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == organization_id,
                    or_(CompanyMemory.title.ilike(pattern), CompanyMemory.content.ilike(pattern)),
                ).limit(limit)
            )
        ).scalars().all()
        for r in memories:
            results.append({"domain": "memories", "entity_type": "memory",
                            "id": r.id, "name": r.title, "match": "memory"})

        timeline = (
            await db.execute(
                select(OrganizationTimeline).where(
                    OrganizationTimeline.organization_id == organization_id,
                    OrganizationTimeline.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in timeline:
            results.append({"domain": "timeline", "entity_type": "timeline",
                            "id": r.id, "name": r.title, "match": "timeline"})

        decisions = (
            await db.execute(
                select(DecisionHistory).where(
                    DecisionHistory.organization_id == organization_id,
                    DecisionHistory.title.ilike(pattern),
                ).limit(limit)
            )
        ).scalars().all()
        for r in decisions:
            results.append({"domain": "decisions", "entity_type": "decision",
                            "id": r.id, "name": r.title, "match": "decision"})

        results.sort(key=lambda x: x["name"].lower().startswith(needle.lower()), reverse=True)
        return {"query": needle, "total": len(results), "results": results[:limit],
                "domains": list(_DOMAINS)}


search_engine = SearchEngine()
