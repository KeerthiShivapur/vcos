"""Shared helpers for Slice 4D.6 brain tests (not collected as tests)."""

from sqlalchemy import select


async def project(client, headers, name="Brain Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "4d6 anchor", "status": "active"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def task(client, headers, project_id, title, status="todo"):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": project_id, "status": status},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def transition(client, headers, task_id, status):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"status": status}, headers=headers
    )
    assert response.status_code == 200, response.text


async def depend(client, headers, task_id, blocker_id):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": blocker_id, "kind": "finish_to_start"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def blocked_project(client, headers, count=3, name="Blocked Brain Project"):
    """Canonical 4D.3 stall setup: dependent task blocked by an open blocker.

    Only a dependency-blocked task emits ``task.blocked`` (the event the
    memory formation pipeline forms experience/lesson memories from), and the
    same events feed the pattern + insight pipelines.
    """
    proj = await project(client, headers, name)
    for i in range(count):
        blocker = await task(client, headers, proj["id"], f"blocker {i}")
        t = await task(client, headers, proj["id"], f"blocked {i}")
        await depend(client, headers, t["id"], blocker["id"])
        await transition(client, headers, t["id"], "blocked")
    return proj


async def decision(client, headers, project_id, title="approve finance approval"):
    response = await client.post(
        "/api/v1/decisions",
        json={"title": title, "project_id": project_id, "description": "pending decision"},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


async def approval(client, headers, entity_type, entity_id, title="Approval request"):
    response = await client.post(
        "/api/v1/approvals",
        json={
            "title": title,
            "approval_type": "project",
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


async def drain_events(db_session_factory, rounds=10):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=200)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def run_patterns(db_session_factory, limit=50, rounds=8):
    from app.workers import pattern_worker

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await pattern_worker.run_once(db=session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def run_insights(db_session_factory, limit=50, rounds=8):
    from app.workers import insight_worker

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await insight_worker.run_once(db=session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def run_memory_formation(db_session_factory, limit=50, rounds=8):
    from app.workers import memory_formation_worker

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await memory_formation_worker.run_once(
                db=session, limit=limit
            )
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def drive_full_stack(client, db_session_factory):
    """Events -> pattern evaluation -> memory formation -> insight evaluation.

    Memory formation is the canonical 4D.3 pipeline: significant events are
    adopted into ``memory.formation`` jobs and drained into experience/lesson
    memories by the same worker the scheduler runs. Patterns and insights
    then evaluate over the same event stream (4D.4/4D.5).
    """
    await drain_events(db_session_factory)
    await run_patterns(db_session_factory)
    await drain_events(db_session_factory)
    formed = await run_memory_formation(db_session_factory)
    await drain_events(db_session_factory)
    await run_insights(db_session_factory)
    return formed


async def seed_memory(client, headers, project_id, title="Previous approval delay"):
    response = await client.post(
        "/api/v1/brain/memory",
        json={
            "memory_type": "institutional",
            "title": title,
            "content": "An approval delay blocked similar work in the past.",
            "importance": "medium",
            "entity_type": "project",
            "entity_id": project_id,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


async def seed_knowledge(client, db_session_factory, headers, organization_id, project_id=None):
    """Published document + persisted chunk index (offline deterministic)."""
    payload = {"title": "Approval policy for enterprise accounts", "content": (
        "All project approvals require a formal decision record. The finance "
        "approval workflow must be reviewed before launch approval is granted. "
        "This approval policy is company policy."
    )}
    if project_id:
        payload["project_id"] = project_id
    response = await client.post("/api/v1/documents", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    document = response.json()
    response = await client.post(
        f"/api/v1/documents/{document['id']}/publish", headers=headers
    )
    assert response.status_code == 200, response.text
    from app.knowledge import semantic_indexer

    async with db_session_factory() as db:
        written = await semantic_indexer.reindex_entity(
            db, organization_id=organization_id, kind="document", entity_id=document["id"]
        )
        await db.commit()
    assert written >= 1
    return document


async def sync_task_graph(db_session_factory, organization_id, task_ids):
    from app.intelligence.graph_engine import graph_engine

    async with db_session_factory() as db:
        for task_id in task_ids:
            await graph_engine.sync_entity_edges(
                db, organization_id=organization_id, entity_type="task", entity_id=task_id
            )
        await db.commit()


async def scope_for_project(client, headers, project_id):
    return (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": f"Scope {project_id[:6]}", "scope_type": "project", "entity_id": project_id},
            headers=headers,
        )
    ).json()


async def invite_scoped_reader(client, headers, scope_id, email):
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Scoped Brain Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Brain Reader",
            "password": "B4DPass123!",
        },
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
        await client.get("/api/v1/governance/assignments", params={"user_id": user_id}, headers=headers)
    ).json()
    org_wide = next(assignment for assignment in assignments if assignment["scope_id"] is None)
    await client.delete(f"/api/v1/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4d6 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def count_rows(db_session_factory, model, organization_id=None):
    async with db_session_factory() as db:
        statement = select(model)
        if organization_id is not None and hasattr(model, "organization_id"):
            statement = statement.where(model.organization_id == organization_id)
        return len(list((await db.execute(statement)).scalars().all()))