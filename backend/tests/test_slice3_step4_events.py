"""Vertical Slice 3 — Step 4 work-domain event catalog & handlers regression tests.

Every work lifecycle mutation must produce a catalogued event; the event
worker must react with graph edges / learning lessons; deleted work entities
must not linger in the organization graph.
"""

import json

import pytest
from sqlalchemy import select

from tests.conftest import register_org


async def _event_rows(db, organization_id, name=None):
    from app.models.notification import Event as EventRow

    stmt = select(EventRow).where(EventRow.organization_id == organization_id)
    if name:
        stmt = stmt.where(EventRow.name == name)
    rows = (await db.execute(stmt)).scalars().all()
    return [(r.name, json.loads(r.payload_json or "{}")) for r in rows]


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _active_edges(db, organization_id, entity_type=None, entity_id=None):
    from app.models.intelligence import OrgGraphEdge

    stmt = select(OrgGraphEdge).where(
        OrgGraphEdge.organization_id == organization_id, OrgGraphEdge.active.is_(True)
    )
    if entity_type and entity_id:
        stmt = stmt.where(
            (OrgGraphEdge.source_type == entity_type) & (OrgGraphEdge.source_id == entity_id)
            | (OrgGraphEdge.target_type == entity_type) & (OrgGraphEdge.target_id == entity_id)
        )
    return (await db.execute(stmt)).scalars().all()


