"""Meeting participant service — live presence, media state, attendance base (Phase 6)."""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import MeetingParticipant


class ParticipantService:
    async def list(
        self, db: AsyncSession, *, organization_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        from app.models.employee import Employee

        rows = (
            await db.execute(
                select(MeetingParticipant)
                .where(
                    MeetingParticipant.organization_id == organization_id,
                    MeetingParticipant.session_id == session_id,
                )
                .order_by(MeetingParticipant.joined_at.asc())
            )
        ).scalars().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            emp = await db.get(Employee, row.employee_id)
            out.append(
                {
                    "id": row.id,
                    "session_id": row.session_id,
                    "employee_id": row.employee_id,
                    "name": emp.full_name if emp else "Unknown",
                    "designation": emp.designation if emp else None,
                    "avatar_url": emp.avatar_url if emp else None,
                    "role": row.role,
                    "status": row.status,
                    "device": row.device,
                    "mic_enabled": row.mic_enabled,
                    "camera_enabled": row.camera_enabled,
                    "screen_sharing": row.screen_sharing,
                    "is_present": row.is_present,
                    "joined_at": row.joined_at,
                    "left_at": row.left_at,
                    "last_active_at": row.last_active_at,
                    "speaking_seconds": row.speaking_seconds,
                    "messages_count": row.messages_count,
                    "raised_hand": row.raised_hand,
                }
            )
        return out

    async def heartbeat(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        session_id: str,
        employee_id: str,
        device: Optional[str] = None,
        mic_enabled: Optional[bool] = None,
        camera_enabled: Optional[bool] = None,
        screen_sharing: Optional[bool] = None,
        raised_hand: Optional[bool] = None,
    ) -> Optional[MeetingParticipant]:
        participant = await self._get(db, organization_id=organization_id, session_id=session_id, employee_id=employee_id)
        if participant is None:
            return None
        participant.is_present = True
        participant.last_active_at = utcnow()
        if device:
            participant.device = device
        if mic_enabled is not None:
            participant.mic_enabled = mic_enabled
        if camera_enabled is not None:
            participant.camera_enabled = camera_enabled
        if screen_sharing is not None:
            participant.screen_sharing = screen_sharing
        if raised_hand is not None:
            participant.raised_hand = raised_hand
        return participant

    async def expire_idle(self, db: AsyncSession, *, organization_id: Optional[str] = None, idle_minutes: int = 10) -> int:
        cutoff = utcnow() - timedelta(minutes=idle_minutes)
        stmt = select(MeetingParticipant).where(
            MeetingParticipant.is_present.is_(True),
            MeetingParticipant.last_active_at.isnot(None),
            MeetingParticipant.last_active_at < cutoff,
        )
        if organization_id:
            stmt = stmt.where(MeetingParticipant.organization_id == organization_id)
        rows = (await db.execute(stmt)).scalars().all()
        now = utcnow()
        for row in rows:
            if row.joined_at:
                row.speaking_seconds += max(
                    0, int((now - ensure_aware(row.joined_at)).total_seconds()) // 10
                )
            row.is_present = False
            row.status = "left"
            row.left_at = now
        return len(rows)

    async def stats(self, db: AsyncSession, *, organization_id: str, session_id: str) -> dict[str, Any]:
        base = select(MeetingParticipant).where(
            MeetingParticipant.organization_id == organization_id,
            MeetingParticipant.session_id == session_id,
        )
        joined = (
            await db.execute(base.where(MeetingParticipant.status == "joined"))
        ).scalars().all()
        present = sum(1 for row in joined if row.is_present)
        total_rows = (await db.execute(base)).scalars().all()
        speaking = sum(row.speaking_seconds for row in total_rows)
        return {
            "session_id": session_id,
            "invited": len(total_rows),
            "joined": len(joined),
            "present": present,
            "speaking_seconds": speaking,
            "with_mic": sum(1 for row in total_rows if row.mic_enabled),
            "with_camera": sum(1 for row in total_rows if row.camera_enabled),
            "screen_sharing": sum(1 for row in total_rows if row.screen_sharing),
            "raised_hands": sum(1 for row in total_rows if row.raised_hand),
        }

    async def _get(
        self, db: AsyncSession, *, organization_id: str, session_id: str, employee_id: str
    ) -> Optional[MeetingParticipant]:
        return (
            await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.organization_id == organization_id,
                    MeetingParticipant.session_id == session_id,
                    MeetingParticipant.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()


participant_service = ParticipantService()
