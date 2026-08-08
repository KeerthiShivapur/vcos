"""Announcements API (Phase 5.5)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.announcement_service import announcement_service
from app.communication.presenters import _names, present_announcement
from app.db.database import get_db
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import AnnouncementCreate, AnnouncementUpdate

router = APIRouter(prefix="/announcements", tags=["Announcements"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_announcement(db: AsyncSession, org: Organization, announcement_id: str):
    announcement = await announcement_service.get(db, organization_id=org.id, announcement_id=announcement_id)
    if announcement is None:
        raise HTTPException(404, "Announcement not found")
    return announcement


async def _present(db: AsyncSession, org: Organization, user: User, announcement):
    actor = await _actor(db, org, user)
    receipt = None
    if actor:
        receipt = await announcement_service.my_receipt(
            db, organization_id=org.id, announcement_id=announcement.id, employee_id=actor.id
        )
    names = await _names(db, [announcement.author_id] if announcement.author_id else [])
    department_name = None
    if announcement.department_id:
        from app.models.department import Department

        department = await db.get(Department, announcement.department_id)
        department_name = department.name if department else None
    return await present_announcement(
        announcement,
        author_name=names.get(announcement.author_id) if announcement.author_id else None,
        department_name=department_name,
        read_by_me=receipt is not None and receipt.read_at is not None,
        acknowledged_by_me=receipt is not None and receipt.acknowledged_at is not None,
    )


@router.get("", response_model=list[dict])
async def list_announcements(
    status: Optional[str] = None,
    type: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    announcements = await announcement_service.list_all(
        db,
        organization_id=org.id,
        status=status,
        type=type,
        priority=priority,
        search=search,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present(db, org, user, a) for a in announcements]


@router.post("", response_model=dict, status_code=201)
async def create_announcement(
    payload: AnnouncementCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    announcement = await announcement_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, announcement)


@router.get("/{announcement_id}", response_model=dict)
async def get_announcement(
    announcement_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    announcement = await _require_announcement(db, org, announcement_id)
    return await _present(db, org, user, announcement)


@router.patch("/{announcement_id}", response_model=dict)
async def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    actor = await _actor(db, org, user)
    announcement = await announcement_service.update(
        db, organization_id=org.id, announcement_id=announcement_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, announcement)


@router.delete("/{announcement_id}", response_model=Message)
async def delete_announcement(
    announcement_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    actor = await _actor(db, org, user)
    await announcement_service.delete(
        db, organization_id=org.id, announcement_id=announcement_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Announcement deleted")


@router.post("/{announcement_id}/publish", response_model=dict)
async def publish_announcement(
    announcement_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    actor = await _actor(db, org, user)
    announcement = await announcement_service.publish(
        db, organization_id=org.id, announcement_id=announcement_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return await _present(db, org, user, announcement)


@router.post("/{announcement_id}/read", response_model=dict)
async def mark_announcement_read(
    announcement_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    receipt = await announcement_service.mark_read(
        db, organization_id=org.id, announcement_id=announcement_id, actor=actor
    )
    await db.commit()
    return {"read": True, "read_at": receipt.read_at}


@router.post("/{announcement_id}/acknowledge", response_model=dict)
async def acknowledge_announcement(
    announcement_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    receipt = await announcement_service.acknowledge(
        db, organization_id=org.id, announcement_id=announcement_id, actor=actor
    )
    await db.commit()
    return {"acknowledged": True, "acknowledged_at": receipt.acknowledged_at}


@router.get("/{announcement_id}/receipts", response_model=list[dict])
async def list_receipts(
    announcement_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_announcement(db, org, announcement_id)
    receipts = await announcement_service.receipts(db, organization_id=org.id, announcement_id=announcement_id)
    names = await _names(db, [r.employee_id for r in receipts])
    return [
        {
            "id": r.id,
            "announcement_id": r.announcement_id,
            "employee_id": r.employee_id,
            "employee_name": names.get(r.employee_id),
            "read_at": r.read_at,
            "acknowledged_at": r.acknowledged_at,
        }
        for r in receipts
    ]
