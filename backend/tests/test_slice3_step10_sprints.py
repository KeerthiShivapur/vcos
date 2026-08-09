"""Vertical Slice 3 — Step 10 project/sprint/roadmap execution tests.

Sprints must behave like an execution engine: guarded start/complete, progress
rolled up from real task work, unfinished work returned to the backlog on
completion, timeline entries, and safe deletion rules for projects, roadmaps,
epics and milestones.
"""

import pytest
from sqlalchemy import select

from app.models.notification import Event as WorkEvent
from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _project(client, headers, **extra):
    r = await client.post("/api/v1/projects", json={"name": "P", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _sprint(client, headers, **extra):
    r = await client.post("/api/v1/sprints", json={"name": "S1", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _task(client, headers, **extra):
    r = await client.post("/api/v1/tasks", json={"title": "T", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _events(db, organization_id, name):
    return (
        await db.execute(
            select(WorkEvent).where(
                WorkEvent.organization_id == organization_id, WorkEvent.name == name
            )
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_sprint_lifecycle_guards(client, db_session_factory):
    org = await register_org(client, email="s10a1@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"])

    r = await client.post(f"/api/v1/sprints/{s['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, "a planned sprint may be completed directly"
    assert r.json()["status"] == "completed"

    r = await client.post(f"/api/v1/sprints/{s['id']}/start", headers=org["headers"])
    assert r.status_code == 400, "a completed sprint cannot be started"

    s2 = await _sprint(client, org["headers"], project_id=p["id"])
    r = await client.post(f"/api/v1/sprints/{s2['id']}/start", headers=org["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = await client.post(f"/api/v1/sprints/{s2['id']}/start", headers=org["headers"])
    assert r.status_code == 400, "an active sprint cannot be started twice"

    r = await client.patch(f"/api/v1/sprints/{s2['id']}", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 400, "sprint status must change through start/complete endpoints"

    r = await client.patch(f"/api/v1/sprints/{s2['id']}", json={"name": "Renamed"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_sprint_progress_rolls_up_from_tasks(client, db_session_factory):
    org = await register_org(client, email="s10a2@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"])
    a = await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"])
    b = await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"])

    r = await client.get(f"/api/v1/sprints/{s['id']}", headers=org["headers"])
    assert r.json()["progress"] == 0
    assert r.json()["tasks_count"] == 2
    assert r.json()["completed_tasks"] == 0

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/sprints/{s['id']}", headers=org["headers"])
    assert r.json()["progress"] == 50, "one of two sprint tasks complete"
    assert r.json()["completed_tasks"] == 1

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/sprints/{s['id']}", headers=org["headers"])
    assert r.json()["progress"] == 100

    listed = (await client.get(f"/api/v1/sprints?project_id={p['id']}", headers=org["headers"])).json()
    assert listed[0]["progress"] == 100


@pytest.mark.asyncio
async def test_sprint_complete_reconciles_unfinished_tasks(client, db_session_factory):
    from sqlalchemy import select as sa_select

    from app.models.project import Sprint
    from app.models.task import Task

    org = await register_org(client, email="s10a3@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"], goal="Ship the pilot")
    done = await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"])
    carry = await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"])

    await client.post(f"/api/v1/sprints/{s['id']}/start", headers=org["headers"])
    await client.post(f"/api/v1/tasks/{done['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    r = await client.post(f"/api/v1/sprints/{s['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["progress"] == 50
    assert r.json()["completed_at"] is not None

    r = await client.post(f"/api/v1/sprints/{s['id']}/complete", headers=org["headers"])
    assert r.status_code == 400, "double completion must be refused"

    async with db_session_factory() as db:
        rows = (await db.execute(
            sa_select(Task.id, Task.sprint_id).where(
                Task.organization_id == org["organization"]["id"],
                Task.id.in_([done["id"], carry["id"]]),
            )
        )).all()
        by_id = {r_id: sprint_id for r_id, sprint_id in rows}
        assert by_id[done["id"]] == s["id"], "completed task keeps its sprint history"
        assert by_id[carry["id"]] is None, "unfinished task returns to the backlog"
        completed = (await db.execute(
            sa_select(Sprint).where(Sprint.id == s["id"])
        )).scalar_one()
        assert completed.status == "completed"
        assert completed.progress == 50

    timeline = (await client.get(f"/api/v1/projects/{p['id']}/timeline", headers=org["headers"])).json()
    kinds = [t["kind"] for t in timeline]
    assert "sprint.started" in kinds
    assert "sprint.completed" in kinds
    started = next(t for t in timeline if t["kind"] == "sprint.started")
    assert "S1" in started["title"]


@pytest.mark.asyncio
async def test_project_delete_rules(client, db_session_factory):
    org = await register_org(client, email="s10a4@test.co")
    active = await _project(client, org["headers"])
    await client.post(f"/api/v1/projects/{active['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])

    r = await client.delete(f"/api/v1/projects/{active['id']}", headers=org["headers"])
    assert r.status_code == 400, "an active project cannot be deleted"

    await client.post(f"/api/v1/projects/{active['id']}/lifecycle", json={"action": "cancel"}, headers=org["headers"])
    r = await client.delete(f"/api/v1/projects/{active['id']}", headers=org["headers"])
    assert r.status_code == 400, "a cancelled project must be archived before deletion"

    await client.post(f"/api/v1/projects/{active['id']}/lifecycle", json={"action": "archive"}, headers=org["headers"])
    r = await client.delete(f"/api/v1/projects/{active['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    draft = await _project(client, org["headers"], status="draft")
    r = await client.delete(f"/api/v1/projects/{draft['id']}", headers=org["headers"])
    assert r.status_code == 200, "a draft project can be deleted"


@pytest.mark.asyncio
async def test_archived_project_cannot_be_edited(client, db_session_factory):
    org = await register_org(client, email="s10a5@test.co")
    p = await _project(client, org["headers"])
    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "complete"}, headers=org["headers"])
    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "archive"}, headers=org["headers"])

    r = await client.patch(f"/api/v1/projects/{p['id']}", json={"name": "Hijacked"}, headers=org["headers"])
    assert r.status_code == 400, "an archived project is read-only"

    r = await client.get(f"/api/v1/projects/{p['id']}", headers=org["headers"])
    assert r.json()["name"] == "P"


@pytest.mark.asyncio
async def test_roadmap_delete_guard(client, db_session_factory):
    org = await register_org(client, email="s10a6@test.co")
    roadmap = (await client.post("/api/v1/roadmaps", json={"name": "R1"}, headers=org["headers"])).json()
    p = await _project(client, org["headers"], roadmap_id=roadmap["id"])

    r = await client.delete(f"/api/v1/roadmaps/{roadmap['id']}", headers=org["headers"])
    assert r.status_code == 400, "roadmap with linked projects cannot be deleted"
    assert "linked project" in r.json()["detail"]

    await client.patch(f"/api/v1/projects/{p['id']}", json={"roadmap_id": None}, headers=org["headers"])
    r = await client.delete(f"/api/v1/roadmaps/{roadmap['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_epic_lifecycle_and_delete_guard(client, db_session_factory):
    org = await register_org(client, email="s10a7@test.co")
    p = await _project(client, org["headers"])
    epic = (await client.post("/api/v1/epics", json={"name": "E1", "project_id": p["id"]}, headers=org["headers"])).json()
    task = await _task(client, org["headers"], project_id=p["id"], epic_id=epic["id"])

    r = await client.post(f"/api/v1/epics/{epic['id']}/start", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = await client.post(f"/api/v1/epics/{epic['id']}/start", headers=org["headers"])
    assert r.status_code == 400, "an in-progress epic cannot be started again"

    r = await client.patch(f"/api/v1/epics/{epic['id']}", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 400, "epic status must change through start/complete endpoints"

    r = await client.delete(f"/api/v1/epics/{epic['id']}", headers=org["headers"])
    assert r.status_code == 400, "epic with tasks cannot be deleted"

    await client.delete(f"/api/v1/tasks/{task['id']}", headers=org["headers"])
    r = await client.post(f"/api/v1/epics/{epic['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    r = await client.delete(f"/api/v1/epics/{epic['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "epic.started")
        assert await _events(db, org["organization"]["id"], "epic.completed")


@pytest.mark.asyncio
async def test_milestone_guards(client, db_session_factory):
    org = await register_org(client, email="s10a8@test.co")
    p = await _project(client, org["headers"])
    m = (await client.post("/api/v1/milestones", json={"name": "M1", "project_id": p["id"]}, headers=org["headers"])).json()
    task = await _task(client, org["headers"], project_id=p["id"], milestone_id=m["id"])

    r = await client.delete(f"/api/v1/milestones/{m['id']}", headers=org["headers"])
    assert r.status_code == 400, "milestone with tasks cannot be deleted"

    r = await client.post(f"/api/v1/milestones/{m['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["progress"] == 100

    r = await client.post(f"/api/v1/milestones/{m['id']}/complete", headers=org["headers"])
    assert r.status_code == 400, "double completion must be refused"

    r = await client.patch(f"/api/v1/milestones/{m['id']}", json={"due_date": "2026-12-31"}, headers=org["headers"])
    assert r.status_code == 400, "a completed milestone is read-only"

    r = await client.patch(f"/api/v1/milestones/{m['id']}", json={"status": "pending"}, headers=org["headers"])
    assert r.status_code == 400, "milestone status must change through the complete endpoint"


@pytest.mark.asyncio
async def test_sprint_delete_detaches_tasks(client, db_session_factory):
    from sqlalchemy import select as sa_select

    from app.models.task import Task

    org = await register_org(client, email="s10a9@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"])
    await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"])

    await client.post(f"/api/v1/sprints/{s['id']}/start", headers=org["headers"])
    r = await client.delete(f"/api/v1/sprints/{s['id']}", headers=org["headers"])
    assert r.status_code == 400, "an active sprint cannot be deleted"

    s2 = await _sprint(client, org["headers"], project_id=p["id"])
    await _task(client, org["headers"], project_id=p["id"], sprint_id=s2["id"])
    r = await client.delete(f"/api/v1/sprints/{s2['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text

    async with db_session_factory() as db:
        detached = (await db.execute(
            sa_select(Task.id).where(
                Task.organization_id == org["organization"]["id"],
                Task.sprint_id == s2["id"],
            )
        )).scalars().all()
        assert detached == [], "deleting a sprint detaches its tasks back to the backlog"


@pytest.mark.asyncio
async def test_task_sprint_filter(client, db_session_factory):
    org = await register_org(client, email="s10a10@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"])
    other = await _sprint(client, org["headers"], project_id=p["id"])
    a = await _task(client, org["headers"], project_id=p["id"], sprint_id=s["id"], title="In sprint")
    await _task(client, org["headers"], project_id=p["id"], sprint_id=other["id"], title="Other sprint")

    r = await client.get(f"/api/v1/tasks?sprint_id={s['id']}", headers=org["headers"])
    titles = [t["title"] for t in r.json()]
    assert titles == ["In sprint"]


async def _notifications(db, organization_id, type):
    from app.models.notification import Notification

    return (
        await db.execute(
            select(Notification).where(
                Notification.organization_id == organization_id, Notification.type == type
            )
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_sprint_events_notifications_and_catalog(client, db_session_factory):
    from app.events.event_models import EVENT_CATALOG
    from app.services.audit_service import audit_service

    org = await register_org(client, email="s10a11@test.co")
    p = await _project(client, org["headers"])
    s = await _sprint(client, org["headers"], project_id=p["id"])

    await client.post(f"/api/v1/sprints/{s['id']}/start", headers=org["headers"])
    await client.post(f"/api/v1/sprints/{s['id']}/complete", headers=org["headers"])
    await _process_pending(db_session_factory)

    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "sprint.started")
        assert await _events(db, org["organization"]["id"], "sprint.completed")
        assert await _notifications(db, org["organization"]["id"], "sprint.started")
        assert await _notifications(db, org["organization"]["id"], "sprint.completed")
        audit = await db.execute(
            select(WorkEvent).where(
                WorkEvent.organization_id == org["organization"]["id"],
                WorkEvent.name == "sprint.completed",
            )
        )
        assert audit.scalars().all()

    assert "sprint.started" in EVENT_CATALOG
    assert "sprint.completed" in EVENT_CATALOG
    assert "epic.started" in EVENT_CATALOG
    assert "epic.completed" in EVENT_CATALOG
    names = audit_service.action_names()
    assert "sprint.started" in names and "sprint.completed" in names
    assert "epic.started" in names and "epic.completed" in names
