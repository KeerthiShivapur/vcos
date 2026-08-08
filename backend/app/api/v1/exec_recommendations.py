"""Phase 8.5 — Executive Recommendation API."""

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.recommendation_engine import recommendation_engine
from app.models.executive import ExecutiveRecommendation
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/recommendations", tags=["executive"])


def _payload(r: ExecutiveRecommendation) -> dict[str, Any]:
    def _load(v: Optional[str]) -> Any:
        if not v:
            return {}
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}

    return {
        "id": r.id,
        "kind": r.kind,
        "title": r.title,
        "rationale": r.rationale,
        "evidence": _load(r.evidence_json),
        "expected_outcome": r.expected_outcome,
        "confidence": r.confidence,
        "impact": r.impact,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
async def list_recommendations(
    refresh: bool = False,
    status: Optional[str] = Query(default=None, pattern="^(active|accepted|dismissed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if refresh:
        from app.executive.risk_engine import risk_engine

        detected = await risk_engine.detect_all(db, organization_id=org.id)
        await risk_engine.persist(db, organization_id=org.id, risks=detected)
        await recommendation_engine.generate(db, organization_id=org.id, persist=True)
        await db.commit()
    query = select(ExecutiveRecommendation).where(ExecutiveRecommendation.organization_id == org.id)
    if status:
        query = query.where(ExecutiveRecommendation.status == status)
    rows = (await db.execute(query.order_by(ExecutiveRecommendation.confidence.desc()).limit(limit))).scalars().all()
    return {"total": len(rows), "recommendations": [_payload(r) for r in rows]}


class RecStatusIn(BaseModel):
    status: str  # active | accepted | dismissed


@router.patch("/{recommendation_id}/status")
async def update_recommendation_status(
    recommendation_id: str,
    payload: RecStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rec = await db.get(ExecutiveRecommendation, recommendation_id)
    if rec is None or rec.organization_id != org.id:
        raise HTTPException(404, "Recommendation not found")
    if payload.status not in ("active", "accepted", "dismissed"):
        raise HTTPException(422, "status must be active|accepted|dismissed")
    rec.status = payload.status
    await db.commit()
    return {"id": rec.id, "status": rec.status}
