"""Slice 4D.3 — memory context snapshots and governance-scope inheritance.

Proves the context collection contract:

* a formed memory carries a bounded ``context_json`` snapshot of its evidence
  (project, task, assignee, dependencies, decisions, discussion),
* collectors are hard-capped — a flood of comments can never blow up a memory,
* governance scope is inherited from the project that owns the evidence:
  a project inside a governance scope produces project-scoped memory, a
  project without a scope node produces organization-wide memory.
"""

from sqlalchemy import select

from app.models.company_memory import CompanyMemory
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Context Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "context snapshot test", "status": "active"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _task(client, headers, project_id, title, assignee_id=None, status="in_progress"):
    body = {"title": title, "project_id": project_id, "status": status}
    if assignee_id:
        body["assignee_id"] = assignee_id
    response = await client.post("/api/v1/tasks", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(client, headers, task_id, status):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"status": status}, headers=headers
    )
    assert response.status_code == 200, response.text


async def _block(client, headers, task_id, blocker_id):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": blocker_id, "kind": "finish_to_start"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def _comment(client, headers, task_id, body):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.text


async def _drain_events(db_session_factory):
    from app.events.event_bus import event_bus

    for _ in range(10):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=200)
            await session.commit()
        if processed == 0:
            break


async def _run_formation(db_session_factory):
    for _ in range(8):
        async with db_session_factory() as session:
            processed = await memory_formation_worker.run_once(db=session, limit=50)
            await session.commit()
        if processed == 0:
            break


async def _blocked_memory(db, organization_id):
    rows = (
        await db.execute(
            select(CompanyMemory).where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.memory_category == "experience",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    return rows[0]


# ------------------------------------------------------ 1. context snapshots


async def test_context_snapshot_captures_task_project_assignee_and_dependency(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_ctx@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()
    project = await _project(client, headers, "Billing Automation")
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(
        client, headers, project["id"], "Set up billing sync", assignee_id=me["id"]
    )
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        memory = await _blocked_memory(db, org_id)
        ctx = memory.context_json or {}
        assert ctx["project"]["title"] == "Billing Automation"
        assert ctx["project"]["id"] == project["id"]
        assert ctx["task"]["title"] == "Set up billing sync"
        assert ctx["task"]["status"] == "blocked"
        assert ctx["task"]["priority"] == "medium"
        assert ctx["assignee"]["id"] == me["id"]
        assert ctx["dependencies"] and ctx["dependencies"][0]["task_id"] == dependent["id"]
        assert ctx["dependencies"][0]["depends_on_task_id"] == blocker["id"]
        assert ctx["dependencies"][0]["kind"] == "finish_to_start"


async def test_comment_flood_is_capped_in_context(client, db_session_factory):
    org = await register_org(client, email="m4d3_cap@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Capped discussion task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    for index in range(8):
        await _comment(client, headers, dependent["id"], f"Comment number {index}")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        memory = await _blocked_memory(db, org_id)
        discussion = (memory.context_json or {}).get("discussion", [])
        assert len(discussion) <= 3  # snapshot is bounded, never the full flood


# ------------------------------------------------- 2. governance-scope inheritance


async def test_project_scope_inheritance_from_governance_scope(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_scope@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    project = await _project(client, headers, "Scoped Rollout")
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Rollout Scope", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Scoped blocked task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        memory = await _blocked_memory(db, org_id)
        assert memory.auth_scope == "project"
        assert memory.auth_project_id == project["id"]
        assert memory.auth_scope_id == scope["id"]


async def test_unscoped_project_forms_org_wide_memory(client, db_session_factory):
    org = await register_org(client, email="m4d3_orgwide@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers, "No Scope Here")
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Open project task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        memory = await _blocked_memory(db, org_id)
        assert memory.auth_scope == "org"
        assert memory.auth_project_id is None
