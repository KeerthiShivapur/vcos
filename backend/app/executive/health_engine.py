"""Phase 8.2 — Company Health Engine.

AI calculates overall company health as a 100-point score built from the
organization's live data: project execution, task completion, meeting
effectiveness, knowledge growth, employee workload, community engagement,
learning progress, innovation, policy compliance and risk posture.

Every dimension is traceable to underlying organizational data so executives
always know *why* the score is what it is.
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIPrediction
from app.models.approval import Risk
from app.models.communication import CommunityPost, InnovationIdea, PostReaction, Recognition
from app.models.department import Department
from app.models.employee import Employee, EmployeeAchievement, EmployeeCertification
from app.models.executive import CompanyHealth
from app.models.goal import Goal
from app.models.knowledge import Decision, Document, Policy, SOP, Template, WikiPage
from app.models.meeting import Meeting, MeetingActionItem
from app.models.project import Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot
from app.work.intelligence_service import intelligence_service

logger = logging.getLogger("vcos.executive.health")

HEALTH_EXCELLENT = 90
HEALTH_GOOD = 75
HEALTH_WATCH = 55


def _status(score: float) -> str:
    if score >= HEALTH_EXCELLENT:
        return "excellent"
    if score >= HEALTH_GOOD:
        return "good"
    if score >= HEALTH_WATCH:
        return "watch"
    return "at_risk"


class HealthEngine:
    async def compute_company_health(
        self, db: AsyncSession, *, organization_id: str, persist: bool = True
    ) -> dict[str, Any]:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        projects = (await db.execute(
            select(Project).where(Project.organization_id == organization_id)
        )).scalars().all()
        active_projects = [p for p in projects if p.status not in ("completed", "cancelled", "archived")]

        # Project execution: average project health of active projects.
        project_healths = []
        for p in active_projects[:30]:
            try:
                project_healths.append(
                    (await intelligence_service.project_health(
                        db, organization_id=organization_id, project_id=p.id
                    ))["health"]
                )
            except Exception as exc:  # pragma: no cover - per-project isolation
                logger.warning("project health failed for %s: %s", p.id, exc)
        project_execution = round(sum(project_healths) / len(project_healths), 1) if project_healths else 100.0

        # Task completion: completion rate penalized by overdue/blocked work.
        task_total = (
            await db.execute(select(func.count(Task.id)).where(Task.organization_id == organization_id))
        ).scalar() or 0
        task_completed = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id, Task.status == "completed"
            ))
        ).scalar() or 0
        task_overdue = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.due_date.isnot(None),
                Task.due_date < now.date(),
                Task.status.notin_(("completed", "archived")),
            ))
        ).scalar() or 0
        task_blocked = (
            await db.execute(select(func.count(Task.id)).where(
                Task.organization_id == organization_id, Task.status == "blocked"
            ))
        ).scalar() or 0
        completion_rate = (task_completed / task_total * 100) if task_total else 100.0
        task_completion = completion_rate
        if task_overdue:
            task_completion -= min(20, task_overdue * 4)
        if task_blocked:
            task_completion -= min(15, task_blocked * 3)
        task_completion = round(max(0, min(100, task_completion)), 1)

        # Meeting effectiveness: completed meetings with summaries/action items.
        meetings = (await db.execute(
            select(Meeting).where(
                Meeting.organization_id == organization_id,
                Meeting.status == "completed",
                Meeting.end_at >= week_ago,
            )
        )).scalars().all()
        effective = [m for m in meetings if m.ai_summary or m.transcript_summary]
        meeting_effectiveness = round(
            (len(effective) / len(meetings)) * 100 if meetings else 90.0, 1
        )

        # Knowledge growth: published knowledge volume (recent vs baseline).
        async def _knowledge_total(models) -> int:
            total = 0
            for model in models:
                total += (
                    await db.execute(select(func.count(model.id)).where(
                        model.organization_id == organization_id
                    ))
                ).scalar() or 0
            return total

        knowledge_total = await _knowledge_total([Document, WikiPage, Policy, SOP, Template, Decision])

        # Employee workload: ratio of overloaded employees in recent snapshots.
        overloaded = (
            await db.execute(select(func.count(func.distinct(WorkloadSnapshot.employee_id))).where(
                WorkloadSnapshot.organization_id == organization_id,
                WorkloadSnapshot.period_start >= week_ago,
                WorkloadSnapshot.is_overloaded.is_(True),
            ))
        ).scalar() or 0
        employees_total = (
            await db.execute(select(func.count(Employee.id)).where(
                Employee.organization_id == organization_id, Employee.status == "active"
            ))
        ).scalar() or 0
        workload_ratio = (overloaded / employees_total) if employees_total else 0.0
        employee_workload = round(max(0, 100 - workload_ratio * 150), 1)

        # Community engagement: posts + reactions + recognitions this month.
        posts_month = (
            await db.execute(select(func.count(CommunityPost.id)).where(
                CommunityPost.organization_id == organization_id,
                CommunityPost.created_at >= month_ago,
            ))
        ).scalar() or 0
        reactions_month = (
            await db.execute(select(func.count(PostReaction.id)).where(
                PostReaction.organization_id == organization_id,
                PostReaction.created_at >= month_ago,
            ))
        ).scalar() or 0
        recognition_month = (
            await db.execute(select(func.count(Recognition.id)).where(
                Recognition.organization_id == organization_id,
                Recognition.created_at >= month_ago,
            ))
        ).scalar() or 0
        community_engagement = round(
            max(0, min(100, (posts_month * 12 + reactions_month * 2 + recognition_month * 8))), 1
        )

        # Learning progress: achievements + certifications + expertise scores.
        achievements = (
            await db.execute(select(func.count(EmployeeAchievement.id)).where(
                EmployeeAchievement.organization_id == organization_id
            ))
        ).scalar() or 0
        certifications = (
            await db.execute(select(func.count(EmployeeCertification.id)).where(
                EmployeeCertification.organization_id == organization_id
            ))
        ).scalar() or 0
        avg_expertise = (
            await db.execute(select(func.avg(Employee.expertise_score)).where(
                Employee.organization_id == organization_id
            ))
        ).scalar() or 0
        learning_progress = round(
            max(0, min(100, float(avg_expertise or 0) * 20 + achievements * 3 + certifications * 5)), 1
        )

        # Innovation: submitted ideas.
        ideas_total = (
            await db.execute(select(func.count(InnovationIdea.id)).where(
                InnovationIdea.organization_id == organization_id
            ))
        ).scalar() or 0
        innovation = round(max(0, min(100, ideas_total * 10)), 1)

        # Policy compliance: published policies vs drafts, approvals pass rate.
        policies = (await db.execute(
            select(Policy).where(Policy.organization_id == organization_id)
        )).scalars().all()
        published_policies = sum(1 for p in policies if getattr(p, "status", "draft") == "published")
        policy_compliance = round(
            (published_policies / len(policies)) * 100 if policies else 100.0, 1
        )

        # Risk posture: penalize open / high risks.
        risk_open = (
            await db.execute(select(func.count(Risk.id)).where(
                Risk.organization_id == organization_id, Risk.status != "closed"
            ))
        ).scalar() or 0
        risk_high = (
            await db.execute(select(func.count(Risk.id)).where(
                Risk.organization_id == organization_id,
                Risk.status != "closed",
                Risk.risk_score >= 9,
            ))
        ).scalar() or 0
        risk_management = round(max(0, min(100, 100 - risk_open * 5 - risk_high * 10)), 1)

        # Strategic goals health.
        goals = (await db.execute(
            select(Goal).where(Goal.organization_id == organization_id)
        )).scalars().all()
        goal_progress = round(
            sum(g.progress or 0 for g in goals) / len(goals) if goals else 100.0, 1
        )

        breakdown = {
            "project_execution": project_execution,
            "task_completion": task_completion,
            "meeting_effectiveness": meeting_effectiveness,
            "knowledge_growth": min(100.0, knowledge_total * 4),
            "employee_workload": employee_workload,
            "community_engagement": community_engagement,
            "learning_progress": learning_progress,
            "innovation": innovation,
            "policy_compliance": policy_compliance,
            "risk_management": risk_management,
            "goals": goal_progress,
        }

        weights = {
            "project_execution": 0.15,
            "task_completion": 0.15,
            "meeting_effectiveness": 0.05,
            "knowledge_growth": 0.10,
            "employee_workload": 0.10,
            "community_engagement": 0.05,
            "learning_progress": 0.10,
            "innovation": 0.05,
            "policy_compliance": 0.05,
            "risk_management": 0.15,
            "goals": 0.05,
        }
        score = round(
            sum(breakdown[k] * weights[k] for k in weights if k in breakdown), 1
        )

        result = {
            "organization_id": organization_id,
            "score": score,
            "status": _status(score),
            "breakdown": {k: round(v, 1) for k, v in breakdown.items()},
            "counts": {
                "active_projects": len(active_projects),
                "tasks_total": task_total,
                "tasks_completed": task_completed,
                "tasks_overdue": task_overdue,
                "tasks_blocked": task_blocked,
                "employees_active": employees_total,
                "overloaded_employees": overloaded,
                "meetings_completed_7d": len(meetings),
                "knowledge_total": knowledge_total,
                "open_risks": risk_open,
                "high_risks": risk_high,
                "goals": len(goals),
                "ideas": ideas_total,
            },
            "computed_at": now.isoformat(),
        }

        if persist:
            await self.persist(db, organization_id=organization_id, health=result)
        return result

    async def persist(self, db: AsyncSession, *, organization_id: str, health: dict[str, Any]) -> None:
        row = CompanyHealth(
            organization_id=organization_id,
            score=health["score"],
            status=health["status"],
            breakdown_json=json.dumps(health["breakdown"]),
            period_start=health["computed_at"],
            period_end=health["computed_at"],
        )
        db.add(row)

    async def department_health(
        self, db: AsyncSession, *, organization_id: str, department_id: str
    ) -> dict[str, Any]:
        dept = await db.get(Department, department_id)
        if dept is None or dept.organization_id != organization_id:
            raise ValueError("Department not found")

        employees = (await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id,
                Employee.department_id == department_id,
                Employee.status == "active",
            )
        )).scalars().all()
        employee_ids = [e.id for e in employees]

        tasks = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.assignee_id.in_(employee_ids) if employee_ids else Task.organization_id.isnot(None),
            )
        )).scalars().all()
        open_tasks = [t for t in tasks if t.status not in ("completed", "archived")]
        overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < utcnow().date()]
        completed = sum(1 for t in tasks if t.status == "completed")

        meetings = (await db.execute(
            select(Meeting).where(Meeting.organization_id == organization_id, Meeting.department_id == department_id)
        )).scalars().all()

        projects = (await db.execute(
            select(Project).where(Project.organization_id == organization_id, Project.department_id == department_id)
        )).scalars().all()

        goals = (await db.execute(
            select(Goal).where(Goal.organization_id == organization_id, Goal.department_id == department_id)
        )).scalars().all()

        # Velocity: completed tasks per active employee.
        velocity = round((completed / len(employees)) if employees else 0, 1)
        completion_rate = round((completed / len(tasks)) * 100 if tasks else 100.0, 1)
        workload = round(
            100 - (len(overdue_tasks) / len(open_tasks)) * 100 if open_tasks else 90.0, 1
        )
        health = max(0, min(100, round(
            completion_rate * 0.45
            + min(100, velocity * 10) * 0.20
            + workload * 0.20
            + (90.0 if len(projects) or len(goals) else 60.0) * 0.15
        , 1)))
        return {
            "department_id": department_id,
            "name": dept.name,
            "health": health,
            "status": _status(health),
            "head_count": len(employees),
            "projects": len(projects),
            "open_tasks": len(open_tasks),
            "overdue_tasks": len(overdue_tasks),
            "completion_rate": completion_rate,
            "velocity_per_employee": velocity,
            "meetings": len(meetings),
            "goals": len(goals),
            "goals_progress": round(sum(g.progress or 0 for g in goals) / len(goals), 1) if goals else 0.0,
        }

    async def departments_health(
        self, db: AsyncSession, *, organization_id: str
    ) -> list[dict[str, Any]]:
        departments = (await db.execute(
            select(Department).where(Department.organization_id == organization_id)
        )).scalars().all()
        results = []
        for dept in departments:
            try:
                results.append(
                    await self.department_health(
                        db, organization_id=organization_id, department_id=dept.id
                    )
                )
            except Exception as exc:  # pragma: no cover - per-department isolation
                logger.warning("department health failed for %s: %s", dept.id, exc)
        return results

    async def project_health(
        self, db: AsyncSession, *, organization_id: str, project_id: str
    ) -> dict[str, Any]:
        project = await db.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            raise ValueError("Project not found")
        return await intelligence_service.project_health(
            db, organization_id=organization_id, project_id=project_id
        )


health_engine = HealthEngine()
