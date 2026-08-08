"""Phase 9 — Background Intelligence & Autonomous Organization tests.

Covers the durable event bus (publish → worker dispatch → handler effects),
the intelligence engines (expertise evolution, org graph, knowledge, search,
collaboration, burnout, duplicates, patterns, workflow, learning), the
autonomous daily briefs, the personalized recommendation feed, on-demand
worker runs, RBAC gating and multi-tenant isolation.
"""

from datetime import timedelta

import pytest

from app.core.timeutils import utcnow
from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _seed_project_task(client, headers, *, code="P9-1", title="Orion", overdue=False):
    me = await _employee_id(client, headers)
    project = await client.post(
        "/api/v1/projects",
        json={"name": title, "code": code, "owner_id": me, "status": "active",
              "end_date": "2020-01-01" if overdue else None},
        headers=headers,
    )
    assert project.status_code == 201, project.text
    pid = project.json()["id"]
    task = await client.post(
        "/api/v1/tasks",
        json={
            "project_id": pid,
            "title": "Core deliverable",
            "assignee_id": me,
            "estimate_hours": 8,
            "due_date": "2020-01-01" if overdue else None,
        },
        headers=headers,
    )
    assert task.status_code == 201, task.text
    return pid, task.json()["id"]


# =================================================================== event bus

@pytest.mark.asyncio
async def test_event_bus_persists_and_dispatches(client):
    org = await register_org(client, email="p9bus@work.test.co")
    headers = org["headers"]
    await _seed_project_task(client, headers, code="P9-BUS")

    events = (await client.get("/api/v1/intelligence/events", headers=headers)).json()
    names = {e["name"] for e in events}
    assert "project.created" in names
    assert "task.created" in names

    processed = (await client.post("/api/v1/intelligence/events/process", headers=headers)).json()
    assert processed["processed"] >= 1

    stats = (await client.get("/api/v1/intelligence/events/stats", headers=headers)).json()
    assert stats.get("done", 0) >= 2


