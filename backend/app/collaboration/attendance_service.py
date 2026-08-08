"""Attendance Intelligence (Phase 6.11) — measures presence, participation,
engagement and attention per session, then snapshots it for analytics."""

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import MeetingAnalytics, MeetingParticipant, MeetingSession
from app.models.meeting import Meeting


class AttendanceService:
    async def metrics(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: Optional[MeetingSession],
    ) -> dict[str, Any]:
        """Live attendance + participation metrics for a session."""
        rows = (
            await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.organization_id == organization_id,
                    MeetingParticipant.session_id == session.id,
                )
            )
        ).scalars().all() if session else []

        duration = session.duration_seconds if session and session.duration_seconds else 0
        start = ensure_aware(session.started_at) if session and session.started_at else None
        end = ensure_aware(session.ended_at) if session and session.ended_at else None

        joined = [r for r in rows if r.status == "joined"]
        present = [r for r in joined if r.is_present]
        late_joiners: list[dict[str, Any]] = []
        early_exits: list[dict[str, Any]] = []
        per_participant: list[dict[str, Any]] = []
        total_speaking = 0
        total_messages = 0

        for row in rows:
            joined_at = ensure_aware(row.joined_at) if row.joined_at else start
            left_at = ensure_aware(row.left_at) if row.left_at else end
            attended = 0
            if joined_at and left_at:
                attended = max(0, int((left_at - joined_at).total_seconds()))
            elif joined_at and start:
                attended = duration or 0
            total_speaking += row.speaking_seconds or 0
            total_messages += row.messages_count or 0
            if start and joined_at and (joined_at - start).total_seconds() > 300:
                late_joiners.append({"employee_id": row.employee_id, "late_seconds": int((joined_at - start).total_seconds())})
            if end and left_at and (end - left_at).total_seconds() > 300:
                early_exits.append({"employee_id": row.employee_id, "early_seconds": int((end - left_at).total_seconds())})
            per_participant.append(
                {
                    "employee_id": row.employee_id,
                    "role": row.role,
                    "status": row.status,
                    "is_present": row.is_present,
                    "attended_seconds": attended,
                    "speaking_seconds": row.speaking_seconds or 0,
                    "messages": row.messages_count or 0,
                    "mic_enabled": row.mic_enabled,
                    "camera_enabled": row.camera_enabled,
                    "screen_sharing": row.screen_sharing,
                    "raised_hand": row.raised_hand,
                    "joined_at": row.joined_at,
                    "left_at": row.left_at,
                }
            )

        participation = 0
        if duration > 0 and per_participant:
            attended_sum = sum(p["attended_seconds"] for p in per_participant)
            participation = int(round(100 * attended_sum / (duration * len(per_participant)))) if attended_sum else 0

        engagement = min(
            100,
            int(
                round(
                    0.5 * participation
                    + 25 * min(1.0, total_speaking / max(duration, 1))
                    + 25 * min(1.0, total_messages / max(len(per_participant), 1))
                )
            ),
        )
        return {
            "duration_seconds": duration,
            "participants_invited": len(rows),
            "participants_joined": len(joined),
            "participants_present": len(present),
            "late_joiners": late_joiners,
            "early_exits": early_exits,
            "with_mic": sum(1 for r in rows if r.mic_enabled),
            "with_camera": sum(1 for r in rows if r.camera_enabled),
            "screen_shares": sum(1 for r in rows if r.screen_sharing),
            "raised_hands": sum(1 for r in rows if r.raised_hand),
            "messages_count": total_messages,
            "speaking_seconds_total": total_speaking,
            "participation_score": participation,
            "engagement_score": engagement,
            "per_participant": per_participant,
        }

    async def snapshot(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting: Meeting,
        session: Optional[MeetingSession],
        metrics: dict[str, Any],
    ) -> MeetingAnalytics:
        row = MeetingAnalytics(
            organization_id=organization_id,
            meeting_id=meeting.id,
            session_id=session.id if session else None,
            duration_seconds=metrics["duration_seconds"],
            participants_invited=metrics["participants_invited"],
            participants_joined=metrics["participants_joined"],
            participants_present=metrics["participants_present"],
            late_joiners=len(metrics["late_joiners"]),
            early_exits=len(metrics["early_exits"]),
            with_mic=metrics["with_mic"],
            with_camera=metrics["with_camera"],
            screen_shares=metrics["screen_shares"],
            messages_count=metrics["messages_count"],
            engagement_score=metrics["engagement_score"],
            snapshot=json.dumps(metrics, default=str),
            created_at=utcnow(),
        )
        db.add(row)
        await db.flush()
        return row

    async def for_meeting(
        self, db: AsyncSession, *, organization_id: str, meeting_id: str
    ) -> Optional[MeetingAnalytics]:
        return (
            await db.execute(
                select(MeetingAnalytics)
                .where(
                    MeetingAnalytics.organization_id == organization_id,
                    MeetingAnalytics.meeting_id == meeting_id,
                )
                .order_by(MeetingAnalytics.created_at.desc())
            )
        ).scalars().first()

    def payload(self, analytics: MeetingAnalytics) -> dict[str, Any]:
        try:
            snapshot = json.loads(analytics.snapshot or "{}")
        except (TypeError, ValueError):
            snapshot = {}
        return {
            "id": analytics.id,
            "meeting_id": analytics.meeting_id,
            "session_id": analytics.session_id,
            "duration_seconds": analytics.duration_seconds,
            "participants_invited": analytics.participants_invited,
            "participants_joined": analytics.participants_joined,
            "participants_present": analytics.participants_present,
            "late_joiners": analytics.late_joiners,
            "early_exits": analytics.early_exits,
            "with_mic": analytics.with_mic,
            "with_camera": analytics.with_camera,
            "screen_shares": analytics.screen_shares,
            "messages_count": analytics.messages_count,
            "engagement_score": analytics.engagement_score,
            "metrics": snapshot,
            "created_at": analytics.created_at,
        }


attendance_service = AttendanceService()
