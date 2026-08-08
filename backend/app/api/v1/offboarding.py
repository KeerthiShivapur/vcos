"""Offboarding & Alumni API (Phase 11.7 — Offboarding & Alumni)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.offboarding_service import offboarding_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/offboarding", tags=["HR Offboarding"])


@router.post("")
async def start_offboarding(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        offboarding = await offboarding_service.start(
            db, organization_id=org.id, data=payload, initiated_by=user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": offboarding.id, "status": offboarding.status, "employee_id": offboarding.employee_id}


@router.get("")
async def list_offboardings(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    return await offboarding_service.list(db, organization_id=org.id, status=status)


@router.get("/{offboarding_id}")
async def get_offboarding(
    offboarding_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    offboarding = await offboarding_service.get(db, organization_id=org.id, offboarding_id=offboarding_id)
    if offboarding is None:
        raise HTTPException(status_code=404, detail="Offboarding not found")
    return offboarding


@router.post("/{offboarding_id}/tasks")
async def add_task(
    offboarding_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await offboarding_service.add_task(db, organization_id=org.id, offboarding_id=offboarding_id, data=payload)
    if task is None:
        raise HTTPException(status_code=404, detail="Offboarding not found")
    await db.commit()
    return {"id": task.id, "title": task.title, "status": task.status}


@router.post("/{offboarding_id}/tasks/{task_id}/complete")
async def complete_task(
    offboarding_id: str,
    task_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await offboarding_service.complete_task(
        db, organization_id=org.id, offboarding_id=offboarding_id, task_id=task_id,
        completed_by=user.id, notes=payload.get("notes"),
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/{offboarding_id}/exit-interview")
async def submit_exit_interview(
    offboarding_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    offboarding = await offboarding_service.submit_exit_interview(
        db, organization_id=org.id, offboarding_id=offboarding_id, data=payload
    )
    if offboarding is None:
        raise HTTPException(status_code=404, detail="Offboarding not found")
    await db.commit()
    return {"id": offboarding.id, "exit_interview_completed": True}


@router.post("/{offboarding_id}/complete")
async def complete_offboarding(
    offboarding_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await offboarding_service.complete(db, organization_id=org.id, offboarding_id=offboarding_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Offboarding not found")
    await db.commit()
    return {"id": result["id"], "status": result["status"], "alumni_transitioned": True}


# ------------------------------------------------------------------ alumni

@router.get("/alumni/list")
async def alumni_list(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    return await offboarding_service.alumni_list(db, organization_id=org.id, status=status)


@router.patch("/alumni/{alumni_id}")
async def update_alumni(
    alumni_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    profile = await offboarding_service.update_alumni(db, organization_id=org.id, alumni_id=alumni_id, data=payload)
    if profile is None:
        raise HTTPException(status_code=404, detail="Alumni profile not found")
    await db.commit()
    return {"id": profile.id, "status": profile.status}


@router.post("/alumni/{alumni_id}/boomerang")
async def mark_boomerang(
    alumni_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    profile = await offboarding_service.mark_boomerang(db, organization_id=org.id, alumni_id=alumni_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Alumni profile not found")
    await db.commit()
    return {"id": profile.id, "status": profile.status}
