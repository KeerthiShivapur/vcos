"""Vertical Slice 3 — Step 7 dependency & execution intelligence regression tests.

The dependency graph must govern execution: tasks cannot complete (or start on
hard-blocking links) while dependencies are unsatisfied, blocked tasks unblock
automatically the moment their blockers clear (completion or removal), and the
execution picture — critical path, ready-to-start, overdue, at-risk, stalled,
blocked chains — is derivable from one insights endpoint.
"""

import pytest
from sqlalchemy import func, select

from app.models.notification import Event as WorkEvent
from app.models.task import Task
from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _task(client, headers, **extra):
    r = await client.post("/api/v1/tasks", json={"title": "T", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _dep(client, headers, task_id, depends_on_task_id, kind="finish_to_start"):
    r = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": depends_on_task_id, "kind": kind},
        headers=headers,
    )
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
async def test_dependency_guard_blocks_premature_completion(client, db_session_factory):
    org = await register_org(client, email="s7a1@test.co")
    a = await _task(client, org["headers"], title="Foundations")
    b = await _task(client, org["headers"], title="Built on A")
    await _dep(client, org["headers"], b["id"], a["id"], "finish_to_start")

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 400, r.text
    assert "unsatisfied" in r.json()["detail"].lower()

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "in_progress"}, headers=org["headers"])
    assert r.status_code == 200, r.text

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["progress"] == 100


@pytest.mark.asyncio
async def test_blocking_link_gates_start_and_force_overrides(client, db_session_factory):
    org = await register_org(client, email="s7a2@test.co")
    a = await _task(client, org["headers"], title="Gatekeeper")
    b = await _task(client, org["headers"], title="Start blocked")
    await _dep(client, org["headers"], b["id"], a["id"], "blocking")

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "in_progress"}, headers=org["headers"])
    assert r.status_code == 400, r.text

    r = await client.post(
        f"/api/v1/tasks/{b['id']}/transition", json={"status": "in_progress", "force": True}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 400

    r = await client.post(
        f"/api/v1/tasks/{b['id']}/transition", json={"status": "completed", "force": True}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_completion_unblocks_dependents(client, db_session_factory):
    org = await register_org(client, email="s7a3@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    a = await _task(client, org["headers"], title="Blocking A")
    b = await _task(client, org["headers"], title="Waiting B", assignee_id=me["id"])
    await _dep(client, org["headers"], b["id"], a["id"], "finish_to_start")

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "blocked"}, headers=org["headers"])
    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    r = await client.get(f"/api/v1/tasks/{b['id']}", headers=org["headers"])
    assert r.json()["status"] == "todo", "dependent should auto-unblock when blocker completes"

    async with db_session_factory() as db:
        events = await _events(db, org["organization"]["id"], "task.unblocked")
        assert events, "task.unblocked event must be emitted"
        assert events[0].payload_json and "task_id" in (events[0].payload_json or {})
        assert await _notifications(db, org["organization"]["id"], "task.unblocked")

    r = await client.get("/api/v1/tasks", headers=org["headers"])
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_dependency_removal_unblocks(client, db_session_factory):
    org = await register_org(client, email="s7a4@test.co")
    a = await _task(client, org["headers"], title="Removable")
    b = await _task(client, org["headers"], title="Freed B")
    dep = await _dep(client, org["headers"], b["id"], a["id"], "blocking")

    await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "blocked"}, headers=org["headers"])

    r = await client.delete(f"/api/v1/tasks/{b['id']}/dependencies/{dep['id']}", headers=org["headers"])
    assert r.status_code == 200
    await _process_pending(db_session_factory)

    r = await client.get(f"/api/v1/tasks/{b['id']}", headers=org["headers"])
    assert r.json()["status"] == "todo", "removing the last blocker should unblock"

    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "task.unblocked")


