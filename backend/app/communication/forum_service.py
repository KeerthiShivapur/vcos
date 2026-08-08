"""Forum service — professional Q&A threads, replies, votes (Phase 5.6)."""

from typing import Any, Optional

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_mentions, notify_user
from app.models.communication import ForumReply, ForumThread, ForumVote
from app.models.employee import Employee


class ForumService:
    # ------------------------------------------------------------- threads

    async def create_thread(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> ForumThread:
        thread = ForumThread(
            organization_id=organization_id,
            category=payload["category"],
            title=payload["title"],
            content=payload.get("content"),
            author_id=actor.id,
            tags=payload.get("tags"),
        )
        db.add(thread)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.posted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"thread_id": thread.id, "category": thread.category},
            resource_type="forum_thread",
            resource_id=thread.id,
        )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text=thread.content,
            type="mention",
            title="You were mentioned in a forum thread",
            body=thread.title,
            actor_id=actor.id,
            link=f"/forums/{thread.id}",
            entity_type="forum_thread",
            entity_id=thread.id,
        )
        return thread

    async def get_thread(self, db: AsyncSession, *, organization_id: str, thread_id: str) -> Optional[ForumThread]:
        return (
            await db.execute(
                select(ForumThread).where(
                    ForumThread.organization_id == organization_id,
                    ForumThread.id == thread_id,
                )
            )
        ).scalar_one_or_none()

    async def list_threads(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ForumThread]:
        filters = [ForumThread.organization_id == organization_id]
        if category:
            filters.append(ForumThread.category == category)
        if status:
            filters.append(ForumThread.status == status)
        if search:
            filters.append(
                func.lower(ForumThread.title).like(f"%{search.lower()}%")
                | func.lower(ForumThread.content).like(f"%{search.lower()}%")
            )
        if tag:
            filters.append(func.cast(ForumThread.tags, String).like(f'%"{tag}"%'))
        return list(
            (
                await db.execute(
                    select(ForumThread)
                    .where(*filters)
                    .order_by(ForumThread.is_pinned.desc(), ForumThread.updated_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update_thread(
        self, db: AsyncSession, *, organization_id: str, thread_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[ForumThread]:
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(thread, key):
                setattr(thread, key, value)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.thread_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"thread_id": thread_id},
            resource_type="forum_thread",
            resource_id=thread_id,
        )
        return thread

    async def delete_thread(
        self, db: AsyncSession, *, organization_id: str, thread_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is None:
            return False
        await db.delete(thread)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.thread_deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"thread_id": thread_id},
            resource_type="forum_thread",
            resource_id=thread_id,
        )
        return True

    async def register_view(self, db: AsyncSession, *, organization_id: str, thread_id: str) -> None:
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is not None:
            thread.view_count = (thread.view_count or 0) + 1

    async def toggle_pin(self, db: AsyncSession, *, organization_id: str, thread_id: str, pinned: bool) -> Optional[ForumThread]:
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is None:
            return None
        thread.is_pinned = pinned
        return thread

    # ------------------------------------------------------------- replies

    async def add_reply(
        self, db: AsyncSession, *, organization_id: str, thread_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> ForumReply:
        reply = ForumReply(
            organization_id=organization_id,
            thread_id=thread_id,
            parent_id=payload.get("parent_id"),
            author_id=actor.id,
            content=payload["content"],
        )
        db.add(reply)
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is not None:
            thread.reply_count = (thread.reply_count or 0) + 1
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.replied",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"thread_id": thread_id, "reply_id": reply.id},
            resource_type="forum_reply",
            resource_id=reply.id,
        )
        if thread is not None and thread.author_id and thread.author_id != actor.id:
            await notify_user(
                db,
                organization_id=organization_id,
                recipient_id=thread.author_id,
                type="community.activity",
                title="New reply to your forum thread",
                body=reply.content[:160],
                actor_id=actor.id,
                link=f"/forums/{thread_id}",
                entity_type="forum_thread",
                entity_id=thread_id,
            )
        await notify_mentions(
            db,
            organization_id=organization_id,
            text=reply.content,
            type="mention",
            title="You were mentioned in a forum reply",
            body=reply.content[:120],
            actor_id=actor.id,
            link=f"/forums/{thread_id}",
            entity_type="forum_thread",
            entity_id=thread_id,
        )
        return reply

    async def get_reply(self, db: AsyncSession, *, organization_id: str, reply_id: str) -> Optional[ForumReply]:
        return (
            await db.execute(
                select(ForumReply).where(
                    ForumReply.organization_id == organization_id,
                    ForumReply.id == reply_id,
                )
            )
        ).scalar_one_or_none()

    async def list_replies(
        self, db: AsyncSession, *, organization_id: str, thread_id: str, limit: int = 300, offset: int = 0
    ) -> list[ForumReply]:
        return list(
            (
                await db.execute(
                    select(ForumReply)
                    .where(ForumReply.organization_id == organization_id, ForumReply.thread_id == thread_id)
                    .order_by(ForumReply.created_at.asc())
                    .limit(min(limit, 1000))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update_reply(
        self, db: AsyncSession, *, organization_id: str, reply_id: str, payload: dict, actor: Employee, ip_address: Optional[str]
    ) -> Optional[ForumReply]:
        reply = await self.get_reply(db, organization_id=organization_id, reply_id=reply_id)
        if reply is None:
            return None
        if "content" in payload:
            reply.content = payload["content"]
            reply.edited = True
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.reply_updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"reply_id": reply_id},
            resource_type="forum_reply",
            resource_id=reply_id,
        )
        return reply

    async def delete_reply(
        self, db: AsyncSession, *, organization_id: str, reply_id: str, actor: Employee, ip_address: Optional[str]
    ) -> bool:
        reply = await self.get_reply(db, organization_id=organization_id, reply_id=reply_id)
        if reply is None:
            return False
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=reply.thread_id)
        if thread is not None:
            thread.reply_count = max(0, (thread.reply_count or 1) - 1)
        await db.delete(reply)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.reply_deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"reply_id": reply_id},
            resource_type="forum_reply",
            resource_id=reply_id,
        )
        return True

    async def accept_answer(
        self, db: AsyncSession, *, organization_id: str, thread_id: str, reply_id: Optional[str], actor: Employee, ip_address: Optional[str]
    ) -> Optional[ForumThread]:
        thread = await self.get_thread(db, organization_id=organization_id, thread_id=thread_id)
        if thread is None:
            return None
        if thread.accepted_reply_id:
            previous = await self.get_reply(db, organization_id=organization_id, reply_id=thread.accepted_reply_id)
            if previous is not None:
                previous.is_accepted = False
        thread.accepted_reply_id = reply_id
        thread.is_resolved = reply_id is not None
        if reply_id:
            reply = await self.get_reply(db, organization_id=organization_id, reply_id=reply_id)
            if reply is not None:
                reply.is_accepted = True
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="forum.accepted_answer",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"thread_id": thread_id, "reply_id": reply_id},
            resource_type="forum_thread",
            resource_id=thread_id,
        )
        return thread

    # ------------------------------------------------------------- votes

    async def vote(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str, value: int, actor: Employee
    ) -> dict[str, Any]:
        if target_type not in ("thread", "reply"):
            raise ValueError("Unknown vote target")
        if target_type == "thread":
            target = await self.get_thread(db, organization_id=organization_id, thread_id=target_id)
        else:
            target = await self.get_reply(db, organization_id=organization_id, reply_id=target_id)
        if target is None:
            raise ValueError("Target not found")
        value = 1 if value >= 0 else -1
        row = (
            await db.execute(
                select(ForumVote).where(
                    ForumVote.organization_id == organization_id,
                    ForumVote.target_type == target_type,
                    ForumVote.target_id == target_id,
                    ForumVote.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            if row.value == value:
                await db.delete(row)
                target.vote_count = max(0, (target.vote_count or 1) - value)
                voted = None
            else:
                target.vote_count = (target.vote_count or 0) + value - row.value
                row.value = value
                voted = value
        else:
            db.add(
                ForumVote(
                    organization_id=organization_id,
                    target_type=target_type,
                    target_id=target_id,
                    employee_id=actor.id,
                    value=value,
                )
            )
            target.vote_count = (target.vote_count or 0) + value
            voted = value
        return {"voted": voted, "vote_count": target.vote_count}

    async def my_vote(
        self, db: AsyncSession, *, organization_id: str, target_type: str, target_id: str, employee_id: str
    ) -> Optional[int]:
        row = (
            await db.execute(
                select(ForumVote.value).where(
                    ForumVote.organization_id == organization_id,
                    ForumVote.target_type == target_type,
                    ForumVote.target_id == target_id,
                    ForumVote.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        return row

    async def categories(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ForumThread.category, func.count(ForumThread.id), func.max(ForumThread.updated_at))
                .where(ForumThread.organization_id == organization_id)
                .group_by(ForumThread.category)
                .order_by(func.count(ForumThread.id).desc())
                .limit(min(limit, 200))
            )
        ).all()
        return [{"category": row[0], "thread_count": row[1], "last_activity": row[2]} for row in rows]


forum_service = ForumService()
