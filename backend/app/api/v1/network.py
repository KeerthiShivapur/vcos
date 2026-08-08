"""Intelligence network API (Phase 19).

Exposes the reasoning engine (enterprise questions), strategic AI advisor,
collective learning, innovation intelligence, the unified organization graph
and decision intelligence with full organizational context.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.intelligence_network.collective_learning import collective_learning
from app.intelligence_network.decision_engine import decision_engine
from app.intelligence_network.innovation_engine import innovation_engine
from app.intelligence_network.organization_graph import organization_graph
from app.intelligence_network.reasoning_engine import INTENTS, reasoning_engine
from app.intelligence_network.strategic_ai import strategic_ai
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/intelligence/network", tags=["Intelligence Network"])


# ------------------------------------------------------------------ overview

@router.get("/overview")
async def network_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    graph = await organization_graph.stats(db, org.id)
    innovations = await innovation_engine.list(db, org.id, limit=5)
    return {
        "graph": graph,
        "innovation": {"total": innovations["total"], "latest": innovations["innovations"][:3]},
        "intents": list(INTENTS),
        "note": "The intelligence network reasons across the whole organization.",
    }


# ------------------------------------------------------------------- reason

class ReasonIn(BaseModel):
    question: str
    intent: Optional[str] = None


@router.post("/reason")
async def reason_question(
    body: ReasonIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return await reasoning_engine.ask(db, org.id, body.question)


@router.post("/advise")
async def strategic_advice(
    body: ReasonIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question is required")
    return await strategic_ai.advise(db, org.id, body.question)


# ----------------------------------------------------------- collective learning

@router.post("/learn")
async def run_collective_learning(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await collective_learning.run(db, org.id)


# ------------------------------------------------------------- innovation

@router.get("/innovation")
async def list_innovations(
    stage: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("innovation:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await innovation_engine.list(db, org.id, stage=stage, limit=limit)


@router.post("/innovation/scan")
async def scan_innovations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("innovation:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await innovation_engine.scan(db, org.id)
    await db.commit()
    return result


# ------------------------------------------------------------ organization graph

@router.get("/graph")
async def graph_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_graph.stats(db, org.id)


@router.get("/graph/nodes")
async def graph_nodes(
    node_type: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=2000),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_graph.nodes(db, org.id, node_type=node_type, limit=limit)


@router.get("/graph/path")
async def graph_path(
    start_type: str,
    start_id: str,
    end_type: str,
    end_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_graph.path(db, org.id, start_type, start_id, end_type, end_id)


@router.get("/graph/{node_type}/{node_id}/neighbors")
async def graph_neighbors(
    node_type: str,
    node_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await organization_graph.neighbors(db, org.id, node_type, node_id)


@router.post("/graph/rebuild")
async def rebuild_graph(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await organization_graph.rebuild(db, org.id)
    await db.commit()
    return result


# ------------------------------------------------------------- decisions

class DecisionCreateIn(BaseModel):
    title: str
    question: Optional[str] = None
    category: str = "strategy"
    context: Optional[str] = None
    alternatives: Optional[list[dict[str, Any]]] = None


class DecisionDecideIn(BaseModel):
    decision: str  # approved | rejected
    outcome: Optional[str] = None
    lessons: Optional[list[str]] = None


@router.get("/decisions")
async def list_network_decisions(
    category: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await decision_engine.list(db, org.id, category=category, status=status)


@router.post("/decisions")
async def create_network_decision(
    body: DecisionCreateIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await decision_engine.create_with_context(
            db, org.id, title=body.title, question=body.question, category=body.category,
            context=body.context, alternatives=body.alternatives, created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row


@router.get("/decisions/{decision_id}")
async def get_network_decision(
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await decision_engine.get(db, org.id, decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return row


@router.post("/decisions/{decision_id}/decide")
async def decide_network_decision(
    decision_id: str,
    body: DecisionDecideIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("autonomy:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await decision_engine.decide(
            db, org.id, decision_id, decision=body.decision, outcome=body.outcome,
            lessons=body.lessons, user_id=user.id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="decision not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return row
