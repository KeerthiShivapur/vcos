"""Onboarding academy service (Phase 10.10 — Onboarding Academy).

The AI builds a personalized onboarding plan for every new employee from
the organization's knowledge (policies, documents, wiki), their role, team
and department. The plan includes company introduction, policies, security
training, people to meet, projects to explore, a mentor, training courses
and quizzes. Managers and HR track progress; completing the plan updates
the learning profile and emits onboarding.completed.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.models.course import Course
from app.models.department import Department
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.knowledge import Policy, SOP, WikiPage
from app.models.learning_profile import LearningHistoryEntry, LearningProfile
from app.models.onboarding import OnboardingPlan, OnboardingTask
from app.models.project import Project
from app.models.team import Team

logger = logging.getLogger("vcos.learning.onboarding")

_event_bus = EventBus()


class OnboardingService:
    async def create_plan(self, db: AsyncSession, *, organization_id: str, employee_id: str, target_days: int = 14) -> Optional[OnboardingPlan]:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.id == employee_id
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            return None
        existing = (
            await db.execute(
                select(OnboardingPlan).where(
                    OnboardingPlan.organization_id == organization_id,
                    OnboardingPlan.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.status == "draft":
                existing.status = "active"
            await db.flush()
            return existing

        plan = OnboardingPlan(
            organization_id=organization_id,
            employee_id=employee_id,
            status="active",
            progress=0.0,
            start_date=utcnow().date(),
            target_date=utcnow().date() + timedelta(days=target_days),
            mentor_id=self._pick_mentor(db, organization_id=organization_id, employee=employee),
        )
        db.add(plan)
        await db.flush()
        await self._build_checklist(db, organization_id=organization_id, plan=plan, employee=employee)
        return plan

    def _pick_mentor(self, db: AsyncSession, *, organization_id: str, employee: Employee) -> Optional[str]:
        """Prefer the manager, then an experienced peer from the same team."""
        if employee.manager_id:
            return employee.manager_id
        return None

    async def _build_checklist(self, db: AsyncSession, *, organization_id: str, plan: OnboardingPlan, employee: Employee) -> None:
        position = 0

        def add(title: str, kind: str, reference_id: Optional[str] = None, description: Optional[str] = None, category: str = "onboarding") -> None:
            nonlocal position
            position += 1
            db.add(
                OnboardingTask(
                    organization_id=organization_id,
                    plan_id=plan.id,
                    title=title,
                    description=description,
                    category=category,
                    kind=kind,
                    reference_id=reference_id,
                    position=position,
                    completed=False,
                )
            )

        add("Welcome to the company — read the company introduction", "document", category="introduction")
        add("Review our core policies", "policy", category="introduction")
        add("Complete security awareness training", "training", category="introduction")

        policies = (
            await db.execute(
                select(Policy).where(
                    Policy.organization_id == organization_id, Policy.status == "published"
                ).limit(5)
            )
        ).scalars().all()
        for policy in policies:
            add(f"Read policy: {policy.title}", "policy", policy.id, "Company policy checklist")

        wiki = (
            await db.execute(
                select(WikiPage).where(
                    WikiPage.organization_id == organization_id, WikiPage.status == "published"
                ).limit(5)
            )
        ).scalars().all()
        for page in wiki:
            add(f"Read wiki: {page.title}", "knowledge", page.id)

        team = None
        if employee.team_id:
            team = await db.get(Team, employee.team_id)
        department = None
        if employee.department_id:
            department = await db.get(Department, employee.department_id)
        if team:
            add(f"Meet your team — {team.name}", "people", team.id)
        if department:
            add(f"Department orientation — {department.name}", "meeting", department.id)
        if employee.manager_id:
            add("Introduce yourself to your manager", "meeting", employee.manager_id)

        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id, Project.status == "active"
                ).limit(3)
            )
        ).scalars().all()
        for project in projects:
            add(f"Explore project: {project.name}", "project", project.id)

        courses = (
            await db.execute(
                select(Course).where(
                    Course.organization_id == organization_id, Course.status == "published"
                ).limit(3)
            )
        ).scalars().all()
        for course in courses:
            add(f"Training: {course.title}", "training", course.id)

        if plan.mentor_id:
            mentor = await db.get(Employee, plan.mentor_id)
            add(
                f"First mentoring session with {mentor.full_name if mentor else 'your mentor'}",
                "mentor",
                plan.mentor_id,
            )
        add("Complete the onboarding quiz", "quiz")
        add("Set up your goals for the first quarter", "checklist")
        add("Mark onboarding complete", "checklist")

    async def list_plans(self, db: AsyncSession, *, organization_id: str, status: str = "active") -> list[dict[str, Any]]:
        query = select(OnboardingPlan).where(OnboardingPlan.organization_id == organization_id)
        if status:
            query = query.where(OnboardingPlan.status == status)
        rows = (await db.execute(query.order_by(OnboardingPlan.created_at.desc()))).scalars().all()
        result = []
        for plan in rows:
            employee = await db.get(Employee, plan.employee_id)
            done, total = await self._progress(db, organization_id=organization_id, plan=plan)
            result.append(
                {
                    "id": plan.id,
                    "employee_id": plan.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "designation": employee.designation if employee else None,
                    "status": plan.status,
                    "progress": round(done / total * 100, 1) if total else 0.0,
                    "start_date": plan.start_date.isoformat() if plan.start_date else None,
                    "target_date": plan.target_date.isoformat() if plan.target_date else None,
                    "mentor_id": plan.mentor_id,
                    "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
                }
            )
        return result

    async def get_plan(self, db: AsyncSession, *, organization_id: str, plan_id: str) -> Optional[dict[str, Any]]:
        plan = (
            await db.execute(
                select(OnboardingPlan).where(
                    OnboardingPlan.organization_id == organization_id, OnboardingPlan.id == plan_id
                )
            )
        ).scalar_one_or_none()
        if plan is None:
            return None
        tasks = (
            await db.execute(
                select(OnboardingTask)
                .where(OnboardingTask.organization_id == organization_id, OnboardingTask.plan_id == plan.id)
                .order_by(OnboardingTask.position)
            )
        ).scalars().all()
        done, total = await self._progress(db, organization_id=organization_id, plan=plan)
        return {
            "id": plan.id,
            "employee_id": plan.employee_id,
            "status": plan.status,
            "plan_status": plan.status,
            "progress": round(done / total * 100, 1) if total else 0.0,
            "start_date": plan.start_date.isoformat() if plan.start_date else None,
            "target_date": plan.target_date.isoformat() if plan.target_date else None,
            "mentor_id": plan.mentor_id,
            "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "category": task.category,
                    "kind": task.kind,
                    "reference_id": task.reference_id,
                    "position": task.position,
                    "completed": task.completed,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                }
                for task in tasks
            ],
        }

    async def _progress(self, db: AsyncSession, *, organization_id: str, plan: OnboardingPlan) -> tuple[int, int]:
        tasks = (
            await db.execute(
                select(OnboardingTask).where(
                    OnboardingTask.organization_id == organization_id, OnboardingTask.plan_id == plan.id
                )
            )
        ).scalars().all()
        return sum(1 for task in tasks if task.completed), len(tasks)

    async def complete_task(self, db: AsyncSession, *, organization_id: str, plan_id: str, task_id: str) -> Optional[dict[str, Any]]:
        task = (
            await db.execute(
                select(OnboardingTask).where(
                    OnboardingTask.organization_id == organization_id,
                    OnboardingTask.plan_id == plan_id,
                    OnboardingTask.id == task_id,
                )
            )
        ).scalar_one_or_none()
        if task is None:
            return None
        if not task.completed:
            task.completed = True
            task.completed_at = utcnow()
        plan = (
            await db.execute(
                select(OnboardingPlan).where(
                    OnboardingPlan.organization_id == organization_id, OnboardingPlan.id == plan_id
                )
            )
        ).scalar_one_or_none()
        if plan:
            done, total = await self._progress(db, organization_id=organization_id, plan=plan)
            plan.progress = round(done / total * 100, 1) if total else 0.0
            if plan.progress >= 100.0 and plan.status != "completed":
                await self.complete_plan(db, organization_id=organization_id, plan=plan)
        await db.flush()
        return await self.get_plan(db, organization_id=organization_id, plan_id=plan_id)

    async def complete_plan(self, db: AsyncSession, *, organization_id: str, plan: OnboardingPlan) -> OnboardingPlan:
        plan.status = "completed"
        plan.progress = 100.0
        plan.completed_at = utcnow()
        from app.learning.profile_service import profile_service
        profile = await profile_service.ensure_profile(
            db, organization_id=organization_id, employee_id=plan.employee_id
        )
        profile.learning_score = min(100.0, (profile.learning_score or 0) + 8.0)
        profile.last_learning_date = utcnow()
        db.add(
            LearningHistoryEntry(
                organization_id=organization_id,
                employee_id=plan.employee_id,
                kind="onboarding",
                title="Completed onboarding",
                entity_id=plan.id,
                occurred_at=utcnow(),
            )
        )
        await _event_bus.publish(
            db,
            name="onboarding.completed",
            organization_id=organization_id,
            actor_id=plan.employee_id,
            payload={"employee_id": plan.employee_id, "plan_id": plan.id},
            flush=False,
        )
        await db.flush()
        return plan


onboarding_service = OnboardingService()