@pytest.mark.asyncio
async def test_event_handlers_update_expertise_and_graph(client):
    org = await register_org(client, email="p9exp@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    _, task_id = await _seed_project_task(client, headers, code="P9-EXP")

    skill = await client.post(
        "/api/v1/expertise/skills",
        json={"name": "Project Management", "category": "Leadership"},
        headers=headers,
    )
    assert skill.status_code == 201, skill.text
    assigned = await client.post(
        f"/api/v1/employees/{me}/skills",
        json={"skill_id": skill.json()["id"], "proficiency": "expert"},
        headers=headers,
    )
    assert assigned.status_code == 201, assigned.text

    completed = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        json={"status": "completed"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    await client.post("/api/v1/intelligence/events/process", headers=headers)

    leaderboard = (await client.get("/api/v1/intelligence/expertise/leaderboard", headers=headers)).json()
    assert leaderboard, "leaderboard should include the CEO after activity"
    assert any(entry["employee_id"] == me for entry in leaderboard)

    history = (await client.get(f"/api/v1/intelligence/expertise/{me}/history", headers=headers)).json()
    assert history, "expertise history should record activity events"
    assert any("task" in h["reason"] or "completed" in h["reason"] for h in history)

    graph = (await client.get("/api/v1/intelligence/graph", headers=headers)).json()
    assert graph["edges"] >= 1

    edges = (await client.get("/api/v1/intelligence/graph/edges", headers=headers)).json()
    assert edges, "graph edges should include structural + activity edges"
    relations = {e["relation"] for e in edges}
    assert "assigned_to" in relations or "completed" in relations

    neighbors = (await client.get(
        f"/api/v1/intelligence/graph/neighbors?entity_type=employee&entity_id={me}",
        headers=headers,
    )).json()
    assert isinstance(neighbors, list)


@pytest.mark.asyncio
async def test_event_dispatch_is_idempotent(client):
    org = await register_org(client, email="p9idem@work.test.co")
    headers = org["headers"]
    await _seed_project_task(client, headers, code="P9-IDEM")
    # drain the queue — each pass may surface newly emitted background audit
    # events (expertise.updated, graph.updated, learning.recorded), which are
    # marked processed on the following pass.
    for _ in range(5):
        response = (await client.post("/api/v1/intelligence/events/process", headers=headers)).json()
        if response["processed"] == 0:
            break
    # a fully drained bus stays drained — no double-dispatch, no leftovers
    assert (await client.post("/api/v1/intelligence/events/process", headers=headers)).json()["processed"] == 0
    events = (await client.get("/api/v1/intelligence/events", headers=headers)).json()
    assert events, "events should have been persisted"
    assert all(e["processed_at"] for e in events), "every event should eventually be processed"


# =================================================================== workers

@pytest.mark.asyncio
async def test_on_demand_worker_runs(client, db_session_factory, monkeypatch):
    org = await register_org(client, email="p9worker@work.test.co")
    headers = org["headers"]

    from app.workers import event_worker, knowledge_intel_worker

    monkeypatch.setattr(event_worker, "SessionLocal", db_session_factory)
    monkeypatch.setattr(knowledge_intel_worker, "SessionLocal", db_session_factory)

    response = await client.post("/api/v1/intelligence/workers/event/run", headers=headers)
    assert response.status_code == 200, response.text
    assert "processed" in response.json()

    scan = await client.post("/api/v1/intelligence/workers/knowledge_intel/run", headers=headers)
    assert scan.status_code == 200, scan.text

    workers = (await client.get("/api/v1/intelligence/workers", headers=headers)).json()
    assert any(w["name"] == "event" for w in workers)
    assert any(w["name"] == "insights" for w in workers)

    missing = await client.post("/api/v1/intelligence/workers/nope/run", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_jobs_tracked(client):
    org = await register_org(client, email="p9jobs@work.test.co")
    headers = org["headers"]
    jobs = (await client.get("/api/v1/intelligence/jobs", headers=headers)).json()
    assert isinstance(jobs, list)


# =================================================================== engines

@pytest.mark.asyncio
async def test_knowledge_scan_and_status_flow(client, db_session):
    org = await register_org(client, email="p9know@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    document = await client.post(
        "/api/v1/documents",
        json={"title": "Outdated policy handbook", "content": "Old content here.",
              "category": "policy", "owner_id": me},
        headers=headers,
    )
    assert document.status_code == 201, document.text

    from app.models.knowledge import Document
    from sqlalchemy import select

    row = (
        await db_session.execute(
            select(Document).where(Document.organization_id == org["organization"]["id"])
        )
    ).scalars().first()
    assert row
    row.updated_at = utcnow() - timedelta(days=400)
    row.created_at = utcnow() - timedelta(days=400)
    await db_session.commit()

    from app.intelligence.knowledge_engine import knowledge_engine

    found = await knowledge_engine.scan(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()
    assert found >= 1

    insights = (await client.get("/api/v1/intelligence/knowledge/insights", headers=headers)).json()
    assert insights
    assert any(i["kind"] == "outdated" for i in insights)

    target = insights[0]
    updated = await client.patch(
        f"/api/v1/intelligence/knowledge/insights/{target['id']}",
        json={"status": "accepted"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_search_metrics_and_insights(client, db_session):
    org = await register_org(client, email="p9search@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    from app.intelligence.search_engine import search_engine

    for query in ("project", "project", "project"):
        await search_engine.record_metric(
            db_session, organization_id=org["organization"]["id"],
            query=query, user_id=me, success=False, result_count=0,
        )
    for _ in range(4):
        await search_engine.record_metric(
            db_session, organization_id=org["organization"]["id"],
            query="wiki", user_id=me, success=True, result_count=5,
        )
    await db_session.commit()
    await search_engine.aggregate(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()

    insights = (await client.get("/api/v1/intelligence/search/insights", headers=headers)).json()
    kinds = {i["kind"] for i in insights}
    assert "failed_search" in kinds
    assert "popular_query" in kinds

    stats = (await client.get("/api/v1/intelligence/search/stats", headers=headers)).json()
    assert stats["total_searches"] >= 7


@pytest.mark.asyncio
async def test_collaboration_metrics(client):
    org = await register_org(client, email="p9collab@work.test.co")
    headers = org["headers"]
    recomputed = await client.post("/api/v1/intelligence/collaboration/recompute", headers=headers)
    assert recomputed.status_code == 200, recomputed.text
    data = recomputed.json()
    assert "pair_interactions" in data or "department_pairs" in data

    latest = await client.get("/api/v1/intelligence/collaboration", headers=headers)
    assert latest.status_code == 200, latest.text


@pytest.mark.asyncio
async def test_burnout_scan_and_signals(client, db_session):
    org = await register_org(client, email="p9burn@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    from app.models.task import Task
    from app.models.project import Project

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Crunch", "code": "P9-BRN", "owner_id": me, "status": "active"},
        headers=headers,
    )
    pid = project.json()["id"]
    for i in range(8):
        response = await client.post(
            "/api/v1/tasks",
            json={"project_id": pid, "title": f"crunch-{i}", "assignee_id": me,
                  "estimate_hours": 12, "status": "todo", "due_date": "2020-01-01"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
    from sqlalchemy import select

    tasks = (await db_session.execute(select(Task).where(Task.organization_id == org["organization"]["id"]))).scalars().all()
    assert len(tasks) >= 8

    from app.intelligence.burnout_engine import burnout_engine

    scanned = await burnout_engine.scan(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()
    assert scanned >= 1

    signals = (await client.get("/api/v1/intelligence/burnout/signals", headers=headers)).json()
    assert signals, "burnout signals should include at least the overloaded employee"
    signal = signals[0]
    updated = await client.patch(
        f"/api/v1/intelligence/burnout/signals/{signal['id']}",
        json={"status": "acknowledged"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_duplicate_detection(client, db_session):
    org = await register_org(client, email="p9dupe@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    for i in range(2):
        response = await client.post(
            "/api/v1/tasks",
            json={"title": "Duplicate onboarding task", "assignee_id": me,
                  "estimate_hours": 4},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    from app.intelligence.duplicate_engine import duplicate_engine

    found = await duplicate_engine.scan(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()
    assert found >= 1

    detections = (await client.get("/api/v1/intelligence/duplicates", headers=headers)).json()
    assert detections
    target = detections[0]
    updated = await client.patch(
        f"/api/v1/intelligence/duplicates/{target['id']}",
        json={"status": "confirmed"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_pattern_detection(client, db_session):
    org = await register_org(client, email="p9pat@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    project = await client.post(
        "/api/v1/projects",
        json={"name": "Late Project", "code": "P9-PAT", "owner_id": me, "status": "active"},
        headers=headers,
    )
    pid = project.json()["id"]
    for i in range(3):
        response = await client.post(
            "/api/v1/tasks",
            json={"project_id": pid, "title": f"late-{i}", "assignee_id": me,
                  "status": "todo", "due_date": "2020-01-01"},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    from app.intelligence.pattern_engine import pattern_engine

    found = await pattern_engine.scan(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()
    assert found >= 1

    patterns = (await client.get("/api/v1/intelligence/patterns", headers=headers)).json()
    assert patterns
    target = patterns[0]
    updated = await client.patch(
        f"/api/v1/intelligence/patterns/{target['id']}",
        json={"status": "acknowledged"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text


@pytest.mark.asyncio
async def test_workflow_insights(client, db_session):
    org = await register_org(client, email="p9wf@work.test.co")
    headers = org["headers"]

    from app.models.approval import Approval
    from app.models.user import User
    from sqlalchemy import select

    owner = (await db_session.execute(
        select(User).where(User.organization_id == org["organization"]["id"])
    )).scalars().first()

    for i in range(2):
        db_session.add(Approval(
            organization_id=org["organization"]["id"],
            requester_id=owner.id,
            approver_id=owner.id,
            title=f"stale approval {i}",
            approval_type="expense",
            status="pending",
            created_at=utcnow() - timedelta(days=10),
        ))
    await db_session.commit()

    from app.intelligence.workflow_engine import workflow_engine

    found = await workflow_engine.scan(db_session, organization_id=org["organization"]["id"])
    await db_session.commit()
    assert found >= 1

    insights = (await client.get("/api/v1/intelligence/workflow/insights", headers=headers)).json()
    assert insights
    assert any(i["insight_type"] == "slow_approval" for i in insights)

    target = insights[0]
    updated = await client.patch(
        f"/api/v1/intelligence/workflow/insights/{target['id']}",
        json={"status": "accepted"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text


@pytest.mark.asyncio
async def test_learning_lessons(client, db_session):
    org = await register_org(client, email="p9learn@work.test.co")
    headers = org["headers"]

    from app.intelligence.learning_engine import learning_engine

    await learning_engine.record(
        db_session, organization_id=org["organization"]["id"],
        event_type="project_completed", title="Lessons from Apollo",
        detail="Rollout went well", lesson="Validate early with real users",
        entity_type="project", entity_id="proj-1", tags=["rollout"], memory=True,
    )
    await db_session.commit()

    lessons = (await client.get("/api/v1/intelligence/learning/lessons", headers=headers)).json()
    assert lessons
    assert lessons[0]["lesson"] == "Validate early with real users"

    summary = (await client.get("/api/v1/intelligence/learning/summary", headers=headers)).json()
    assert summary["total"] >= 1
    assert "project_completed" in summary["by_type"]


# =================================================================== briefs & feed

@pytest.mark.asyncio
async def test_executive_brief_generated_on_demand(client):
    org = await register_org(client, email="p9brief@work.test.co")
    headers = org["headers"]
    await _seed_project_task(client, headers, code="P9-BRF")

    brief = await client.get("/api/v1/intelligence/briefs/executive", headers=headers)
    assert brief.status_code == 200, brief.text
    data = brief.json()
    assert data["brief_type"] == "executive"
    assert isinstance(data["sections"], list) and data["sections"]

    listed = (await client.get("/api/v1/intelligence/briefs", headers=headers)).json()
    assert any(b["brief_type"] == "executive" for b in listed)


@pytest.mark.asyncio
async def test_employee_brief_and_recommendation_feed(client):
    org = await register_org(client, email="p9feed@work.test.co")
    headers = org["headers"]
    await _seed_project_task(client, headers, code="P9-FEED")

    brief = await client.get("/api/v1/intelligence/briefs/employee", headers=headers)
    assert brief.status_code == 200, brief.text
    assert brief.json()["brief_type"] == "employee"

    refreshed = await client.post("/api/v1/intelligence/recommendations/refresh", headers=headers)
    assert refreshed.status_code == 200, refreshed.text

    feed = (await client.get("/api/v1/intelligence/recommendations", headers=headers)).json()
    assert isinstance(feed, list)

    if feed:
        target = feed[0]
        updated = await client.patch(
            f"/api/v1/intelligence/recommendations/{target['id']}",
            json={"status": "accepted"},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_briefs_generate_endpoint(client):
    org = await register_org(client, email="p9gen@work.test.co")
    headers = org["headers"]
    response = await client.post("/api/v1/intelligence/briefs/generate", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["executive"]["brief_type"] == "executive"


# =================================================================== overview & RBAC

@pytest.mark.asyncio
async def test_intelligence_overview(client):
    org = await register_org(client, email="p9ov@work.test.co")
    headers = org["headers"]
    response = await client.get("/api/v1/intelligence/overview", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    for key in ("graph", "search", "learning", "jobs", "burnout", "knowledge",
                "duplicates", "patterns", "workflow"):
        assert key in data, f"missing {key} in overview"


@pytest.mark.asyncio
async def test_intelligence_rbac_employee_denied(client):
    org = await register_org(client, email="p9rbac@work.test.co")
    headers = org["headers"]
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "worker@rbac.test.co", "full_name": "Emp Worker", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Worker", "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    employee_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    denied = await client.get("/api/v1/intelligence/overview", headers=employee_headers)
    assert denied.status_code == 403

    denied_run = await client.post(
        "/api/v1/intelligence/events/process", headers=employee_headers
    )
    assert denied_run.status_code == 403

    briefs = await client.get("/api/v1/intelligence/briefs/executive", headers=employee_headers)
    assert briefs.status_code == 403

    feed = await client.get("/api/v1/intelligence/recommendations", headers=employee_headers)
    assert feed.status_code == 200


@pytest.mark.asyncio
async def test_intelligence_requires_auth(client):
    response = await client.get("/api/v1/intelligence/overview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation_for_intelligence(client):
    org_a = await register_org(client, email="p9tena@work.test.co")
    org_b = await register_org(client, email="p9tenb@work.test.co")
    await _seed_project_task(client, org_a["headers"], code="P9-TENA")

    events_a = (await client.get("/api/v1/intelligence/events", headers=org_a["headers"])).json()
    events_b = (await client.get("/api/v1/intelligence/events", headers=org_b["headers"])).json()
    assert any(e["name"] == "project.created" for e in events_a)
    assert not any(e["name"] == "project.created" for e in events_b)


@pytest.mark.asyncio
async def test_event_catalog_endpoint(client):
    org = await register_org(client, email="p9cat@work.test.co")
    headers = org["headers"]
    catalog = (await client.get("/api/v1/intelligence/catalog", headers=headers)).json()
    names = {c["name"] for c in catalog}
    assert "task.created" in names
    assert "meeting.ended" in names
    assert "policy.approved" in names


# =================================================================== background risk engine (Phase 9.9)

@pytest.mark.asyncio
async def test_background_risk_engine_creates_strategic_risks(client, db_session_factory):
    org = await register_org(client, email="p9risk@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    from datetime import datetime, timezone

    from app.models.executive import StrategicRisk
    from app.models.intelligence import BurnoutSignal, KnowledgeInsight
    from sqlalchemy import select

    async with db_session_factory() as db:
        db.add(
            KnowledgeInsight(
                organization_id=org["organization"]["id"], kind="outdated",
                entity_type="document", entity_id="doc-1", title="Outdated runbook",
                detail="Last updated long ago.", confidence=0.9, status="open",
                source="knowledge_worker",
            )
        )
        db.add(
            BurnoutSignal(
                organization_id=org["organization"]["id"], employee_id=me,
                score=72, level="high", signals_json='{"overdue_tasks": "3 overdue tasks"}',
                status="open",
                period_start=datetime.now(timezone.utc) - timedelta(days=14),
                period_end=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    scan = await client.post("/api/v1/insights/risks/scan", headers=headers)
    assert scan.status_code == 200, scan.text
    assert scan.json()["new_risks"] >= 2

    risks = (await client.get("/api/v1/insights/risks", headers=headers)).json()
    assert risks["total"] >= 2
    kinds = {r["kind"] for r in risks["risks"]}
    assert {"knowledge_loss", "overload"} <= kinds
    overload = next(r for r in risks["risks"] if r["kind"] == "overload")
    assert overload["level"] == "high"  # severity-aware scoring

    # idempotent: a second scan must not duplicate open risks
    scan2 = (await client.post("/api/v1/insights/risks/scan", headers=headers)).json()
    assert scan2["new_risks"] == 0

    # the scan published a risk.detected background event (audit stream)
    events = (await client.get("/api/v1/intelligence/events", headers=headers)).json()
    assert any(e["name"] == "risk.detected" for e in events)


# =================================================================== autonomous notifications (Phase 9.14)

@pytest.mark.asyncio
async def test_notification_engine_generates_and_dedupes_alerts(client, db_session_factory):
    org = await register_org(client, email="p9notif@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    from datetime import datetime, timezone

    from app.models.intelligence import BurnoutSignal
    from sqlalchemy import select

    async with db_session_factory() as db:
        db.add(
            BurnoutSignal(
                organization_id=org["organization"]["id"], employee_id=me,
                score=72, level="high", signals_json='{"overdue_tasks": "3 overdue tasks"}',
                status="open",
                period_start=datetime.now(timezone.utc) - timedelta(days=14),
                period_end=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    # create a high overload risk first so risk alerts have something to say
    scan = await client.post("/api/v1/insights/risks/scan", headers=headers)
    assert scan.status_code == 200, scan.text
    assert scan.json()["new_risks"] >= 1

    gen = await client.post("/api/v1/insights/notifications/generate", headers=headers)
    assert gen.status_code == 200, gen.text
    assert gen.json()["generated"] >= 1

    # 24h dedup window: regenerating must not create duplicates
    gen2 = (await client.post("/api/v1/insights/notifications/generate", headers=headers)).json()
    assert gen2["generated"] == 0

    notifications = (await client.get("/api/v1/insights/notifications", headers=headers)).json()
    types = {n["type"] for n in notifications}
    assert "risk" in types and "burnout" in types
    assert all(n["priority"] in ("high", "urgent", "normal") for n in notifications)


# =================================================================== background audit events from engines

@pytest.mark.asyncio
async def test_engines_emit_background_audit_events(client):
    org = await register_org(client, email="p9bgevent@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    _, task_id = await _seed_project_task(client, headers, code="P9-BGE")

    skill = await client.post(
        "/api/v1/expertise/skills",
        json={"name": "Project Management", "category": "Leadership"},
        headers=headers,
    )
    assigned = await client.post(
        f"/api/v1/employees/{me}/skills",
        json={"skill_id": skill.json()["id"], "proficiency": "expert"},
        headers=headers,
    )
    assert assigned.status_code == 201, assigned.text
    completed = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        json={"status": "completed"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text

    for _ in range(5):
        response = (await client.post("/api/v1/intelligence/events/process", headers=headers)).json()
        if response["processed"] == 0:
            break

    events = (await client.get("/api/v1/intelligence/events", headers=headers)).json()
    names = {e["name"] for e in events}
    assert "expertise.updated" in names, "expertise engine must emit expertise.updated"
    assert "graph.updated" in names, "graph engine must emit graph.updated"
    assert "learning.recorded" in names, "learning engine must emit learning.recorded"


# =================================================================== scheduler package (Phase 9.16)

@pytest.mark.asyncio
async def test_scheduler_package_tiers_cover_registry():
    from app.scheduler import DAILY_JOBS, HOURLY_JOBS, RECURRING_JOBS, WEEKLY_JOBS, interval_for
    from app.workers.scheduler import WORKER_REGISTRY

    registry_names = {name for name, _ in WORKER_REGISTRY}
    tier_names = set(HOURLY_JOBS) | set(DAILY_JOBS) | set(WEEKLY_JOBS)
    assert tier_names == registry_names, "tier modules must cover the registry exactly"
    assert len(RECURRING_JOBS) == len(WORKER_REGISTRY)
    for job in RECURRING_JOBS:
        assert job["tier"] in ("hourly", "daily", "weekly")
        assert interval_for(job["name"]) == job["interval_seconds"]
    # every tier worker module must expose the run_once contract
    import asyncio
    import importlib

    for name in registry_names:
        module = importlib.import_module(f"app.workers.{name}_worker")
        assert asyncio.iscoroutinefunction(module.run_once), f"{name}_worker missing run_once"
        if name in {"event", "graph_updates", "search_insight", "knowledge_intel",
                    "collab_intel", "burnout", "expertise_evolve", "workflow_intel",
                    "pattern", "learning", "insights", "recommendation_feed",
                    "risk", "notification"}:
            assert asyncio.iscoroutinefunction(module.run_forever), f"{name}_worker missing run_forever"


# =================================================================== spec-path routers (Phase 9.1)

@pytest.mark.asyncio
async def test_recommendations_router_personal_feed(client):
    org = await register_org(client, email="p9recrt@work.test.co")
    headers = org["headers"]
    await _seed_project_task(client, headers, code="P9-RECRT")

    refreshed = await client.post("/api/v1/recommendations/refresh", headers=headers)
    assert refreshed.status_code == 200, refreshed.text

    feed = (await client.get("/api/v1/recommendations", headers=headers)).json()
    assert isinstance(feed, list)
    assert all("id" in item and "kind" in item for item in feed)


@pytest.mark.asyncio
async def test_insights_router_feed_risks_notifications(client, db_session_factory):
    org = await register_org(client, email="p9insight@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    from datetime import datetime, timezone

    from app.models.intelligence import BurnoutSignal

    async with db_session_factory() as db:
        db.add(
            BurnoutSignal(
                organization_id=org["organization"]["id"], employee_id=me,
                score=70, level="elevated", signals_json='{"meeting_load": "8 meetings"}',
                status="open",
                period_start=datetime.now(timezone.utc) - timedelta(days=14),
                period_end=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    feed = await client.get("/api/v1/insights", headers=headers)
    assert feed.status_code == 200, feed.text
    data = feed.json()
    for key in ("risks", "knowledge", "burnout", "duplicates", "patterns", "workflow", "search", "counts"):
        assert key in data, f"missing {key} in insights feed"

    risks = await client.get("/api/v1/insights/risks", headers=headers)
    assert risks.status_code == 200
    assert "total" in risks.json()

    notifications = await client.get("/api/v1/insights/notifications", headers=headers)
    assert notifications.status_code == 200
    assert isinstance(notifications.json(), list)

    scan = await client.post("/api/v1/insights/risks/scan", headers=headers)
    assert scan.status_code == 200, scan.text
    assert scan.json()["new_risks"] >= 1


@pytest.mark.asyncio
async def test_insights_rbac_employee_denied(client):
    org = await register_org(client, email="p9insrbac@work.test.co")
    headers = org["headers"]
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "worker2@rbac.test.co", "full_name": "Emp Two", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Two", "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    employee_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    denied = await client.get("/api/v1/insights", headers=employee_headers)
    assert denied.status_code == 403
    denied_scan = await client.post("/api/v1/insights/risks/scan", headers=employee_headers)
    assert denied_scan.status_code == 403
    denied_risks = await client.get("/api/v1/insights/risks", headers=employee_headers)
    assert denied_risks.status_code == 403
    # personal recommendation feed stays open to every employee
    feed = await client.get("/api/v1/recommendations", headers=employee_headers)
    assert feed.status_code == 200


@pytest.mark.asyncio
async def test_risk_and_notification_workers_run_on_demand(client, db_session_factory, monkeypatch):
    org = await register_org(client, email="p9wrk@work.test.co")
    headers = org["headers"]

    from app.workers import notification_worker, risk_worker

    monkeypatch.setattr(risk_worker, "SessionLocal", db_session_factory)
    monkeypatch.setattr(notification_worker, "SessionLocal", db_session_factory)

    risk_run = await client.post("/api/v1/intelligence/workers/risk/run", headers=headers)
    assert risk_run.status_code == 200, risk_run.text
    assert "processed" in risk_run.json()

    notif_run = await client.post("/api/v1/intelligence/workers/notification/run", headers=headers)
    assert notif_run.status_code == 200, notif_run.text
    assert "processed" in notif_run.json()

    # both workers now appear in the on-demand worker list
    workers = (await client.get("/api/v1/intelligence/workers", headers=headers)).json()
    names = {w["name"] for w in workers}
    assert {"risk", "notification"} <= names
