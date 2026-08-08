"""Phase 8.14 — Executive Predictive Analytics API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.forecasting import forecasting_service
from app.models.ai import AIPrediction
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/predictions", tags=["executive"])


def _payload(p: AIPrediction) -> dict[str, Any]:
    import json

    def _load(v: Optional[str]) -> Any:
        if not v:
            return {}
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}

    return {
        "id": p.id,
        "subject_type": p.subject_type,
        "subject_id": p.subject_id,
        "metric": p.metric,
        "score": p.score,
        "level": p.level,
        "rationale": p.rationale,
        "factors": _load(p.factors_json),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
async def predictions(
    refresh: bool = False,
    level: Optional[str] = Query(default=None, pattern="^(low|medium|high)$"),
    metric: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if refresh:
        await forecasting_service.predict_all(db, organization_id=org.id, persist=True)
        await db.commit()
    query = select(AIPrediction).where(AIPrediction.organization_id == org.id)
    if level:
        query = query.where(AIPrediction.level == level)
    if metric:
        query = query.where(AIPrediction.metric == metric)
    rows = (await db.execute(query.order_by(AIPrediction.score.desc()).limit(limit))).scalars().all()
    return {"total": len(rows), "predictions": [_payload(p) for p in rows]}
