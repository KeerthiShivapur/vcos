"""Calendar API — the organization's time system (Phase 3)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import CalendarEventCreate, CalendarEventOut, CalendarEventUpdate
from app.work.calendar_service import calendar_service

router = APIRouter(prefix="/calendar", tags=["Calendar"])


@router.get("/events", response_model=list[CalendarEventOut])
async def list_events(
    employee_id: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    scope: Optional[str] = None,
    project_id: Optional[str] = None,
    team_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("calendar:read")),
    db: AsyncSession = Depends(get_db),
):
    return await calendar_service.list_all(
        db, organization_id=org.id, employee_id=employee_id,
        start=start, end=end, scope=scope, project_id=project_id, team_id=team_id,
    )


@router.post("/events", response_model=CalendarEventOut, status_code=201)
async def create_event(
    payload: CalendarEventCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("calendar:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    event = await calendar_service.create(
        db, organization_id=org.id, data=payload.model_dump(exclude_unset=True),
        created_by=actor.id if actor else None,
    )
    await db.commit()
    event = await calendar_service.get(db, organization_id=org.id, event_id=event.id)
    return CalendarEventOut.model_validate(event)


@router.get("/events/{event_id}", response_model=CalendarEventOut)
async def get_event(
    event_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("calendar:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await calendar_service.get(db, organization_id=org.id, event_id=event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    return CalendarEventOut.model_validate(event)


@router.patch("/events/{event_id}", response_model=CalendarEventOut)
async def update_event(
    event_id: str,
    payload: CalendarEventUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("calendar:manage")),
    db: AsyncSession = Depends(get_db),
):
    event = await calendar_service.get(db, organization_id=org.id, event_id=event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    event = await calendar_service.update(db, event=event, data=payload.model_dump(exclude_unset=True))
    await db.commit()
    return CalendarEventOut.model_validate(event)


@router.delete("/events/{event_id}", response_model=Message)
async def delete_event(
    event_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("calendar:manage")),
    db: AsyncSession = Depends(get_db),
):
    event = await calendar_service.get(db, organization_id=org.id, event_id=event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    await calendar_service.delete(db, event=event)
    await db.commit()
    return Message(message="Event deleted")
