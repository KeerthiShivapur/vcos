"""In-session chat service (Phase 6.5) — persisted messages + system events."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.collaboration import MeetingChatMessage, MeetingParticipant
from app.models.employee import Employee


class ChatService:
    async def list(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        before: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(MeetingChatMessage)
            .where(
                MeetingChatMessage.organization_id == organization_id,
                MeetingChatMessage.meeting_id == meeting_id,
            )
            .order_by(MeetingChatMessage.created_at.desc())
            .limit(min(limit, 200))
        )
        rows = list((await db.execute(stmt)).scalars().all())
        rows.reverse()
        out: list[dict[str, Any]] = []
        for row in rows:
            sender = await db.get(Employee, row.employee_id) if row.employee_id else None
            out.append(self._payload(row, sender))
        return out

    async def send(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session_id: Optional[str],
        employee: Employee,
        content: str,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValueError("Message cannot be empty")
        if len(text) > 4000:
            raise ValueError("Message is too long (4000 chars max)")
        message = MeetingChatMessage(
            organization_id=organization_id,
            meeting_id=meeting_id,
            session_id=session_id,
            employee_id=employee.id,
            content=text,
            kind="message",
            reply_to=reply_to,
            created_at=utcnow(),
        )
        db.add(message)
        await db.flush()
        if session_id:
            participant = (
                await db.execute(
                    select(MeetingParticipant).where(
                        MeetingParticipant.organization_id == organization_id,
                        MeetingParticipant.session_id == session_id,
                        MeetingParticipant.employee_id == employee.id,
                    )
                )
            ).scalar_one_or_none()
            if participant is not None:
                participant.messages_count = (participant.messages_count or 0) + 1
        return self._payload(message, employee)

    async def add_system(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        meeting_id: str,
        session_id: Optional[str],
        content: str,
    ) -> dict[str, Any]:
        message = MeetingChatMessage(
            organization_id=organization_id,
            meeting_id=meeting_id,
            session_id=session_id,
            employee_id=None,
            content=content,
            kind="system",
            created_at=utcnow(),
        )
        db.add(message)
        await db.flush()
        return self._payload(message, None)

    async def get(
        self, db: AsyncSession, *, organization_id: str, meeting_id: str, message_id: str
    ) -> Optional[MeetingChatMessage]:
        return (
            await db.execute(
                select(MeetingChatMessage).where(
                    MeetingChatMessage.organization_id == organization_id,
                    MeetingChatMessage.meeting_id == meeting_id,
                    MeetingChatMessage.id == message_id,
                )
            )
        ).scalar_one_or_none()

    async def delete(
        self, db: AsyncSession, *, message: MeetingChatMessage, actor: Employee, is_host: bool
    ) -> bool:
        """Deletable by the author or the meeting host."""
        if message.employee_id != actor.id and not is_host:
            raise ValueError("Only the author or the meeting host can delete this message")
        await db.delete(message)
        return True

    def _payload(self, message: MeetingChatMessage, sender: Optional[Employee]) -> dict[str, Any]:
        return {
            "id": message.id,
            "meeting_id": message.meeting_id,
            "session_id": message.session_id,
            "employee_id": message.employee_id,
            "sender_name": sender.full_name if sender else None,
            "sender_designation": sender.designation if sender else None,
            "avatar_url": sender.avatar_url if sender else None,
            "content": message.content,
            "kind": message.kind,
            "reply_to": message.reply_to,
            "created_at": message.created_at,
        }


chat_service = ChatService()
