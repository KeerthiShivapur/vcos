"""Performance API (Phase 11.6 — Continuous Performance Management)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.performance_service import performance_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/performance", tags=["HR Performance"])


@router.post("/cycles")
async def create_cycle(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    cycle = await performance_service.create_cycle(db, organization_id=org.id, data=payload, created_by=user.id)
    await db.commit()
    return {"id": cycle.id, "name": cycle.name, "status": cycle.status}


@router.get("/cycles")
async def list_cycles(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
):
    cycles = await performance_service.list_cycles(db, organization_id=org.id, status=status)
    return [
        {
            "id": cycle.id,
            "name": cycle.name,
            "period": cycle.period or {},
            "status": cycle.status,
            "description": cycle.description,
            "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
        }
        for cycle in cycles
    ]


@router.post("/cycles/{cycle_id}/status")
async def set_cycle_status(
    cycle_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        cycle = await performance_service.set_cycle_status(
            db, organization_id=org.id, cycle_id=cycle_id, status=payload.get("status", "open")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if cycle is None:
        raise HTTPException(status_code=404, detail="Cycle not found")
    await db.commit()
    return {"id": cycle.id, "status": cycle.status}


@router.post("/goals")
async def create_goal(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    goal = await performance_service.create_goal(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": goal.id, "title": goal.title, "status": goal.status}


@router.patch("/goals/{goal_id}/progress")
async def update_goal_progress(
    goal_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    goal = await performance_service.update_goal_progress(
        db, organization_id=org.id, goal_id=goal_id, progress=int(payload.get("progress", 0))
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    await db.commit()
    return {"id": goal.id, "progress": goal.progress, "status": goal.status}


@router.get("/goals")
async def list_goals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    cycle_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    goals = await performance_service.list_goals(
        db, organization_id=org.id, employee_id=employee_id, cycle_id=cycle_id, status=status
    )
    return [
        {
            "id": goal.id,
            "employee_id": goal.employee_id,
            "cycle_id": goal.cycle_id,
            "title": goal.title,
            "kind": goal.kind,
            "status": goal.status,
            "progress": goal.progress,
            "weight": goal.weight,
            "due_date": goal.due_date.isoformat() if goal.due_date else None,
            "description": goal.description,
        }
        for goal in goals
    ]


@router.post("/reviews")
async def create_review(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    review = await performance_service.create_review(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": review.id, "kind": review.kind, "status": review.status}


@router.post("/reviews/{review_id}/submit")
async def submit_review(
    review_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    review = await performance_service.submit_review(db, organization_id=org.id, review_id=review_id, data=payload)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found or already closed")
    await db.commit()
    return {"id": review.id, "status": review.status, "rating": review.rating}


@router.post("/reviews/{review_id}/complete")
async def complete_review(
    review_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    review = await performance_service.complete_review(db, organization_id=org.id, review_id=review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found or not submitted")
    await db.commit()
    return {"id": review.id, "status": review.status, "ai_summary": review.ai_summary}


@router.get("/reviews")
async def list_reviews(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    reviewer_id: Optional[str] = Query(None),
    cycle_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    return await performance_service.list_reviews(
        db, organization_id=org.id, employee_id=employee_id,
        reviewer_id=reviewer_id, cycle_id=cycle_id, status=status,
    )


@router.get("/summary")
async def performance_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await performance_service.summary(db, organization_id=org.id)
