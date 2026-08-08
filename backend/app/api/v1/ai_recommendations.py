"""AI recommendation endpoints (Phase 7.7)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.recommendations import recommendation_engine
from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/recommendations", tags=["ai"])


@router.get("")
async def recommendations(
    audience: str = "user",
    limit: int = 10,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if audience == "organization":
        items = await recommendation_engine.for_organization(
            db, organization_id=org.id, limit=limit
        )
    else:
        items = await recommendation_engine.for_user(
            db, organization_id=org.id, user=user, limit=limit
        )
    await db.commit()
    return {"total": len(items), "recommendations": items}


@router.post("/{recommendation_id}/accept")
async def accept_recommendation(
    recommendation_id: str,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await recommendation_engine.accept(db, recommendation_id)
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return {"status": "accepted"}


@router.post("/{recommendation_id}/dismiss")
async def dismiss_recommendation(
    recommendation_id: str,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await recommendation_engine.dismiss(db, recommendation_id)
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return {"status": "dismissed"}
