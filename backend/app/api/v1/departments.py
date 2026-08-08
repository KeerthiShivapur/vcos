"""Departments, business units, and locations API (Phase 2)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.department_service import department_service
from app.schemas.common import Message
from app.schemas.people import (
    BusinessUnitCreate,
    BusinessUnitOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentStats,
    DepartmentUpdate,
    LocationCreate,
    LocationOut,
)

router = APIRouter(prefix="/departments", tags=["Departments"])


async def get_actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)


# ------------------------------------------------------------------ business units

@router.post("/business-units", response_model=BusinessUnitOut, status_code=201)
async def create_business_unit(
    payload: BusinessUnitCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        bu = await department_service.create_business_unit(
            db, organization_id=org.id, data=payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return BusinessUnitOut.model_validate(bu)


@router.get("/business-units", response_model=list[BusinessUnitOut])
async def list_business_units(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:read")),
    db: AsyncSession = Depends(get_db),
):
    units = await department_service.list_business_units(db, organization_id=org.id)
    return [
        BusinessUnitOut.model_validate(
            {
                "id": u.id,
                "name": u.name,
                "code": u.code,
                "description": u.description,
                "head_id": u.head_id,
                "head_name": getattr(u, "head_name", None),
                "parent_id": u.parent_id,
                "employees_count": getattr(u, "employees_count", 0),
            }
        )
        for u in units
    ]


# ------------------------------------------------------------------ locations

@router.post("/locations", response_model=LocationOut, status_code=201)
async def create_location(
    payload: LocationCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        loc = await department_service.create_location(db, organization_id=org.id, data=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return LocationOut.model_validate(loc)


@router.get("/locations", response_model=list[LocationOut])
async def list_locations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:read")),
    db: AsyncSession = Depends(get_db),
):
    locs = await department_service.list_locations(db, organization_id=org.id)
    return [
        LocationOut.model_validate(
            {
                "id": l.id, "name": l.name, "code": l.code, "city": l.city,
                "country": l.country, "address": l.address, "is_office": l.is_office,
                "timezone": l.timezone, "employees_count": getattr(l, "employees_count", 0),
            }
        )
        for l in locs
    ]


# ------------------------------------------------------------------ departments

@router.get("", response_model=list[DepartmentOut])
async def list_departments(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:read")),
    db: AsyncSession = Depends(get_db),
):
    depts = await department_service.list_departments(db, organization_id=org.id)
    return [
        DepartmentOut.model_validate(
            {
                "id": d.id,
                "name": d.name,
                "code": d.code,
                "description": d.description,
                "parent_id": d.parent_id,
                "parent_name": getattr(d, "parent_name", None),
                "head_id": d.head_id,
                "head_name": getattr(d, "head_name", None),
                "location_id": d.location_id,
                "location_name": getattr(d, "location_name", None),
                "members_count": getattr(d, "members_count", 0),
                "teams_count": getattr(d, "teams_count", 0),
                "children": [{"id": c.id, "name": c.name} for c in getattr(d, "_children", None) or []],
            }
        )
        for d in depts
    ]


@router.post("", response_model=DepartmentOut, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await get_actor(db, org, user)
    try:
        dep = await department_service.create_department(
            db, organization_id=org.id, data=payload.model_dump(), actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    dep = await department_service.get_department(db, organization_id=org.id, department_id=dep.id)
    return DepartmentOut.model_validate(
        {
            "id": dep.id, "name": dep.name, "code": dep.code, "description": dep.description,
            "parent_id": dep.parent_id, "parent_name": getattr(dep, "parent_name", None),
            "head_id": dep.head_id, "head_name": getattr(dep, "head_name", None),
            "location_id": dep.location_id, "location_name": getattr(dep, "location_name", None),
            "members_count": getattr(dep, "members_count", 0),
            "teams_count": getattr(dep, "teams_count", 0),
        }
    )


@router.get("/{department_id}", response_model=DepartmentOut)
async def get_department(
    department_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:read")),
    db: AsyncSession = Depends(get_db),
):
    dep = await department_service.get_department(db, organization_id=org.id, department_id=department_id)
    if dep is None:
        raise HTTPException(404, "Department not found")
    return DepartmentOut.model_validate(
        {
            "id": dep.id, "name": dep.name, "code": dep.code, "description": dep.description,
            "parent_id": dep.parent_id, "parent_name": getattr(dep, "parent_name", None),
            "head_id": dep.head_id, "head_name": getattr(dep, "head_name", None),
            "location_id": dep.location_id, "location_name": getattr(dep, "location_name", None),
            "members_count": getattr(dep, "members_count", 0),
            "teams_count": getattr(dep, "teams_count", 0),
        }
    )


@router.patch("/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:manage")),
    db: AsyncSession = Depends(get_db),
):
    dep = await department_service.get_department(db, organization_id=org.id, department_id=department_id)
    if dep is None:
        raise HTTPException(404, "Department not found")
    actor = await get_actor(db, org, user)
    try:
        dep = await department_service.update_department(
            db, organization_id=org.id, department=dep,
            data=payload.model_dump(exclude_unset=True), actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    dep = await department_service.get_department(db, organization_id=org.id, department_id=dep.id)
    return DepartmentOut.model_validate(
        {
            "id": dep.id, "name": dep.name, "code": dep.code, "description": dep.description,
            "parent_id": dep.parent_id, "parent_name": getattr(dep, "parent_name", None),
            "head_id": dep.head_id, "head_name": getattr(dep, "head_name", None),
            "location_id": dep.location_id, "location_name": getattr(dep, "location_name", None),
            "members_count": getattr(dep, "members_count", 0),
            "teams_count": getattr(dep, "teams_count", 0),
        }
    )


@router.get("/{department_id}/stats", response_model=DepartmentStats)
async def department_stats(
    department_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("department:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await department_service.department_stats(db, organization_id=org.id, department_id=department_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
