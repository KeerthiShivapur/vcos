"""Leave service (Phase 11.3 — Leave Management).

Typed leave (annual, casual, sick, maternity, paternity, bereavement,
compensatory, work-from-home, unpaid, custom) with an Employee → Manager →
HR approval workflow, balance allocation / accrual / consumption, overlap
validation, calendar aggregation and payroll-facing summaries.
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date
from app.models.employee import Employee
from app.models.hr import LeaveBalance, LeaveRequest, LeaveType, Holiday

logger = logging.getLogger("vcos.hr.leave")

_event_bus = EventBus()

# (code, name, days_per_year, color, is_paid, carry_over, requires_approval)
DEFAULT_LEAVE_TYPES: list[tuple[str, str, float, str, bool, bool, bool]] = [
    ("annual", "Annual Leave", 20.0, "#6366f1", True, True, True),
    ("casual", "Casual Leave", 12.0, "#22c55e", True, False, True),
    ("sick", "Sick Leave", 10.0, "#ef4444", True, True, True),
    ("maternity", "Maternity Leave", 90.0, "#ec4899", True, True, True),
    ("paternity", "Paternity Leave", 15.0, "#f59e0b", True, False, True),
    ("bereavement", "Bereavement Leave", 5.0, "#64748b", True, False, True),
    ("compensatory", "Compensatory Off", 10.0, "#0ea5e9", True, False, True),
    ("work_from_home", "Work From Home", 30.0, "#8b5cf6", True, False, True),
    ("unpaid", "Unpaid Leave", 0.0, "#94a3b8", False, False, True),
]


class LeaveService:
    # ------------------------------------------------------------------ types

    async def ensure_default_types(self, db: AsyncSession, *, organization_id: str) -> list[LeaveType]:
        existing_codes = set(
            (await db.execute(select(LeaveType.code).where(LeaveType.organization_id == organization_id))).scalars().all()
        )
        for code, name, days, color, paid, carry, approval in DEFAULT_LEAVE_TYPES:
            if code in existing_codes:
                continue
            db.add(
                LeaveType(
                    organization_id=organization_id,
                    code=code,
                    name=name,
                    days_per_year=days,
                    color=color,
                    is_paid=paid,
                    carry_over=carry,
                    requires_approval=approval,
                )
            )
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
        return (await db.execute(select(LeaveType).where(LeaveType.organization_id == organization_id))).scalars().all()

    async def create_type(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> LeaveType:
        leave_type = LeaveType(
            organization_id=organization_id,
            name=data["name"],
            code=data["code"],
            color=data.get("color", "#6366f1"),
            days_per_year=float(data.get("days_per_year", 15.0)),
            carry_over=bool(data.get("carry_over", False)),
            requires_approval=bool(data.get("requires_approval", True)),
            is_paid=bool(data.get("is_paid", True)),
            is_active=bool(data.get("is_active", True)),
        )
        db.add(leave_type)
        await db.flush()
        return leave_type

    async def list_types(self, db: AsyncSession, *, organization_id: str, active_only: bool = True) -> list[LeaveType]:
        await self.ensure_default_types(db, organization_id=organization_id)
        query = select(LeaveType).where(LeaveType.organization_id == organization_id)
        if active_only:
            query = query.where(LeaveType.is_active.is_(True))
        return (await db.execute(query.order_by(LeaveType.name))).scalars().all()

    async def update_type(self, db: AsyncSession, *, organization_id: str, leave_type_id: str, data: dict[str, Any]) -> Optional[LeaveType]:
        leave_type = (
            await db.execute(
                select(LeaveType).where(LeaveType.organization_id == organization_id, LeaveType.id == leave_type_id)
            )
        ).scalar_one_or_none()
        if leave_type is None:
            return None
        for field in ("name", "code", "color", "days_per_year", "carry_over",
                      "requires_approval", "is_paid", "is_active"):
            if field in data:
                setattr(leave_type, field, data[field])
        await db.flush()
        return leave_type

    # ------------------------------------------------------------------ balances

    async def _balance_for(self, db: AsyncSession, *, organization_id: str, employee_id: str, leave_type: LeaveType, year: int) -> LeaveBalance:
        balance = (
            await db.execute(
                select(LeaveBalance).where(
                    LeaveBalance.organization_id == organization_id,
                    LeaveBalance.employee_id == employee_id,
                    LeaveBalance.leave_type_id == leave_type.id,
                    LeaveBalance.year == year,
                )
            )
        ).scalar_one_or_none()
        if balance is None:
            balance = LeaveBalance(
                organization_id=organization_id,
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                year=year,
                allocated=leave_type.days_per_year,
                used=0.0,
                carried_over=0.0,
            )
            db.add(balance)
            await db.flush()
        return balance

    async def balances(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, year: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        year = year or utcnow().date().year
        result = []
        for leave_type in await self.list_types(db, organization_id=organization_id):
            balance = await self._balance_for(db, organization_id=organization_id, employee_id=employee_id,
                                              leave_type=leave_type, year=year)
            result.append(
                {
                    "leave_type_id": leave_type.id,
                    "code": leave_type.code,
                    "name": leave_type.name,
                    "color": leave_type.color,
                    "is_paid": leave_type.is_paid,
                    "allocated": balance.allocated,
                    "carried_over": balance.carried_over,
                    "used": balance.used,
                    "remaining": balance.remaining,
                }
            )
        return result

    # ------------------------------------------------------------------ requests

    def _business_days(self, start: date, end: date, holidays: list[Holiday]) -> float:
        holiday_dates = {h.date for h in holidays}
        days = 0.0
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5 and cursor not in holiday_dates:
                days += 1.0
            cursor += timedelta(days=1)
        return days

    async def request(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, data: dict[str, Any],
    ) -> LeaveRequest:
        start = to_date(data["start_date"])
        end = to_date(data["end_date"])
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        leave_type = (
            await db.execute(
                select(LeaveType).where(
                    LeaveType.organization_id == organization_id, LeaveType.id == data["leave_type_id"]
                )
            )
        ).scalar_one_or_none()
        if leave_type is None:
            raise ValueError("unknown leave type")

        holidays = await self._holidays_between(db, organization_id=organization_id, start=start, end=end)
        days = self._business_days(start, end, holidays)
        if data.get("half_day"):
            days = max(0.5, days - 0.5)

        # overlap check against pending/approved requests
        overlaps = (
            await db.execute(
                select(LeaveRequest).where(
                    LeaveRequest.organization_id == organization_id,
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.status.in_(["pending", "approved"]),
                    LeaveRequest.start_date <= end,
                    LeaveRequest.end_date >= start,
                )
            )
        ).scalars().all()
        if overlaps:
            raise ValueError("overlaps an existing pending or approved leave request")

        # balance check (unpaid always allowed)
        if leave_type.is_paid:
            year_balance = await self._balance_for(db, organization_id=organization_id, employee_id=employee_id,
                                                   leave_type=leave_type, year=start.year)
            if days > year_balance.remaining:
                raise ValueError(
                    f"insufficient {leave_type.code} balance: {year_balance.remaining:.1f} days available, {days:.1f} requested"
                )

        request = LeaveRequest(
            organization_id=organization_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            start_date=start,
            end_date=end,
            days=days,
            reason=data.get("reason"),
            backup_employee_id=data.get("backup_employee_id"),
            half_day=bool(data.get("half_day", False)),
        )
        db.add(request)
        await db.flush()
        await _event_bus.publish(
            db,
            name="leave.requested",
            organization_id=organization_id,
            actor_id=employee_id,
            payload={
                "request_id": request.id,
                "leave_type": leave_type.code,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "days": days,
                "status": request.status,
            },
            flush=False,
        )
        return request

    async def _holidays_between(self, db: AsyncSession, *, organization_id: str, start: date, end: date) -> list[Holiday]:
        return (
            await db.execute(
                select(Holiday).where(
                    Holiday.organization_id == organization_id,
                    Holiday.date >= start,
                    Holiday.date <= end,
                )
            )
        ).scalars().all()

    async def list_requests(
        self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None,
        status: Optional[str] = None, start: Optional[date] = None, end: Optional[date] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(LeaveRequest).where(LeaveRequest.organization_id == organization_id)
        if employee_id:
            query = query.where(LeaveRequest.employee_id == employee_id)
        if status:
            query = query.where(LeaveRequest.status == status)
        if start:
            query = query.where(LeaveRequest.start_date >= start)
        if end:
            query = query.where(LeaveRequest.end_date <= end)
        rows = await db.execute(query.order_by(LeaveRequest.created_at.desc()).limit(limit))
        return [await self._request_out(db, r) for r in rows.scalars().all()]

    async def get_request(self, db: AsyncSession, *, organization_id: str, request_id: str) -> Optional[dict[str, Any]]:
        request = (
            await db.execute(
                select(LeaveRequest).where(LeaveRequest.organization_id == organization_id, LeaveRequest.id == request_id)
            )
        ).scalar_one_or_none()
        return await self._request_out(db, request) if request else None

    async def _request_out(self, db: AsyncSession, request: LeaveRequest) -> dict[str, Any]:
        leave_type = await db.get(LeaveType, request.leave_type_id)
        employee = await db.get(Employee, request.employee_id)
        return {
            "id": request.id,
            "employee_id": request.employee_id,
            "employee_name": employee.full_name if employee else None,
            "leave_type_id": request.leave_type_id,
            "leave_type": leave_type.code if leave_type else None,
            "leave_type_name": leave_type.name if leave_type else None,
            "color": leave_type.color if leave_type else "#6366f1",
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "days": request.days,
            "half_day": request.half_day,
            "reason": request.reason,
            "status": request.status,
            "approved_by": request.approved_by,
            "approved_at": request.approved_at.isoformat() if request.approved_at else None,
            "backup_employee_id": request.backup_employee_id,
            "reviewer_note": request.reviewer_note,
        }

    async def approve(
        self, db: AsyncSession, *, organization_id: str, request_id: str, reviewer_id: str, note: Optional[str] = None,
    ) -> Optional[LeaveRequest]:
        request = (
            await db.execute(
                select(LeaveRequest).where(LeaveRequest.organization_id == organization_id, LeaveRequest.id == request_id)
            )
        ).scalar_one_or_none()
        if request is None or request.status != "pending":
            return request
        leave_type = await db.get(LeaveType, request.leave_type_id)
        if leave_type and leave_type.is_paid:
            balance = await self._balance_for(db, organization_id=organization_id, employee_id=request.employee_id,
                                              leave_type=leave_type, year=request.start_date.year)
            balance.used = balance.used + request.days
        request.status = "approved"
        request.approved_by = reviewer_id
        request.approved_at = utcnow()
        request.reviewer_note = note
        await db.flush()
        await _event_bus.publish(
            db,
            name="leave.approved",
            organization_id=organization_id,
            actor_id=reviewer_id,
            payload={
                "request_id": request.id,
                "employee_id": request.employee_id,
                "leave_type": leave_type.code if leave_type else None,
                "start_date": request.start_date.isoformat(),
                "days": request.days,
            },
            flush=False,
        )
        return request

    async def reject(
        self, db: AsyncSession, *, organization_id: str, request_id: str, reviewer_id: str, note: Optional[str] = None,
    ) -> Optional[LeaveRequest]:
        request = (
            await db.execute(
                select(LeaveRequest).where(LeaveRequest.organization_id == organization_id, LeaveRequest.id == request_id)
            )
        ).scalar_one_or_none()
        if request is None or request.status != "pending":
            return request
        request.status = "rejected"
        request.approved_by = reviewer_id
        request.approved_at = utcnow()
        request.reviewer_note = note
        await db.flush()
        return request

    async def cancel(self, db: AsyncSession, *, organization_id: str, request_id: str, employee_id: str) -> Optional[LeaveRequest]:
        request = (
            await db.execute(
                select(LeaveRequest).where(
                    LeaveRequest.organization_id == organization_id,
                    LeaveRequest.id == request_id,
                    LeaveRequest.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if request is None or request.status not in ("pending", "approved"):
            return request
        leave_type = await db.get(LeaveType, request.leave_type_id)
        if request.status == "approved" and leave_type and leave_type.is_paid:
            balance = await self._balance_for(db, organization_id=organization_id, employee_id=employee_id,
                                              leave_type=leave_type, year=request.start_date.year)
            balance.used = max(0.0, balance.used - request.days)
        request.status = "cancelled"
        await db.flush()
        return request

    async def pending_requests(
        self, db: AsyncSession, *, organization_id: str, manager_employee_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Pending queue — all pending for HR, or the manager's reports' pending."""
        query = select(LeaveRequest).where(
            LeaveRequest.organization_id == organization_id, LeaveRequest.status == "pending"
        )
        rows = await db.execute(query.order_by(LeaveRequest.created_at))
        result = []
        for request in rows.scalars().all():
            if manager_employee_id:
                employee = await db.get(Employee, request.employee_id)
                if employee is None or employee.manager_id != manager_employee_id:
                    continue
            result.append(await self._request_out(db, request))
        return result

    # ------------------------------------------------------------------ calendar & summary

    async def calendar(
        self, db: AsyncSession, *, organization_id: str, start: date, end: date,
    ) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.organization_id == organization_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
        events = []
        for request in rows.scalars().all():
            event = await self._request_out(db, request)
            event["kind"] = "leave"
            events.append(event)
        for holiday in await self._holidays_between(db, organization_id=organization_id, start=start, end=end):
            events.append(
                {
                    "kind": "holiday",
                    "holiday_id": holiday.id,
                    "name": holiday.name,
                    "date": holiday.date.isoformat(),
                    "optional": holiday.optional,
                }
            )
        return events

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        """Org-wide leave summary: pending counts, utilization per type."""
        await self.ensure_default_types(db, organization_id=organization_id)
        requests = (
            await db.execute(
                select(LeaveRequest).where(LeaveRequest.organization_id == organization_id)
            )
        ).scalars().all()
        per_type: dict[str, dict[str, Any]] = {}
        status_counts: dict[str, int] = {}
        for request in requests:
            status_counts[request.status] = status_counts.get(request.status, 0) + 1
            leave_type = await db.get(LeaveType, request.leave_type_id)
            code = leave_type.code if leave_type else request.leave_type_id
            bucket = per_type.setdefault(
                code, {"code": code, "name": leave_type.name if leave_type else code, "requests": 0, "days": 0.0}
            )
            bucket["requests"] += 1
            bucket["days"] += request.days
        total_employees = (
            await db.execute(
                select(Employee.id).where(
                    Employee.organization_id == organization_id, Employee.status == "active"
                )
            )
        ).scalars().all()
        return {
            "status_counts": status_counts,
            "pending_count": status_counts.get("pending", 0),
            "approved_count": status_counts.get("approved", 0),
            "per_type": sorted(per_type.values(), key=lambda item: item["days"], reverse=True),
            "active_employees": len(total_employees),
        }


leave_service = LeaveService()
