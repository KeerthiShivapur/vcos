"""Attendance API (Phase 11.2 — Attendance & Time Tracking).

Employees clock in / out (app, QR, GPS, Wi-Fi, manual), view their records
and summaries, and request corrections. HR manages shifts, holidays, manual
records and reviews corrections.
"""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.attendance_service import attendance_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/attendance", tags=["HR Attendance"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.user_id == str(user.id))
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


# ------------------------------------------------------------------ shifts & holidays

@router.post("/shifts")
async def create_shift(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        shift = await attendance_service.create_shift(db, organization_id=org.id, data=payload)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
    await db.commit()
    return {"id": shift.id, "name": shift.name, "start_time": shift.start_time, "end_time": shift.end_time}


@router.get("/shifts")
async def list_shifts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(False),
):
    shifts = await attendance_service.list_shifts(db, organization_id=org.id, active_only=active_only)
    return [
        {
            "id": shift.id,
            "name": shift.name,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "work_hours": shift.work_hours,
            "break_minutes": shift.break_minutes,
            "days": shift.days or [],
            "timezone": shift.timezone,
            "is_flexible": shift.is_flexible,
            "is_active": shift.is_active,
        }
        for shift in shifts
    ]


@router.patch("/shifts/{shift_id}")
async def update_shift(
    shift_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    shift = await attendance_service.update_shift(db, organization_id=org.id, shift_id=shift_id, data=payload)
    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    await db.commit()
    return {"id": shift.id, "name": shift.name}


@router.delete("/shifts/{shift_id}")
async def delete_shift(
    shift_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    deleted = await attendance_service.delete_shift(db, organization_id=org.id, shift_id=shift_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Shift not found")
    await db.commit()
    return {"deleted": True}


@router.post("/holidays")
async def add_holiday(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    holiday = await attendance_service.add_holiday(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": holiday.id, "name": holiday.name, "date": holiday.date.isoformat()}


@router.get("/holidays")
async def list_holidays(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = Query(None),
):
    holidays = await attendance_service.list_holidays(db, organization_id=org.id, year=year)
    return [
        {
            "id": holiday.id,
            "name": holiday.name,
            "date": holiday.date.isoformat(),
            "kind": holiday.kind,
            "optional": holiday.optional,
        }
        for holiday in holidays
    ]


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    deleted = await attendance_service.delete_holiday(db, organization_id=org.id, holiday_id=holiday_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Holiday not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ clock in / out

@router.post("/clock-in")
async def clock_in(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    record = await attendance_service.clock_in(
        db,
        organization_id=org.id,
        employee_id=employee_id,
        source=payload.get("source", "app"),
        shift_id=payload.get("shift_id"),
        work_mode=payload.get("work_mode", "office"),
        location=payload.get("location"),
        note=payload.get("note"),
    )
    await db.commit()
    return {
        "id": record.id,
        "date": record.date.isoformat(),
        "check_in": record.check_in.isoformat() if record.check_in else None,
        "status": record.status,
        "work_mode": record.work_mode,
    }


@router.post("/clock-out")
async def clock_out(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    record = await attendance_service.clock_out(
        db, organization_id=org.id, employee_id=employee_id, note=payload.get("note")
    )
    if record is None:
        raise HTTPException(status_code=409, detail="No open attendance record to clock out")
    await db.commit()
    return {
        "id": record.id,
        "date": record.date.isoformat(),
        "check_in": record.check_in.isoformat() if record.check_in else None,
        "check_out": record.check_out.isoformat() if record.check_out else None,
        "work_minutes": record.work_minutes,
        "late_minutes": record.late_minutes,
        "overtime_minutes": record.overtime_minutes,
    }


@router.post("/breaks")
async def start_break(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    record = await attendance_service.add_break(
        db, organization_id=org.id, employee_id=employee_id, minutes=int(payload.get("minutes", 30))
    )
    if record is None:
        raise HTTPException(status_code=409, detail="No open attendance record")
    await db.commit()
    return {"on_break": True, "breaks": record.breaks}


@router.post("/breaks/end")
async def end_break(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    record = await attendance_service.end_break(db, organization_id=org.id, employee_id=employee_id)
    if record is None:
        raise HTTPException(status_code=409, detail="No open attendance record")
    await db.commit()
    return {"on_break": False, "breaks": record.breaks}


@router.get("/today")
async def today_status(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    record = await attendance_service.today_record(db, organization_id=org.id, employee_id=employee_id)
    if record is None:
        return {"checked_in": False}
    return {
        "checked_in": True,
        "checked_out": record.check_out is not None,
        "record_id": record.id,
        "date": record.date.isoformat(),
        "check_in": record.check_in.isoformat() if record.check_in else None,
        "check_out": record.check_out.isoformat() if record.check_out else None,
        "status": record.status,
        "work_mode": record.work_mode,
        "work_minutes": record.work_minutes,
    }


# ------------------------------------------------------------------ records & summary

@router.get("/my")
async def my_records(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    employee_id = await _employee_id(db, org, user)
    records = await attendance_service.my_records(
        db, organization_id=org.id, employee_id=employee_id, start=start, end=end, limit=limit
    )
    return [
        {
            "id": record.id,
            "date": record.date.isoformat(),
            "work_mode": record.work_mode,
            "status": record.status,
            "check_in": record.check_in.isoformat() if record.check_in else None,
            "check_out": record.check_out.isoformat() if record.check_out else None,
            "work_minutes": record.work_minutes,
            "late_minutes": record.late_minutes,
            "early_departure_minutes": record.early_departure_minutes,
            "overtime_minutes": record.overtime_minutes,
            "source": record.source,
            "location": record.location,
            "note": record.note,
        }
        for record in records
    ]


@router.get("")
async def list_records(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    records = await attendance_service.list_records(
        db, organization_id=org.id, employee_id=employee_id, start=start, end=end, limit=limit
    )
    return [
        {
            "id": record.id,
            "employee_id": record.employee_id,
            "date": record.date.isoformat(),
            "work_mode": record.work_mode,
            "status": record.status,
            "check_in": record.check_in.isoformat() if record.check_in else None,
            "check_out": record.check_out.isoformat() if record.check_out else None,
            "work_minutes": record.work_minutes,
            "late_minutes": record.late_minutes,
            "overtime_minutes": record.overtime_minutes,
            "source": record.source,
        }
        for record in records
    ]


@router.post("/manual")
async def record_manual(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    record = await attendance_service.record_manual(
        db, organization_id=org.id, employee_id=payload["employee_id"], data=payload, actor_id=user.id
    )
    await db.commit()
    return {"id": record.id, "date": record.date.isoformat(), "status": record.status}


@router.get("/summary")
async def attendance_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
):
    if employee_id:
        summary = await attendance_service.summary(
            db, organization_id=org.id, employee_id=employee_id, start=start, end=end
        )
    else:
        summary = await attendance_service.summary(
            db, organization_id=org.id, employee_id=await _employee_id(db, org, user), start=start, end=end
        )
    return summary


# ------------------------------------------------------------------ corrections

@router.post("/corrections")
async def request_correction(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    correction = await attendance_service.request_correction(
        db, organization_id=org.id, employee_id=employee_id, data=payload
    )
    await db.commit()
    return {
        "id": correction.id,
        "requested_date": correction.requested_date.isoformat(),
        "status": correction.status,
    }


@router.get("/corrections")
async def list_corrections(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    corrections = await attendance_service.list_corrections(
        db, organization_id=org.id, employee_id=employee_id, status=status
    )
    return [
        {
            "id": correction.id,
            "employee_id": correction.employee_id,
            "attendance_id": correction.attendance_id,
            "requested_date": correction.requested_date.isoformat(),
            "reason": correction.reason,
            "status": correction.status,
            "adjusted_check_in": correction.adjusted_check_in.isoformat() if correction.adjusted_check_in else None,
            "adjusted_check_out": correction.adjusted_check_out.isoformat() if correction.adjusted_check_out else None,
            "reviewed_by": correction.reviewed_by,
            "reviewed_at": correction.reviewed_at.isoformat() if correction.reviewed_at else None,
        }
        for correction in corrections
    ]


@router.post("/corrections/{correction_id}/review")
async def review_correction(
    correction_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    correction = await attendance_service.review_correction(
        db, organization_id=org.id, correction_id=correction_id,
        decision=payload.get("decision", "reject"), reviewer_id=user.id,
    )
    if correction is None:
        raise HTTPException(status_code=404, detail="Correction not found")
    await db.commit()
    return {"id": correction.id, "status": correction.status}
