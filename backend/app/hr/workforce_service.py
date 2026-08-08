"""Workforce service (Phase 11.9 — Workforce Planning & Organization Intelligence).

Workforce plans, succession pipelines with readiness ratings, periodic
workforce snapshots (headcount, hires, exits, attrition, department
distribution) and AI-lite hiring-need signals derived from open roles and
attrition pressure.
"""

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.department import Department
from app.models.employee import Employee
from app.models.hr import Job, Offboarding, SuccessionCandidate, WorkforcePlan, WorkforceSnapshot
from app.models.team import Team

logger = logging.getLogger("vcos.hr.workforce")

PLAN_STATUSES = ["draft", "approved", "active", "completed"]
SUCCESSION_STATUSES = ["identified", "developing", "ready"]


class WorkforceService:
    # ------------------------------------------------------------------ plans

    async def create_plan(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], created_by: Optional[str] = None) -> WorkforcePlan:
        plan = WorkforcePlan(
            organization_id=organization_id,
            title=data["title"],
            horizon=data.get("horizon", "quarter"),
            department=data.get("department"),
            headcount_target=int(data.get("headcount_target", 0)),
            skill_needs=data.get("skill_needs") or [],
            budget=float(data.get("budget", 0.0)),
            status=data.get("status", "draft") if data.get("status") in PLAN_STATUSES else "draft",
            notes=data.get("notes"),
            created_by=created_by,
        )
        db.add(plan)
        await db.flush()
        return plan

    async def list_plans(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None) -> list[WorkforcePlan]:
        query = select(WorkforcePlan).where(WorkforcePlan.organization_id == organization_id)
        if status:
            query = query.where(WorkforcePlan.status == status)
        return (await db.execute(query.order_by(WorkforcePlan.created_at.desc()))).scalars().all()

    async def get_plan(self, db: AsyncSession, *, organization_id: str, plan_id: str) -> Optional[WorkforcePlan]:
        return (
            await db.execute(
                select(WorkforcePlan).where(WorkforcePlan.organization_id == organization_id, WorkforcePlan.id == plan_id)
            )
        ).scalar_one_or_none()

    async def update_plan(self, db: AsyncSession, *, organization_id: str, plan_id: str, data: dict[str, Any]) -> Optional[WorkforcePlan]:
        plan = await self.get_plan(db, organization_id=organization_id, plan_id=plan_id)
        if plan is None:
            return None
        for field in ("title", "horizon", "department", "headcount_target", "skill_needs", "budget", "status", "notes"):
            if field in data:
                setattr(plan, field, data[field])
        await db.flush()
        return plan

    # ------------------------------------------------------------------ succession

    async def add_succession_candidate(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
    ) -> SuccessionCandidate:
        candidate_employee = await db.get(Employee, data["candidate_employee_id"])
        if candidate_employee is None or candidate_employee.organization_id != organization_id:
            raise ValueError("unknown candidate employee")
        existing = (
            await db.execute(
                select(SuccessionCandidate).where(
                    SuccessionCandidate.organization_id == organization_id,
                    SuccessionCandidate.position_title == data["position_title"],
                    SuccessionCandidate.candidate_employee_id == data["candidate_employee_id"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            await self.update_candidate(
                db, organization_id=organization_id, candidate_id=existing.id,
                data={"readiness": data.get("readiness", existing.readiness),
                      "rationale": data.get("rationale"), "status": data.get("status")},
            )
            return existing
        candidate = SuccessionCandidate(
            organization_id=organization_id,
            position_title=data["position_title"],
            employee_id=data.get("employee_id"),
            candidate_employee_id=data["candidate_employee_id"],
            readiness=int(data.get("readiness", 0)),
            rationale=data.get("rationale"),
            status=data.get("status", "identified") if data.get("status") in SUCCESSION_STATUSES else "identified",
        )
        db.add(candidate)
        await db.flush()
        if int(candidate.readiness) >= 80:
            candidate.status = "ready"
        elif int(candidate.readiness) >= 40 and candidate.status == "identified":
            candidate.status = "developing"
        await db.flush()
        return candidate

    async def update_candidate(
        self, db: AsyncSession, *, organization_id: str, candidate_id: str, data: dict[str, Any],
    ) -> Optional[SuccessionCandidate]:
        candidate = (
            await db.execute(
                select(SuccessionCandidate).where(
                    SuccessionCandidate.organization_id == organization_id, SuccessionCandidate.id == candidate_id
                )
            )
        ).scalar_one_or_none()
        if candidate is None:
            return None
        for field in ("readiness", "rationale", "status", "position_title", "employee_id"):
            if field in data:
                setattr(candidate, field, data[field])
        candidate.last_updated_at = utcnow()
        if "status" not in data:
            if int(candidate.readiness) >= 80:
                candidate.status = "ready"
            elif int(candidate.readiness) >= 40:
                candidate.status = "developing"
            else:
                candidate.status = "identified"
        await db.flush()
        return candidate

    async def list_succession(self, db: AsyncSession, *, organization_id: str, position_title: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(SuccessionCandidate).where(SuccessionCandidate.organization_id == organization_id)
        if position_title:
            query = query.where(SuccessionCandidate.position_title == position_title)
        rows = await db.execute(query.order_by(SuccessionCandidate.position_title, SuccessionCandidate.readiness.desc()))
        result = []
        for candidate in rows.scalars().all():
            employee = await db.get(Employee, candidate.candidate_employee_id)
            result.append(
                {
                    "id": candidate.id,
                    "position_title": candidate.position_title,
                    "employee_id": candidate.employee_id,
                    "candidate_employee_id": candidate.candidate_employee_id,
                    "candidate_name": employee.full_name if employee else None,
                    "candidate_designation": employee.designation if employee else None,
                    "readiness": candidate.readiness,
                    "status": candidate.status,
                    "rationale": candidate.rationale,
                    "last_updated_at": candidate.last_updated_at.isoformat() if candidate.last_updated_at else None,
                }
            )
        return result

    # ------------------------------------------------------------------ snapshots

    async def compute_snapshot(self, db: AsyncSession, *, organization_id: str, snapshot_date: Optional[date] = None) -> WorkforceSnapshot:
        """Compute and store a workforce snapshot for the given date."""
        snapshot_date = snapshot_date or utcnow().date()
        existing = (
            await db.execute(
                select(WorkforceSnapshot).where(
                    WorkforceSnapshot.organization_id == organization_id, WorkforceSnapshot.date == snapshot_date
                )
            )
        ).scalar_one_or_none()
        month_start = snapshot_date.replace(day=1)
        next_month = (month_start.replace(day=28) + __import__("datetime").timedelta(days=5)).replace(day=1)

        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id, Employee.status == "active")
            )
        ).scalars().all()
        headcount = len(employees)
        hires = (
            await db.execute(
                select(func.count()).select_from(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.created_at >= month_start,
                    Employee.created_at < next_month,
                )
            )
        ).scalar_one() or 0
        exits = (
            await db.execute(
                select(func.count()).select_from(Offboarding).where(
                    Offboarding.organization_id == organization_id,
                    Offboarding.status == "completed",
                    Offboarding.completed_at >= month_start,
                    Offboarding.completed_at < next_month,
                )
            )
        ).scalar_one() or 0
        attrition = round(exits * 100.0 / headcount, 1) if headcount else 0.0

        departments: dict[str, Any] = {}
        dept_rows = (
            await db.execute(
                select(Department, func.count(Employee.id))
                .outerjoin(Employee, Employee.department_id == Department.id)
                .where(Department.organization_id == organization_id, Employee.status == "active")
                .group_by(Department.id)
            )
        ).all()
        open_jobs = (
            await db.execute(
                select(Job).where(Job.organization_id == organization_id, Job.status == "open")
            )
        ).scalars().all()
        for dept, count in dept_rows:
            departments[dept.name] = {
                "count": count,
                "open_roles": sum(1 for job in open_jobs if job.department == dept.name),
            }

        snapshot = existing or WorkforceSnapshot(organization_id=organization_id, date=snapshot_date)
        snapshot.headcount = headcount
        snapshot.hires_month = int(hires)
        snapshot.exits_month = int(exits)
        snapshot.attrition_rate = attrition
        snapshot.departments = departments
        if not existing:
            db.add(snapshot)
        await db.flush()
        return snapshot

    async def snapshots(self, db: AsyncSession, *, organization_id: str, limit: int = 12) -> list[WorkforceSnapshot]:
        return (
            await db.execute(
                select(WorkforceSnapshot)
                .where(WorkforceSnapshot.organization_id == organization_id)
                .order_by(WorkforceSnapshot.date.desc())
                .limit(limit)
            )
        ).scalars().all()

    # ------------------------------------------------------------------ hiring needs & analytics

    async def hiring_needs(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        """AI-lite hiring signal: open roles + attrition pressure + plan targets."""
        jobs = (
            await db.execute(select(Job).where(Job.organization_id == organization_id, Job.status == "open"))
        ).scalars().all()
        open_by_dept: dict[str, int] = {}
        for job in jobs:
            dept = job.department or "General"
            open_by_dept[dept] = open_by_dept.get(dept, 0) + job.openings
        latest = (
            await db.execute(
                select(WorkforceSnapshot)
                .where(WorkforceSnapshot.organization_id == organization_id)
                .order_by(WorkforceSnapshot.date.desc())
            )
        ).scalars().first()
        plans = (await self.list_plans(db, organization_id=organization_id, status="active")) + (
            await self.list_plans(db, organization_id=organization_id, status="approved")
        )
        needs: list[dict[str, Any]] = []
        for dept, count in open_by_dept.items():
            plan_growth = sum(plan.headcount_target for plan in plans if plan.department == dept)
            needs.append(
                {
                    "department": dept,
                    "open_positions": count,
                    "plan_growth": plan_growth,
                    "priority": "high" if count + plan_growth >= 5 else ("medium" if count + plan_growth >= 2 else "low"),
                }
            )
        return {
            "by_department": sorted(needs, key=lambda item: item["open_positions"], reverse=True),
            "total_open_positions": sum(item["open_positions"] for item in needs),
            "attrition_rate": latest.attrition_rate if latest else 0.0,
            "attrition_pressure": latest.attrition_rate > 10 if latest else False,
            "last_snapshot_date": latest.date.isoformat() if latest else None,
        }

    async def analytics(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        snapshots = await self.snapshots(db, organization_id=organization_id, limit=12)
        trend = [
            {
                "date": snapshot.date.isoformat(),
                "headcount": snapshot.headcount,
                "hires": snapshot.hires_month,
                "exits": snapshot.exits_month,
                "attrition": snapshot.attrition_rate,
            }
            for snapshot in reversed(snapshots)
        ]
        latest = snapshots[0] if snapshots else None
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id, Employee.status == "active")
            )
        ).scalars().all()
        team_counts: dict[str, int] = {}
        for employee in employees:
            team_counts[employee.team_id or "none"] = team_counts.get(employee.team_id or "none", 0) + 1
        by_status = {
            "active": len(employees),
            "total": (
                await db.execute(select(func.count()).select_from(Employee).where(Employee.organization_id == organization_id))
            ).scalar_one() or 0,
        }
        succession = await self.list_succession(db, organization_id=organization_id)
        return {
            "headcount": latest.headcount if latest else len(employees),
            "hires_month": latest.hires_month if latest else 0,
            "exits_month": latest.exits_month if latest else 0,
            "attrition_rate": latest.attrition_rate if latest else 0.0,
            "trend": trend,
            "succession_pipeline": {
                "total": len(succession),
                "ready": sum(1 for item in succession if item["status"] == "ready"),
                "developing": sum(1 for item in succession if item["status"] == "developing"),
            },
            "hiring_needs": await self.hiring_needs(db, organization_id=organization_id),
            "headcount_status": by_status,
        }


workforce_service = WorkforceService()
