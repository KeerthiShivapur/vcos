"""Collaboration service — comments, mentions, watchers, favorites, presence (Phase 4.7)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.models.employee import Employee
from app.models.knowledge import (
    DocumentComment,
    DocumentFavorite,
    DocumentPresence,
    DocumentWatcher,
)
from app.models.user import User


class CollabService:
    async def list_comments(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
    ) -> list[DocumentComment]:
        rows = (
            await db.execute(
                select(DocumentComment)
                .where(
                    DocumentComment.organization_id == organization_id,
                    DocumentComment.entity_type == entity_type,
                    DocumentComment.entity_id == entity_id,
                )
                .order_by(DocumentComment.created_at.asc())
            )
        ).scalars().all()
        return list(rows)

    async def add_comment(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
        content: str, actor: User, ip_address: Optional[str] = None, parent_id: Optional[str] = None,
    ) -> DocumentComment:
        comment = DocumentComment(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            author_id=actor.id,
            content=content,
            parent_id=parent_id,
        )
        db.add(comment)
        await db.flush()
        await kb.emit_and_audit(
            db, organization_id=organization_id, name="knowledge.comment", actor=None,
            actor_user_id=actor.id, ip_address=ip_address,
            payload={"entity_type": entity_type, "entity_id": entity_id, "comment_id": comment.id, "content": content[:200]},
            resource_type=entity_type, resource_id=entity_id,
        )
        await self.notify_mentions(
            db, organization_id=organization_id, content=content,
            entity_type=entity_type, entity_id=entity_id, actor_user_id=actor.id,
        )
        await kb.notify_watchers(
            db,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            title="New comment on knowledge item",
            body=content[:120],
            actor_user_id=actor.id,
        )
        return comment

    async def update_comment(
        self, db: AsyncSession, *, organization_id: str, comment_id: str, content: str, user: User,
    ) -> Optional[DocumentComment]:
        comment = (
            await db.execute(
                select(DocumentComment).where(
                    DocumentComment.organization_id == organization_id, DocumentComment.id == comment_id
                )
            )
        ).scalar_one_or_none()
        if comment is None or comment.author_id != user.id:
            return None
        comment.content = content
        comment.updated_at = utcnow()
        await db.flush()
        return comment

    async def delete_comment(
        self, db: AsyncSession, *, organization_id: str, comment_id: str, user: User,
    ) -> bool:
        comment = (
            await db.execute(
                select(DocumentComment).where(
                    DocumentComment.organization_id == organization_id, DocumentComment.id == comment_id
                )
            )
        ).scalar_one_or_none()
        if comment is None or comment.author_id != user.id:
            return False
        replies = (
            await db.execute(
                select(DocumentComment).where(
                    DocumentComment.organization_id == organization_id, DocumentComment.parent_id == comment_id
                )
            )
        ).scalars().all()
        for reply in replies:
            await db.delete(reply)
        await db.delete(comment)
        await db.flush()
        return True

    async def notify_mentions(
        self, db: AsyncSession, *, organization_id: str, content: str,
        entity_type: str, entity_id: str, actor_user_id: str,
    ) -> None:
        names = [name.strip("@").strip() for name in content.split() if name.startswith("@")]
        if not names:
            return
        rows = (
            await db.execute(
                select(Employee.user_id).where(
                    Employee.organization_id == organization_id,
                    Employee.user_id.isnot(None),
                    Employee.full_name.in_(names),
                )
            )
        ).scalars().all()
        for user_id in rows:
            if user_id == actor_user_id:
                continue
            existing = (
                await db.execute(
                    select(DocumentWatcher).where(
                        DocumentWatcher.organization_id == organization_id,
                        DocumentWatcher.entity_type == entity_type,
                        DocumentWatcher.entity_id == entity_id,
                        DocumentWatcher.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    DocumentWatcher(
                        organization_id=organization_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        user_id=user_id,
                    )
                )
        await db.flush()

    async def toggle_watch(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
        user: User,
    ) -> dict[str, Any]:
        watcher = (
            await db.execute(
                select(DocumentWatcher).where(
                    DocumentWatcher.organization_id == organization_id,
                    DocumentWatcher.entity_type == entity_type,
                    DocumentWatcher.entity_id == entity_id,
                    DocumentWatcher.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if watcher is not None:
            await db.delete(watcher)
            await db.flush()
            return {"watching": False}
        db.add(
            DocumentWatcher(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user.id,
            )
        )
        await db.flush()
        return {"watching": True}

    async def watchers(self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str) -> list[DocumentWatcher]:
        rows = (
            await db.execute(
                select(DocumentWatcher).where(
                    DocumentWatcher.organization_id == organization_id,
                    DocumentWatcher.entity_type == entity_type,
                    DocumentWatcher.entity_id == entity_id,
                )
            )
        ).scalars().all()
        return list(rows)

    async def toggle_favorite(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
        user: User,
    ) -> dict[str, Any]:
        favorite = (
            await db.execute(
                select(DocumentFavorite).where(
                    DocumentFavorite.organization_id == organization_id,
                    DocumentFavorite.entity_type == entity_type,
                    DocumentFavorite.entity_id == entity_id,
                    DocumentFavorite.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if favorite is not None:
            await db.delete(favorite)
            await db.flush()
            return {"favorited": False}
        db.add(
            DocumentFavorite(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user.id,
            )
        )
        await db.flush()
        return {"favorited": True}

    async def favorites(self, db: AsyncSession, *, organization_id: str, user: User) -> list[DocumentFavorite]:
        rows = (
            await db.execute(
                select(DocumentFavorite).where(
                    DocumentFavorite.organization_id == organization_id,
                    DocumentFavorite.user_id == user.id,
                ).order_by(DocumentFavorite.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def touch_presence(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
        user: User, mode: str = "view",
    ) -> None:
        presence = (
            await db.execute(
                select(DocumentPresence).where(
                    DocumentPresence.organization_id == organization_id,
                    DocumentPresence.entity_type == entity_type,
                    DocumentPresence.entity_id == entity_id,
                    DocumentPresence.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if presence is None:
            presence = DocumentPresence(
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user.id,
            )
            db.add(presence)
        presence.last_active_at = utcnow()
        await db.flush()

    async def present(self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str) -> list[DocumentPresence]:
        rows = (
            await db.execute(
                select(DocumentPresence).where(
                    DocumentPresence.organization_id == organization_id,
                    DocumentPresence.entity_type == entity_type,
                    DocumentPresence.entity_id == entity_id,
                )
            )
        ).scalars().all()
        return list(rows)


collab_service = CollabService()
