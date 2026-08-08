"""Phase 8.7 — Scenario Simulation API."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.simulation_engine import SCENARIOS, simulation_engine
from app.models.executive import Simulation
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/simulations", tags=["executive"])


class SimulationIn(BaseModel):
    scenario: str
    params: dict[str, Any] = {}


@router.post("")
async def run_simulation(
    payload: SimulationIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await simulation_engine.simulate(
            db,
            organization_id=org.id,
            scenario=payload.scenario,
            params=payload.params,
            user_id=user.id,
            persist=True,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    await db.commit()
    return result


@router.get("")
async def list_simulations(
    limit: int = Query(default=30, ge=1, le=100),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows = (await db.execute(
        select(Simulation).where(Simulation.organization_id == org.id)
        .order_by(Simulation.created_at.desc()).limit(limit)
    )).scalars().all()
    return {
        "total": len(rows),
        "simulations": [
            {
                "id": s.id,
                "scenario": s.scenario,
                "title": s.title,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
    }


@router.get("/{simulation_id}")
async def get_simulation(
    simulation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    sim = await db.get(Simulation, simulation_id)
    if sim is None or sim.organization_id != org.id:
        raise HTTPException(404, "Simulation not found")

    import json

    def _load(v: Optional[str], default: Any) -> Any:
        if not v:
            return default
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return default

    return {
        "id": sim.id,
        "scenario": sim.scenario,
        "title": sim.title,
        "assumptions": _load(sim.assumptions_json, []),
        "results": _load(sim.results_json, {}),
        "status": sim.status,
        "created_at": sim.created_at.isoformat() if sim.created_at else None,
    }


@router.get("/scenarios/list")
async def scenarios_list(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
) -> dict[str, Any]:
    return {"scenarios": SCENARIOS}
