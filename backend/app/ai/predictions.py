"""Phase 7.8 — prediction engine.

Heuristic risk predictions persisted to ``ai_predictions``:

  project:      delay_risk          overdue/blocked ratio + open risks
  employee:     burnout_risk        utilization + meeting load
  employee:     overload            snapshot flag + utilization
  employee:     attrition_risk      inactivity + high utilization + long tenure
  organization: missed_deadline     org-wide overdue ratio

Predictions are deliberately explainable: score, level and rationale are
stored alongside the numeric factors that produced them.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.ai import AIPrediction
from app.models.employee import Employee
from app.models.meeting import Meeting, MeetingAttendee
from app.models.project import Project
from app.models.task import Task
from app.models.workload import WorkloadSnapshot


def _level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


class PredictionEngine:
    async def project_delay_risk(self, db, organization_id: str, project_id: str) -> dict[str, Any]:
        project = await db.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            return {}
        tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id, Task.project_id == project_id
                )
            )
        ).scalars().all()
        now = utcnow().date()
        total = len(tasks)
        overdue = [t for t in tasks if t.status not in ("completed", "archived") and t.due_date and t.due_date < now]
        blocked = [t for t in tasks if t.status == "blocked"]
        completed = [t for t in tasks if t.status == "completed"]
        factors = {
            "total_tasks": total,
            "overdue": len(overdue),
            "blocked": len(blocked),
            "completed": len(completed),
            "completion_rate": round(len(completed) / total * 100) if total else 0,
        }
        if total == 0:
            score = 0.0
        else:
            score = min(1.0, (len(overdue) * 0.5 + len(blocked) * 0.3) / max(1, total) + (0 if factors["completion_rate"] >= 50 else 0.2))
        rationale = (
            f"{len(overdue)} overdue and {len(blocked)} blocked task(s) out of {total} "
            f"({factors['completion_rate']}% complete)."
        )
        return await self._persist(
            db, organization_id=organization_id, subject_type="project", subject_id=project_id,
            metric="delay_risk", score=score, rationale=rationale, factors=factors,
        )

    async def employee_overload(self, db, organization_id: str, employee_id: str) -> dict[str, Any]:
        snapshot = (
            await db.execute(
                select(WorkloadSnapshot)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.employee_id == employee_id,
                )
                .order_by(WorkloadSnapshot.period_start.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        factors = {}
        if snapshot is not None:
            factors = {
                "utilization": round(snapshot.utilization),
                "tasks_count": snapshot.tasks_count,
                "meetings_hours": round(snapshot.meetings_hours, 1),
                "is_overloaded": bool(snapshot.is_overloaded),
            }
            score = min(1.0, snapshot.utilization / 110 + (0.2 if snapshot.is_overloaded else 0.0))
            rationale = (
                f"Utilization {round(snapshot.utilization)}% with {snapshot.tasks_count} task(s) "
                f"and {round(snapshot.meetings_hours)} meeting hours."
            )
        else:
            score = 0.0
            rationale = "No workload snapshot available yet."
        return await self._persist(
            db, organization_id=organization_id, subject_type="employee", subject_id=employee_id,
            metric="overload", score=score, rationale=rationale, factors=factors,
        )

    async def employee_burnout_risk(self, db, organization_id: str, employee_id: str) -> dict[str, Any]:
        snapshot = (
            await db.execute(
                select(WorkloadSnapshot)
                .where(
                    WorkloadSnapshot.organization_id == organization_id,
                    WorkloadSnapshot.employee_id == employee_id,
                )
                .order_by(WorkloadSnapshot.period_start.desc())
                .limit(2)
            )
        ).scalars().all()
        if not snapshot:
            score, factors, rationale = 0.0, {}, "No workload history available yet."
        else:
            latest = snapshot[0]
            prev = snapshot[1] if len(snapshot) > 1 else None
            trend = (latest.utilization - prev.utilization) if prev else 0.0
            factors = {
                "utilization": round(latest.utilization),
                "meetings_hours": round(latest.meetings_hours, 1),
                "trend_points": round(trend, 1),
            }
            score = min(
                1.0,
                latest.utilization / 130 + latest.meetings_hours / 40 + max(0.0, trend / 30),
            )
            rationale = (
                f"Utilization {round(latest.utilization)}% (trend {round(trend, 1)} pts), "
                f"{round(latest.meetings_hours)} meeting hours/week."
            )
        return await self._persist(
            db, organization_id=organization_id, subject_type="employee", subject_id=employee_id,
            metric="burnout_risk", score=score, rationale=rationale, factors=factors,
        )

    async def employee_attrition_risk(self, db, organization_id: str, employee_id: str) -> dict[str, Any]:
        employee = await db.get(Employee, employee_id)
        if employee is None or employee.organization_id != organization_id:
            return {}
        today = utcnow()
        months = 0
        if employee.joining_date:
            months = max(
                0,
                (today.year - employee.joining_date.year) * 12
                + (today.month - employee.joining_date.month),
            )
        open_tasks = (
            await db.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.assignee_id == employee_id,
                    Task.status.notin_(("completed", "archived")),
                )
            )
        ).scalar_one()
        factors = {
            "tenure_months": months,
            "open_tasks": int(open_tasks),
            "status": employee.status,
        }
        score = 0.0
        if employee.status == "active":
            if open_tasks == 0:
                score += 0.3
            if months and months > 30:
                score += 0.2
        rationale = (
            f"Tenure {months} months, {open_tasks} open task(s)."
            if employee.status == "active"
            else f"Employee status is '{employee.status}'."
        )
        return await self._persist(
            db, organization_id=organization_id, subject_type="employee", subject_id=employee_id,
            metric="attrition_risk", score=score, rationale=rationale, factors=factors,
        )

    async def organization_missed_deadline(self, db, organization_id: str) -> dict[str, Any]:
        now = utcnow().date()
        all_tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.due_date.is_not(None),
                )
            )
        ).scalars().all()
        overdue = [t for t in all_tasks if t.status not in ("completed", "archived") and t.due_date < now]
        factors = {
            "total_with_due": len(all_tasks),
            "overdue": len(overdue),
            "overdue_ratio": round(len(overdue) / len(all_tasks) * 100) if all_tasks else 0,
        }
        score = min(1.0, len(overdue) / max(1, len(all_tasks)) * 2) if all_tasks else 0.0
        rationale = f"{len(overdue)} overdue task(s) out of {len(all_tasks)} with due dates."
        return await self._persist(
            db, organization_id=organization_id, subject_type="organization", subject_id=organization_id,
            metric="missed_deadline", score=score, rationale=rationale, factors=factors,
        )

    async def predict_all(self, db, organization_id: str) -> dict[str, int]:
        results: dict[str, int] = {"project": 0, "employee": 0, "organization": 0}
        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id,
                    Project.status.notin_(("completed", "archived")),
                ).limit(50)
            )
        ).scalars().all()
        for project in projects:
            await self.project_delay_risk(db, organization_id, project.id)
            results["project"] += 1
        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id, Employee.status == "active"
                ).limit(100)
            )
        ).scalars().all()
        for employee in employees:
            await self.employee_overload(db, organization_id, employee.id)
            await self.employee_burnout_risk(db, organization_id, employee.id)
            await self.employee_attrition_risk(db, organization_id, employee.id)
            results["employee"] += 3
        await self.organization_missed_deadline(db, organization_id)
        results["organization"] += 1
        return results

    async def _persist(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        subject_type: str,
        subject_id: str,
        metric: str,
        score: float,
        rationale: str,
        factors: dict[str, Any],
    ) -> dict[str, Any]:
        row = AIPrediction(
            organization_id=organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
            metric=metric,
            score=round(score, 3),
            level=_level(score),
            rationale=rationale,
            factors_json=json.dumps(factors, default=str),
        )
        db.add(row)
        await db.flush()
        return {
            "id": row.id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "metric": metric,
            "score": row.score,
            "level": row.level,
            "rationale": rationale,
            "factors": factors,
        }


prediction_engine = PredictionEngine()
