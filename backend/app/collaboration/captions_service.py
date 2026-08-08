"""Caption + transcript service (Phase 6.8/6.9) — live caption segments with
translation, and full speaker transcripts.

In production, streaming STT (e.g. Azure Speech) pushes caption segments here
and the transcription worker finalizes the transcript. When AI_PROVIDER is
none, the meeting intelligence service synthesizes segments from chat/notes.
"""

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.collaboration import MeetingCaption, MeetingTranscript
from app.models.employee import Employee

TRANSLATION_LANGUAGES = ("en", "hi", "kn", "ja", "de", "es", "fr", "zh", "ar", "pt", "ru", "it")


class CaptionsService:
    async def add(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session_id: Optional[str],
        employee_id: Optional[str],
        text: str,
        language: str = "en",
        start_ms: int = 0,
        end_ms: int = 0,
        translated_text: Optional[str] = None,
        translation_language: Optional[str] = None,
    ) -> MeetingCaption:
        caption = MeetingCaption(
            organization_id=organization_id,
            meeting_id=meeting_id,
            session_id=session_id,
            employee_id=employee_id,
            language=language,
            text=text,
            translated_text=translated_text,
            translation_language=translation_language,
            start_ms=start_ms,
            end_ms=end_ms,
            created_at=utcnow(),
        )
        db.add(caption)
        await db.flush()
        return caption

    async def list(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        after_ms: Optional[int] = None,
        language: Optional[str] = None,
        limit: int = 500,
    ) -> list[MeetingCaption]:
        stmt = select(MeetingCaption).where(
            MeetingCaption.organization_id == organization_id,
            MeetingCaption.meeting_id == meeting_id,
        )
        if after_ms is not None:
            stmt = stmt.where(MeetingCaption.start_ms >= after_ms)
        if language:
            stmt = stmt.where(MeetingCaption.language == language)
        stmt = stmt.order_by(MeetingCaption.start_ms.asc()).limit(limit)
        return list((await db.execute(stmt)).scalars().all())

    async def delete_all(self, db: AsyncSession, *, organization_id: str, meeting_id: str) -> int:
        rows = (
            await db.execute(
                select(MeetingCaption).where(
                    MeetingCaption.organization_id == organization_id,
                    MeetingCaption.meeting_id == meeting_id,
                )
            )
        ).scalars().all()
        for row in rows:
            await db.delete(row)
        return len(rows)

    def payload(self, caption: MeetingCaption, sender: Optional[Employee] = None) -> dict[str, Any]:
        return {
            "id": caption.id,
            "meeting_id": caption.meeting_id,
            "session_id": caption.session_id,
            "employee_id": caption.employee_id,
            "speaker_name": sender.full_name if sender else None,
            "language": caption.language,
            "text": caption.text,
            "translated_text": caption.translated_text,
            "translation_language": caption.translation_language,
            "start_ms": caption.start_ms,
            "end_ms": caption.end_ms,
            "created_at": caption.created_at,
        }


class TranscriptService:
    async def get(self, db: AsyncSession, *, organization_id: str, meeting_id: str) -> Optional[MeetingTranscript]:
        return (
            await db.execute(
                select(MeetingTranscript).where(
                    MeetingTranscript.organization_id == organization_id,
                    MeetingTranscript.meeting_id == meeting_id,
                )
            )
        ).scalar_one_or_none()

    async def get_or_create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session_id: Optional[str],
        language: str = "en",
    ) -> MeetingTranscript:
        transcript = await self.get(db, organization_id=organization_id, meeting_id=meeting_id)
        if transcript is None:
            transcript = MeetingTranscript(
                organization_id=organization_id,
                meeting_id=meeting_id,
                session_id=session_id,
                status="requested",
                language=language,
                content="",
                segments="[]",
                speakers="[]",
                word_count=0,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(transcript)
            await db.flush()
        return transcript

    async def save(
        self,
        db: AsyncSession,
        *,
        transcript: MeetingTranscript,
        content: str,
        segments: Optional[list[dict[str, Any]]] = None,
        speakers: Optional[list[dict[str, Any]]] = None,
        language: Optional[str] = None,
        status: str = "completed",
    ) -> MeetingTranscript:
        transcript.content = content
        if segments is not None:
            transcript.segments = json.dumps(segments, default=str)
        if speakers is not None:
            transcript.speakers = json.dumps(speakers, default=str)
        if language:
            transcript.language = language
        transcript.word_count = len(content.split())
        transcript.status = status
        transcript.updated_at = utcnow()
        return transcript

    def payload(self, transcript: MeetingTranscript) -> dict[str, Any]:
        try:
            segments = json.loads(transcript.segments or "[]")
            speakers = json.loads(transcript.speakers or "[]")
        except (TypeError, ValueError):
            segments, speakers = [], []
        return {
            "id": transcript.id,
            "meeting_id": transcript.meeting_id,
            "session_id": transcript.session_id,
            "status": transcript.status,
            "language": transcript.language,
            "content": transcript.content or "",
            "segments": segments,
            "speakers": speakers,
            "word_count": transcript.word_count,
            "created_at": transcript.created_at,
            "updated_at": transcript.updated_at,
        }


captions_service = CaptionsService()
transcript_service = TranscriptService()
