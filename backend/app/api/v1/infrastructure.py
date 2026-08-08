"""Global Scale, Cloud Infrastructure & Enterprise Reliability API (Phase 16).

One control plane for multi-region topology and routing, zero-downtime
deployments, backups & PITR, replicated cluster health, disaster recovery,
autoscaling, infrastructure observability and reliability engineering
(circuit breakers, chaos runs). Reads require infrastructure:read; writes
require infrastructure:manage (granted to ceo/admin, read-only for
manager). Infrastructure data is platform-wide: these tables describe the
fleet every organization runs on, not a single tenant.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.infrastructure.autoscaling_service import autoscaling_service
from app.infrastructure.backups_service import backups_service
from app.infrastructure.clusters_service import clusters_service
from app.infrastructure.deployments_service import deployments_service
from app.infrastructure.disaster_recovery_service import disaster_recovery_service
from app.infrastructure.observability_service import observability_service
from app.infrastructure.regions_service import regions_service
from app.infrastructure.reliability_service import reliability_service
from app.models.infrastructure import ChaosRun
from app.models.organization import Organization

router = APIRouter(prefix="/infrastructure", tags=["Infrastructure"])


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


# ---------------------------------------------------------------------------
# Regions & multi-region routing
# ---------------------------------------------------------------------------


@router.get("/regions")
async def list_regions(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
):
    return await regions_service.list_regions(db, status=status)


@router.post("/regions", status_code=201)
async def create_region(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await regions_service.create_region(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/regions/nearest")
async def nearest_region(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    ip: Optional[str] = None,
    latency: Optional[int] = None,
    continent: Optional[str] = None,
):
    return await regions_service.nearest_region(db, ip=ip, latency=latency, continent=continent)


@router.get("/regions/summary")
async def region_summary(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await regions_service.summary(db)


@router.get("/regions/canary")
async def canary_regions(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await regions_service.canary_regions(db)


@router.get("/regions/{region_id}")
async def get_region(
    region_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    region = await regions_service.get_region(db, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")
    return region


@router.patch("/regions/{region_id}")
async def update_region(
    region_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    region = await regions_service.update_region(db, region_id, **payload)
    await db.commit()
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")
    return region


@router.delete("/regions/{region_id}")
async def delete_region(
    region_id: str,
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    deleted = await regions_service.delete_region(db, region_id)
    await db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"deleted": True}


@router.get("/regions/{region_id}/residency")
async def residency_check(
    region_id: str,
    compliance: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await regions_service.residency_check(db, region_id, compliance=compliance)


# ---------------------------------------------------------------------------
# Zero-downtime deployments
# ---------------------------------------------------------------------------


@router.get("/deployments")
async def list_deployments(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    service: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
):
    return await deployments_service.list_deployments(db, service=service, status=status, limit=limit)


@router.post("/deployments", status_code=201)
async def start_deployment(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await deployments_service.start(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/deployments/validate")
async def validate_deployment(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await deployments_service.validate(db, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/deployments/{deployment_id}")
async def get_deployment(
    deployment_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    deployment = await deployments_service.get_deployment(db, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.post("/deployments/{deployment_id}/complete")
async def complete_deployment(
    deployment_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    deployment = await deployments_service.complete(db, deployment_id=deployment_id, organization_id=org.id, **payload)
    await db.commit()
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.post("/deployments/{deployment_id}/promote")
async def promote_canary(
    deployment_id: str,
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        deployment = await deployments_service.promote_canary(db, deployment_id=deployment_id, organization_id=org.id)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.post("/deployments/{deployment_id}/rollback")
async def rollback_deployment(
    deployment_id: str,
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    deployment = await deployments_service.rollback(db, deployment_id=deployment_id, organization_id=org.id)
    await db.commit()
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


# ---------------------------------------------------------------------------
# Backups & PITR
# ---------------------------------------------------------------------------


@router.get("/backups")
async def list_backups(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
):
    return await backups_service.list_backups(db, status=status, kind=kind, limit=limit)


@router.post("/backups", status_code=201)
async def create_backup(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await backups_service.create(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/backups/pitr")
async def pitr_point(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    timestamp: str = "",
    max_lag_minutes: int = 5,
):
    try:
        result = await backups_service.pitr_point(db, timestamp=timestamp, max_lag_minutes=max_lag_minutes)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/backups/summary")
async def backup_summary(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await backups_service.summary(db)


@router.get("/backups/gaps")
async def backup_gaps(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await backups_service.gap_analysis(db)


@router.get("/backups/{backup_id}")
async def get_backup(
    backup_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    backup = await backups_service.get_backup(db, backup_id)
    if backup is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup


@router.post("/backups/{backup_id}/complete")
async def complete_backup(
    backup_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        backup = await backups_service.complete(db, backup_id=backup_id, organization_id=org.id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if backup is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        backup = await backups_service.restore(db, backup_id=backup_id, organization_id=org.id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if backup is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup


# ---------------------------------------------------------------------------
# Replicated cluster health & failover
# ---------------------------------------------------------------------------


@router.get("/clusters")
async def list_clusters(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    cluster_type: Optional[str] = None,
    status: Optional[str] = None,
):
    return await clusters_service.list_clusters(db, cluster_type=cluster_type, status=status)


@router.get("/clusters/topology/{cluster_type}")
async def cluster_topology(
    cluster_type: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await clusters_service.topology(db, cluster_type)


@router.post("/clusters/nodes", status_code=201)
async def upsert_cluster_node(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await clusters_service.upsert_node(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/clusters/failover")
async def cluster_failover(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await clusters_service.failover(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/clusters/{cluster_id}")
async def get_cluster(
    cluster_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    cluster = await clusters_service.get_cluster(db, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster node not found")
    return cluster


@router.post("/clusters/{cluster_id}/failure")
async def cluster_node_failure(
    cluster_id: str,
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    cluster = await clusters_service.node_failure(db, cluster_id=cluster_id, organization_id=org.id)
    await db.commit()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster node not found")
    return cluster


# ---------------------------------------------------------------------------
# Disaster recovery
# ---------------------------------------------------------------------------


@router.get("/dr")
async def list_dr_runs(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    scenario: Optional[str] = None,
    limit: int = 100,
):
    return await disaster_recovery_service.list_runs(db, status=status, scenario=scenario, limit=limit)


@router.post("/dr", status_code=201)
async def start_dr_run(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await disaster_recovery_service.start(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/dr/rpo-rto")
async def dr_rpo_rto(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await disaster_recovery_service.rpo_rto_summary(db)


@router.get("/dr/{run_id}")
async def get_dr_run(
    run_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    run = await disaster_recovery_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="DR run not found")
    return run


@router.post("/dr/{run_id}/advance")
async def advance_dr_run(
    run_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await disaster_recovery_service.advance(db, run_id=run_id, organization_id=org.id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="DR run not found")
    return run


@router.post("/dr/{run_id}/verify")
async def verify_dr_run(
    run_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await disaster_recovery_service.verify(db, run_id=run_id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="DR run not found")
    return run


# ---------------------------------------------------------------------------
# Autoscaling
# ---------------------------------------------------------------------------


@router.get("/autoscaling")
async def list_autoscaling_events(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    resource: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
):
    return await autoscaling_service.list_events(db, resource=resource, status=status, limit=limit)


@router.post("/autoscaling/evaluate")
async def evaluate_autoscaling(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await autoscaling_service.evaluate(db, organization_id=org.id, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/autoscaling/summary")
async def autoscaling_summary(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    events = await autoscaling_service.list_events(db, limit=1000)
    up = sum(1 for event in events if event.direction == "scale_up" and event.to_capacity > event.from_capacity)
    down = sum(1 for event in events if event.direction == "scale_down" and event.to_capacity < event.from_capacity)
    return {
        "events": len(events),
        "scale_ups": up,
        "scale_downs": down,
        "applied": sum(1 for event in events if event.status == "applied"),
        "resources": sorted({event.resource for event in events}),
    }


@router.get("/autoscaling/{event_id}")
async def get_autoscaling_event(
    event_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    event = await autoscaling_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Autoscaling event not found")
    return event


@router.post("/autoscaling/{event_id}/apply")
async def apply_autoscaling(
    event_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        event = await autoscaling_service.apply(db, event_id=event_id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Autoscaling event not found")
    return event


# ---------------------------------------------------------------------------
# Observability: health & service metrics
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def infra_dashboard(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await observability_service.dashboard(db)


@router.get("/health")
async def list_health_metrics(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    service: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 100,
):
    return await observability_service.query_health(db, service=service, region=region, limit=limit)


@router.get("/metrics")
async def list_service_metrics(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    service: Optional[str] = None,
    metric_name: Optional[str] = None,
    limit: int = 100,
):
    return await observability_service.query_service_metric(
        db, service=service, metric_name=metric_name, limit=limit
    )


@router.post("/metrics/health", status_code=201)
async def record_health_metric(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await observability_service.record_health(db, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.post("/metrics/service", status_code=201)
async def record_service_metric(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    result = await observability_service.record_service_metric(db, **payload)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Reliability engineering: circuit breakers & chaos
# ---------------------------------------------------------------------------


@router.get("/circuits")
async def circuit_summary(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await reliability_service.circuit_summary()


@router.get("/circuits/{name}")
async def circuit_state(
    name: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await reliability_service.circuit_state(name)


@router.post("/circuits/{name}/success")
async def circuit_success(
    name: str,
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    reliability_service.record_success(name)
    return {"name": name, "state": "closed"}


@router.post("/circuits/{name}/failure")
async def circuit_failure(
    name: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    tripped = reliability_service.record_failure(name, threshold=int(payload.get("threshold", 5)))
    await db.commit()
    return {"name": name, "tripped": tripped, "state": "open" if tripped else "closed"}


@router.post("/health-checks")
async def run_health_check(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    result = await reliability_service.health_check(db, **payload)
    await db.commit()
    return result


@router.get("/chaos")
async def list_chaos_runs(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    scenario: Optional[str] = None,
    limit: int = 100,
):
    return await reliability_service.list_chaos_runs(db, status=status, scenario=scenario, limit=limit)


@router.post("/chaos", status_code=201)
async def run_chaos_experiment(
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await reliability_service.run_chaos(db, **payload)
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad(str(exc)) from exc


@router.get("/chaos/{run_id}/blast-radius")
async def chaos_blast_radius(
    run_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    affected_services: int = 1,
):
    result = await reliability_service.blast_radius(db, run_id=run_id, affected_services=affected_services)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Chaos run not found")
    return result


@router.get("/chaos/{run_id}")
async def get_chaos_run(
    run_id: str,
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    run = await db.get(ChaosRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Chaos run not found")
    return run


@router.post("/chaos/{run_id}/complete")
async def complete_chaos_run(
    run_id: str,
    payload: dict[str, Any] = {},
    _user: Any = Depends(require_permission("infrastructure:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await reliability_service.complete_chaos(db, run_id=run_id, **payload)
        await db.commit()
    except ValueError as exc:
        raise _bad(str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Chaos run not found")
    return run


# ---------------------------------------------------------------------------
# Reliability summary
# ---------------------------------------------------------------------------


@router.get("/reliability/summary")
async def reliability_summary(
    _user: Any = Depends(require_permission("infrastructure:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    circuits = await reliability_service.circuit_summary()
    chaos = await reliability_service.list_chaos_runs(db, limit=1000)
    deployments = await deployments_service.list_deployments(db, limit=1000)
    return {
        "circuits": circuits,
        "chaos_runs": len(chaos),
        "chaos_completed": sum(1 for run in chaos if run.status == "completed"),
        "deployments": len(deployments),
        "deployments_failed": sum(1 for run in deployments if run.status == "failed"),
        "recommendations": [
            "keep chaos experiments small and scoped to one service",
            "run failover drills quarterly against RPO/RTO targets",
        ],
    }
