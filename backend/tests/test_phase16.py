"""Phase 16 — Global Scale, Cloud Infrastructure & Enterprise Reliability.

Covers the infrastructure control plane: multi-region topology & routing,
zero-downtime deployments (blue-green/canary/rolling/rollback), backups &
PITR, replicated cluster health & failover, disaster recovery (RPO/RTO),
autoscaling, observability dashboards, reliability engineering (circuit
breakers, chaos runs), RBAC gating, platform-wide events, universal search
and the Phase 16 workers.
"""

import pytest

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Infra Worker", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Infra Worker", "password": "InfraPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=50", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


async def _seed_region(client, headers, name="na-virginia", **overrides):
    payload = {"name": name, "provider": "aws", "location": "Virginia, USA",
               "continent": "north_america", "latency_ms": 10, "load_percent": 40,
               "residency": ["gdpr", "soc2"], "active_instances": 4}
    payload.update(overrides)
    response = await client.post("/api/v1/infrastructure/regions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _start_deployment(client, headers, version="v1.2.0", service="api-gateway", strategy="blue_green"):
    response = await client.post(
        "/api/v1/infrastructure/deployments",
        json={"version": version, "service": service, "strategy": strategy,
              "old_replicas": 3, "new_replicas": 3, "canary_percentage": 10},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ regions


async def test_region_crud_routing_and_residency(client):
    org = await register_org(client, email="p16reg@test.co")
    headers = org["headers"]

    region = await _seed_region(client, headers)
    assert region["status"] == "active"
    assert region["residency"] == ["gdpr", "soc2"]

    duplicate = await client.post(
        "/api/v1/infrastructure/regions",
        json={"name": "na-virginia"}, headers=headers,
    )
    assert duplicate.status_code == 400

    missing = await client.post(
        "/api/v1/infrastructure/regions", json={"name": ""}, headers=headers
    )
    assert missing.status_code == 400

    nearest = (await client.get("/api/v1/infrastructure/regions/nearest", headers=headers)).json()
    assert nearest["region"] == "na-virginia"

    updated = await client.patch(
        f"/api/v1/infrastructure/regions/{region['id']}",
        json={"load_percent": 85, "status": "degraded"}, headers=headers,
    )
    assert updated.json()["load_percent"] == 85

    summary = (await client.get("/api/v1/infrastructure/regions/summary", headers=headers)).json()
    assert summary["regions"] >= 1
    assert summary["by_status"]["degraded"] >= 1

    filtered = await client.get(
        "/api/v1/infrastructure/regions", params={"status": "degraded"}, headers=headers
    )
    assert len(filtered.json()) >= 1

    canary = await client.get("/api/v1/infrastructure/regions/canary", headers=headers)
    assert canary.status_code == 200

    allowed = await client.get(
        f"/api/v1/infrastructure/regions/{region['id']}/residency",
        params={"compliance": "gdpr"}, headers=headers,
    )
    assert allowed.json()["allowed"] is True
    blocked = await client.get(
        f"/api/v1/infrastructure/regions/{region['id']}/residency",
        params={"compliance": "hipaa"}, headers=headers,
    )
    assert blocked.json()["allowed"] is False

    deleted = await client.delete(f"/api/v1/infrastructure/regions/{region['id']}", headers=headers)
    assert deleted.status_code == 200
    assert (await client.get(f"/api/v1/infrastructure/regions/{region['id']}", headers=headers)).status_code == 404


# -------------------------------------------------------------- deployments


async def test_deployment_lifecycle_blue_green_rolling_canary(client):
    org = await register_org(client, email="p16dep@test.co")
    headers = org["headers"]

    bad = await client.post(
        "/api/v1/infrastructure/deployments",
        json={"version": "v1", "service": "api", "strategy": "everything"}, headers=headers,
    )
    assert bad.status_code == 400

    deployment = await _start_deployment(client, headers)
    assert deployment["status"] == "started"
    assert deployment["strategy"] == "blue_green"

    validation = await client.post(
        "/api/v1/infrastructure/deployments/validate",
        json={"version": "v1.3.0", "service": "api-gateway", "strategy": "rolling"}, headers=headers,
    )
    assert validation.json()["valid"] is True
    invalid = await client.post(
        "/api/v1/infrastructure/deployments/validate",
        json={"version": "", "service": "api", "strategy": "rollback"}, headers=headers,
    )
    assert invalid.json()["valid"] is False

    completed = await client.post(
        f"/api/v1/infrastructure/deployments/{deployment['id']}/complete",
        json={"status": "completed"}, headers=headers,
    )
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    failed = await _start_deployment(client, headers, version="v1.2.1", service="api-gateway", strategy="rolling")
    rolled = await client.post(
        f"/api/v1/infrastructure/deployments/{failed['id']}/rollback", headers=headers
    )
    assert rolled.json()["status"] == "rolled_back"

    canary = await _start_deployment(client, headers, version="v1.2.2", service="api-gateway", strategy="canary")
    assert canary["canary_percentage"] == 10
    promoted = await client.post(
        f"/api/v1/infrastructure/deployments/{canary['id']}/promote", headers=headers
    )
    assert promoted.json()["status"] == "promoted"
    assert promoted.json()["canary_percentage"] == 100

    listing = (await client.get("/api/v1/infrastructure/deployments", headers=headers)).json()
    assert len(listing) >= 3
    listing = (await client.get(
        "/api/v1/infrastructure/deployments", params={"status": "completed"}, headers=headers
    )).json()
    assert all(d["status"] == "completed" for d in listing)


# ----------------------------------------------------------------- backups


async def test_backup_lifecycle_pitr_and_gaps(client):
    org = await register_org(client, email="p16bak@test.co")
    headers = org["headers"]

    bad = await client.post(
        "/api/v1/infrastructure/backups",
        json={"kind": "monthly", "target": "postgres"}, headers=headers,
    )
    assert bad.status_code == 400

    backup = await client.post(
        "/api/v1/infrastructure/backups",
        json={"kind": "pitr", "target": "postgres", "region": "na-virginia", "retention_days": 45},
        headers=headers,
    )
    assert backup.status_code == 201, backup.text
    backup_id = backup.json()["id"]
    assert backup.json()["status"] == "started"

    completed = await client.post(
        f"/api/v1/infrastructure/backups/{backup_id}/complete",
        json={"status": "completed", "size_bytes": 1048576, "verified": True}, headers=headers,
    )
    assert completed.json()["status"] == "completed"
    assert completed.json()["verified"] is True

    pitr = await client.get(
        "/api/v1/infrastructure/backups/pitr",
        params={"timestamp": completed.json()["completed_at"]}, headers=headers,
    )
    assert pitr.json()["available"] is True
    assert pitr.json()["backup_id"] == backup_id

    restored = await client.post(
        f"/api/v1/infrastructure/backups/{backup_id}/restore",
        json={"target": "staging"}, headers=headers,
    )
    assert restored.json()["status"] == "restored"

    double = await client.post(
        f"/api/v1/infrastructure/backups/{backup_id}/restore", headers=headers
    )
    assert double.status_code == 400

    summary = (await client.get("/api/v1/infrastructure/backups/summary", headers=headers)).json()
    assert summary["backups"] >= 1
    assert summary["verified"] >= 1

    gaps = await client.get("/api/v1/infrastructure/backups/gaps", headers=headers)
    assert gaps.status_code == 200


# ----------------------------------------------------------------- clusters


async def test_cluster_topology_failure_and_failover(client):
    org = await register_org(client, email="p16cls@test.co")
    headers = org["headers"]

    primary = await client.post(
        "/api/v1/infrastructure/clusters/nodes",
        json={"cluster_type": "postgres", "region": "na-virginia", "name": "pg-1",
              "role": "primary", "status": "healthy", "version": "16", "lag_seconds": 0,
              "healthy_nodes": 3, "total_nodes": 3},
        headers=headers,
    )
    assert primary.status_code == 201, primary.text

    replica = await client.post(
        "/api/v1/infrastructure/clusters/nodes",
        json={"cluster_type": "postgres", "region": "na-virginia", "name": "pg-2",
              "role": "replica", "status": "healthy", "lag_seconds": 2,
              "healthy_nodes": 3, "total_nodes": 3},
        headers=headers,
    )
    assert replica.status_code == 201, replica.text

    no_failover = await client.post(
        "/api/v1/infrastructure/clusters/failover",
        json={"cluster_type": "postgres", "region": "na-virginia"}, headers=headers,
    )
    assert no_failover.json()["failover"] is False

    failed = await client.post(
        f"/api/v1/infrastructure/clusters/{primary.json()['id']}/failure", headers=headers
    )
    assert failed.json()["status"] == "degraded"

    failover = await client.post(
        "/api/v1/infrastructure/clusters/failover",
        json={"cluster_type": "postgres", "region": "na-virginia"}, headers=headers,
    )
    body = failover.json()
    assert body["failover"] is True
    assert body["new_primary"] == "pg-2"

    topology = (await client.get("/api/v1/infrastructure/clusters/topology/postgres", headers=headers)).json()
    assert topology["nodes"] >= 2
    assert topology["primaries"] >= 1
    assert any(n["name"] == "pg-2" and n["role"] == "primary" for n in topology["topology"])

    bad = await client.post(
        "/api/v1/infrastructure/clusters/nodes",
        json={"cluster_type": "mainframe", "role": "primary"}, headers=headers,
    )
    assert bad.status_code == 400


# ------------------------------------------------------------ disaster recovery


async def test_disaster_recovery_flow_and_rpo_rto(client):
    org = await register_org(client, email="p16dr@test.co")
    headers = org["headers"]

    run = await client.post(
        "/api/v1/infrastructure/dr",
        json={"scenario": "region_outage", "region": "na-virginia",
              "steps": ["detect outage", "drain traffic"]},
        headers=headers,
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    failover = await client.post(
        f"/api/v1/infrastructure/dr/{run_id}/advance",
        json={"status": "failover", "rpo_minutes": 8, "rto_minutes": 12, "outcome": "failover ok"},
        headers=headers,
    )
    assert failover.json()["status"] == "failover"

    verified = await client.post(
        f"/api/v1/infrastructure/dr/{run_id}/verify", json={"outcome": "ok"}, headers=headers
    )
    assert verified.json()["outcome"] == "ok"

    completed = await client.post(
        f"/api/v1/infrastructure/dr/{run_id}/advance",
        json={"status": "completed", "rpo_minutes": 10, "rto_minutes": 15}, headers=headers,
    )
    assert completed.json()["status"] == "completed"
    assert completed.json()["rpo_minutes"] == 10

    summary = (await client.get("/api/v1/infrastructure/dr/rpo-rto", headers=headers)).json()
    assert summary["report"] is True
    assert summary["runs_evaluated"] >= 1
    assert summary["rpo_breached"] == 0

    listing = (await client.get(
        "/api/v1/infrastructure/dr", params={"status": "completed"}, headers=headers
    )).json()
    assert any(r["id"] == run_id for r in listing)

    bad = await client.post(
        "/api/v1/infrastructure/dr", json={"scenario": "alien_invasion"}, headers=headers
    )
    assert bad.status_code == 400


# --------------------------------------------------------------- autoscaling


async def test_autoscaling_evaluate_apply_and_cooldown(client):
    org = await register_org(client, email="p16auto@test.co")
    headers = org["headers"]

    scale_up = await client.post(
        "/api/v1/infrastructure/autoscaling/evaluate",
        json={"resource": "api", "region": "na-virginia", "cpu_percent": 92.0,
              "current_capacity": 2, "scale_out_at": 70.0, "scale_in_at": 30.0},
        headers=headers,
    )
    assert scale_up.status_code == 200, scale_up.text
    event = scale_up.json()
    assert event["direction"] == "scale_up"
    assert event["to_capacity"] > event["from_capacity"]

    applied = await client.post(
        f"/api/v1/infrastructure/autoscaling/{event['id']}/apply",
        json={"status": "applied"}, headers=headers,
    )
    assert applied.json()["status"] == "applied"

    scale_down = await client.post(
        "/api/v1/infrastructure/autoscaling/evaluate",
        json={"resource": "workers", "cpu_percent": 5.0, "current_capacity": 4,
              "scale_out_at": 70.0, "scale_in_at": 30.0},
        headers=headers,
    )
    assert scale_down.json()["direction"] == "scale_down"

    summary = (await client.get("/api/v1/infrastructure/autoscaling/summary", headers=headers)).json()
    assert summary["scale_ups"] >= 1
    assert summary["scale_downs"] >= 1
    assert summary["applied"] >= 1

    listing = (await client.get(
        "/api/v1/infrastructure/autoscaling", params={"resource": "api"}, headers=headers
    )).json()
    assert len(listing) >= 1

    bad = await client.post(
        "/api/v1/infrastructure/autoscaling/evaluate",
        json={"resource": "quantum", "cpu_percent": 95.0}, headers=headers,
    )
    assert bad.status_code == 400


# -------------------------------------------------------------- observability


async def test_observability_metrics_and_dashboard(client):
    org = await register_org(client, email="p16obs@test.co")
    headers = org["headers"]

    health = await client.post(
        "/api/v1/infrastructure/metrics/health",
        json={"region": "na-virginia", "service": "api-gateway", "status": "ok",
              "metric_name": "availability", "value": 99.95},
        headers=headers,
    )
    assert health.status_code == 201, health.text

    degraded = await client.post(
        "/api/v1/infrastructure/metrics/health",
        json={"region": "na-virginia", "service": "api-gateway", "status": "warn",
              "metric_name": "latency_ms", "value": 240.0, "unit": "ms"},
        headers=headers,
    )
    assert degraded.status_code == 201, degraded.text

    bad = await client.post(
        "/api/v1/infrastructure/metrics/health",
        json={"region": "na-virginia", "service": "x", "status": "exploded"},
        headers=headers,
    )
    assert bad.status_code == 400

    metric = await client.post(
        "/api/v1/infrastructure/metrics/service",
        json={"service": "workers", "metric_name": "queue_depth", "value": 7,
              "unit": "count", "region": "na-virginia", "details": {"priority": "high"}},
        headers=headers,
    )
    assert metric.status_code == 201, metric.text

    metrics = (await client.get(
        "/api/v1/infrastructure/metrics", params={"service": "workers"}, headers=headers
    )).json()
    assert any(m["metric_name"] == "queue_depth" for m in metrics)

    health_list = (await client.get(
        "/api/v1/infrastructure/health", params={"service": "api-gateway"}, headers=headers
    )).json()
    assert len(health_list) >= 2

    dashboard = (await client.get("/api/v1/infrastructure/dashboard", headers=headers)).json()
    assert dashboard["health"]["total"] >= 2
    assert dashboard["health"]["healthy_percent"] > 0
    assert "workers" in dashboard["services"]
    assert "api-gateway" in dashboard["warn_services"]


# ----------------------------------------------- reliability: circuit breakers


async def test_circuit_breaker_opens_and_recovers(client):
    org = await register_org(client, email="p16cb@test.co")
    headers = org["headers"]

    state = await client.get("/api/v1/infrastructure/circuits/payments", headers=headers)
    assert state.json()["state"] == "closed"

    for _ in range(5):
        await client.post(
            "/api/v1/infrastructure/circuits/payments/failure", json={"threshold": 5}, headers=headers
        )
    state = await client.get("/api/v1/infrastructure/circuits/payments", headers=headers)
    assert state.json()["state"] == "open"
    assert state.json()["failures"] == 5

    success = await client.post("/api/v1/infrastructure/circuits/payments/success", headers=headers)
    assert success.json()["state"] == "closed"

    summary = (await client.get("/api/v1/infrastructure/circuits", headers=headers)).json()
    assert summary["total"] >= 1


async def test_health_checks_and_chaos_experiments(client):
    org = await register_org(client, email="p16chaos@test.co")
    headers = org["headers"]

    check = await client.post(
        "/api/v1/infrastructure/health-checks",
        json={"service": "api-gateway", "timeout_ms": 2000}, headers=headers,
    )
    assert check.status_code == 200, check.text
    assert check.json()["status"] == "healthy"

    run = await client.post(
        "/api/v1/infrastructure/chaos",
        json={"scenario": "kill_replica", "target_region": "na-virginia",
              "target_service": "api-gateway", "expected_impact": "brief 5xx"}, headers=headers,
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    assert run.json()["status"] == "running"

    radius = await client.get(
        f"/api/v1/infrastructure/chaos/{run_id}/blast-radius",
        params={"affected_services": 2}, headers=headers,
    )
    assert radius.json()["severity"] == "medium"

    completed = await client.post(
        f"/api/v1/infrastructure/chaos/{run_id}/complete",
        json={"status": "completed", "summary": "no impact observed"}, headers=headers,
    )
    assert completed.json()["status"] == "completed"

    listing = (await client.get(
        "/api/v1/infrastructure/chaos", params={"scenario": "kill_replica"}, headers=headers
    )).json()
    assert any(r["id"] == run_id for r in listing)

    bad = await client.post(
        "/api/v1/infrastructure/chaos",
        json={"scenario": "drop_table", "target_service": "api"}, headers=headers,
    )
    assert bad.status_code == 400

    summary = (await client.get("/api/v1/infrastructure/reliability/summary", headers=headers)).json()
    assert summary["chaos_runs"] >= 1
    assert summary["chaos_completed"] >= 1
    assert summary["circuits"]["total"] >= 1


# ------------------------------------------------------------- RBAC & events


async def test_infrastructure_rbac_and_events(client):
    org = await register_org(client, email="p16rbac@test.co")
    headers = org["headers"]

    await _seed_region(client, headers)
    deployment = await _start_deployment(client, headers)
    await client.post(
        f"/api/v1/infrastructure/deployments/{deployment['id']}/complete",
        json={"status": "completed"}, headers=headers,
    )
    backup = await client.post(
        "/api/v1/infrastructure/backups",
        json={"kind": "daily", "target": "postgres"}, headers=headers,
    )
    await client.post(
        f"/api/v1/infrastructure/backups/{backup.json()['id']}/complete",
        json={"status": "completed"}, headers=headers,
    )
    primary = await client.post(
        "/api/v1/infrastructure/clusters/nodes",
        json={"cluster_type": "redis", "region": "na-virginia", "name": "redis-1",
              "role": "primary", "status": "healthy", "healthy_nodes": 2, "total_nodes": 2},
        headers=headers,
    )
    await client.post(f"/api/v1/infrastructure/clusters/{primary.json()['id']}/failure", headers=headers)
    await client.post(
        "/api/v1/infrastructure/autoscaling/evaluate",
        json={"resource": "search", "cpu_percent": 85.0, "current_capacity": 1}, headers=headers,
    )
    await client.post(
        "/api/v1/infrastructure/dr", json={"scenario": "db_failover", "region": "na-virginia"}, headers=headers
    )

    names = await _event_names(client, headers)
    for expected in (
        "deployment.started",
        "deployment.completed",
        "backup.started",
        "backup.completed",
        "replica.failed",
        "autoscaling.triggered",
        "disaster.recovery.started",
    ):
        assert expected in names, f"missing event {expected}"

    employee = await _invite(client, headers, "p16emp@test.co", role="employee")
    emp_headers = employee["headers"]
    denied = await client.get("/api/v1/infrastructure/regions", headers=emp_headers)
    assert denied.status_code == 403
    denied = await client.post(
        "/api/v1/infrastructure/regions", json={"name": "na-oregon"}, headers=emp_headers
    )
    assert denied.status_code == 403

    manager = await _invite(client, headers, "p16mgr@test.co", role="manager")
    mgr_headers = manager["headers"]
    regions = await client.get("/api/v1/infrastructure/regions", headers=mgr_headers)
    assert regions.status_code == 200
    denied = await client.post(
        "/api/v1/infrastructure/deployments",
        json={"version": "v9", "service": "api"}, headers=mgr_headers,
    )
    assert denied.status_code == 403


async def test_infrastructure_search(client):
    org = await register_org(client, email="p16search@test.co")
    headers = org["headers"]

    await _seed_region(client, headers)
    await _start_deployment(client, headers, service="canary-api")
    await client.post(
        "/api/v1/infrastructure/clusters/nodes",
        json={"cluster_type": "opensearch", "region": "na-virginia", "name": "search-prod-1",
              "role": "primary", "status": "healthy", "healthy_nodes": 3, "total_nodes": 3},
        headers=headers,
    )
    await client.post(
        "/api/v1/infrastructure/chaos",
        json={"scenario": "network_partition", "target_service": "api-gateway"}, headers=headers,
    )

    response = await client.get("/api/v1/search?q=virginia", headers=headers)
    assert response.status_code == 200, response.text
    types = {r["type"] for r in response.json()["results"]}
    assert "cloud_region" in types
    assert "cluster" in types

    response = await client.get("/api/v1/search?q=canary-api", headers=headers)
    types = {r["type"] for r in response.json()["results"]}
    assert "deployment" in types

    response = await client.get("/api/v1/search?q=network_partition", headers=headers)
    types = {r["type"] for r in response.json()["results"]}
    assert "chaos_run" in types


# ------------------------------------------------------------- Phase 16 workers


async def test_phase16_workers_registered_and_run(db_session_factory):
    from app.workers.scheduler import WORKER_REGISTRY

    names = [name for name, _ in WORKER_REGISTRY]
    assert "infra_health" in names, "infra_health worker not registered"

    from app.workers import infra_health_worker

    async with db_session_factory() as db:
        assert isinstance(await infra_health_worker.run_once(db=db), int)
        await db.commit()
