"""Vertical Slice 3 — Step 8 project & roadmap management regression tests.

Project and roadmap lifecycle must be explicit and guarded (start/pause/resume/
complete/cancel/archive), progress must roll up from actual task execution, the
portfolio endpoint must expose health signals for every project, and the roadmap
detail must show its epics and linked projects.
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
async def test_project_lifecycle_guards(client, db_session_factory):
    org = await register_org(client, email="s8a1@test.co")
    p = await _project(client, org["headers"], status="draft")

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "bogus"}, headers=org["headers"])
    assert r.status_code == 422, "unrecognized actions must be rejected"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "archive"}, headers=org["headers"])
    assert r.status_code == 400, "archiving an unfinished project must be refused"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "pause"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paused"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "resume"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "complete"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["progress"] == 100
    assert r.json()["health"] in ("healthy", "at_risk", "delayed", "critical")

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    assert r.status_code == 400, "completed project cannot restart"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "archive"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_cancel_then_restart(client, db_session_factory):
    org = await register_org(client, email="s8a2@test.co")
    p = await _project(client, org["headers"])

    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "cancel"}, headers=org["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    r = await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    assert r.status_code == 200, "cancelled project may be restarted"

    r = await client.get(f"/api/v1/projects/{p['id']}/timeline", headers=org["headers"])
    assert r.status_code == 200
    assert len(r.json()) >= 3, "lifecycle actions must be recorded on the timeline"


@pytest.mark.asyncio
async def test_lifecycle_emits_events_and_notifications(client, db_session_factory):
    org = await register_org(client, email="s8a3@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    p = await _project(client, org["headers"])
    await client.post(
        f"/api/v1/projects/{p['id']}/members",
        json={"employee_id": me["id"]}, headers=org["headers"],
    )

    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])
    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "cancel"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "project.started")
        assert await _events(db, org["organization"]["id"], "project.cancelled")
        assert await _notifications(db, org["organization"]["id"], "project.started")
        assert await _notifications(db, org["organization"]["id"], "project.cancelled")


@pytest.mark.asyncio
async def test_completing_tasks_drives_project_progress(client, db_session_factory):
    org = await register_org(client, email="s8a4@test.co")
    p = await _project(client, org["headers"])
    a = await _task(client, org["headers"], project_id=p["id"])
    b = await _task(client, org["headers"], project_id=p["id"])
    await client.post(f"/api/v1/projects/{p['id']}/lifecycle", json={"action": "start"}, headers=org["headers"])

    r = await client.get(f"/api/v1/projects/{p['id']}", headers=org["headers"])
    assert r.json()["progress"] == 0

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/projects/{p['id']}", headers=org["headers"])
    assert r.json()["progress"] == 50, "task completion must roll into project progress"

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/projects/{p['id']}", headers=org["headers"])
    assert r.json()["progress"] == 100


@pytest.mark.asyncio
async def test_milestone_and_epic_progress_rollup(client, db_session_factory):
    org = await register_org(client, email="s8a5@test.co")
    p = await _project(client, org["headers"])
    epic = (
        await client.post(
            "/api/v1/epics", json={"name": "Epic R", "project_id": p["id"]}, headers=org["headers"]
        )
    ).json()
    ms = (
        await client.post(
            "/api/v1/milestones", json={"name": "M1", "project_id": p["id"]}, headers=org["headers"]
        )
    ).json()
    a = await _task(client, org["headers"], project_id=p["id"], epic_id=epic["id"], milestone_id=ms["id"])
    b = await _task(client, org["headers"], project_id=p["id"], epic_id=epic["id"], milestone_id=ms["id"])

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    r = await client.get(f"/api/v1/epics/{epic['id']}", headers=org["headers"])
    assert r.json()["progress"] == 50
    r = await client.get(f"/api/v1/milestones/{ms['id']}", headers=org["headers"])
    assert r.json()["progress"] == 50

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/milestones/{ms['id']}", headers=org["headers"])
    assert r.json()["status"] == "completed", "milestone auto-completes when its tasks finish"
    assert r.json()["progress"] == 100

    await client.post(
        f"/api/v1/milestones/{ms['id']}/complete", headers=org["headers"]
    )
    r = await client.get(f"/api/v1/projects/{p['id']}", headers=org["headers"])
    assert r.json()["progress"] >= 70, "completed milestone must lift project progress"


@pytest.mark.asyncio
async def test_roadmap_lifecycle_and_detail(client, db_session_factory):
    org = await register_org(client, email="s8a6@test.co")
    r = await client.post("/api/v1/roadmaps", json={"name": "H1 2026"}, headers=org["headers"])
    roadmap = r.json()

    r = await client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/lifecycle", json={"action": "complete"}, headers=org["headers"]
    )
    assert r.status_code == 400, "inactive roadmap cannot be completed"

    r = await client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/lifecycle", json={"action": "activate"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    p = await _project(client, org["headers"], roadmap_id=roadmap["id"])
    epic = (
        await client.post("/api/v1/epics", json={"name": "Epic D", "project_id": p["id"]}, headers=org["headers"])
    ).json()

    r = await client.get(f"/api/v1/roadmaps/{roadmap['id']}/detail", headers=org["headers"])
    assert r.status_code == 200
    detail = r.json()
    assert detail["roadmap"]["id"] == roadmap["id"]
    assert any(e["id"] == epic["id"] for e in detail["epics"])
    assert any(x["id"] == p["id"] for x in detail["projects"])

    await client.post(
        f"/api/v1/roadmaps/{roadmap['id']}/lifecycle", json={"action": "complete"}, headers=org["headers"]
    )
    r = await client.get(f"/api/v1/roadmaps/{roadmap['id']}", headers=org["headers"])
    assert r.json()["status"] == "completed"
    assert r.json()["progress"] >= 50


@pytest.mark.asyncio
async def test_roadmap_progress_from_projects(client, db_session_factory):
    org = await register_org(client, email="s8a7@test.co")
    r = await client.post("/api/v1/roadmaps", json={"name": "FY26"}, headers=org["headers"])
    roadmap = r.json()
    p = await _project(client, org["headers"], roadmap_id=roadmap["id"])
    a = await _task(client, org["headers"], project_id=p["id"])
    b = await _task(client, org["headers"], project_id=p["id"])

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    r = await client.get(f"/api/v1/roadmaps/{roadmap['id']}/detail", headers=org["headers"])
    assert r.json()["roadmap"]["progress"] == 50

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/roadmaps/{roadmap['id']}/detail", headers=org["headers"])
    assert r.json()["roadmap"]["progress"] == 100


@pytest.mark.asyncio
async def test_portfolio_exposes_health_signals(client, db_session_factory):
    org = await register_org(client, email="s8a8@test.co")
    p = await _project(client, org["headers"])
    await _task(client, org["headers"], project_id=p["id"], due_date="2020-01-01")
    await _task(client, org["headers"], project_id=p["id"])

    r = await client.get("/api/v1/projects/portfolio", headers=org["headers"])
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list)
    row = next(x for x in rows if x["project_id"] == p["id"])
    assert row["health"] in ("healthy", "watch", "at_risk", "delayed", "critical")
    assert isinstance(row["signals"], list)
    assert row["overdue_tasks"] >= 1
    assert row["tasks_total"] == 2


@pytest.mark.asyncio
async def test_lifecycle_names_in_catalog_and_audit(client, db_session_factory):
    from app.events.event_models import EVENT_CATALOG
    from app.services.audit_service import audit_service

    known = audit_service.action_names()
    for name in (
        "project.started", "project.paused", "project.resumed",
        "project.completed", "project.cancelled", "project.archived",
        "roadmap.started", "roadmap.completed", "roadmap.archived",
    ):
        assert name in EVENT_CATALOG, f"{name} must be documented in the event catalog"
        assert name in known, f"{name} must be a known audit action"
