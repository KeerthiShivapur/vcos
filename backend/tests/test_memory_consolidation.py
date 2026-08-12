"""Slice 4D.3 — memory consolidation (evidence merge, related links, supersede).

Proves the consolidation laws:

* a memory grows, never silently rewrites: later events merge evidence and
  source-event lineage into the same dedupe-keyed memory,
* semantically similar experiences in the same scope link as related memories
  (bounded top-K, never across scopes),
* ``project.cancelled`` supersedes the ``project.started`` experience:
  the earlier memory is marked ``superseded`` with a pointer to its successor.
"""

from sqlalchemy import select

from app.models.company_memory import CompanyMemory
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Consolidation Project", status=None):
    body = {"name": name, "description": "consolidation test"}
    if status:
        body["status"] = status
    response = await client.post("/api/v1/projects", json=body, headers=headers)
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


async def _comment(client, headers, task_id, body):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.text


async def _lifecycle(client, headers, project_id, action):
    response = await client.post(
        f"/api/v1/projects/{project_id}/lifecycle", json={"action": action}, headers=headers
    )
    assert response.status_code == 200, response.text


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


async def _memories(db, organization_id):
    return list(
        (
            await db.execute(
                select(CompanyMemory).where(CompanyMemory.organization_id == organization_id)
            )
        ).scalars().all()
    )


async def _by_dedupe(db, organization_id, dedupe_key):
    row = (
        await db.execute(
            select(CompanyMemory).where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.dedupe_key == dedupe_key,
            )
        )
    ).scalar_one_or_none()
    assert row is not None, f"missing memory for {dedupe_key}"
    return row


# ---------------------------------------------------- 1. evidence merge & growth


async def test_evidence_and_lineage_merge_across_events(client, db_session_factory):
    org = await register_org(client, email="m4d3_merge@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Merge evidence task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)
    await _comment(client, headers, dependent["id"], "Vendor response overdue.")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        memory = await _by_dedupe(db, org_id, f"task.blocked:{dependent['id']}")
        events = memory.source_event_ids or []
        assert len(events) == 2  # block + comment merged into one memory
        evidence = memory.evidence_json or []
        event_evidence = [item for item in evidence if item["type"] == "event"]
        assert len(event_evidence) == 2
        assert {item["relationship"] for item in event_evidence} == {"task.blocked", "task.commented"}
        discussion = (memory.context_json or {}).get("discussion", [])
        assert discussion and "Vendor response overdue." in discussion[0]["body"]

        # Exactly one row per dedupe key — consolidation never duplicates.
        rows = await _memories(db, org_id)
        assert len(rows) == 1


# ------------------------------------------------------- 2. related memories


async def test_similar_experiences_link_as_related(client, db_session_factory):
    org = await register_org(client, email="m4d3_related@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    first_blocker = await _task(client, headers, project["id"], "Prereq A")
    second_blocker = await _task(client, headers, project["id"], "Prereq B")
    third_blocker = await _task(client, headers, project["id"], "Prereq C")
    first = await _task(client, headers, project["id"], "Set up billing sync for Northwind")
    second = await _task(client, headers, project["id"], "Set up billing sync for Contoso")
    third = await _task(client, headers, project["id"], "Set up billing sync for Acme")
    for task, blocker in ((first, first_blocker), (second, second_blocker), (third, third_blocker)):
        await _block(client, headers, task["id"], blocker["id"])
        await _transition(client, headers, task["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        a = await _by_dedupe(db, org_id, f"task.blocked:{first['id']}")
        b = await _by_dedupe(db, org_id, f"task.blocked:{second['id']}")
        c = await _by_dedupe(db, org_id, f"task.blocked:{third['id']}")
        # The latest-written memory links its similar same-scope experiences.
        linked = set(c.related_memory_ids or [])
        assert a.id in linked and b.id in linked
        # Related links never point outside the memory's own scope/org.
        for memory in (a, b, c):
            assert all(
                related in (a.id, b.id, c.id)
                for related in (memory.related_memory_ids or [])
            )
            assert memory.related_memory_ids is None or len(memory.related_memory_ids) <= 5


# -------------------------------------------------------------- 3. supersede


async def test_project_cancelled_supersedes_started_experience(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_super@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers, "Doomed Rollout", status="draft")

    await _lifecycle(client, headers, project["id"], "start")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)
    async with db_session_factory() as db:
        started = await _by_dedupe(db, org_id, f"project.started:{project['id']}")
        assert started.status == "active"
        started_id = started.id

    await _lifecycle(client, headers, project["id"], "cancel")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        cancelled = await _by_dedupe(db, org_id, f"project.cancelled:{project['id']}")
        assert cancelled.status == "active"
        assert cancelled.outcome_type == "negative"
        assert cancelled.lesson and "cancelled" in cancelled.lesson

        refreshed = await db.get(CompanyMemory, started_id)
        assert refreshed.status == "superseded"
        assert refreshed.supersedes_id == cancelled.id

        # The superseding memory's lineage includes the cancellation event.
        assert len(cancelled.source_event_ids or []) == 1
        events = cancelled.evidence_json or []
        assert any(item.get("relationship") == "project.cancelled" for item in events)
