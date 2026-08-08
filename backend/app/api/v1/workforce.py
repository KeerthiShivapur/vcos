"""Workforce API (Phase 11.9 — Workforce Planning & Organization Intelligence)."""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.workforce_service import workforce_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/workforce", tags=["HR Workforce"])


@router.post("/plans")
async def create_plan(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    plan = await workforce_service.create_plan(db, organization_id=org.id, data=payload, created_by=user.id)
    await db.commit()
    return {"id": plan.id, "title": plan.title, "status": plan.status}


@router.get("/plans")
async def list_plans(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    plans = await workforce_service.list_plans(db, organization_id=org.id, status=status)
    return [
        {
            "id": plan.id,
            "title": plan.title,
            "horizon": plan.horizon,
            "department": plan.department,
            "headcount_target": plan.headcount_target,
            "skill_needs": plan.skill_needs or [],
            "budget": plan.budget,
            "status": plan.status,
            "notes": plan.notes,
        }
        for plan in plans
    ]


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    plan = await workforce_service.update_plan(db, organization_id=org.id, plan_id=plan_id, data=payload)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    await db.commit()
    return {"id": plan.id, "status": plan.status}


@router.post("/succession")
async def add_succession_candidate(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        candidate = await workforce_service.add_succession_candidate(db, organization_id=org.id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": candidate.id, "position_title": candidate.position_title, "status": candidate.status}


@router.patch("/succession/{candidate_id}")
async def update_succession_candidate(
    candidate_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    candidate = await workforce_service.update_candidate(
        db, organization_id=org.id, candidate_id=candidate_id, data=payload
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Succession candidate not found")
    await db.commit()
    return {"id": candidate.id, "readiness": candidate.readiness, "status": candidate.status}


@router.get("/succession")
async def list_succession(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    position_title: Optional[str] = Query(None),
):
    return await workforce_service.list_succession(db, organization_id=org.id, position_title=position_title)


@router.post("/snapshots")
async def compute_snapshot(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await workforce_service.compute_snapshot(db, organization_id=org.id)
    await db.commit()
    return {
        "id": snapshot.id,
        "date": snapshot.date.isoformat(),
        "headcount": snapshot.headcount,
        "hires_month": snapshot.hires_month,
        "exits_month": snapshot.exits_month,
        "attrition_rate": snapshot.attrition_rate,
    }


@router.get("/snapshots")
async def list_snapshots(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(12, ge=1, le=60),
):
    snapshots = await workforce_service.snapshots(db, organization_id=org.id, limit=limit)
    return [
        {
            "id": snapshot.id,
            "date": snapshot.date.isoformat(),
            "headcount": snapshot.headcount,
            "hires_month": snapshot.hires_month,
            "exits_month": snapshot.exits_month,
            "attrition_rate": snapshot.attrition_rate,
            "departments": snapshot.departments or {},
        }
        for snapshot in snapshots
    ]


@router.get("/analytics")
async def workforce_analytics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workforce_service.analytics(db, organization_id=org.id)


@router.get("/hiring-needs")
async def hiring_needs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workforce_service.hiring_needs(db, organization_id=org.id)
