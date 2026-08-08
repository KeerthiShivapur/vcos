"""AI prediction endpoints (Phase 7.8)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.ai import AIPrediction
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai/predictions", tags=["ai"])


@router.get("")
async def predictions(
    subject_type: Optional[str] = None,
    metric: Optional[str] = None,
    level: Optional[str] = None,
    refresh: bool = False,
    limit: int = 50,
    user: User = Depends(require_permission("ai:use")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if refresh:
        from app.ai.predictions import prediction_engine

        await prediction_engine.predict_all(db, organization_id=org.id)
        await db.commit()
    filters = [AIPrediction.organization_id == org.id]
    if subject_type:
        filters.append(AIPrediction.subject_type == subject_type)
    if metric:
        filters.append(AIPrediction.metric == metric)
    if level:
        filters.append(AIPrediction.level == level)
    rows = (
        await db.execute(
            select(AIPrediction)
            .where(*filters)
            .order_by(AIPrediction.score.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "total": len(rows),
        "predictions": [
            {
                "id": p.id,
                "subject_type": p.subject_type,
                "subject_id": p.subject_id,
                "metric": p.metric,
                "score": p.score,
                "level": p.level,
                "rationale": p.rationale,
                "created_at": p.created_at,
            }
            for p in rows
        ],
    }
