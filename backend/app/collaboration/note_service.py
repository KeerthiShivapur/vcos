"""Meeting notes service — collaborative markdown, versioned (Phase 6)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.collaboration import MeetingNote
from app.models.employee import Employee


class NoteService:
    async def list(self, db: AsyncSession, *, organization_id: str, meeting_id: str) -> list[MeetingNote]:
        rows = (
            await db.execute(
                select(MeetingNote)
                .where(MeetingNote.organization_id == organization_id, MeetingNote.meeting_id == meeting_id)
                .order_by(MeetingNote.updated_at.asc())
            )
        ).scalars().all()
        for note in rows:
            if note.author_id:
                author = await db.get(Employee, note.author_id)
                note.author_name = author.full_name if author else None
        return rows

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        author: Employee,
        content: str,
        session_id: Optional[str] = None,
    ) -> MeetingNote:
        note = MeetingNote(
            organization_id=organization_id,
            meeting_id=meeting_id,
            session_id=session_id,
            author_id=author.id,
            content=content or "",
        )
        db.add(note)
        await db.flush()
        return note

    async def get(self, db: AsyncSession, *, organization_id: str, meeting_id: str, note_id: str) -> Optional[MeetingNote]:
        return (
            await db.execute(
                select(MeetingNote).where(
                    MeetingNote.organization_id == organization_id,
                    MeetingNote.meeting_id == meeting_id,
                    MeetingNote.id == note_id,
                )
            )
        ).scalar_one_or_none()

    async def update(
        self, db: AsyncSession, *, note: MeetingNote, content: str, author: Optional[Employee] = None
    ) -> MeetingNote:
        if note.content != content:
            note.content = content
            note.version = (note.version or 1) + 1
            note.updated_at = utcnow()
        if author is not None and note.author_id is None:
            note.author_id = author.id
        return note

    async def delete(self, db: AsyncSession, *, note: MeetingNote) -> None:
        await db.delete(note)


note_service = NoteService()
