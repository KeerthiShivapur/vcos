"""Messaging service — channels, conversations, DMs, reactions, receipts (Phase 5.17)."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import (
    _user_id_for_employee,
    emit_and_audit,
    notify_mentions,
    notify_user,
)
from app.models.communication import (
    Conversation,
    ConversationMember,
    Message,
    MessageReadReceipt,
    MessageReaction,
    PinnedMessage,
)
from app.models.employee import Employee


class MessageService:
    # ------------------------------------------------------------- conversations

    async def create_conversation(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Conversation:
        if payload.get("channel_kind") and payload.get("channel_key"):
            existing = (
                await db.execute(
                    select(Conversation).where(
                        Conversation.organization_id == organization_id,
                        Conversation.channel_kind == payload.get("channel_kind"),
                        Conversation.channel_key == payload.get("channel_key"),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                member_exists = (
                    await db.execute(
                        select(ConversationMember).where(
                            ConversationMember.organization_id == organization_id,
                            ConversationMember.conversation_id == existing.id,
                            ConversationMember.employee_id == actor.id,
                        )
                    )
                ).scalar_one_or_none()
                if member_exists is None:
                    db.add(
                        ConversationMember(
                            organization_id=organization_id,
                            conversation_id=existing.id,
                            employee_id=actor.id,
                            role="member",
                        )
                    )
                    await db.flush()
                return existing
        conversation = Conversation(
            organization_id=organization_id,
            type=payload.get("type", "dm"),
            title=payload.get("title"),
            channel_kind=payload.get("channel_kind"),
            channel_key=payload.get("channel_key"),
            community_id=payload.get("community_id"),
            created_by=actor.id,
        )
        db.add(conversation)
        await db.flush()
        db.add(
            ConversationMember(
                organization_id=organization_id,
                conversation_id=conversation.id,
                employee_id=actor.id,
                role="owner",
            )
        )
        for employee_id in payload.get("member_ids") or []:
            if employee_id == actor.id:
                continue
            db.add(
                ConversationMember(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    employee_id=employee_id,
                    role="member",
                )
            )
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.conversation_created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation.id, "type": conversation.type},
            resource_type="conversation",
            resource_id=conversation.id,
        )
        return conversation

    async def get_conversation(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str
    ) -> Optional[Conversation]:
        return (
            await db.execute(
                select(Conversation).where(
                    Conversation.organization_id == organization_id,
                    Conversation.id == conversation_id,
                )
            )
        ).scalar_one_or_none()

    async def list_conversations(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[Conversation]:
        rows = (
            await db.execute(
                select(Conversation)
                .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
                .where(
                    Conversation.organization_id == organization_id,
                    ConversationMember.employee_id == employee_id,
                    Conversation.is_archived.is_(False),
                )
                .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def update_conversation(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[Conversation]:
        conversation = await self.get_conversation(db, organization_id=organization_id, conversation_id=conversation_id)
        if conversation is None:
            return None
        for key in ("title", "channel_kind", "channel_key", "community_id"):
            if key in payload and payload[key] is not None:
                setattr(conversation, key, payload[key])
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.conversation_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation_id},
            resource_type="conversation",
            resource_id=conversation_id,
        )
        return conversation

    async def archive_conversation(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        conversation = await self.get_conversation(db, organization_id=organization_id, conversation_id=conversation_id)
        if conversation is None:
            return False
        conversation.is_archived = True
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.conversation_archived",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation_id},
            resource_type="conversation",
            resource_id=conversation_id,
        )
        return True

    async def add_member(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, employee_id: str, actor: Employee, ip_address: Optional[str]
    ) -> Optional[ConversationMember]:
        conversation = await self.get_conversation(db, organization_id=organization_id, conversation_id=conversation_id)
        if conversation is None:
            return None
        existing = (
            await db.execute(
                select(ConversationMember).where(
                    ConversationMember.organization_id == organization_id,
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        member = ConversationMember(
            organization_id=organization_id,
            conversation_id=conversation_id,
            employee_id=employee_id,
            role="member",
        )
        db.add(member)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.member_added",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation_id, "employee_id": employee_id},
            resource_type="conversation",
            resource_id=conversation_id,
        )
        return member

    async def remove_member(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, employee_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        member = (
            await db.execute(
                select(ConversationMember).where(
                    ConversationMember.organization_id == organization_id,
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return False
        await db.delete(member)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.member_removed",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation_id, "employee_id": employee_id},
            resource_type="conversation",
            resource_id=conversation_id,
        )
        return True

    async def members(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str
    ) -> list[ConversationMember]:
        return list(
            (
                await db.execute(
                    select(ConversationMember).where(
                        ConversationMember.organization_id == organization_id,
                        ConversationMember.conversation_id == conversation_id,
                    )
                )
            ).scalars().all()
        )

    async def find_or_create_dm(
        self, db: AsyncSession, *, organization_id: str, other_employee_id: str, actor: Employee, ip_address: Optional[str] = None
    ) -> Conversation:
        my_rows = (
            await db.execute(
                select(ConversationMember.conversation_id).where(
                    ConversationMember.organization_id == organization_id,
                    ConversationMember.employee_id == actor.id,
                )
            )
        ).scalars().all()
        if my_rows:
            candidate = (
                await db.execute(
                    select(Conversation).join(
                        ConversationMember, ConversationMember.conversation_id == Conversation.id
                    ).where(
                        Conversation.organization_id == organization_id,
                        Conversation.type == "dm",
                        Conversation.id.in_(my_rows),
                        ConversationMember.employee_id == other_employee_id,
                    )
                )
            ).scalars().first()
            if candidate is not None:
                return candidate
        conversation = Conversation(
            organization_id=organization_id,
            type="dm",
            created_by=actor.id,
        )
        db.add(conversation)
        await db.flush()
        db.add(
            ConversationMember(
                organization_id=organization_id,
                conversation_id=conversation.id,
                employee_id=actor.id,
                role="owner",
            )
        )
        db.add(
            ConversationMember(
                organization_id=organization_id,
                conversation_id=conversation.id,
                employee_id=other_employee_id,
                role="member",
            )
        )
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.conversation_created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation.id, "type": conversation.type},
            resource_type="conversation",
            resource_id=conversation.id,
        )
        return conversation

    # ------------------------------------------------------------- messages

    async def send(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Message:
        conversation = await self.get_conversation(db, organization_id=organization_id, conversation_id=conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")
        message = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            sender_id=actor.id,
            content=payload.get("content"),
            reply_to=payload.get("reply_to"),
            attachments=payload.get("attachments"),
            mentions=payload.get("mentions"),
        )
        db.add(message)
        conversation.last_message_at = func.now()
        conversation.message_count = (conversation.message_count or 0) + 1
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.message_sent",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"conversation_id": conversation_id, "message_id": message.id},
            resource_type="message",
            resource_id=message.id,
        )
        member_employees = await self.members(db, organization_id=organization_id, conversation_id=conversation_id)
        for member in member_employees:
            if member.employee_id == actor.id:
                continue
            user_id = await _user_id_for_employee(db, organization_id, member.employee_id)
            if not user_id:
                continue
            await notify_user(
                db,
                organization_id=organization_id,
                recipient_id=user_id,
                type="messaging.message",
                title=conversation.title or "New direct message",
                body=(payload.get("content") or "")[:160],
                actor_id=actor.id,
                link=f"/messages/{conversation_id}",
                entity_type="message",
                entity_id=message.id,
                priority="low",
            )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text=message.content or "",
            type="mention",
            title="You were mentioned in a message",
            body=(payload.get("content") or "")[:120],
            actor_id=actor.id,
            link=f"/messages/{conversation_id}",
            entity_type="message",
            entity_id=message.id,
            default_employee_ids=message.mentions,
        )
        return message

    async def get_message(
        self, db: AsyncSession, *, organization_id: str, message_id: str
    ) -> Optional[Message]:
        return (
            await db.execute(
                select(Message).where(
                    Message.organization_id == organization_id,
                    Message.id == message_id,
                )
            )
        ).scalar_one_or_none()

    async def list_messages(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, limit: int = 100, offset: int = 0
    ) -> list[Message]:
        return list(
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.organization_id == organization_id,
                        Message.conversation_id == conversation_id,
                    )
                    .order_by(Message.created_at.desc())
                    .limit(min(limit, 200))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update_message(
        self, db: AsyncSession, *, organization_id: str, message_id: str, content: str, actor: Employee, ip_address: Optional[str]
    ) -> Optional[Message]:
        message = await self.get_message(db, organization_id=organization_id, message_id=message_id)
        if message is None:
            return None
        message.content = content
        message.edited = True
        message.edited_at = datetime.now(timezone.utc)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.message_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"message_id": message_id},
            resource_type="message",
            resource_id=message_id,
        )
        return message

    async def delete_message(
        self, db: AsyncSession, *, organization_id: str, message_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        message = await self.get_message(db, organization_id=organization_id, message_id=message_id)
        if message is None:
            return False
        message.deleted = True
        message.deleted_at = func.now()
        message.content = None
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="messaging.message_deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"message_id": message_id},
            resource_type="message",
            resource_id=message_id,
        )
        return True

    async def toggle_reaction(
        self, db: AsyncSession, *, organization_id: str, message_id: str, emoji: str, actor: Employee,
        ip_address: Optional[str] = None,
    ) -> dict[str, Any]:
        message = await self.get_message(db, organization_id=organization_id, message_id=message_id)
        if message is None:
            raise ValueError("Message not found")
        row = (
            await db.execute(
                select(MessageReaction).where(
                    MessageReaction.organization_id == organization_id,
                    MessageReaction.message_id == message_id,
                    MessageReaction.employee_id == actor.id,
                    MessageReaction.emoji == emoji,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            reacted = False
        else:
            db.add(
                MessageReaction(
                    organization_id=organization_id,
                    message_id=message_id,
                    employee_id=actor.id,
                    emoji=emoji,
                )
            )
            reacted = True
        count = (
            await db.execute(
                select(func.count(MessageReaction.id)).where(
                    MessageReaction.organization_id == organization_id,
                    MessageReaction.message_id == message_id,
                )
            )
        ).scalar_one()
        message.reaction_count = count
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name=(
                "messaging.message_reaction_added" if reacted else "messaging.message_reaction_removed"
            ),
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"message_id": message_id, "emoji": emoji},
            resource_type="message",
            resource_id=message_id,
        )
        return {"reacted": reacted, "reaction_count": count}

    async def reactions(
        self, db: AsyncSession, *, organization_id: str, message_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(MessageReaction.emoji, func.count(MessageReaction.id))
                .where(
                    MessageReaction.organization_id == organization_id,
                    MessageReaction.message_id == message_id,
                )
                .group_by(MessageReaction.emoji)
                .order_by(func.count(MessageReaction.id).desc())
            )
        ).all()
        return [{"emoji": emoji, "count": count} for emoji, count in rows]

    async def mark_read(
        self, db: AsyncSession, *, organization_id: str, message_id: str, employee_id: str
    ) -> bool:
        message = await self.get_message(db, organization_id=organization_id, message_id=message_id)
        if message is None or message.sender_id == employee_id:
            return False
        row = (
            await db.execute(
                select(MessageReadReceipt).where(
                    MessageReadReceipt.organization_id == organization_id,
                    MessageReadReceipt.message_id == message_id,
                    MessageReadReceipt.reader_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            stmt = (
                pg_insert(MessageReadReceipt)
                .values(
                    organization_id=organization_id,
                    message_id=message_id,
                    reader_id=employee_id,
                )
                .on_conflict_do_nothing(
                    constraint="uq_message_read_receipts_reader",
                )
            )
            await db.execute(stmt)
        return True

    async def unread_counts(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Message.conversation_id, func.count(Message.id))
                .outerjoin(
                    MessageReadReceipt,
                    and_(
                        MessageReadReceipt.message_id == Message.id,
                        MessageReadReceipt.reader_id == employee_id,
                    ),
                )
                .where(
                    Message.organization_id == organization_id,
                    Message.sender_id != employee_id,
                    Message.deleted.is_(False),
                    MessageReadReceipt.id.is_(None),
                )
                .group_by(Message.conversation_id)
            )
        ).all()
        return [{"conversation_id": cid, "unread": count} for cid, count in rows]

    async def mark_conversation_read(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, employee_id: str
    ) -> None:
        messages = (
            await db.execute(
                select(Message).where(
                    Message.organization_id == organization_id,
                    Message.conversation_id == conversation_id,
                    Message.sender_id != employee_id,
                    Message.deleted.is_(False),
                )
            )
        ).scalars().all()
        if messages:
            stmt = pg_insert(MessageReadReceipt).on_conflict_do_nothing(
                constraint="uq_message_read_receipts_reader",
            )
            await db.execute(stmt, [
                {
                    "organization_id": organization_id,
                    "message_id": message.id,
                    "reader_id": employee_id,
                }
                for message in messages
            ])
        membership = (
            await db.execute(
                select(ConversationMember).where(
                    ConversationMember.organization_id == organization_id,
                    ConversationMember.conversation_id == conversation_id,
                    ConversationMember.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if membership is not None:
            membership.last_read_at = func.now()

    async def pin_message(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str, message_id: str, actor: Employee
    ) -> bool:
        message = await self.get_message(db, organization_id=organization_id, message_id=message_id)
        if message is None or message.conversation_id != conversation_id:
            return False
        existing = (
            await db.execute(
                select(PinnedMessage).where(
                    PinnedMessage.organization_id == organization_id,
                    PinnedMessage.message_id == message_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await db.delete(existing)
            return False
        db.add(
            PinnedMessage(
                organization_id=organization_id,
                conversation_id=conversation_id,
                message_id=message_id,
                pinned_by=actor.id,
            )
        )
        return True

    async def pinned_messages(
        self, db: AsyncSession, *, organization_id: str, conversation_id: str
    ) -> list[PinnedMessage]:
        return list(
            (
                await db.execute(
                    select(PinnedMessage)
                    .where(
                        PinnedMessage.organization_id == organization_id,
                        PinnedMessage.conversation_id == conversation_id,
                    )
                    .order_by(PinnedMessage.created_at.desc())
                )
            ).scalars().all()
        )

    async def my_mention_threads(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, limit: int = 50
    ) -> list[Message]:
        me = (
            await db.execute(
                select(Employee.email).where(
                    Employee.organization_id == organization_id,
                    Employee.id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if not me or "@" not in me:
            return []
        handle = me.split("@", 1)[0].lower()
        return list(
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.organization_id == organization_id,
                        Message.sender_id != employee_id,
                        Message.deleted.is_(False),
                        Message.content.like(f"%@{handle}%"),
                    )
                    .order_by(Message.created_at.desc())
                    .limit(min(limit, 200))
                )
            ).scalars().all()
        )


message_service = MessageService()
