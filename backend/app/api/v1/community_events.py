"""Community events API (Phase 5.11-5.14)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.communication.event_service import event_service
from app.communication.presenters import (
    _names,
    _community_names,
    present_event,
    present_registration,
)
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.communication import EventCreate, EventRegisterPayload, EventUpdate

router = APIRouter(prefix="/community-events", tags=["Community Events"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


async def _require_event(db: AsyncSession, org: Organization, event_id: str):
    event = await event_service.get(db, organization_id=org.id, event_id=event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    return event


async def _present(db: AsyncSession, org: Organization, user: User, event):
    actor = await _actor(db, org, user)
    creator_names = await _names(db, [event.created_by] if event.created_by else [])
    community_names = await _community_names(db, [event.community_id] if event.community_id else [])
    registration = None
    if actor:
        registration = await event_service.my_registration(
            db, organization_id=org.id, event_id=event.id, employee_id=actor.id
        )
    return await present_event(
        event,
        creator_name=creator_names.get(event.created_by) if event.created_by else None,
        community_name=community_names.get(event.community_id) if event.community_id else None,
        registered=registration is not None,
        my_registration=(
            {
                "id": registration.id,
                "team_name": registration.team_name,
                "role": registration.role,
                "status": registration.status,
            }
            if registration
            else None
        ),
    )


@router.get("/stats", response_model=dict)
async def event_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    return await event_service.stats(db, organization_id=org.id)


@router.get("", response_model=list[dict])
async def list_events(
    type: Optional[str] = None,
    upcoming: Optional[bool] = None,
    community_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    events = await event_service.list_all(
        db,
        organization_id=org.id,
        type=type,
        upcoming=upcoming,
        community_id=community_id,
        search=search,
        limit=min(limit, 500),
        offset=offset,
    )
    return [await _present(db, org, user, event) for event in events]


@router.post("", response_model=dict, status_code=201)
async def create_event(
    payload: EventCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    event = await event_service.create(
        db, organization_id=org.id, payload=payload.model_dump(exclude_unset=True), actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, event)


@router.get("/{event_id}", response_model=dict)
async def get_event(
    event_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await _require_event(db, org, event_id)
    return await _present(db, org, user, event)


@router.patch("/{event_id}", response_model=dict)
async def update_event(
    event_id: str,
    payload: EventUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_event(db, org, event_id)
    actor = await _actor(db, org, user)
    event = await event_service.update(
        db, organization_id=org.id, event_id=event_id, payload=payload.model_dump(exclude_unset=True),
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return await _present(db, org, user, event)


@router.delete("/{event_id}", response_model=Message)
async def delete_event(
    event_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_event(db, org, event_id)
    actor = await _actor(db, org, user)
    await event_service.delete(
        db, organization_id=org.id, event_id=event_id, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Event deleted")


@router.post("/{event_id}/register", response_model=dict)
async def register_for_event(
    event_id: str,
    payload: Optional[EventRegisterPayload] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:read")),
    db: AsyncSession = Depends(get_db),
):
    await _require_event(db, org, event_id)
    actor = await _actor(db, org, user)
    if actor is None:
        raise HTTPException(400, "No employee profile linked")
    try:
        result = await event_service.register(
            db,
            organization_id=org.id,
            event_id=event_id,
            actor=actor,
            team_name=payload.team_name if payload else None,
            role=payload.role if payload else "participant",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return result


@router.get("/{event_id}/registrations", response_model=list[dict])
async def list_registrations(
    event_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("communication:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _require_event(db, org, event_id)
    registrations = await event_service.registrations(db, organization_id=org.id, event_id=event_id)
    names = await _names(db, [r.employee_id for r in registrations])
    return [
        await present_registration(r, employee_name=names.get(r.employee_id)) for r in registrations
    ]
