"""Slice 4G.1 — the Execution surfaces: command_center, execution_next and
the universal query routing (with honest fallbacks).

* command_center: every active project's execution state, counts and last
  change (from snapshot history), sorted by health,
* execution_next: unresolved decisions first, then critical-path pressure,
  blocked work on the path, overdue milestones, then ready high priority,
* the universal knowledge query routes execution questions deterministically
  and falls back to the pre-existing surfaces when there is no execution
  record to answer with.
"""

from datetime import date, timedelta

from app.intelligence.execution_engine import execution_engine
from app.models.knowledge import Decision
from app.models.task import Task, TaskDependency
from tests.conftest import register_org

BRAIN = "/api/v1/brain"


async def _drain(db_session_factory, limit=200, rounds=4):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _published(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"gs-{name.lower().replace(' ', '-')[:20]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _drained_project(client, headers, db_session_factory, name):
    project = await _project(client, headers, name)
    await _drain(db_session_factory)
    return project


async def _task(db, org_id, project_id, title, *, status="backlog",
                priority="medium", estimate_hours=None, due_date=None,
                decision_id=None):
    task = Task(
        organization_id=org_id, project_id=project_id, title=title,
        status=status, priority=priority, estimate_hours=estimate_hours,
        due_date=due_date, decision_id=decision_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _decision(db, org_id, project_id, slug, title="Pick a vendor"):
    decision = Decision(
        organization_id=org_id, title=title,
        slug=f"{slug}-{org_id[:8]}", status="proposed",
        project_id=project_id,
    )
    db.add(decision)
    await db.flush()
    return decision


def _row(body, name):
    return next(r for r in body["projects"] if r["name"] == name)


# -------------------------------------------------------------- command center


async def test_command_center_counts_sort_and_last_change(client, db_session_factory):
    org = await register_org(client, email="4g1_s1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    quiet = await _drained_project(client, headers, db_session_factory, "Quiet One")
    loud = await _drained_project(client, headers, db_session_factory, "Loud One")

    async with db_session_factory() as db:
        root = await _task(db, org_id, loud["id"], "Bottleneck", status="todo")
        leaf = await _task(db, org_id, loud["id"], "Stuck leaf", status="blocked")
        db.add(TaskDependency(organization_id=org_id, task_id=leaf.id,
                              depends_on_task_id=root.id, kind="blocking"))
        await db.commit()
        leaf_id = leaf.id
    await _published(
        db_session_factory, org_id, org["user"]["id"], "task.blocked",
        {"task_id": leaf_id, "project_id": loud["id"], "status": "blocked"},
    )

    async with db_session_factory() as db:
        body = await execution_engine.command_center(db, organization_id=org_id)
    assert body["total_projects"] == 2
    assert body["counts"]["active_projects"] == 2
    assert body["counts"]["blocked_projects"] == 1
    assert _row(body, "Quiet One")["health_status"] == "healthy"
    assert _row(body, "Loud One")["health_status"] != "healthy"
    assert body["projects"][0]["name"] == "Loud One"
    assert _row(body, "Quiet One")["last_change"] == "project.created"
    assert "task.blocked" in _row(body, "Loud One")["last_change"]


async def test_command_center_over_api(client, db_session_factory):
    org = await register_org(client, email="4g1_s2@test.co")
    headers = org["headers"]
    project = await _drained_project(
        client, headers, db_session_factory, "API Center")

    res = await client.get(f"{BRAIN}/execution/command", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_projects"] == 1
    row = body["projects"][0]
    assert row["project_id"] == project["id"]
    assert row["health_status"] == "healthy"
    assert "last_event_at" in row
    assert "explain" in row


# -------------------------------------------------------------- execution next


async def test_next_prioritizes_open_decisions_first(client, db_session_factory):
    org = await register_org(client, email="4g1_s3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Gated")

    async with db_session_factory() as db:
        decision = await _decision(db, org_id, project["id"], "4g1-vend")
        action = await _task(db, org_id, project["id"], "Evaluate vendor",
                             status="todo", decision_id=decision.id)
        await db.commit()
        decision_id = action.decision_id
    await _published(
        db_session_factory, org_id, org["user"]["id"], "decision.made",
        {"decision_id": decision_id, "project_id": project["id"]},
    )

    async with db_session_factory() as db:
        body = await execution_engine.execution_next(db, organization_id=org_id)
    assert body["total"] >= 1
    assert body["items"][0]["kind"] == "decision"
    assert "Resolve decision" in body["items"][0]["title"]


async def test_next_promotes_critical_path_pressure(client, db_session_factory):
    org = await register_org(client, email="4g1_s4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Crunch")

    yesterday = date.today() - timedelta(days=1)
    async with db_session_factory() as db:
        a = await _task(db, org_id, project["id"], "A", estimate_hours=4)
        b = await _task(db, org_id, project["id"], "B", estimate_hours=2,
                        due_date=yesterday)
        db.add(TaskDependency(organization_id=org_id, task_id=b.id,
                              depends_on_task_id=a.id, kind="finish_to_start"))
        await db.commit()
        b_id = b.id
    await _published(
        db_session_factory, org_id, org["user"]["id"], "task.transitioned",
        {"task_id": b_id, "project_id": project["id"], "status": "todo"},
    )

    async with db_session_factory() as db:
        body = await execution_engine.execution_next(db, organization_id=org_id)
    assert body["total"] >= 1
    assert body["items"][0]["kind"] == "critical"
    assert "critical path" in body["items"][0]["title"]
    assert body["items"][0]["project_name"] == "Crunch"


async def test_next_over_api_is_bounded(client, db_session_factory):
    org = await register_org(client, email="4g1_s5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Next API")

    async with db_session_factory() as db:
        for i in range(30):
            await _task(db, org_id, project["id"], f"Ready {i}",
                        status="todo", priority="high", estimate_hours=1)
        await db.commit()
    await _published(
        db_session_factory, org_id, org["user"]["id"], "task.created",
        {"task_id": "x", "project_id": project["id"], "status": "todo"},
    )

    res = await client.get(f"{BRAIN}/execution/next", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert 1 <= body["total"] <= 20


# ------------------------------------------------------------- query routing


async def test_query_routes_execution_questions(client, db_session_factory):
    org = await register_org(client, email="4g1_s6@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _drained_project(client, headers, db_session_factory, "Aurora")

    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": "is the Aurora project on track?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent"] == "execution"
    assert body["project"]["name"] == "Aurora"
    assert body["project"]["health_status"] == "healthy"


async def test_query_blocked_and_overdue_upgrades(client, db_session_factory):
    org = await register_org(client, email="4g1_s7@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Gated Q")

    async with db_session_factory() as db:
        decision = await _decision(db, org_id, project["id"], "4g1-dq", "Gate it")
        await _task(db, org_id, project["id"], "Action item", status="todo",
                    decision_id=decision.id)
        await db.commit()
        decision_id = decision.id
    await _published(
        db_session_factory, org_id, org["user"]["id"], "decision.made",
        {"decision_id": decision_id, "project_id": project["id"]},
    )

    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": "what should we do next?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent"] == "execution_next"
    assert body["total"] >= 1
    assert body["items"][0]["kind"] == "decision"


async def test_query_falls_back_honestly(client, db_session_factory):
    org = await register_org(client, email="4g1_s8@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _drained_project(client, headers, db_session_factory, "Clean Slate")

    async with db_session_factory() as db:
        for i in range(3):
            await _task(db, org_id, org_id, f"Wander {i}", status="todo")
        await db.commit()

    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": "what is blocked?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent"] == "blocked"

    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": "what should we do next?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["intent"] == "next"