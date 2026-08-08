"""Intelligence API — background intelligence center (Phase 9).

Exposes everything the autonomous organization has learned: event bus
observability, on-demand worker runs, org graph, expertise evolution,
knowledge/search/burnout/duplicate/pattern/workflow insights, and lessons
learned. All reads require `intelligence:read`; all writes (worker runs,
insight status changes) require `intelligence:manage`.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.events.event_bus import event_bus
from app.events.event_models import describe
from app.intelligence.burnout_engine import burnout_engine
from app.intelligence.duplicate_engine import duplicate_engine
from app.intelligence.expertise_engine import expertise_engine
from app.intelligence.graph_engine import graph_engine
from app.intelligence.knowledge_engine import knowledge_engine
from app.intelligence.learning_engine import learning_engine
from app.intelligence.pattern_engine import pattern_engine
from app.intelligence.risk_engine import background_risk_engine
from app.intelligence.search_engine import search_engine
from app.intelligence.workflow_engine import workflow_engine
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


# ------------------------------------------------------------------ overview

@router.get("/overview")
async def intelligence_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    graph_stats = await graph_engine.stats(db, organization_id=org.id)
    search_stats = await search_engine.stats(db, organization_id=org.id)
    learning_summary = await learning_engine.summary(db, organization_id=org.id)
    burnout_signals = await burnout_engine.list_signals(db, organization_id=org.id, limit=10)
    knowledge_insights = await knowledge_engine.list_insights(db, organization_id=org.id, limit=10)
    duplicates = await duplicate_engine.list_detections(db, organization_id=org.id, limit=10)
    patterns = await pattern_engine.list_patterns(db, organization_id=org.id, limit=10)
    workflow = await workflow_engine.list_insights(db, organization_id=org.id, limit=10)
    risks = await background_risk_engine.list_open(db, organization_id=org.id, limit=10)
    notification_count = (
        await db.execute(
            select(Notification.id)
            .where(
                Notification.organization_id == org.id,
                Notification.type.in_(("risk", "burnout", "pattern")),
            )
        )
    ).scalars().all()

    job_counts = {
        "queued": 0, "running": 0, "done": 0, "failed": 0, "retry": 0,
    }
    rows = (
        await db.execute(
            select(BackgroundJob.status, BackgroundJob.id)
            .where(BackgroundJob.organization_id == org.id)
        )
    ).all()
    for status, _ in rows:
        job_counts[status] = job_counts.get(status, 0) + 1

    return {
        "graph": graph_stats,
        "search": search_stats,
        "learning": learning_summary,
        "jobs": job_counts,
        "burnout": {"count": len(burnout_signals), "latest": burnout_signals[:3]},
        "knowledge": {"count": len(knowledge_insights), "latest": knowledge_insights[:3]},
        "duplicates": {"count": len(duplicates), "latest": duplicates[:3]},
        "patterns": {"count": len(patterns), "latest": patterns[:3]},
        "workflow": {"count": len(workflow), "latest": workflow[:3]},
        "risks": {"count": len(risks), "latest": risks[:3]},
        "autonomous_notifications": {"count": len(notification_count)},
    }


# ------------------------------------------------------------------ event bus

@router.get("/events")
async def recent_events(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    processed: bool = Query(None),
):
    return await event_bus.recent_events(
        db, organization_id=org.id, limit=limit, processed=processed
    )


@router.get("/events/stats")
async def event_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    return await event_bus.stats(db, organization_id=org.id)


@router.post("/events/process")
async def process_pending_events(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
):
    """Trigger the event dispatcher on demand (normally the event worker does this)."""
    count = await event_bus.process_pending(db, limit=limit)
    await db.commit()
    return {"processed": count}


# ------------------------------------------------------------------ workers / jobs

@router.get("/jobs")
async def list_jobs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    status: str = Query(None),
):
    stmt = select(BackgroundJob).where(BackgroundJob.organization_id == org.id)
    if status:
        stmt = stmt.where(BackgroundJob.status == status)
    stmt = stmt.order_by(BackgroundJob.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": j.id, "name": j.name, "status": j.status,
            "attempts": j.attempts, "max_attempts": j.max_attempts,
            "error": j.error, "payload": j.payload,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in rows
    ]


_WORKER_MODULES = {
    "event": "app.workers.event_worker",
    "graph_updates": "app.workers.graph_updates_worker",
    "search_insight": "app.workers.search_insight_worker",
    "knowledge_intel": "app.workers.knowledge_intel_worker",
    "collab_intel": "app.workers.collab_intel_worker",
    "burnout": "app.workers.burnout_worker",
    "expertise_evolve": "app.workers.expertise_evolve_worker",
    "workflow_intel": "app.workers.workflow_intel_worker",
    "pattern": "app.workers.pattern_worker",
    "learning": "app.workers.learning_worker",
    "insights": "app.workers.insights_worker",
    "recommendation_feed": "app.workers.recommendation_feed_worker",
    "risk": "app.workers.risk_worker",
    "notification": "app.workers.notification_worker",
    "skill": "app.workers.skill_worker",
    "certification": "app.workers.certification_worker",
    "mentor": "app.workers.mentor_worker",
    "assessment": "app.workers.assessment_worker",
}


@router.get("/workers")
async def list_workers(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    from app.workers.scheduler import WORKER_REGISTRY

    registry = dict(WORKER_REGISTRY)
    return [
        {
            "name": name,
            "interval_seconds": registry.get(name),
            "run_on_demand": name in _WORKER_MODULES,
        }
        for name in _WORKER_MODULES
    ]


@router.post("/workers/{name}/run")
async def run_worker(
    name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Run a background worker's single pass on demand."""
    module_name = _WORKER_MODULES.get(name)
    if not module_name:
        raise HTTPException(status_code=404, detail=f"Unknown worker: {name}")
    import importlib
    import inspect

    module = importlib.import_module(module_name)
    try:
        if "db" in inspect.signature(module.run_once).parameters:
            count = await module.run_once(db=db)
        else:
            count = await module.run_once()
    except Exception as exc:  # pragma: no cover - surfaced to caller
        raise HTTPException(status_code=500, detail=f"Worker {name} failed: {exc}")
    await db.commit()
    return {"worker": name, "processed": count}


