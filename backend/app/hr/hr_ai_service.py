"""HR AI companion (Phase 11.15 — Organization Intelligence).

Role-aware HR questions answered with live organization data:

- Employees: leave balance, approval path, promotion readiness, mentors,
  training requirements.
- Managers: overloaded reports, promotion-ready reports, pending approvals,
  onboarding support, hiring needs.
- HR / Executives: attrition, hiring risk, workforce health, leadership
  pipeline, compliance posture.

Deterministic by design (no external AI required in the default deployment);
the answer always cites the data it used.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.attendance_service import attendance_service
from app.hr.leave_service import leave_service
from app.hr.wellbeing_service import wellbeing_service
from app.hr.workforce_service import workforce_service
from app.models.employee import Employee
from app.models.hr import LeaveRequest, Offboarding, PerformanceReview
from app.models.user import User

logger = logging.getLogger("vcos.hr.ai")


class HrAiService:
    async def answer(
        self, db: AsyncSession, *, organization_id: str, user: User, question: str,
    ) -> dict[str, Any]:
        employee = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id, Employee.user_id == str(user.id))
            )
        ).scalar_one_or_none()
        is_manager = bool(employee and await self._has_reports(db, employee.id))
        manager_employee_id = employee.id if is_manager else None
        q = question.lower()

        context: list[str] = []

        if any(word in q for word in ("balance", "leave left", "vacation left", "how many days")):
            context.append("leave balance")
            answer = await self._leave_balance_answer(db, organization_id=organization_id, employee_id=employee.id if employee else None)
        elif any(word in q for word in ("approver", "who approve", "approval path", "who approves")):
            context.append("leave approval path")
            manager = None
            if employee and employee.manager_id:
                manager = await db.get(Employee, employee.manager_id)
            answer = (
                f"Your leave requests go to your manager ({manager.full_name} · {manager.designation}) for approval, "
                f"then HR. Unpaid leave still needs approval. You have {len(await leave_service.pending_requests(db, organization_id=organization_id, manager_employee_id=employee.id if employee else None))} pending request(s) awaiting review."
                if manager else
                "You do not have a manager assigned, so leave requests go directly to the HR review queue."
            )
        elif any(word in q for word in ("promotion", "promot", "career", "next role", "ready")):
            context.append("promotion readiness")
            answer = await self._promotion_answer(db, organization_id=organization_id, employee_id=employee.id if employee else None)
        elif any(word in q for word in ("mentor", "training", "learn", "course")):
            context.append("mentorship and training")
            trainings = await self._trainings_summary(db, organization_id=organization_id, employee_id=employee.id if employee else None)
            answer = (
                f"Your compliance training posture: {trainings['summary']}. "
                "Check the Learning Center for mentors, courses and your career path — the mentorship tab matches you with mentors for your target skills."
            )
        elif any(word in q for word in ("overload", "overloaded", "burned out", "too much work", "who is overloaded")):
            context.append("team workload")
            answer = await self._overload_answer(db, organization_id=organization_id, manager_employee_id=manager_employee_id)
        elif any(word in q for word in ("attrition", "leaving", "turnover", "exit", "quit")):
            context.append("attrition")
            answer = await self._attrition_answer(db, organization_id=organization_id)
        elif any(word in q for word in ("hiring", "recruit", "open role", "open position", "hire")):
            context.append("hiring needs")
            needs = await workforce_service.hiring_needs(db, organization_id=organization_id)
            by_dept = ", ".join(f"{item['department']}: {item['open_positions']}" for item in needs["by_department"]) or "none"
            answer = (
                f"There are {needs['total_open_positions']} open position(s) right now ({by_dept}). "
                f"Monthly attrition is {needs['attrition_rate']}% — {'this adds hiring pressure.' if needs['attrition_pressure'] else 'attrition is under control.'}"
            )
        elif any(word in q for word in ("wellbeing", "healthy", "health", "risk")):
            context.append("workforce wellbeing")
            overview = await wellbeing_service.overview(db, organization_id=organization_id)
            answer = (
                f"Wellbeing overview: {overview['total_checks']} check-ins recorded — {overview['low']} low, "
                f"{overview['medium']} medium, {overview['high']} high risk. "
                f"{overview['at_risk_employees']} employee(s) currently show sustained high workload signals."
            )
        elif any(word in q for word in ("leadership", "succession", "pipeline", "next ceo", "backup")):
            context.append("leadership pipeline")
            succession = await workforce_service.list_succession(db, organization_id=organization_id)
            ready = [item for item in succession if item["status"] == "ready"]
            answer = (
                f"Succession pipeline: {len(succession)} candidate(s) tracked across {len(set(item['position_title'] for item in succession))} position(s). "
                f"{len(ready)} candidate(s) are ready now: "
                + (", ".join(f"{item['candidate_name']} → {item['position_title']}" for item in ready[:5]) or "none")
                + "."
            )
        elif any(word in q for word in ("compliance", "expire", "visa", "certificate", "training", "policy")):
            context.append("compliance posture")
            answer = await self._compliance_answer(db, organization_id=organization_id)
        elif any(word in q for word in ("attendance", "absent", "late", "present", "work from home")):
            context.append("attendance")
            answer = await self._attendance_answer(db, organization_id=organization_id, employee_id=employee.id if employee else None)
        elif any(word in q for word in ("review", "performance", "rating")):
            context.append("performance reviews")
            reviews = (
                await db.execute(
                    select(PerformanceReview).where(
                        PerformanceReview.organization_id == organization_id, PerformanceReview.status == "completed"
                    )
                )
            ).scalars().all()
            ratings = [review.rating for review in reviews if review.rating > 0]
            answer = (
                f"{len(reviews)} review(s) completed org-wide with an average rating of "
                f"{round(sum(ratings) / len(ratings), 2) if ratings else 0.0}/5."
            )
        else:
            context.append("workforce overview")
            analytics = await workforce_service.analytics(db, organization_id=organization_id)
            answer = (
                f"Your workforce: {analytics['headcount']} active employee(s), {analytics['hires_month']} hire(s) and "
                f"{analytics['exits_month']} exit(s) this month, monthly attrition {analytics['attrition_rate']}%. "
                "Ask me about leave balances, promotion readiness, overload, attrition, hiring needs, leadership pipeline, compliance or attendance."
            )
        return {"answer": answer, "context": context, "question": question}

    async def _has_reports(self, db: AsyncSession, employee_id: str) -> bool:
        return bool(
            (await db.execute(select(Employee.id).where(Employee.manager_id == employee_id).limit(1))).scalars().first()
        )

    # ------------------------------------------------------------- answer builders

    async def _leave_balance_answer(self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str]) -> str:
        if not employee_id:
            return "No employee profile found for your account."
        balances = await leave_service.balances(db, organization_id=organization_id, employee_id=employee_id)
        if not balances:
            return "No leave types configured yet."
        top = sorted(balances, key=lambda item: item["remaining"], reverse=True)[:4]
        parts = " · ".join(f"{item['name']}: {item['remaining']:.1f} days" for item in top)
        total_remaining = round(sum(item["remaining"] for item in balances), 1)
        return f"You have {total_remaining:.1f} days of leave available across all types. {parts}."

    async def _promotion_answer(self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str]) -> str:
        if not employee_id:
            return "No employee profile found for your account."
        try:
            from app.learning.career_service import career_service
            progress = await career_service.progress_for(db, organization_id=organization_id, employee_id=employee_id)
        except Exception:  # pragma: no cover
            progress = {}
        if not progress.get("next"):
            return "You are at the top of your career path — no further promotion step is defined."
        ready = "You are promotion-ready" if progress.get("promotion_ready") else "You are not promotion-ready yet"
        return (
            f"{ready} for {progress['next']['title']} (readiness {progress.get('readiness', 0)}/100). "
            f"Required skills: {', '.join(str(item.get('skill') or item.get('name') or '') for item in progress['next'].get('required_skills', [])) or 'none recorded'}."
        )

    async def _trainings_summary(self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str]) -> dict[str, str]:
        if not employee_id:
            return {"summary": "no employee profile found"}
        from app.hr.compliance_service import compliance_service
        completions = await compliance_service.list_completions(db, organization_id=organization_id, employee_id=employee_id)
        current = sum(1 for item in completions if not item["expired"])
        missing = await compliance_service.missing_trainings(db, organization_id=organization_id)
        my_missing = sum(1 for item in missing if item["employee_id"] == employee_id)
        return {"summary": f"{current} training completion(s) current, {my_missing} requirement(s) outstanding"}

    async def _overload_answer(self, db: AsyncSession, *, organization_id: str, manager_employee_id: Optional[str]) -> str:
        checks = await wellbeing_service.list_checks(db, organization_id=organization_id)
        at_risk = [item for item in checks if item["risk_level"] == "high"]
        if manager_employee_id:
            reports = (await db.execute(select(Employee).where(Employee.manager_id == manager_employee_id))).scalars().all()
            report_ids = {report.id for report in reports}
            at_risk = [item for item in at_risk if item["employee_id"] in report_ids]
        if not at_risk:
            return "No sustained overload signals detected right now. Workload looks balanced."
        names = {item["employee_name"] or item["employee_id"]: item["signals"][0] for item in at_risk[:5]}
        detail = ", ".join(f"{name} ({signal})" for name, signal in list(names.items())[:3])
        return f"{len(at_risk)} employee(s) show sustained overload signals. {detail}. A 1:1 workload review is recommended."

    async def _attrition_answer(self, db: AsyncSession, *, organization_id: str) -> str:
        analytics = await workforce_service.analytics(db, organization_id=organization_id)
        offboardings = (
            await db.execute(
                select(Offboarding).where(
                    Offboarding.organization_id == organization_id, Offboarding.status == "in_progress"
                )
            )
        ).scalars().all()
        names = []
        for offboarding in offboardings:
            employee = await db.get(Employee, offboarding.employee_id)
            names.append(employee.full_name if employee else "unknown")
        return (
            f"Monthly attrition is {analytics['attrition_rate']}% with {analytics['exits_month']} exit(s) this month. "
            f"{len(offboardings)} offboarding(s) are in progress"
            + (f" ({', '.join(names)})" if names else "")
            + ". Ask me for hiring needs if you want to backfill."
        )

    async def _compliance_answer(self, db: AsyncSession, *, organization_id: str) -> str:
        from app.hr.compliance_service import compliance_service
        overview = await compliance_service.overview(db, organization_id=organization_id)
        docs = overview["documents"]
        return (
            f"Compliance posture: {docs['expired']} expired document(s), {docs['expiring_30']} expiring within 30 days, "
            f"{docs['expiring_60']} within 60, {docs['expiring_90']} within 90. "
            f"{overview['trainings']['missing']} training requirement(s) are outstanding."
        )

    async def _attendance_answer(self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str]) -> str:
        if not employee_id:
            return "No employee profile found for your account."
        summary = await attendance_service.summary(db, organization_id=organization_id, employee_id=employee_id)
        return (
            f"This month you have {summary['days']} attendance record(s), "
            f"{summary['overtime_minutes']} minutes of overtime and {summary['late_minutes']} minutes late."
        )


hr_ai_service = HrAiService()
