"""Attendance service (Phase 11.2 — Attendance & Time Tracking).

Supports office / remote / hybrid / field / shift / flexible work modes with
clock-in/clock-out from manual, app, QR, biometric, GPS or Wi-Fi sources,
breaks, late / overtime computation, corrections with a review workflow and
period summaries for analytics.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date, to_dt
from app.models.employee import Employee
from app.models.hr import AttendanceCorrection, AttendanceRecord, Holiday, Shift

logger = logging.getLogger("vcos.hr.attendance")

_event_bus = EventBus()

WORK_MODES = ["office", "remote", "hybrid", "field", "shift", "flexible"]
SOURCES = ["manual", "app", "qr", "biometric", "gps", "wifi"]
RECORD_STATUSES = ["present", "absent", "half_day", "work_from_home", "on_leave", "holiday"]


def _parse_hm(value: str) -> Optional[time]:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


class AttendanceService:
    # ------------------------------------------------------------------ shifts

    async def create_shift(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Shift:
        shift = Shift(
            organization_id=organization_id,
            name=data["name"],
            start_time=data.get("start_time", "09:00"),
            end_time=data.get("end_time", "17:00"),
            work_hours=float(data.get("work_hours", 8.0)),
            break_minutes=int(data.get("break_minutes", 60)),
            days=data.get("days") or [0, 1, 2, 3, 4],
            timezone=data.get("timezone", "UTC"),
            is_flexible=bool(data.get("is_flexible", False)),
            is_active=bool(data.get("is_active", True)),
        )
        db.add(shift)
        await db.flush()
        return shift

    async def update_shift(self, db: AsyncSession, *, organization_id: str, shift_id: str, data: dict[str, Any]) -> Optional[Shift]:
        shift = (
            await db.execute(
                select(Shift).where(Shift.organization_id == organization_id, Shift.id == shift_id)
            )
        ).scalar_one_or_none()
        if shift is None:
            return None
        for field in ("name", "start_time", "end_time", "work_hours", "break_minutes",
                      "days", "timezone", "is_flexible", "is_active"):
            if field in data:
                setattr(shift, field, data[field])
        await db.flush()
        return shift

    async def get_shift(self, db: AsyncSession, *, organization_id: str, shift_id: str) -> Optional[Shift]:
        return (
            await db.execute(
                select(Shift).where(Shift.organization_id == organization_id, Shift.id == shift_id)
            )
        ).scalar_one_or_none()

    async def list_shifts(self, db: AsyncSession, *, organization_id: str, active_only: bool = False) -> list[Shift]:
        query = select(Shift).where(Shift.organization_id == organization_id)
        if active_only:
            query = query.where(Shift.is_active.is_(True))
        return (await db.execute(query.order_by(Shift.name))).scalars().all()

    async def delete_shift(self, db: AsyncSession, *, organization_id: str, shift_id: str) -> bool:
        shift = await self.get_shift(db, organization_id=organization_id, shift_id=shift_id)
        if shift is None:
            return False
        await db.delete(shift)
        await db.flush()
        return True

    # ------------------------------------------------------------------ holidays

    async def add_holiday(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> Holiday:
        holiday = Holiday(
            organization_id=organization_id,
            name=data["name"],
            date=to_date(data["date"]),
            kind=data.get("kind", "public"),
            optional=bool(data.get("optional", False)),
        )
        db.add(holiday)
        await db.flush()
        return holiday

    async def list_holidays(self, db: AsyncSession, *, organization_id: str, year: Optional[int] = None) -> list[Holiday]:
        query = select(Holiday).where(Holiday.organization_id == organization_id)
        if year:
            query = query.where(func.extract("year", Holiday.date) == year)
        return (await db.execute(query.order_by(Holiday.date))).scalars().all()

    async def delete_holiday(self, db: AsyncSession, *, organization_id: str, holiday_id: str) -> bool:
        holiday = (
            await db.execute(
                select(Holiday).where(Holiday.organization_id == organization_id, Holiday.id == holiday_id)
            )
        ).scalar_one_or_none()
        if holiday is None:
            return False
        await db.delete(holiday)
        await db.flush()
        return True

    # ------------------------------------------------------------------ clock in / out

    async def today_record(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> Optional[AttendanceRecord]:
        return (
            await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.organization_id == organization_id,
                    AttendanceRecord.employee_id == employee_id,
                    AttendanceRecord.date == utcnow().date(),
                )
            )
        ).scalar_one_or_none()

    async def clock_in(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        source: str = "app", shift_id: Optional[str] = None, work_mode: str = "office",
        location: Optional[str] = None, note: Optional[str] = None,
    ) -> AttendanceRecord:
        """Clock in for today. Idempotent — returns the existing open record."""
        record = await self.today_record(db, organization_id=organization_id, employee_id=employee_id)
        now = utcnow()
        if record is None:
            record = AttendanceRecord(
                organization_id=organization_id,
                employee_id=employee_id,
                date=now.date(),
                shift_id=shift_id,
                check_in=now,
                status="work_from_home" if work_mode in ("remote", "work_from_home") else "present",
                work_mode=work_mode,
                source=source if source in SOURCES else "app",
                location=location,
                note=note,
            )
            db.add(record)
            await db.flush()
            await _event_bus.publish(
                db,
                name="attendance.recorded",
                organization_id=organization_id,
                actor_id=employee_id,
                payload={"record_id": record.id, "event": "clock_in", "source": source, "date": record.date.isoformat()},
                flush=False,
            )
        elif record.check_out is None:
            record.source = source
        return record

    async def clock_out(self, db: AsyncSession, *, organization_id: str, employee_id: str, note: Optional[str] = None) -> Optional[AttendanceRecord]:
        """Clock out the open record and compute work / late / overtime minutes."""
        record = await self.today_record(db, organization_id=organization_id, employee_id=employee_id)
        if record is None or record.check_out is not None:
            return None
        now = utcnow()
        record.check_out = now
        record.note = note
        await self._compute_times(db, record)
        await db.flush()
        await _event_bus.publish(
            db,
            name="attendance.recorded",
            organization_id=organization_id,
            actor_id=employee_id,
            payload={
                "record_id": record.id, "event": "clock_out", "date": record.date.isoformat(),
                "work_minutes": record.work_minutes, "overtime_minutes": record.overtime_minutes,
                "late_minutes": record.late_minutes,
            },
            flush=False,
        )
        return record

    async def _compute_times(self, db: AsyncSession, record: AttendanceRecord) -> None:
        """Fill late / early / work / overtime minutes from check-in/out + shift."""
        shift = None
        if record.shift_id:
            shift = (
                await db.execute(
                    select(Shift).where(Shift.organization_id == record.organization_id, Shift.id == record.shift_id)
                )
            ).scalar_one_or_none()
        if shift is None:
            query = select(Shift).where(Shift.organization_id == record.organization_id, Shift.is_active.is_(True))
            rows = (await db.execute(query)).scalars().all()
            if rows:
                shift = rows[0]

        check_in = ensure_aware(record.check_in)
        check_out = ensure_aware(record.check_out)
        if check_in and check_out:
            worked = max(0, int((check_out - check_in).total_seconds() // 60))
            break_minutes = sum(int(b.get("minutes", 0) or 0) for b in (record.breaks or []))
            record.work_minutes = max(0, worked - break_minutes)

        if shift and check_in:
            start = datetime.combine(check_in.date(), _parse_hm(shift.start_time) or time(9, 0))
            late = int((ensure_aware(check_in) - ensure_aware(start)).total_seconds() // 60)
            record.late_minutes = max(0, late)
            if shift.is_flexible:
                record.late_minutes = 0
        if shift and check_out:
            end = datetime.combine(check_out.date(), _parse_hm(shift.end_time) or time(17, 0))
            beyond = int((ensure_aware(check_out) - ensure_aware(end)).total_seconds() // 60)
            record.overtime_minutes = max(0, beyond)
            early = int((ensure_aware(end) - ensure_aware(check_out)).total_seconds() // 60)
            record.early_departure_minutes = max(0, early)

    async def add_break(self, db: AsyncSession, *, organization_id: str, employee_id: str, minutes: int = 30) -> Optional[AttendanceRecord]:
        record = await self.today_record(db, organization_id=organization_id, employee_id=employee_id)
        if record is None or record.check_out is not None:
            return None
        breaks = list(record.breaks or [])
        now = utcnow()
        if breaks and breaks[-1].get("end") is None:
            return record  # already on break
        breaks.append({"start": now.isoformat(), "end": None, "minutes": minutes})
        record.breaks = breaks
        await db.flush()
        return record

    async def end_break(self, db: AsyncSession, *, organization_id: str, employee_id: str) -> Optional[AttendanceRecord]:
        record = await self.today_record(db, organization_id=organization_id, employee_id=employee_id)
        if record is None or record.check_out is not None:
            return None
        breaks = list(record.breaks or [])
        if breaks and breaks[-1].get("end") is None:
            started = ensure_aware(datetime.fromisoformat(breaks[-1]["start"]))
            elapsed = max(1, int((utcnow() - started).total_seconds() // 60))
            breaks[-1]["end"] = utcnow().isoformat()
            breaks[-1]["minutes"] = elapsed
            record.breaks = breaks
            await db.flush()
        return record

    # ------------------------------------------------------------------ manual records

    async def record_manual(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> AttendanceRecord:
        """HR-entered attendance for a past date (manual source)."""
        record_date = to_date(data["date"])
        existing = (
            await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.organization_id == organization_id,
                    AttendanceRecord.employee_id == employee_id,
                    AttendanceRecord.date == record_date,
                )
            )
        ).scalar_one_or_none()
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        record = existing or AttendanceRecord(
            organization_id=organization_id,
            employee_id=employee_id,
            date=record_date,
        )
        if check_in:
            record.check_in = to_dt(check_in)
        if check_out:
            record.check_out = to_dt(check_out)
        record.status = data.get("status", "present")
        record.source = "manual"
        record.note = data.get("note")
        record.verified_by = actor_id
        record.is_verified = True
        if record.check_in and record.check_out:
            await self._compute_times(db, record)
        if not existing:
            db.add(record)
        await db.flush()
        return record

    # ------------------------------------------------------------------ records & summary

    async def my_records(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        start: Optional[date] = None, end: Optional[date] = None, limit: int = 50,
    ) -> list[AttendanceRecord]:
        query = select(AttendanceRecord).where(
            AttendanceRecord.organization_id == organization_id,
            AttendanceRecord.employee_id == employee_id,
        )
        if start:
            query = query.where(AttendanceRecord.date >= start)
        if end:
            query = query.where(AttendanceRecord.date <= end)
        return (await db.execute(query.order_by(AttendanceRecord.date.desc()).limit(limit))).scalars().all()

    async def list_records(
        self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None,
        start: Optional[date] = None, end: Optional[date] = None, limit: int = 100,
    ) -> list[AttendanceRecord]:
        query = select(AttendanceRecord).where(AttendanceRecord.organization_id == organization_id)
        if employee_id:
            query = query.where(AttendanceRecord.employee_id == employee_id)
        if start:
            query = query.where(AttendanceRecord.date >= start)
        if end:
            query = query.where(AttendanceRecord.date <= end)
        return (await db.execute(query.order_by(AttendanceRecord.date.desc()).limit(limit))).scalars().all()

    async def summary(
        self, db: AsyncSession, *, organization_id: str, employee_id: str,
        start: Optional[date] = None, end: Optional[date] = None,
    ) -> dict[str, Any]:
        """Per-employee attendance summary for a period (default: current month)."""
        end = end or utcnow().date()
        start = start or end.replace(day=1)
        records = await self.my_records(db, organization_id=organization_id, employee_id=employee_id,
                                        start=start, end=end, limit=500)
        statuses: dict[str, int] = {}
        total_minutes = 0
        overtime_minutes = 0
        late_minutes = 0
        for record in records:
            statuses[record.status] = statuses.get(record.status, 0) + 1
            total_minutes += record.work_minutes or 0
            overtime_minutes += record.overtime_minutes or 0
            late_minutes += record.late_minutes or 0
        return {
            "employee_id": employee_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": len(records),
            "statuses": statuses,
            "total_minutes": total_minutes,
            "average_minutes": round(total_minutes / len(records)) if records else 0,
            "overtime_minutes": overtime_minutes,
            "late_minutes": late_minutes,
        }

    # ------------------------------------------------------------------ corrections

    async def request_correction(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, data: dict[str, Any],
    ) -> AttendanceCorrection:
        correction = AttendanceCorrection(
            organization_id=organization_id,
            employee_id=employee_id,
            attendance_id=data.get("attendance_id"),
            requested_date=to_date(data["date"]),
            reason=data["reason"],
            adjusted_check_in=to_dt(data.get("adjusted_check_in")),
            adjusted_check_out=to_dt(data.get("adjusted_check_out")),
        )
        db.add(correction)
        await db.flush()
        return correction

    async def list_corrections(
        self, db: AsyncSession, *, organization_id: str, employee_id: Optional[str] = None, status: Optional[str] = None,
    ) -> list[AttendanceCorrection]:
        query = select(AttendanceCorrection).where(AttendanceCorrection.organization_id == organization_id)
        if employee_id:
            query = query.where(AttendanceCorrection.employee_id == employee_id)
        if status:
            query = query.where(AttendanceCorrection.status == status)
        return (await db.execute(query.order_by(AttendanceCorrection.created_at.desc()))).scalars().all()

    async def review_correction(
        self, db: AsyncSession, *, organization_id: str, correction_id: str, decision: str, reviewer_id: str,
    ) -> Optional[AttendanceCorrection]:
        correction = (
            await db.execute(
                select(AttendanceCorrection).where(
                    AttendanceCorrection.organization_id == organization_id, AttendanceCorrection.id == correction_id
                )
            )
        ).scalar_one_or_none()
        if correction is None:
            return None
        correction.status = "approved" if decision == "approve" else "rejected"
        correction.reviewed_by = reviewer_id
        correction.reviewed_at = utcnow()
        if correction.status == "approved" and correction.attendance_id:
            record = await db.get(AttendanceRecord, correction.attendance_id)
            if record:
                if correction.adjusted_check_in:
                    record.check_in = correction.adjusted_check_in
                if correction.adjusted_check_out:
                    record.check_out = correction.adjusted_check_out
                await self._compute_times(db, record)
                record.is_verified = True
                record.verified_by = reviewer_id
        await db.flush()
        return correction

    # ------------------------------------------------------------------ anomalies (worker)

    async def detect_anomalies(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        """Records missing a check-out (previous days) or duplicate open records."""
        anomalies: list[dict[str, Any]] = []
        yesterday = utcnow().date() - timedelta(days=1)
        query = (
            select(AttendanceRecord, Employee)
            .join(Employee, Employee.id == AttendanceRecord.employee_id)
            .where(
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.check_in.is_not(None),
                AttendanceRecord.check_out.is_(None),
                AttendanceRecord.date <= yesterday,
            )
        )
        rows = await db.execute(query)
        for record, employee in rows.all():
            anomalies.append(
                {
                    "type": "missing_checkout",
                    "record_id": record.id,
                    "employee_id": record.employee_id,
                    "employee_name": employee.full_name,
                    "date": record.date.isoformat(),
                }
            )
        return anomalies


attendance_service = AttendanceService()
