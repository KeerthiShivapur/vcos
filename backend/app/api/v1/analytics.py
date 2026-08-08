"""Analytics & Relationship Intelligence API (Phase 12 — CROS)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.ai_service import customer_ai
from app.customers.analytics_service import analytics_service
from app.customers.relationship_service import relationship_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["Customer Analytics"])


@router.get("/dashboard")
async def dashboard(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.dashboard(db, organization_id=org.id)


@router.get("/overview")
async def analytics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.analytics(db, organization_id=org.id)


@router.post("/health/recompute")
async def recompute_health(
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    updated = await analytics_service.compute_customer_health(
        db, organization_id=org.id, customer_id=payload.get("customer_id"))
    await db.commit()
    return {"updated": len(updated), "customers": updated}


@router.get("/health")
async def health_report(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await analytics_service.health(db, organization_id=org.id)


@router.get("/renewals")
async def renewals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    horizon_days: int = Query(120, ge=7, le=730),
):
    return await analytics_service.renewals(db, organization_id=org.id, horizon_days=horizon_days)


@router.get("/relationships")
async def relationships(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await relationship_service.relationships(db, organization_id=org.id)


@router.post("/relationships/build")
async def build_relationship_graph(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await relationship_service.build_graph(db, organization_id=org.id)
    await db.commit()
    return result


@router.get("/relationships/risks")
async def relationship_risks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await relationship_service.risks(db, organization_id=org.id)


@router.post("/ask")
async def ask_customer_ai(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    question = payload.get("question") or payload.get("query") or ""
    if not question.strip():
        return {"answer": "Ask about renewals, at-risk customers, next meetings or opportunities."}
    result = await customer_ai.answer(db, organization_id=org.id, user=user, question=question)
    if result is None:
        return {"answer": "I can help with customer summaries, renewals, at-risk accounts, next meetings and the pipeline."}
    return result
