"""Slice 4D.3 — memory outcomes (resolution, progression, manual feedback).

Proves the outcome lifecycle:

* completing a previously blocked task resolves the experience: the blocked
  memory gains a positive outcome, an outcome memory and a lesson memory are
  formed, and the outcome is traceable in ``memory_outcomes``,
* outcome progression is monotonic — a later event may upgrade the observed
  outcome but never downgrade it,
* manual outcome feedback (``POST /brain/memory/{id}/outcome``) records a
  traceable observation and only ever nudges confidence upward,
* invalid outcome types are rejected by the API contract.
"""

from sqlalchemy import select

from app.models.company_memory import CompanyMemory, MemoryOutcome
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Outcome Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "outcome test", "status": "active"},
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


async def _blocked_experience(db, organization_id, task_id):
    return (
        await db.execute(
            select(CompanyMemory).where(
                CompanyMemory.organization_id == organization_id,
                CompanyMemory.dedupe_key == f"task.blocked:{task_id}",
            )
        )
    ).scalar_one_or_none()


async def _outcome_rows(db, memory_id):
    return list(
        (
            await db.execute(
                select(MemoryOutcome).where(MemoryOutcome.memory_id == memory_id)
            )
        ).scalars().all()
    )


# --------------------------------------------------------- 1. resolution flow


async def test_completion_resolves_blocked_experience_with_full_lineage(
    client, db_session_factory
):
    org = await register_org(client, email="m4d3_outflow@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Billing sync delivery")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    await _transition(client, headers, blocker["id"], "completed")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    await _transition(client, headers, dependent["id"], "completed")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        experience = await _blocked_experience(db, org_id, dependent["id"])
        assert experience is not None
        assert experience.outcome_type == "positive"
        # Either the unblock event (blocker completion) or the completion event
        # records the final positive outcome text; the type is what matters.
        assert experience.outcome and (
            "was unblocked" in experience.outcome or "was completed" in experience.outcome
        )
        assert experience.status == "active"  # resolved, never archived

        history = await _outcome_rows(db, experience.id)
        # Both the unblock (blocker completion) and the completion event record
        # traceable positive observations on the same experience.
        assert len(history) == 2
        assert {row.outcome_type for row in history} == {"positive"}
        relationships = {
            item.get("relationship")
            for row in history
            for item in (row.evidence_json or [])
            if item.get("type") == "event"
        }
        assert {"task.unblocked", "task.completed"} <= relationships

        categories = {
            row.memory_category for row in (
                await db.execute(
                    select(CompanyMemory).where(CompanyMemory.organization_id == org_id)
                )
            ).scalars().all()
        }
        # Experience + outcome memory + lesson memory all present.
        assert {"experience", "outcome", "lesson"} <= categories

        lesson = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == org_id,
                    CompanyMemory.memory_category == "lesson",
                )
            )
        ).scalar_one()
        assert lesson.fact_kind == "lesson"
        assert "blocked" in (lesson.lesson or "")

        outcome_memory = (
            await db.execute(
                select(CompanyMemory).where(
                    CompanyMemory.organization_id == org_id,
                    CompanyMemory.dedupe_key == f"task.outcome:{dependent['id']}",
                )
            )
        ).scalar_one()
        assert outcome_memory.memory_category == "outcome"
        assert outcome_memory.outcome_type == "positive"


# ---------------------------------------------- 2. monotonic outcome progression


async def test_outcome_progression_never_downgrades(client, db_session_factory):
    org = await register_org(client, email="m4d3_prog@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Progress task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        experience = await _blocked_experience(db, org_id, dependent["id"])
        memory_id = experience.id
        assert experience.outcome_type is None  # a block alone records no outcome

    # Manual negative observation.
    recorded = await client.post(
        f"/api/v1/brain/memory/{memory_id}/outcome",
        json={"outcome_type": "negative", "outcome": "Vendor still unresponsive"},
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["outcome_type"] == "negative"

    # Completion upgrades negative -> positive.
    await _transition(client, headers, blocker["id"], "completed")
    await _transition(client, headers, dependent["id"], "completed")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        experience = await db.get(CompanyMemory, memory_id)
        assert experience.outcome_type == "positive"
        positive_confidence = experience.confidence

    # A later manual "partial" observation must NOT downgrade the memory.
    downgrade = await client.post(
        f"/api/v1/brain/memory/{memory_id}/outcome",
        json={"outcome_type": "partial", "outcome": "second look at the fix"},
        headers=headers,
    )
    assert downgrade.status_code == 200, downgrade.text
    assert downgrade.json()["outcome_type"] == "positive"  # never downgraded

    async with db_session_factory() as db:
        experience = await db.get(CompanyMemory, memory_id)
        assert experience.outcome_type == "positive"
        assert experience.confidence >= positive_confidence
        # Every observation is traceable, including the rejected downgrade.
        history = await _outcome_rows(db, memory_id)
        assert len(history) == 3


# --------------------------------------------------- 3. manual outcome feedback


async def test_manual_outcome_is_traceable_and_bounded(client, db_session_factory):
    org = await register_org(client, email="m4d3_manual@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Feedback task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        experience = await _blocked_experience(db, org_id, dependent["id"])
        memory_id = experience.id
        baseline = experience.confidence

    recorded = await client.post(
        f"/api/v1/brain/memory/{memory_id}/outcome",
        json={
            "outcome_type": "partial",
            "outcome": "Half of the integration shipped",
            "entity_type": "task",
            "entity_id": dependent["id"],
        },
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    body = recorded.json()
    assert body["outcome_type"] == "partial"
    assert body["outcome"] == "Half of the integration shipped"
    assert 0.0 < body["confidence"] - baseline <= 0.05  # confidence only nudges up

    async with db_session_factory() as db:
        history = await _outcome_rows(db, memory_id)
        assert len(history) == 1
        assert history[0].applied_entity_type == "task"
        assert history[0].applied_entity_id == dependent["id"]
        assert any(item.get("relationship") == "observed" for item in (history[0].evidence_json or []))


async def test_manual_outcome_invalid_type_rejected(client, db_session_factory):
    org = await register_org(client, email="m4d3_invalid@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], "Prereq task")
    dependent = await _task(client, headers, project["id"], "Validation task")
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)

    async with db_session_factory() as db:
        experience = await _blocked_experience(db, org_id, dependent["id"])
        memory_id = experience.id

    rejected = await client.post(
        f"/api/v1/brain/memory/{memory_id}/outcome",
        json={"outcome_type": "banana", "outcome": "nope"},
        headers=headers,
    )
    assert rejected.status_code == 422
