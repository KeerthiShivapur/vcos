"""Announcement service (Phase 5.5)."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.communication.events import emit_and_audit, notify_user
from app.models.communication import Announcement, AnnouncementReceipt
from app.models.employee import Employee


class AnnouncementService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, payload: dict, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Announcement:
        announcement = Announcement(
            organization_id=organization_id,
            title=payload["title"],
            body=payload.get("body"),
            type=payload.get("type", "general"),
            priority=payload.get("priority", "normal"),
            status=payload.get("status", "draft"),
            author_id=actor.id if actor else None,
            department_id=payload.get("department_id"),
            team_id=payload.get("team_id"),
            starts_at=payload.get("starts_at"),
            ends_at=payload.get("ends_at"),
            pinned=payload.get("pinned", False),
            acknowledge_required=payload.get("acknowledge_required", False),
            attachments=payload.get("attachments"),
        )
        db.add(announcement)
        await db.flush()
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="announcement.created",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"announcement_id": announcement.id, "title": announcement.title},
            resource_type="announcement",
            resource_id=announcement.id,
        )
        return announcement

    async def get(self, db: AsyncSession, *, organization_id: str, announcement_id: str) -> Optional[Announcement]:
        return (
            await db.execute(
                select(Announcement).where(
                    Announcement.organization_id == organization_id,
                    Announcement.id == announcement_id,
                )
            )
        ).scalar_one_or_none()

    async def list_all(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        type: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Announcement]:
        filters = [Announcement.organization_id == organization_id]
        if status:
            filters.append(Announcement.status == status)
        if type:
            filters.append(Announcement.type == type)
        if priority:
            filters.append(Announcement.priority == priority)
        if search:
            filters.append(func.lower(Announcement.title).like(f"%{search.lower()}%"))
        return list(
            (
                await db.execute(
                    select(Announcement)
                    .where(*filters)
                    .order_by(Announcement.pinned.desc(), Announcement.created_at.desc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )

    async def update(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, payload: dict, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Optional[Announcement]:
        announcement = await self.get(db, organization_id=organization_id, announcement_id=announcement_id)
        if announcement is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(announcement, key):
                setattr(announcement, key, value)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="announcement.updated",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"announcement_id": announcement_id},
            resource_type="announcement",
            resource_id=announcement_id,
        )
        return announcement

    async def delete(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, actor: Optional[Employee], ip_address: Optional[str]
    ) -> bool:
        announcement = await self.get(db, organization_id=organization_id, announcement_id=announcement_id)
        if announcement is None:
            return False
        await db.delete(announcement)
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="announcement.deleted",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"announcement_id": announcement_id},
            resource_type="announcement",
            resource_id=announcement_id,
        )
        return True

    async def publish(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, actor: Optional[Employee], ip_address: Optional[str]
    ) -> Optional[Announcement]:
        announcement = await self.get(db, organization_id=organization_id, announcement_id=announcement_id)
        if announcement is None:
            return None
        announcement.status = "published"
        await emit_and_audit(
            db,
            organization_id=organization_id,
            name="announcement.published",
            actor=actor,
            actor_user_id=None,
            ip_address=ip_address,
            payload={"announcement_id": announcement_id, "title": announcement.title},
            resource_type="announcement",
            resource_id=announcement_id,
        )
        await self._broadcast(db, organization_id=organization_id, announcement=announcement, actor=actor)
        return announcement

    async def _broadcast(
        self, db: AsyncSession, *, organization_id: str, announcement: Announcement, actor: Optional[Employee]
    ) -> None:
        from app.models.user import User
        from app.services.notification_service import notification_service

        rows = (
            await db.execute(
                select(User).where(
                    User.organization_id == organization_id,
                    User.status == "active",
                )
            )
        ).scalars().all()
        for user in rows:
            await notification_service.create(
                db,
                organization_id=organization_id,
                recipient_id=user.id,
                actor_id=actor.id if actor else None,
                type="announcement",
                title=announcement.title,
                body=(announcement.body or "")[:200],
                priority="high" if announcement.priority in ("high", "urgent") else "normal",
                link=f"/announcements/{announcement.id}",
                entity_type="announcement",
                entity_id=announcement.id,
            )

    async def mark_read(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, actor: Employee
    ) -> AnnouncementReceipt:
        receipt = (
            await db.execute(
                select(AnnouncementReceipt).where(
                    AnnouncementReceipt.organization_id == organization_id,
                    AnnouncementReceipt.announcement_id == announcement_id,
                    AnnouncementReceipt.employee_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        announcement = await self.get(db, organization_id=organization_id, announcement_id=announcement_id)
        if receipt is None:
            receipt = AnnouncementReceipt(
                organization_id=organization_id,
                announcement_id=announcement_id,
                employee_id=actor.id,
            )
            db.add(receipt)
            if announcement is not None:
                announcement.read_count = (announcement.read_count or 0) + 1
        if receipt.read_at is None:
            from app.models.communication import utcnow

            receipt.read_at = utcnow()
        return receipt

    async def acknowledge(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, actor: Employee
    ) -> AnnouncementReceipt:
        receipt = await self.mark_read(db, organization_id=organization_id, announcement_id=announcement_id, actor=actor)
        if receipt.acknowledged_at is None:
            from app.models.communication import utcnow

            receipt.acknowledged_at = utcnow()
            announcement = await self.get(db, organization_id=organization_id, announcement_id=announcement_id)
            if announcement is not None:
                announcement.acknowledged_count = (announcement.acknowledged_count or 0) + 1
        return receipt

    async def my_receipt(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, employee_id: str
    ) -> Optional[AnnouncementReceipt]:
        return (
            await db.execute(
                select(AnnouncementReceipt).where(
                    AnnouncementReceipt.organization_id == organization_id,
                    AnnouncementReceipt.announcement_id == announcement_id,
                    AnnouncementReceipt.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()

    async def receipts(
        self, db: AsyncSession, *, organization_id: str, announcement_id: str, limit: int = 200, offset: int = 0
    ) -> list[AnnouncementReceipt]:
        return list(
            (
                await db.execute(
                    select(AnnouncementReceipt)
                    .where(
                        AnnouncementReceipt.organization_id == organization_id,
                        AnnouncementReceipt.announcement_id == announcement_id,
                    )
                    .order_by(AnnouncementReceipt.read_at.asc())
                    .limit(min(limit, 500))
                    .offset(offset)
                )
            ).scalars().all()
        )


announcement_service = AnnouncementService()
