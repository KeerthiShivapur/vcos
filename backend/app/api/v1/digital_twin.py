"""Phase 18 — Autonomous Enterprise Intelligence API.

Exposes the organizational digital twin, health engine, predictions,
simulations, forecasts, recommendations, optimization, decision history,
the executive intelligence center (brief) and the twin AI question engine.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.digital_twin.ai_service import twin_ai_service
from app.digital_twin.decision_service import decision_service
from app.digital_twin.executive_service import executive_service
from app.digital_twin.forecasting_service import forecasting_service
from app.digital_twin.health_service import health_service
from app.digital_twin.optimization_service import optimization_service
from app.digital_twin.prediction_service import prediction_service
from app.digital_twin.recommendation_service import recommendation_service
from app.digital_twin.simulation_service import simulation_service
from app.digital_twin.twin_service import digital_twin_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/twin", tags=["digital-twin"])


class SimulationIn(BaseModel):
    scenario: str
    params: dict[str, Any] = {}


class RecommendationStatusIn(BaseModel):
    status: str


class DecisionCreateIn(BaseModel):
    decision: str
    decided_by: Optional[str] = None
    category: str = "strategy"
    reason: Optional[str] = None
    alternatives: Optional[list[str]] = None
    evidence: Optional[list[dict[str, Any]]] = None


class DecisionOutcomeIn(BaseModel):
    outcome: str
    outcome_score: float


class AskIn(BaseModel):
    question: str


@router.get("")
async def get_twin(
    refresh: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if refresh:
        payload = await digital_twin_service.refresh(db, org.id)
        await db.commit()
        return payload
    twin = await digital_twin_service.get_twin(db, org.id)
    if twin is None:
        await digital_twin_service.refresh(db, org.id)
        twin = await digital_twin_service.get_twin(db, org.id)
    await health_service.compute(db, org.id)
    await db.commit()
    twin = await digital_twin_service.get_twin(db, org.id)
    return digital_twin_service.serialize(twin)


@router.post("/refresh")
async def refresh_twin(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await digital_twin_service.refresh(db, org.id)
    await db.commit()
    return {"status": "refreshed", "organization_id": org.id}


@router.get("/history")
async def twin_history(
    limit: int = Query(default=30, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await digital_twin_service.history(db, org.id, limit=limit)
    return {"total": len(rows), "history": rows}


@router.get("/health")
async def twin_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    latest = await health_service.latest(db, org.id)
    if latest is None:
        latest = await health_service.compute(db, org.id)
        await db.commit()
    return latest


@router.get("/health/history")
async def health_history(
    limit: int = Query(default=30, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await health_service.history(db, org.id, limit=limit)
    return {"total": len(rows), "history": rows}


@router.get("/predictions")
async def predictions(
    status: Optional[str] = Query(default=None, pattern="^(active|acknowledged|dismissed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await prediction_service.list(db, org.id, status=status, limit=limit)
    return {"total": len(rows), "predictions": rows}


@router.post("/predictions/generate")
async def generate_predictions(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await prediction_service.generate(db, org.id)
    await db.commit()
    return {"total": len(created), "predictions": created}


@router.post("/predictions/{prediction_id}/acknowledge")
async def acknowledge_prediction(
    prediction_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await prediction_service.set_status(db, org.id, prediction_id, "acknowledged")
    if row is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    await db.commit()
    return row


@router.post("/predictions/{prediction_id}/dismiss")
async def dismiss_prediction(
    prediction_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await prediction_service.set_status(db, org.id, prediction_id, "dismissed")
    if row is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    await db.commit()
    return row


@router.post("/simulations/run")
async def run_simulation(
    payload: SimulationIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await simulation_service.run(db, org.id, user.id, scenario=payload.scenario, parameters=payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


@router.get("/simulations")
async def simulations(
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await simulation_service.list(db, org.id, limit=limit)
    return {"total": len(rows), "simulations": rows}


@router.get("/simulations/{simulation_id}")
async def simulation_detail(
    simulation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await simulation_service.get(db, org.id, simulation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return row


@router.post("/forecasts/generate")
async def generate_forecasts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await forecasting_service.generate(db, org.id)
    await db.commit()
    return {"total": len(created), "forecasts": created}


@router.get("/forecasts")
async def forecasts(
    dimension: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await forecasting_service.list(db, org.id, dimension=dimension, limit=limit)
    return {"total": len(rows), "forecasts": rows}


@router.post("/recommendations/generate")
async def generate_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await recommendation_service.generate(db, org.id)
    await db.commit()
    return {"total": len(created), "recommendations": created}


@router.get("/recommendations")
async def recommendations(
    status: Optional[str] = Query(default=None, pattern="^(active|accepted|dismissed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await recommendation_service.list(db, org.id, status=status, limit=limit)
    return {"total": len(rows), "recommendations": rows}


@router.post("/recommendations/{recommendation_id}/status")
async def recommendation_status(
    recommendation_id: str,
    payload: RecommendationStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if payload.status not in ("accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be accepted or dismissed")
    row = await recommendation_service.set_status(db, org.id, recommendation_id, payload.status)
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    await db.commit()
    return row


@router.post("/optimization/generate")
async def generate_optimizations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    created = await optimization_service.generate(db, org.id)
    await db.commit()
    return {"total": len(created), "optimizations": created}


@router.get("/optimization")
async def optimizations(
    status: Optional[str] = Query(default=None, pattern="^(suggested|applied)$"),
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await optimization_service.list(db, org.id, status=status, limit=limit)
    return {"total": len(rows), "optimizations": rows}


@router.post("/optimization/{action_id}/apply")
async def apply_optimization(
    action_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await optimization_service.apply(db, org.id, action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Optimization action not found")
    await db.commit()
    return row


@router.post("/decisions")
async def create_decision(
    payload: DecisionCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await decision_service.create(
        db,
        org.id,
        decision=payload.decision,
        decided_by=payload.decided_by or user.id,
        category=payload.category,
        reason=payload.reason,
        alternatives=payload.alternatives,
        evidence=payload.evidence,
    )
    await db.commit()
    return row


@router.get("/decisions")
async def decisions(
    category: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = await decision_service.list(db, org.id, category=category, limit=limit)
    return {"total": len(rows), "decisions": rows}


@router.post("/decisions/{decision_id}/outcome")
async def decision_outcome(
    decision_id: str,
    payload: DecisionOutcomeIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await decision_service.record_outcome(
        db, org.id, decision_id, outcome=payload.outcome, outcome_score=payload.outcome_score
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    await db.commit()
    return row


@router.post("/decisions/{decision_id}/analyze")
async def analyze_decision(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await decision_service.analyze(db, org.id, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return row


@router.get("/brief")
async def executive_brief(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await executive_service.brief(db, org.id)


@router.get("/intelligence")
async def intelligence_center(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await executive_service.dashboard(db, org.id)


@router.post("/ask")
async def ask_twin(
    payload: AskIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("digital_twin:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await twin_ai_service.ask(db, org.id, payload.question)