# ------------------------------------------------------------------ expertise evolution

@router.get("/expertise/leaderboard")
async def expertise_leaderboard(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    return await expertise_engine.leaderboard(db, organization_id=org.id, limit=limit)


@router.get("/expertise/{employee_id}/history")
async def expertise_history(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    return await expertise_engine.history(
        db, organization_id=org.id, employee_id=employee_id, limit=limit
    )


# ------------------------------------------------------------------ org graph

@router.get("/graph")
async def graph_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    return await graph_engine.stats(db, organization_id=org.id)


@router.get("/graph/edges")
async def graph_edges(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    relation: str = Query(None),
    entity_type: str = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    return await graph_engine.edges(
        db, organization_id=org.id, relation=relation, entity_type=entity_type, limit=limit
    )


@router.get("/graph/neighbors")
async def graph_neighbors(
    entity_type: str,
    entity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    return await graph_engine.neighbors(
        db, organization_id=org.id, entity_type=entity_type, entity_id=entity_id, limit=limit
    )


@router.get("/graph/path")
async def graph_path(
    from_employee: str,
    to_employee: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    max_depth: int = Query(4, ge=1, le=6),
):
    return await graph_engine.collaboration_path(
        db, organization_id=org.id, from_employee=from_employee,
        to_employee=to_employee, max_depth=max_depth,
    )


@router.get("/graph/bottlenecks")
async def graph_bottlenecks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
):
    return await graph_engine.bottlenecks(db, organization_id=org.id, limit=limit)


@router.delete("/graph/edges/{edge_id}")
async def deactivate_graph_edge(
    edge_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await graph_engine.deactivate_edge(db, organization_id=org.id, edge_id=edge_id)
    await db.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"ok": True}


# ------------------------------------------------------------------ knowledge insights

@router.get("/knowledge/insights")
async def knowledge_insights(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    kind: str = Query(None),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await knowledge_engine.list_insights(
        db, organization_id=org.id, kind=kind, status=status, limit=limit
    )


@router.patch("/knowledge/insights/{insight_id}")
async def update_knowledge_insight(
    insight_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status")
    if status not in ("open", "accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be open|accepted|dismissed")
    result = await knowledge_engine.set_status(
        db, organization_id=org.id, insight_id=insight_id, status=status
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Insight not found")
    return result


# ------------------------------------------------------------------ search insights

@router.get("/search/insights")
async def search_insights(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    kind: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await search_engine.list_insights(db, organization_id=org.id, kind=kind, limit=limit)


@router.get("/search/stats")
async def search_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    return await search_engine.stats(db, organization_id=org.id)


# ------------------------------------------------------------------ burnout signals

@router.get("/burnout/signals")
async def burnout_signals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    min_level: str = Query("moderate"),
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await burnout_engine.list_signals(
        db, organization_id=org.id, min_level=min_level, status=status, limit=limit
    )


@router.patch("/burnout/signals/{signal_id}")
async def update_burnout_signal(
    signal_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status")
    if status not in ("open", "acknowledged", "resolved"):
        raise HTTPException(status_code=422, detail="status must be open|acknowledged|resolved")
    result = await burnout_engine.set_status(
        db, organization_id=org.id, signal_id=signal_id, status=status
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Signal not found")
    return result


# ------------------------------------------------------------------ duplicates

@router.get("/duplicates")
async def duplicate_detections(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    kind: str = Query(None),
    status: str = Query("open"),
    limit: int = Query(50, ge=1, le=200),
):
    return await duplicate_engine.list_detections(
        db, organization_id=org.id, kind=kind, status=status, limit=limit
    )


@router.patch("/duplicates/{detection_id}")
async def update_duplicate_detection(
    detection_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status")
    if status not in ("open", "confirmed", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be open|confirmed|dismissed")
    result = await duplicate_engine.set_status(
        db, organization_id=org.id, detection_id=detection_id, status=status
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Detection not found")
    return result


# ------------------------------------------------------------------ patterns

@router.get("/patterns")
async def org_patterns(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    pattern_type: str = Query(None),
    status: str = Query("open"),
    limit: int = Query(50, ge=1, le=200),
):
    return await pattern_engine.list_patterns(
        db, organization_id=org.id, pattern_type=pattern_type, status=status, limit=limit
    )


@router.patch("/patterns/{pattern_id}")
async def update_pattern(
    pattern_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status")
    if status not in ("open", "acknowledged", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be open|acknowledged|dismissed")
    result = await pattern_engine.set_status(
        db, organization_id=org.id, pattern_id=pattern_id, status=status
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return result


# ------------------------------------------------------------------ workflow insights

@router.get("/workflow/insights")
async def workflow_insights(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("open"),
    limit: int = Query(50, ge=1, le=200),
):
    return await workflow_engine.list_insights(
        db, organization_id=org.id, status=status, limit=limit
    )


@router.patch("/workflow/insights/{insight_id}")
async def update_workflow_insight(
    insight_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status")
    if status not in ("open", "accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be open|accepted|dismissed")
    result = await workflow_engine.set_status(
        db, organization_id=org.id, insight_id=insight_id, status=status
    )
    await db.commit()
    if not result:
        raise HTTPException(status_code=404, detail="Insight not found")
    return result


# ------------------------------------------------------------------ learning

@router.get("/learning/lessons")
async def lessons_learned(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
    event_type: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await learning_engine.lessons(
        db, organization_id=org.id, event_type=event_type, limit=limit
    )


@router.get("/learning/summary")
async def learning_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
    db: AsyncSession = Depends(get_db),
):
    return await learning_engine.summary(db, organization_id=org.id)


# ------------------------------------------------------------------ event catalog

@router.get("/catalog")
async def event_catalog(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("intelligence:read")),
):
    return [
        {"name": name, "description": describe(name), "points": points}
        for name, points in [
            (n, _expertise_points(n))
            for n in sorted(
                __import__("app.events.event_models", fromlist=["EVENT_CATALOG"])
                .EVENT_CATALOG
            )
        ]
    ]


def _expertise_points(name: str) -> Optional[float]:
    from app.events.event_models import EXPERTISE_EVENTS

    return EXPERTISE_EVENTS.get(name)
