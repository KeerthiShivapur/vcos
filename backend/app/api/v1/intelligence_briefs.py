"""Intelligence briefs & recommendations API (Phase 9) — the autonomous daily
brief (executive + personal) and the personalized recommendation feed.

The briefs are normally generated every morning by the insights worker; these
endpoints surface the latest brief and allow on-demand regeneration. The
recommendation feed is personal: any employee reads and acts on their own
feed, while `intelligence:read` is needed to view other feeds' executive
briefs.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.intelligence.insights_engine import insights_engine
from app.intelligence.recommendation_engine import recommendation_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


# ------------------------------------------------------------------ daily briefs

@router.get("/briefs")
async def list_briefs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    return await insights_engine.list_briefs(db, organization_id=org.id, limit=limit)


@router.get("/briefs/executive")
async def executive_brief(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    """Latest executive brief (or generate on the fly if none exists yet)."""
    brief = await insights_engine.latest_brief(
        db, organization_id=org.id, brief_type="executive"
    )
    if not brief:
        brief = await insights_engine.generate_executive_brief(db, organization_id=org.id)
        await db.commit()
    return brief


@router.get("/briefs/employee")
async def employee_brief(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Personal daily brief for the authenticated employee."""
    brief = await insights_engine.latest_brief(
        db, organization_id=org.id, brief_type="employee", recipient_id=str(user.id)
    )
    if not brief:
        brief = await insights_engine.generate_employee_brief(
            db, organization_id=org.id, user_id=str(user.id)
        )
        await db.commit()
    return brief


@router.post("/briefs/generate")
async def generate_briefs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate the daily briefs on demand (normally done by the insights worker)."""
    exec_brief = await insights_engine.generate_executive_brief(db, organization_id=org.id)
    await db.commit()
    return {"executive": exec_brief}


# ------------------------------------------------------------------ recommendation feed

@router.get("/recommendations")
async def my_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(25, ge=1, le=100),
):
    """Personal recommendation feed for the authenticated user."""
    feed = await recommendation_engine.feed(
        db, organization_id=org.id, user_id=str(user.id), limit=limit
    )
    if not feed:
        await recommendation_engine.generate_for_user(db, organization_id=org.id, user_id=str(user.id))
        await db.commit()
        feed = await recommendation_engine.feed(
            db, organization_id=org.id, user_id=str(user.id), limit=limit
        )
    return feed


@router.post("/recommendations/refresh")
async def refresh_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate this user's recommendation feed on demand."""
    items = await recommendation_engine.generate_for_user(
        db, organization_id=org.id, user_id=str(user.id)
    )
    await db.commit()
    return {"generated": len(items)}


@router.patch("/recommendations/{item_id}")
async def update_recommendation(
    item_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept or dismiss one recommendation in the user's own feed."""
    status = payload.get("status")
    if status not in ("active", "accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be active|accepted|dismissed")
    result = await recommendation_engine.set_status(
        db, organization_id=org.id, item_id=item_id, status=status, user_id=str(user.id)
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return result
