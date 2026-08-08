"""Recognition and badges API (Phase 5.8, 5.15)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.badge_service import badge_service
from app.communication.presenters import (
    _names,
    present_employee_badge,
    present_recognition,
)
from app.communication.recognition_service import recognition_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import RecognitionCreate

router = APIRouter(prefix="/recognition", tags=["Recognition"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _present(db: AsyncSession, org: Organization, recognition):
    names = await _names(db, [recognition.giver_id, recognition.recipient_id])
    return await present_recognition(
        recognition,
        giver_name=names.get(recognition.giver_id) if recognition.giver_id else None,
        recipient_name=names.get(recognition.recipient_id) if recognition.recipient_id else None,
    )


@router.get("", response_model=list[dict])
async def list_recognitions(
    employee_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    recognitions = await recognition_service.list_all(
        db,
        organization_id=org.id,
        employee_id=employee_id,
        category=category,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present(db, org, r) for r in recognitions]


@router.post("", response_model=dict, status_code=201)
async def give_recognition(
    payload: RecognitionCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    if payload.recipient_id == actor.id:
        raise HTTPException(400, "You cannot recognize yourself")
    recognition = await recognition_service.give(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, recognition)


@router.get("/stats", response_model=dict)
async def recognition_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    stats = await recognition_service.stats(db, organization_id=org.id)
    names = await _names(
        db,
        [e["employee_id"] for e in stats["top_recipients"] + stats["top_givers"]],
    )
    stats["top_recipients"] = [
        {**entry, "employee_name": names.get(entry["employee_id"])} for entry in stats["top_recipients"]
    ]
    stats["top_givers"] = [
        {**entry, "employee_name": names.get(entry["employee_id"])} for entry in stats["top_givers"]
    ]
    return stats


@router.get("/badges", response_model=list[dict])
async def my_badges(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    if actor is None:
        return []
    rows = await badge_service.employee_badges(db, organization_id=org.id, employee_id=actor.id)
    return [await present_employee_badge(db, b) for b in rows]


@router.get("/badges/all", response_model=list[dict])
async def all_badges(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.communication.presenters import present_badge

    badges = await badge_service.list_badges(db, organization_id=org.id)
    return [await present_badge(b) for b in badges]


@router.get("/leaderboard", response_model=list[dict])
async def recognition_leaderboard(
    limit: int = 20,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await badge_service.leaderboard(db, organization_id=org.id, limit=min(limit, 100))
    names = await _names(db, [row["employee_id"] for row in rows])
    return [{**row, "employee_name": names.get(row["employee_id"])} for row in rows]


@router.delete("/{recognition_id}", response_model=Message)
async def delete_recognition(
    recognition_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    recognition = await recognition_service.get(db, organization_id=org.id, recognition_id=recognition_id)
    if recognition is None:
        raise HTTPException(404, "Recognition not found")
    actor = await _actor(db, org, user)
    if actor is None or recognition.giver_id != actor.id:
        raise HTTPException(403, "Only the giver can remove this recognition")
    await recognition_service.delete(
        db, organization_id=org.id, recognition_id=recognition_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Recognition removed")
