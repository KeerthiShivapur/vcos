"""Collaboration intelligence API (Phase 9) — department pair interactions,
department activity and silo detection."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence.collaboration_engine import collaboration_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/intelligence/collaboration", tags=["Intelligence"])


@router.get("")
async def collaboration_metrics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    """Latest computed collaboration metrics for the organization."""
    return await collaboration_engine.latest(db, organization_id=org.id)


@router.post("/recompute")
async def recompute_collaboration(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Recompute collaboration metrics on demand (normally done by the worker)."""
    result = await collaboration_engine.compute(db, organization_id=org.id)
    await db.commit()
    return result
