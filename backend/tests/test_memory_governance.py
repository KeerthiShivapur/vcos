"""Slice 4D.3 — memory governance (visibility law, downward-only scoping).

Proves the memory layer obeys the same governance law as Slice 4D.2:

* organization-wide callers see every memory (org-wide and project-scoped),
* scoped callers see only project-scoped memories inside their visible
  projects — org-wide memories and other projects' memories are absent from
  every surface (feed, search, timeline, get, evidence, related),
* a hidden memory is indistinguishable from a missing one (404, not 403),
* the outcome endpoint needs ``brain:manage`` even for org-wide callers with
  read access,
* tenants never see each other's memories.
"""

from sqlalchemy import select

from app.models.company_memory import CompanyMemory
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Governance Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "governance test", "status": "active"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _task(client, headers, project_id, title):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": project_id, "status": "in_progress"},
        headers=headers,
    )
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


async def _blocked_memory(client, headers, task_id):
    response = await client.get(f"/api/v1/brain/memory/feed", headers=headers)
    assert response.status_code == 200, response.text
    for memory in response.json()["memories"]:
        if memory["entity_type"] == "task" and memory["entity_id"] == task_id:
            return memory
    raise AssertionError(f"no memory found for task {task_id}")


async def _scope_for_project(client, headers, project_id):
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": f"Scope {project_id}", "scope_type": "project", "entity_id": project_id},
            headers=headers,
        )
    ).json()
    return scope


async def _invite_scoped_reader(client, headers, scope_id, email):
    """Invite an employee, scope them to one project scope, drop their
    org-wide assignment, then grant org-wide ``brain:read`` via the existing
    delegation machinery (Slice 4C) so retrieval scoping is governed by their
    scoped assignment alone."""
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")

    invited = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Scoped Reader", "role": "employee"},
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invited.json()["token"], "full_name": "Scoped Reader", "password": "S4DPass123!"},
    )
    assert joined.status_code == 201, joined.text
    scoped_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    user_id = joined.json()["user"]["id"]

    await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": user_id, "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers,
    )
    assignments = (
        await client.get(
            "/api/v1/governance/assignments", params={"user_id": user_id}, headers=headers
        )
    ).json()
    org_wide = next(assignment for assignment in assignments if assignment["scope_id"] is None)
    removed = await client.delete(
        f"/api/v1/governance/assignments/{org_wide['id']}", headers=headers
    )
    assert removed.status_code == 200, removed.text
    delegated = await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "slice 4d.3 scoped memory"},
        headers=headers,
    )
    assert delegated.status_code == 201, delegated.text
    return scoped_headers


async def _feed(client, headers):
    response = await client.get("/api/v1/brain/memory/feed", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["memories"]


# ---------------------------------------------------------------- 1. visibility


async def test_org_wide_caller_sees_all_visible_memories(client, db_session_factory):
    org = await register_org(client, email="m4d3_owner@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    scoped_project = await _project(client, headers, "Scoped Project")
    await _scope_for_project(client, headers, scoped_project["id"])
    open_project = await _project(client, headers, "Open Project")
    for project, title in (
        (scoped_project, "Inside scoped project"),
        (open_project, "Inside open project"),
    ):
        blocker = await _task(client, headers, project["id"], f"Prereq {title}")
        dependent = await _task(client, headers, project["id"], title)
        await _block(client, headers, dependent["id"], blocker["id"])
        await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(CompanyMemory).where(CompanyMemory.organization_id == org_id)
            )
        ).scalars().all()
    assert len(rows) == 2
    scoped_memory = next(row for row in rows if row.auth_scope == "project")
    assert scoped_memory.auth_project_id == scoped_project["id"]

    feed = await _feed(client, headers)
    assert len(feed) == 2  # org-wide caller: both scoped and org memories


