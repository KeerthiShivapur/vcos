"""Recording service (Phase 6.7) — start/stop/list/lookup/delete recordings.

In production the `start` action would hand off to a media gateway (SFU/mixer)
and the worker would poll object storage; here we manage the lifecycle metadata
and let the recording worker finalize completed items.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.collaboration import MeetingRecording, MeetingSession


class RecordingService:
    async def start(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session: Optional[MeetingSession],
        created_by: str,
        title: Optional[str] = None,
        kind: str = "manual",
        captions_enabled: bool = False,
        language: str = "en",
    ) -> MeetingRecording:
        recording = MeetingRecording(
            organization_id=organization_id,
            meeting_id=meeting_id,
            session_id=session.id if session else None,
            room_id=session.room_id if session else None,
            title=title or f"Recording {meeting_id[:8]}",
            kind=kind,
            status="recording",
            started_at=utcnow(),
            captions_enabled=captions_enabled,
            language=language,
            created_by=created_by,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(recording)
        await db.flush()
        if session is not None:
            session.is_recording = True
            session.updated_at = utcnow()
        return recording

    async def stop(self, db: AsyncSession, *, organization_id: str, recording_id: str) -> Optional[MeetingRecording]:
        recording = await self.get(db, organization_id=organization_id, recording_id=recording_id)
        if recording is None:
            return None
        now = utcnow()
        if recording.status in ("recording", "requested"):
            recording.status = "processing"
            recording.ended_at = now
            if recording.started_at:
                recording.duration_seconds = int((now - ensure_aware(recording.started_at)).total_seconds())
            recording.updated_at = now
        return recording

    async def get(self, db: AsyncSession, *, organization_id: str, recording_id: str) -> Optional[MeetingRecording]:
        return (
            await db.execute(
                select(MeetingRecording).where(
                    MeetingRecording.organization_id == organization_id,
                    MeetingRecording.id == recording_id,
                )
            )
        ).scalar_one_or_none()

    async def list(
        self, db: AsyncSession, *, organization_id: str, meeting_id: Optional[str] = None, limit: int = 50
    ) -> list[MeetingRecording]:
        stmt = select(MeetingRecording).where(MeetingRecording.organization_id == organization_id)
        if meeting_id:
            stmt = stmt.where(MeetingRecording.meeting_id == meeting_id)
        stmt = stmt.order_by(MeetingRecording.created_at.desc()).limit(limit)
        return list((await db.execute(stmt)).scalars().all())

    async def mark_complete(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        recording_id: str,
        file_url: Optional[str] = None,
        storage_key: Optional[str] = None,
        size_bytes: int = 0,
        format: str = "webm",
        mime_type: str = "video/webm",
        duration_seconds: Optional[int] = None,
    ) -> Optional[MeetingRecording]:
        recording = await self.get(db, organization_id=organization_id, recording_id=recording_id)
        if recording is None:
            return None
        recording.status = "completed"
        if file_url:
            recording.file_url = file_url
        if storage_key:
            recording.storage_key = storage_key
        recording.size_bytes = size_bytes or recording.size_bytes
        recording.format = format
        recording.mime_type = mime_type
        if duration_seconds is not None:
            recording.duration_seconds = duration_seconds
        recording.updated_at = utcnow()
        session = (
            await db.execute(
                select(MeetingSession).where(MeetingSession.id == recording.session_id)
            )
        ).scalar_one_or_none() if recording.session_id else None
        if session is not None:
            session.is_recording = False
            session.updated_at = utcnow()
        return recording

    async def delete(self, db: AsyncSession, *, recording: MeetingRecording) -> None:
        await db.delete(recording)

    def payload(self, recording: MeetingRecording) -> dict[str, Any]:
        return {
            "id": recording.id,
            "meeting_id": recording.meeting_id,
            "session_id": recording.session_id,
            "room_id": recording.room_id,
            "title": recording.title,
            "kind": recording.kind,
            "status": recording.status,
            "started_at": recording.started_at,
            "ended_at": recording.ended_at,
            "duration_seconds": recording.duration_seconds,
            "file_url": recording.file_url,
            "storage_key": recording.storage_key,
            "size_bytes": recording.size_bytes,
            "format": recording.format,
            "mime_type": recording.mime_type,
            "resolution": recording.resolution,
            "captions_enabled": recording.captions_enabled,
            "language": recording.language,
            "visibility": recording.visibility,
            "retention_days": recording.retention_days,
            "is_encrypted": recording.is_encrypted,
            "created_by": recording.created_by,
            "created_at": recording.created_at,
            "updated_at": recording.updated_at,
        }


recording_service = RecordingService()
