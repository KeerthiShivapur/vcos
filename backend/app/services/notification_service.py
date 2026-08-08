import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

logger = logging.getLogger("vcos.notifications")


class NotificationService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        recipient_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        actor_id: Optional[str] = None,
        priority: str = "normal",
        channel: str = "in_app",
        link: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Notification:
        notification = Notification(
            organization_id=organization_id,
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type,
            title=title,
            body=body,
            priority=priority,
            channel=channel,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=json.dumps(metadata, default=str) if metadata else None,
            delivered_at=datetime.now(timezone.utc),
        )
        db.add(notification)
        await db.flush()
        return notification

    async def list_notifications(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        organization_id: str,
        page: int,
        page_size: int,
        unread_only: bool = False,
        type: Optional[str] = None,
    ) -> tuple[list[Notification], int]:
        filters = [
            Notification.recipient_id == user_id,
            Notification.organization_id == organization_id,
            Notification.is_archived.is_(False),
        ]
        if unread_only:
            filters.append(Notification.is_read.is_(False))
        if type:
            filters.append(Notification.type == type)
        total = (await db.execute(select(func.count()).select_from(Notification).where(*filters))).scalar_one()
        result = await db.execute(
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def stats(self, db: AsyncSession, *, user_id: str, organization_id: str) -> dict[str, Any]:
        unread = await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == user_id,
                Notification.organization_id == organization_id,
                Notification.is_read.is_(False),
                Notification.is_archived.is_(False),
            )
        )
        by_priority = {
            row.priority: row.count
            for row in (
                await db.execute(
                    select(Notification.priority, func.count().label("count"))
                    .where(
                        Notification.recipient_id == user_id,
                        Notification.organization_id == organization_id,
                        Notification.is_read.is_(False),
                    )
                    .group_by(Notification.priority)
                )
            ).all()
        }
        by_type = {
            row.type: row.count
            for row in (
                await db.execute(
                    select(Notification.type, func.count().label("count"))
                    .where(
                        Notification.recipient_id == user_id,
                        Notification.organization_id == organization_id,
                        Notification.is_read.is_(False),
                    )
                    .group_by(Notification.type)
                )
            ).all()
        }
        return {
            "total_unread": unread.scalar_one(),
            "by_priority": by_priority,
            "by_type": by_type,
        }

    async def mark_read(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        organization_id: str,
        ids: Optional[list[str]] = None,
    ) -> int:
        filters = [
            Notification.recipient_id == user_id,
            Notification.organization_id == organization_id,
            Notification.is_read.is_(False),
        ]
        if ids is not None:
            filters.append(Notification.id.in_(ids))
        rows = (await db.execute(select(Notification).where(*filters))).scalars().all()
        now = datetime.now(timezone.utc)
        for row in rows:
            row.is_read = True
            row.read_at = now
        return len(rows)

    async def mark_archived(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        organization_id: str,
        ids: list[str],
    ) -> int:
        rows = (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == user_id,
                    Notification.organization_id == organization_id,
                    Notification.id.in_(ids),
                )
            )
        ).scalars().all()
        for row in rows:
            row.is_archived = True
        return len(rows)

    async def broadcast(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        type: str,
        title: str,
        body: Optional[str] = None,
        actor_id: Optional[str] = None,
        priority: str = "normal",
        recipient_ids: Optional[list[str]] = None,
        exclude_ids: Optional[list[str]] = None,
    ) -> int:
        from app.models.user import User

        filters = [User.organization_id == organization_id, User.status == "active"]
        if recipient_ids:
            filters.append(User.id.in_(recipient_ids))
        if exclude_ids:
            filters.append(User.id.notin_(exclude_ids))
        users = (await db.execute(select(User.id).where(*filters))).scalars().all()
        for uid in users:
            await self.create(
                db,
                organization_id=organization_id,
                recipient_id=uid,
                type=type,
                title=title,
                body=body,
                actor_id=actor_id,
                priority=priority,
            )
        return len(users)


notification_service = NotificationService()
