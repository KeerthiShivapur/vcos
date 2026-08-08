"""Personalized learning recommendations API (Phase 10 — Learning Recommendations).

The recommendation feed is personal: any employee reads and acts on their own
feed. Generation is normally driven by the recommendation_feed worker; these
endpoints surface the feed and allow an on-demand refresh.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user
from app.db.database import get_db
from app.learning.recommendation_service import recommendation_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/recommendations", tags=["Intelligence"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org.id, Employee.user_id == str(user.id)
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


def _payload(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "description": item.description,
        "reason": item.reason,
        "score": item.score,
        "source": item.source,
        "entity_id": item.entity_id,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("")
async def my_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(25, ge=1, le=100),
):
    """Personal recommendation feed for the authenticated employee."""
    employee_id = await _employee_id(db, org, user)
    items = await recommendation_service.list(
        db, organization_id=org.id, employee_id=employee_id,
        statuses=("pending", "accepted"), limit=limit,
    )
    if not items:
        await recommendation_service.refresh_for_employee(
            db, organization_id=org.id, employee_id=employee_id
        )
        await db.commit()
        items = await recommendation_service.list(
            db, organization_id=org.id, employee_id=employee_id,
            statuses=("pending", "accepted"), limit=limit,
        )
    return [_payload(item) for item in items]


@router.post("/refresh")
async def refresh_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate this employee's recommendation feed on demand."""
    employee_id = await _employee_id(db, org, user)
    count = await recommendation_service.refresh_for_employee(
        db, organization_id=org.id, employee_id=employee_id
    )
    await db.commit()
    return {"generated": count}


@router.patch("/{item_id}")
async def update_recommendation(
    item_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept or dismiss one recommendation in the employee's own feed."""
    status = payload.get("status")
    if status not in ("active", "accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be active|accepted|dismissed")
    employee_id = await _employee_id(db, org, user)
    result = await recommendation_service.update_status(
        db, organization_id=org.id, employee_id=employee_id,
        recommendation_id=item_id, status=status,
    )
    await db.commit()
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return _payload(result)