async def _learning_rows(db, organization_id, entity_type=None, entity_id=None):
    from app.models.intelligence import LearningEvent

    stmt = select(LearningEvent).where(LearningEvent.organization_id == organization_id)
    if entity_type:
        stmt = stmt.where(LearningEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(LearningEvent.entity_id == entity_id)
    return (await db.execute(stmt)).scalars().all()


async def _create_project(client, headers, name="Core Platform"):
    r = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_task(client, headers, title="Task", **extra):
    r = await client.post("/api/v1/tasks", json={"title": title, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- task lifecycle


@pytest.mark.asyncio
async def test_task_lifecycle_emits_events(client, db_session_factory):
    org = await register_org(client, email="s4a1@test.co")
    task = await _create_task(client, org["headers"], "Lifecycle Task")

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition", json={"status": "in_progress"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    r = await client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "Renamed"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.delete(f"/api/v1/tasks/{task['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        names = {name for name, _ in await _event_rows(db, org["organization"]["id"])}
        assert {"task.created", "task.transitioned", "task.updated", "task.deleted"} <= names

        _, payload = next(
            (n, p) for n, p in await _event_rows(db, org["organization"]["id"], "task.transitioned")
        )
        assert payload["task_id"] == task["id"]


@pytest.mark.asyncio
async def test_task_deleted_cleans_graph(client, db_session_factory):
    org = await register_org(client, email="s4a2@test.co")
    emp = (await client.post(
        "/api/v1/employees", json={"first_name": "Dev", "email": "dev@test.co"}, headers=org["headers"]
    )).json()
    task = await _create_task(client, org["headers"], "Graph Task", assignee_id=emp["id"])

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        assert await _active_edges(db, org["organization"]["id"], "task", task["id"])

    r = await client.delete(f"/api/v1/tasks/{task['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    await _process_pending(db_session_factory)

    async with db_session_factory() as db:
        assert await _active_edges(db, org["organization"]["id"], "task", task["id"]) == []


# --------------------------------------------------------------------------- dependencies


@pytest.mark.asyncio
async def test_dependency_events_feed_learning(client, db_session_factory):
    org = await register_org(client, email="s4a3@test.co")
    a = await _create_task(client, org["headers"], "A")
    b = await _create_task(client, org["headers"], "B")

    r = await client.post(
        f"/api/v1/tasks/{b['id']}/dependencies",
        json={"depends_on_task_id": a["id"], "kind": "finish_to_start"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    dep = r.json()
    r = await client.delete(f"/api/v1/tasks/{b['id']}/dependencies/{dep['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        names = {name for name, _ in await _event_rows(db, org["organization"]["id"])}
        assert {"dependency.added", "dependency.removed"} <= names

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        lessons = await _learning_rows(db, org["organization"]["id"], "task")
        assert any("Dependency added" in x.title for x in lessons)
        assert any("Dependency removed" in x.title for x in lessons)


# --------------------------------------------------------------------------- planning structures


@pytest.mark.asyncio
async def test_sprint_lifecycle_emits_events(client, db_session_factory):
    org = await register_org(client, email="s4a4@test.co")
    project = await _create_project(client, org["headers"], "Sprint Project")

    r = await client.post(
        "/api/v1/sprints", json={"name": "S1", "project_id": project["id"]}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    sprint = r.json()
    r = await client.patch(f"/api/v1/sprints/{sprint['id']}", json={"goal": "Ship it"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/sprints/{sprint['id']}/start", headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/sprints/{sprint['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        rows = await _event_rows(db, org["organization"]["id"])
        names = {name for name, _ in rows}
        assert {"sprint.created", "sprint.updated", "sprint.started", "sprint.completed"} <= names
        _, payload = next(n for n in rows if n[0] == "sprint.completed")
        assert payload["sprint_id"] == sprint["id"]

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        lessons = await _learning_rows(db, org["organization"]["id"], "sprint")
        assert any("Sprint completed" in x.title for x in lessons)
        assert any("Sprint started" in x.title for x in lessons)


@pytest.mark.asyncio
async def test_planning_events_build_graph(client, db_session_factory):
    org = await register_org(client, email="s4a5@test.co")
    project = await _create_project(client, org["headers"], "Planning Graph")
    owner = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()["id"]

    r = await client.post(
        "/api/v1/roadmaps", json={"name": "Q3 Roadmap", "owner_id": owner}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    roadmap = r.json()
    r = await client.post(
        "/api/v1/epics",
        json={"name": "Epic A", "project_id": project["id"], "roadmap_id": roadmap["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    epic = r.json()
    r = await client.post(
        "/api/v1/milestones", json={"name": "M1", "project_id": project["id"]}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    milestone = r.json()
    r = await client.patch(f"/api/v1/milestones/{milestone['id']}", json={"name": "M1 Updated"}, headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        names = {name for name, _ in await _event_rows(db, org["organization"]["id"])}
        assert {"roadmap.created", "epic.created", "milestone.created", "milestone.updated"} <= names

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        assert await _active_edges(db, org["organization"]["id"], "roadmap", roadmap["id"])
        assert await _active_edges(db, org["organization"]["id"], "epic", epic["id"])
        assert await _active_edges(db, org["organization"]["id"], "milestone", milestone["id"])


# --------------------------------------------------------------------------- risk & meetings


@pytest.mark.asyncio
async def test_risk_close_emits_event(client, db_session_factory):
    org = await register_org(client, email="s4a6@test.co")
    r = await client.post(
        "/api/v1/risks",
        json={"title": "Supply risk", "probability": 4, "impact": 4},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    risk = r.json()
    r = await client.post(f"/api/v1/risks/{risk['id']}/close", headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        rows = await _event_rows(db, org["organization"]["id"], "risk.closed")
        assert rows and rows[0][1]["risk_id"] == risk["id"]

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        lessons = await _learning_rows(db, org["organization"]["id"], "risk")
        assert any("Risk closed" in x.title for x in lessons)


@pytest.mark.asyncio
async def test_meeting_updated_emits_event(client, db_session_factory):
    org = await register_org(client, email="s4a7@test.co")
    r = await client.post("/api/v1/meetings", json={"title": "Sync"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    meeting = r.json()
    r = await client.patch(f"/api/v1/meetings/{meeting['id']}", json={"title": "Sync 2"}, headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        rows = await _event_rows(db, org["organization"]["id"], "meeting.updated")
        assert rows and rows[0][1]["meeting_id"] == meeting["id"]


# --------------------------------------------------------------------------- goals


@pytest.mark.asyncio
async def test_goal_completed_emits_event(client, db_session_factory):
    org = await register_org(client, email="s4a8@test.co")
    r = await client.post("/api/v1/goals", json={"name": "OKR-1", "scope": "personal"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    goal = r.json()
    r = await client.post(
        f"/api/v1/goals/{goal['id']}/key-results",
        json={"title": "KR-1", "target": 100, "current": 0},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    kr = r.json()
    r = await client.patch(
        f"/api/v1/goals/{goal['id']}/key-results/{kr['id']}", json={"current": 100}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        rows = await _event_rows(db, org["organization"]["id"], "goal.completed")
        assert rows and rows[0][1]["goal_id"] == goal["id"]


# --------------------------------------------------------------------------- catalog integrity


@pytest.mark.asyncio
async def test_catalog_covers_every_work_event():
    from app.events.event_models import EVENT_CATALOG

    work_events = {
        "project.created", "project.updated", "project.deleted",
        "task.created", "task.updated", "task.completed", "task.blocked",
        "task.deleted", "task.transitioned",
        "dependency.added", "dependency.removed",
        "roadmap.created", "roadmap.updated", "roadmap.deleted",
        "epic.created", "epic.updated", "epic.deleted",
        "milestone.created", "milestone.updated", "milestone.completed", "milestone.deleted",
        "sprint.created", "sprint.updated", "sprint.started", "sprint.completed", "sprint.deleted",
        "meeting.created", "meeting.updated", "meeting.ended", "meeting.completed",
        "goal.created", "goal.updated", "goal.progress_updated", "goal.completed", "goal.deleted",
        "approval.requested", "approval.approved", "approval.rejected", "approval.cancelled",
        "risk.detected", "risk.updated", "risk.closed",
    }
    assert work_events <= set(EVENT_CATALOG)


@pytest.mark.asyncio
async def test_work_events_process_without_failures(client, db_session_factory):
    org = await register_org(client, email="s4a9@test.co")
    project = await _create_project(client, org["headers"], "Reliability")
    task = await _create_task(client, org["headers"], "Reliable Task", project_id=project["id"])
    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition", json={"status": "blocked"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/v1/sprints", json={"name": "SX", "project_id": project["id"]}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text

    await _process_pending(db_session_factory)

    from app.models.intelligence import BackgroundJob

    # Slice 4D.4: transitioned events also enqueue pattern.evaluate jobs;
    # drain the pattern worker so every enqueued job reaches a terminal state.
    from app.workers import pattern_worker

    for _ in range(8):
        async with db_session_factory() as session:
            processed = await pattern_worker.run_once(db=session, limit=50)
            await session.commit()
        if processed == 0:
            break

    # Slice 4D.3: task.blocked also enqueues a memory.formation job; drain the
    # formation worker so every enqueued job reaches a terminal state.
    from app.workers import memory_formation_worker

    for _ in range(8):
        async with db_session_factory() as session:
            processed = await memory_formation_worker.run_once(db=session, limit=50)
            await session.commit()
        if processed == 0:
            break

    async with db_session_factory() as db:
        jobs = (await db.execute(select(BackgroundJob))).scalars().all()
        assert jobs, "events should have been claimed by the worker"
        assert all(j.status == "done" for j in jobs), [j.status for j in jobs]
