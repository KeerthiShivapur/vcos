"""Presence and availability API (Phase 2)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.availability_service import availability_service
from app.people.employee_service import employee_service
from app.people.presence_service import presence_service
from app.schemas.people import AvailabilityOut, AvailabilityUpdate, PresenceOut, PresenceUpdate

router = APIRouter(prefix="/presence", tags=["Presence"])


async def _my_employee(db: AsyncSession, org: Organization, user: User):
    employee = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if employee is None:
        raise HTTPException(404, "No employee record for this user")
    return employee


@router.get("/me", response_model=dict)
async def my_presence_and_availability(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _my_employee(db, org, user)
    presence = await presence_service.get(db, organization_id=org.id, employee_id=employee.id)
    availability = await availability_service.get(db, organization_id=org.id, employee_id=employee.id)
    return {
        "employee_id": employee.id,
        "presence": PresenceOut.model_validate(presence) if presence else None,
        "availability": AvailabilityOut.model_validate(availability) if availability else None,
    }


@router.put("/me/presence", response_model=PresenceOut)
async def update_my_presence(
    payload: PresenceUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _my_employee(db, org, user)
    presence = await presence_service.update(
        db, organization_id=org.id, employee=employee,
        data=payload.model_dump(exclude_unset=True),
    )
    await db.commit()
    return PresenceOut.model_validate(presence)


@router.post("/heartbeat", response_model=PresenceOut)
async def heartbeat(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
    status: str = "online",
):
    employee = await _my_employee(db, org, user)
    try:
        presence = await presence_service.heartbeat(
            db, organization_id=org.id, employee_id=employee.id, status=status
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return PresenceOut.model_validate(presence)


@router.get("/employees/{employee_id}", response_model=dict)
async def employee_presence(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    employee = await employee_service.get(db, organization_id=org.id, employee_id=employee_id)
    if employee is None:
        raise HTTPException(404, "Employee not found")
    presence = await presence_service.get(db, organization_id=org.id, employee_id=employee_id)
    return {"employee_id": employee_id, "presence": PresenceOut.model_validate(presence) if presence else None}


@router.get("/employees/{employee_id}/availability", response_model=AvailabilityOut)
async def employee_availability(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    availability = await availability_service.get(db, organization_id=org.id, employee_id=employee_id)
    if availability is None:
        raise HTTPException(404, "No availability record")
    return AvailabilityOut.model_validate(availability)


@router.put("/me/availability", response_model=AvailabilityOut)
async def update_my_availability(
    payload: AvailabilityUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _my_employee(db, org, user)
    try:
        availability = await availability_service.update(
            db, organization_id=org.id, employee=employee, data=payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AvailabilityOut.model_validate(availability)


@router.get("/stats", response_model=dict)
async def presence_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("presence:read")),
    db: AsyncSession = Depends(get_db),
):
    return {
        "online_now": await presence_service.online_count(db, organization_id=org.id),
        "on_leave": await availability_service.on_leave_count(db, organization_id=org.id),
    }
