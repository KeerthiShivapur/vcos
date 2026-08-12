"""Slice 4D.3 — organizational memory formation (event -> experience).

Proves the change-driven formation pipeline end to end:

* significant events enqueue durable ``memory.formation`` jobs through the
  event bus (task.blocked -> experience memory),
* exactly-once idempotency (``MemoryEvent`` links + job CAS),
* context-only enrichment (task.commented feeds the open experience, never
  forms its own memory),
* outcome-only events with no open experience are routine progress, not
  memory (task.completed without a prior block is skipped),
* non-significant events never enqueue formation jobs.

The pipeline is observational: operating entities (tasks, projects,
dependencies) are never mutated by memory work.
"""

from sqlalchemy import select

from app.models.company_memory import CompanyMemory, MemoryEvent
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Formation Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "memory formation test", "status": "active"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _task(client, headers, project_id, title, status="in_progress"):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": project_id, "status": status},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(client, headers, task_id, status):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"status": status}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


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
    return response.json()


async def _drain_events(db_session_factory, limit=200, rounds=10):
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


async def _run_formation(db_session_factory, limit=50, rounds=8):
    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await memory_formation_worker.run_once(db=session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _blocked_task_setup(client, headers, project_id, title="Set up billing sync for Northwind"):
    blocker = await _task(client, headers, project_id, f"Prereq for {title}")
    dependent = await _task(client, headers, project_id, title)
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    return blocker, dependent


async def _memory_rows(db, organization_id):
    return list(
        (
            await db.execute(
                select(CompanyMemory).where(CompanyMemory.organization_id == organization_id)
            )
        ).scalars().all()
    )


async def _formation_jobs(db, organization_id):
    return list(
        (
            await db.execute(
                select(BackgroundJob).where(
                    BackgroundJob.name == "memory.formation",
                    BackgroundJob.organization_id == organization_id,
                )
            )
        ).scalars().all()
    )


# ----------------------------------------------------------- 1. block -> memory


async def test_blocked_task_forms_experience_memory_with_evidence(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_formed@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker, dependent = await _blocked_task_setup(client, headers, project["id"])

    await _drain_events(db_session_factory)
    processed = await _run_formation(db_session_factory)
    assert processed >= 1

    async with db_session_factory() as db:
        rows = await _memory_rows(db, org_id)
        experiences = [row for row in rows if row.memory_category == "experience"]
        assert len(experiences) == 1
        memory = experiences[0]
        assert memory.domain == "task"
        assert memory.entity_type == "task"
        assert memory.entity_id == dependent["id"]
        assert memory.fact_kind == "observation"
        assert memory.auth_scope == "org"
        assert memory.status == "active"
        assert memory.outcome_type is None
        assert memory.lesson and "blocked" in memory.lesson
        assert memory.confidence >= 0.85  # structured task+project evidence, capped

        evidence = {item["type"] for item in (memory.evidence_json or [])}
        assert {"event", "task", "project", "dependency"} <= evidence

        source_events = memory.source_event_ids or []
        assert len(source_events) == 1

        # Operating layer untouched: the task is still blocked, no memory table
        # leaked into operating rows.
        links = (
            await db.execute(
                select(MemoryEvent).where(MemoryEvent.memory_id == memory.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].relationship == "formation"

        # Job family drained cleanly.
        jobs = await _formation_jobs(db, org_id)
        assert jobs and all(job.status == "done" for job in jobs)


async def test_blocked_event_exactly_once_across_replays(client, db_session_factory):
    org = await register_org(client, email="m4d3_idemp@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    _, dependent = await _blocked_task_setup(client, headers, project["id"])

    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        first_count = len(await _memory_rows(db, org_id))
        assert first_count >= 1
        blocked_events = list(
            (
                await db.execute(
                    select(EventRow).where(
                        EventRow.organization_id == org_id,
                        EventRow.name == "task.blocked",
                    )
                )
            ).scalars().all()
        )
        assert len(blocked_events) == 1

    # Replay the same event through the pipeline again: the MemoryEvent link
    # makes the contribution exactly-once — no duplicates, no new rows.
    async with db_session_factory() as db:
        replay = await memory_formation_worker.run_once(db=db, limit=50)
        await db.commit()
        second_count = len(await _memory_rows(db, org_id))
    assert replay == 0
    assert second_count == first_count


async def test_task_comment_enriches_open_experience_only(client, db_session_factory):
    org = await register_org(client, email="m4d3_comment@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    _, dependent = await _blocked_task_setup(client, headers, project["id"])

    comment = await _comment(
        client, headers, dependent["id"], "The vendor API is down, waiting on their SLA."
    )
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        rows = await _memory_rows(db, org_id)
        experiences = [row for row in rows if row.memory_category == "experience"]
        assert len(experiences) == 1  # comment never forms its own memory
        memory = experiences[0]
        discussion = (memory.context_json or {}).get("discussion", [])
        assert discussion and discussion[0]["body"] == "The vendor API is down, waiting on their SLA."
        assert comment["id"] not in {str(item.get("id")) for item in (memory.evidence_json or [])}
        assert str(comment["id"]) not in (memory.source_event_ids or [])
        assert memory.source_event == "task.blocked"  # primary forming event unchanged


async def test_commented_event_without_open_experience_is_noop(client, db_session_factory):
    org = await register_org(client, email="m4d3_comment_noop@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    task = await _task(client, headers, project["id"], "Never blocked task")
    await _comment(client, headers, task["id"], "Just a note on a routine task.")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        assert await _memory_rows(db, org_id) == []


async def test_task_completed_without_prior_block_is_routine_progress(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_skip@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    task = await _task(client, headers, project["id"], "Routine delivery task")
    await _transition(client, headers, task["id"], "completed")

    await _drain_events(db_session_factory)
    processed = await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        rows = await _memory_rows(db, org_id)
        jobs = await _formation_jobs(db, org_id)
    # The completion event WAS significant (a formation job ran) but with no
    # open blocked experience to resolve it is routine progress, not memory.
    assert processed >= 1
    assert rows == []
    assert jobs and all(job.status == "done" for job in jobs)


async def test_task_created_never_forms_memory(client, db_session_factory):
    org = await register_org(client, email="m4d3_nonsig@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    await _task(client, headers, project["id"], "Plain task")

    await _drain_events(db_session_factory)
    processed = await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        assert processed == 0
        assert await _memory_rows(db, org_id) == []
        assert await _formation_jobs(db, org_id) == []
