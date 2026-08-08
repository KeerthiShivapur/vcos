"""Phase 19 — Predictive intelligence API (/predictions)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.autonomy.prediction_engine import prediction_engine
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/predictions", tags=["autonomy"])


class PredictionStatusIn(BaseModel):
    status: str


class PredictionValidateIn(BaseModel):
    came_true: bool
    notes: Optional[str] = None


@router.get("")
async def list_predictions(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await prediction_engine.list(db, org.id, status=status, limit=limit)


@router.post("/generate")
async def generate_predictions(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await prediction_engine.generate(db, org.id)
    await db.commit()
    return result


@router.get("/history")
async def prediction_history(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.prediction import PredictionHistory

    rows = (
        await db.execute(
            select(PredictionHistory)
            .where(PredictionHistory.organization_id == org.id)
            .order_by(PredictionHistory.validated_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return {
        "total": len(rows),
        "history": [
            {
                "id": r.id, "prediction_id": r.prediction_id, "kind": r.kind,
                "outcome": r.outcome, "accuracy": r.accuracy, "notes": r.notes,
                "validated_at": r.validated_at.isoformat() if r.validated_at else None,
            }
            for r in rows
        ],
    }


@router.get("/models")
async def prediction_models(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    models = await prediction_engine.models(db, org.id)
    return {"total": len(models), "models": models}


@router.get("/{prediction_id}")
async def get_prediction(
    prediction_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await prediction_engine.get(db, org.id, prediction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return row


@router.patch("/{prediction_id}")
async def set_prediction_status(
    prediction_id: str,
    body: PredictionStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await prediction_engine.set_status(db, org.id, prediction_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    await db.commit()
    return row


@router.post("/{prediction_id}/validate")
async def validate_prediction(
    prediction_id: str,
    body: PredictionValidateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("predictions:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await prediction_engine.validate(db, org.id, prediction_id, came_true=body.came_true)
    except LookupError:
        raise HTTPException(status_code=404, detail="prediction not found")
    await db.commit()
    return result
