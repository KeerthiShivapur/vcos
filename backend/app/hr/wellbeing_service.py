"""Wellbeing service (Phase 11.11 — Wellbeing).

Deliberately NOT a health or medical system. It observes workload and
engagement patterns only — meeting hours, task load, learning load, leave
balance usage, recognitions, engagement — and computes a risk level
(low / medium / high) with human-readable signals so managers and HR can
step in early.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.hr import WellbeingCheck

logger = logging.getLogger("vcos.hr.wellbeing")

RISK_LEVELS = ["low", "medium", "high"]


def _compute_risk(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    """Deterministic pattern-based risk scoring."""
    signals: list[str] = []
    meeting_hours = float(metrics.get("meeting_hours", 0) or 0)
    task_load = int(metrics.get("task_load", 0) or 0)
    learning_load = int(metrics.get("learning_load", 0) or 0)
    leave_balance = float(metrics.get("leave_balance_days", 0) or 0)
    recognitions = int(metrics.get("recognitions", 0) or 0)
    engagement = int(metrics.get("engagement", 0) or 0)

    if meeting_hours > 40:
        signals.append("Very heavy meeting load this week")
    elif meeting_hours > 25:
        signals.append("Above-average meeting load")
    if task_load > 25:
        signals.append("High open task count")
    elif task_load > 15:
        signals.append("Elevated open task count")
    if learning_load > 6:
        signals.append("High learning load on top of work")
    if leave_balance < 3:
        signals.append("Leave balance nearly exhausted — break overdue")
    if recognitions == 0:
        signals.append("No recognition received recently")
    if engagement < 2:
        signals.append("Low engagement signal")
    if meeting_hours <= 15 and task_load <= 8 and leave_balance >= 8 and recognitions >= 2:
        signals.append("Healthy balance of work, rest and recognition")

    score = len(signals)
    if score >= 4:
        risk = "high"
    elif score >= 2:
        risk = "medium"
    else:
        risk = "low"
    if not signals:
        signals = ["No significant workload or engagement concerns"]
    return risk, signals


class WellbeingService:
    async def check_in(self, db: AsyncSession, *, organization_id: str, employee_id: str, data: dict[str, Any]) -> WellbeingCheck:
        metrics = data.get("metrics") or {}
        risk, signals = _compute_risk(metrics)
        check = WellbeingCheck(
            organization_id=organization_id,
            employee_id=employee_id,
            check_date=data.get("check_date") or utcnow().date(),
            metrics=metrics,
            risk_level=risk,
            signals=signals,
            notes=data.get("notes"),
        )
        db.add(check)
        await db.flush()
        return check

    async def my_checks(self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 30) -> list[WellbeingCheck]:
        return (
            await db.execute(
                select(WellbeingCheck)
                .where(
                    WellbeingCheck.organization_id == organization_id,
                    WellbeingCheck.employee_id == employee_id,
                )
                .order_by(WellbeingCheck.check_date.desc())
                .limit(limit)
            )
        ).scalars().all()

    async def list_checks(self, db: AsyncSession, *, organization_id: str, risk_level: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        query = select(WellbeingCheck).where(WellbeingCheck.organization_id == organization_id)
        if risk_level:
            query = query.where(WellbeingCheck.risk_level == risk_level)
        rows = await db.execute(query.order_by(WellbeingCheck.check_date.desc()).limit(limit))
        result = []
        for check in rows.scalars().all():
            employee = await db.get(Employee, check.employee_id)
            result.append(
                {
                    "id": check.id,
                    "employee_id": check.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "check_date": check.check_date.isoformat(),
                    "metrics": check.metrics or {},
                    "risk_level": check.risk_level,
                    "signals": check.signals or [],
                    "notes": check.notes,
                    "reviewed": check.reviewed,
                }
            )
        return result

    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        checks = (
            await db.execute(
                select(WellbeingCheck)
                .where(WellbeingCheck.organization_id == organization_id)
                .order_by(WellbeingCheck.created_at.desc(), WellbeingCheck.id.desc())
            )
        ).scalars().all()
        counts = {"low": 0, "medium": 0, "high": 0}
        latest_by_employee: dict[str, str] = {}
        for check in checks:
            counts[check.risk_level] = counts.get(check.risk_level, 0) + 1
            latest_by_employee.setdefault(check.employee_id, check.risk_level)
        latest_high = await self.list_checks(db, organization_id=organization_id, risk_level="high", limit=20)
        return {
            "total_checks": len(checks),
            "low": counts.get("low", 0),
            "medium": counts.get("medium", 0),
            "high": counts.get("high", 0),
            "at_risk_employees": len([r for r in latest_by_employee.values() if r == "high"]),
            "latest_high": latest_high,
        }

    async def recommendations(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        """Pattern-based recommendations (not medical advice)."""
        overview = await self.overview(db, organization_id=organization_id)
        recommendations: list[dict[str, Any]] = []
        if overview["high"]:
            recommendations.append(
                {
                    "priority": "high",
                    "title": "Follow up with at-risk team members",
                    "description": f"{overview['at_risk_employees']} employee(s) show sustained high workload signals. Have a 1:1 conversation, review workload, and offer time off.",
                }
            )
        if overview["medium"]:
            recommendations.append(
                {
                    "priority": "medium",
                    "title": "Encourage leave utilization",
                    "description": "Team members with medium risk should be encouraged to take earned leave before balances shrink.",
                }
            )
        recommendations.append(
            {
                "priority": "low",
                "title": "Normalize recognition",
                "description": "Employees without recent recognitions show lower engagement signals — a little recognition goes far.",
            }
        )
        return recommendations


wellbeing_service = WellbeingService()