async def test_scoped_caller_only_sees_their_project_memories(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_gov@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    visible_project = await _project(client, headers, "Visible Rollout")
    scope = await _scope_for_project(client, headers, visible_project["id"])
    hidden_project = await _project(client, headers, "Hidden Rollout")
    visible_blocker = await _task(client, headers, visible_project["id"], "Prereq V")
    hidden_blocker = await _task(client, headers, hidden_project["id"], "Prereq H")
    visible_task = await _task(client, headers, visible_project["id"], "Visible blocked task")
    hidden_task = await _task(client, headers, hidden_project["id"], "Hidden blocked task")
    await _block(client, headers, visible_task["id"], visible_blocker["id"])
    await _block(client, headers, hidden_task["id"], hidden_blocker["id"])
    await _transition(client, headers, visible_task["id"], "blocked")
    await _transition(client, headers, hidden_task["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(CompanyMemory).where(CompanyMemory.organization_id == org_id)
            )
        ).scalars().all()
    visible_memory = next(row for row in rows if row.entity_id == visible_task["id"])
    hidden_memory = next(row for row in rows if row.entity_id == hidden_task["id"])
    # Only the visible project is inside a governance scope; the hidden
    # project's memory is organization-wide (invisible downward).
    assert visible_memory.auth_scope == "project"
    assert hidden_memory.auth_scope == "org"

    scoped_headers = await _invite_scoped_reader(
        client, headers, scope["id"], "m4d3_gov_u@test.co"
    )

    feed = await _feed(client, scoped_headers)
    visible_ids = {memory["id"] for memory in feed}
    assert visible_memory.id in visible_ids
    assert hidden_memory.id not in visible_ids

    shown = await client.get(
        f"/api/v1/brain/memory/{visible_memory.id}", headers=scoped_headers
    )
    assert shown.status_code == 200
    hidden = await client.get(
        f"/api/v1/brain/memory/{hidden_memory.id}", headers=scoped_headers
    )
    assert hidden.status_code == 404  # hidden is indistinguishable from missing

    hidden_evidence = await client.get(
        f"/api/v1/brain/memory/{hidden_memory.id}/evidence", headers=scoped_headers
    )
    assert hidden_evidence.status_code == 404
    hidden_related = await client.get(
        f"/api/v1/brain/memory/{hidden_memory.id}/related", headers=scoped_headers
    )
    assert hidden_related.status_code == 404

    search = await client.post(
        "/api/v1/brain/memory/search",
        json={"question": "task was blocked during execution in project"},
        headers=scoped_headers,
    )
    assert search.status_code == 200, search.text
    search_ids = {memory["id"] for memory in search.json()["memories"]}
    assert visible_memory.id in search_ids
    assert hidden_memory.id not in search_ids

    timeline = await client.get("/api/v1/brain/memory/timeline", headers=scoped_headers)
    assert timeline.status_code == 200
    episode_ids = {episode["id"] for episode in timeline.json()["episodes"]}
    assert visible_memory.id in episode_ids
    assert hidden_memory.id not in episode_ids


async def test_scoped_caller_cannot_record_outcome(client, db_session_factory):
    org = await register_org(client, email="m4d3_perm@test.co")
    headers = org["headers"]
    project = await _project(client, headers, "Permission Project")
    scope = await _scope_for_project(client, headers, project["id"])
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Permission task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)
    visible = await _blocked_memory(client, headers, dependent["id"])

    scoped_headers = await _invite_scoped_reader(
        client, headers, scope["id"], "m4d3_perm_u@test.co"
    )
    forbidden = await client.post(
        f"/api/v1/brain/memory/{visible['id']}/outcome",
        json={"outcome_type": "positive", "outcome": "nope"},
        headers=scoped_headers,
    )
    assert forbidden.status_code == 403  # brain:manage required, read is not enough


# ------------------------------------------------------------------ 2. tenants


async def test_tenants_never_see_each_others_memories(client, db_session_factory):
    org_a = await register_org(client, email="m4d3_tenant_a@test.co")
    headers_a = org_a["headers"]
    project = await _project(client, headers_a, "Tenant A Project")
    blocker = await _task(client, headers_a, project["id"], "Prereq task")
    dependent = await _task(client, headers_a, project["id"], "Tenant A task")
    await _block(client, headers_a, dependent["id"], blocker["id"])
    await _transition(client, headers_a, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    org_b = await register_org(client, email="m4d3_tenant_b@test.co")
    headers_b = org_b["headers"]
    assert await _feed(client, headers_b) == []

    search = await client.post(
        "/api/v1/brain/memory/search",
        json={"question": "task was blocked during execution in project"},
        headers=headers_b,
    )
    assert search.status_code == 200
    assert search.json()["matched"] == 0
