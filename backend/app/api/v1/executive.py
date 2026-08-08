"""Phase 8 — Executive Intelligence API (dashboard, twin, timeline, memory, analytics)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.analytics import executive_analytics
from app.executive.dashboard import executive_dashboard
from app.executive.digital_twin import digital_twin
from app.executive.timeline import organization_timeline
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive", tags=["executive"])


class MemorySearchIn(BaseModel):
    query: str
    limit: int = 20


@router.get("/dashboard")
async def dashboard(
    refresh: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await executive_dashboard.get(
        db, organization_id=org.id, refresh=refresh, user_id=user.id
    )


@router.get("/snapshot")
async def snapshot(
    persist: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if persist:
        await digital_twin.snapshot(db, organization_id=org.id)
        await db.commit()
    return await digital_twin.describe(db, organization_id=org.id)


@router.get("/twin")
async def twin(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await digital_twin.describe(db, organization_id=org.id)


@router.post("/twin/search-memory")
async def search_memory(
    payload: MemorySearchIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    results = await digital_twin.search_memory(
        db, organization_id=org.id, query=payload.query, limit=payload.limit
    )
    return {"total": len(results), "results": results}


@router.get("/timeline")
async def timeline(
    limit: int = Query(default=60, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_timeline.get(db, organization_id=org.id, limit=limit)


@router.get("/analytics/trends")
async def trends(
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly|quarterly|yearly)$"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await executive_analytics.trends(db, organization_id=org.id, period=period)


@router.get("/analytics/metrics")
async def metrics(
    refresh: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    history = await executive_analytics.history(db, organization_id=org.id, limit=limit)
    if refresh or history["total"] == 0:
        await executive_analytics.refresh(db, organization_id=org.id)
        await db.commit()
        history = await executive_analytics.history(db, organization_id=org.id, limit=limit)
    return history