@pytest.mark.asyncio
async def test_dependency_sync_replaces_set(client, db_session_factory):
    org = await register_org(client, email="s7a5@test.co")
    a = await _task(client, org["headers"], title="A")
    b = await _task(client, org["headers"], title="B")
    c = await _task(client, org["headers"], title="C")
    t = await _task(client, org["headers"], title="Target")
    await _dep(client, org["headers"], t["id"], a["id"])
    await _dep(client, org["headers"], t["id"], b["id"])

    r = await client.put(
        f"/api/v1/tasks/{t['id']}/dependencies",
        json=[{"depends_on_task_id": c["id"], "kind": "blocking"}],
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    ids = {d["depends_on_task_id"] for d in r.json()}
    assert ids == {c["id"]}

    r = await client.put(
        f"/api/v1/tasks/{t['id']}/dependencies",
        json=[{"depends_on_task_id": t["id"]}],
        headers=org["headers"],
    )
    assert r.status_code == 400, "cycle via sync must be rejected"


@pytest.mark.asyncio
async def test_critical_path_and_ready_to_start(client, db_session_factory):
    org = await register_org(client, email="s7a6@test.co")
    r = await client.post("/api/v1/projects", json={"name": "CP"}, headers=org["headers"])
    project_id = r.json()["id"]
    a = await _task(client, org["headers"], title="A", project_id=project_id, estimate_hours=4)
    b = await _task(client, org["headers"], title="B", project_id=project_id, estimate_hours=2)
    c = await _task(client, org["headers"], title="C", project_id=project_id, estimate_hours=3)
    d = await _task(client, org["headers"], title="D", project_id=project_id, estimate_hours=5)
    await _dep(client, org["headers"], c["id"], b["id"])
    await _dep(client, org["headers"], b["id"], a["id"])
    await _dep(client, org["headers"], d["id"], a["id"])
    # graph: a->b->c (9h), a->d (9h) — tie on a->d

    r = await client.get(f"/api/v1/execution/insights?project_id={project_id}", headers=org["headers"])
    assert r.status_code == 200, r.text
    insights = r.json()
    assert insights["counts"]["ready_to_start"] == 1
    assert insights["ready_to_start"][0]["task_id"] == a["id"]
    path = insights["critical_path"]
    assert path["task_ids"][0] == a["id"]
    assert path["total_hours"] == 9.0
    assert set(path["task_ids"]) in ({a["id"], d["id"]}, {a["id"], b["id"], c["id"]})

    await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    r = await client.get(f"/api/v1/execution/insights?project_id={project_id}", headers=org["headers"])
    assert any(t["task_id"] == b["id"] for t in r.json()["ready_to_start"])


@pytest.mark.asyncio
async def test_execution_insights_buckets_and_blocked_chains(client, db_session_factory):
    org = await register_org(client, email="s7a7@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    x = await _task(client, org["headers"], title="Root")
    y = await _task(client, org["headers"], title="Mid")
    z = await _task(client, org["headers"], title="Leaf")
    await _dep(client, org["headers"], y["id"], x["id"], "blocking")
    await _dep(client, org["headers"], z["id"], y["id"], "blocking")
    await client.post(f"/api/v1/tasks/{z['id']}/transition", json={"status": "blocked"}, headers=org["headers"])
    await client.post(f"/api/v1/tasks/{y['id']}/transition", json={"status": "blocked"}, headers=org["headers"])

    overdue = await _task(client, org["headers"], title="Late", due_date="2020-01-01")
    await _task(client, org["headers"], title="DueSoon", due_date="2099-01-01")

    r = await client.get("/api/v1/execution/insights", headers=org["headers"])
    assert r.status_code == 200, r.text
    insights = r.json()
    counts = insights["counts"]
    assert counts["overdue"] >= 1
    assert any(t["task_id"] == overdue["id"] for t in insights["overdue"])
    assert counts["blocked"] >= 2
    leaf = next(b for b in insights["blocked"] if b["task_id"] == z["id"])
    assert leaf["deeply_blocked"] is True
    assert leaf["chain_depth"] >= 1
    mid = next(b for b in insights["blocked"] if b["task_id"] == y["id"])
    assert mid["deeply_blocked"] is False


@pytest.mark.asyncio
async def test_task_unblocked_in_catalog(client, db_session_factory):
    from app.events.event_models import EVENT_CATALOG

    assert "task.unblocked" in EVENT_CATALOG
