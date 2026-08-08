"""Notifications: center, stats, read/archive actions."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message, Paginated
from app.schemas.notifications import MarkReadRequest, NotificationOut, NotificationStats
from app.db.database import get_db
from app.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=Paginated[NotificationOut])
async def list_notifications(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    type: str = Query(None),
):
    items, total = await notification_service.list_notifications(
        db,
        user_id=user.id,
        organization_id=org.id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
        type=type,
    )
    return Paginated(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size) if page_size else 0,
    )


@router.get("/stats", response_model=NotificationStats)
async def notification_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return NotificationStats(**await notification_service.stats(db, user_id=user.id, organization_id=org.id))


@router.post("/read", response_model=Message)
async def mark_read(
    payload: MarkReadRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await notification_service.mark_read(
        db, user_id=user.id, organization_id=org.id, ids=payload.ids
    )
    await db.commit()
    return Message(message=f"{count} notification(s) marked as read")


@router.post("/archive", response_model=Message)
async def archive_notifications(
    payload: MarkReadRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await notification_service.mark_archived(
        db, user_id=user.id, organization_id=org.id, ids=payload.ids or []
    )
    await db.commit()
    return Message(message=f"{count} notification(s) archived")
