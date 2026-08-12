"""Slice 4D.3 — memory lineage and retrieval (evidence, timeline, search, brain).

Proves the read surfaces that make memory answerable:

* evidence resolution: ``/brain/memory/{id}/evidence`` turns refs into
  titles/urls — why VCOS believes a memory,
* timeline: episode-style history links each memory to its forming events,
* semantic search: deterministic embeddings score only visible memories,
  unrelated queries return nothing,
* the reasoning engine cites historical memory (labeled by fact kind, category,
  outcome and confidence) for history questions, and says so explicitly when
  no historical experience exists.
"""

from app.intelligence_network.reasoning_engine import reasoning_engine
from app.models.user import User
from app.workers import memory_formation_worker
from tests.conftest import register_org


async def _project(client, headers, name="Lineage Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "lineage test", "status": "active"},
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


async def _formed_blocked_journey(client, headers, db_session_factory, title="Billing sync delivery"):
    project = await _project(client, headers)
    blocker = await _task(client, headers, project["id"], f"Prereq {title}")
    dependent = await _task(client, headers, project["id"], title)
    await _block(client, headers, dependent["id"], blocker["id"])
    await _transition(client, headers, dependent["id"], "blocked")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)
    await _transition(client, headers, blocker["id"], "completed")
    await _transition(client, headers, dependent["id"], "completed")
    await _drain_events(db_session_factory)
    await _run_formation(db_session_factory)
    return dependent


async def _memory_by_entity(client, headers, entity_type, entity_id, source_event=None):
    response = await client.get("/api/v1/brain/memory/feed", headers=headers)
    assert response.status_code == 200, response.text
    for memory in response.json()["memories"]:
        if memory["entity_type"] == entity_type and memory["entity_id"] == entity_id:
            if source_event is not None and memory.get("source_event") != source_event:
                continue
            return memory
    raise AssertionError(f"no memory for {entity_type} {entity_id}")


# --------------------------------------------------------------- 1. evidence


async def test_evidence_resolution_endpoint(client, db_session_factory):
    org = await register_org(client, email="m4d3_evid@test.co")
    headers = org["headers"]
    dependent = await _formed_blocked_journey(client, headers, db_session_factory)
    memory = await _memory_by_entity(client, headers, "task", dependent["id"], source_event="task.blocked")

    response = await client.get(
        f"/api/v1/brain/memory/{memory['id']}/evidence", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["memory"]["id"] == memory["id"]

    resolved = {item["type"]: item for item in body["evidence"]}
    assert resolved["task"]["resolved"] is True
    assert resolved["task"]["title"] == "Billing sync delivery"
    assert resolved["task"]["url"] == f"/tasks/{dependent['id']}"
    assert resolved["project"]["resolved"] is True
    assert resolved["project"]["title"]  # project name resolves
    assert resolved["dependency"]["resolved"] is True
    assert resolved["event"]["resolved"] is True
    assert resolved["event"]["title"]  # human-readable event description


# ---------------------------------------------------------------- 2. timeline


async def test_timeline_links_episodes_to_forming_events(client, db_session_factory):
    org = await register_org(client, email="m4d3_tline@test.co")
    headers = org["headers"]
    dependent = await _formed_blocked_journey(client, headers, db_session_factory)

    timeline = await client.get("/api/v1/brain/memory/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    episodes = timeline.json()["episodes"]
    categories = {episode["memory_category"] for episode in episodes}
    assert {"experience", "outcome", "lesson"} <= categories

    by_entity = {episode["entity_id"]: episode for episode in episodes if episode["entity_type"] == "task"}
    episode = by_entity.get(dependent["id"])
    assert episode is not None
    assert len(episode["episode_events"]) >= 1
    assert set(episode["episode_events"]) <= set(episode["source_event_ids"] or [])


# ---------------------------------------------------------------- 3. search


async def test_search_semantic_retrieval_with_scores(client, db_session_factory):
    org = await register_org(client, email="m4d3_search@test.co")
    headers = org["headers"]
    dependent = await _formed_blocked_journey(client, headers, db_session_factory)
    experience = await _memory_by_entity(client, headers, "task", dependent["id"])

    hit = await client.post(
        "/api/v1/brain/memory/search",
        json={"question": "task was blocked during execution in project"},
        headers=headers,
    )
    assert hit.status_code == 200, hit.text
    body = hit.json()
    assert body["matched"] >= 1
    assert any(memory["id"] == experience["id"] for memory in body["memories"])
    top = body["memories"][0]
    assert top["fact_kind"] == "observation"
    assert top["memory_category"] in ("experience", "outcome", "lesson")

    miss = await client.post(
        "/api/v1/brain/memory/search",
        json={"question": "quarterly revenue grew by twelve percent"},
        headers=headers,
    )
    assert miss.status_code == 200
    assert miss.json()["matched"] == 0

    empty = await client.post(
        "/api/v1/brain/memory/search",
        json={"question": ""},
        headers=headers,
    )
    assert empty.status_code == 422


# --------------------------------------------- 4. brain answer historical claims


async def test_brain_cites_historical_memory_claims(client, db_session_factory):
    org = await register_org(client, email="m4d3_claims@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    dependent = await _formed_blocked_journey(client, headers, db_session_factory)
    await _memory_by_entity(client, headers, "task", dependent["id"])

    async with db_session_factory() as db:
        user = await db.get(User, org["user"]["id"])
        claims = await reasoning_engine._claims_from_context(
            db,
            org_id,
            "task was blocked during execution like this before",
            {"evidence": [], "scope_ids": []},
            user=user,
        )
        memory_claims = [claim for claim in claims if claim.get("evidence")]
        assert memory_claims, "expected historical memory claims"
        evidence = memory_claims[0]["evidence"]
        assert evidence[0]["type"] == "memory"
        assert evidence[0]["url"].startswith("/brain/memory/")
        assert memory_claims[0]["memory_category"] in ("experience", "lesson", "outcome")
        assert memory_claims[0]["kind"] in ("fact", "observation", "inference", "lesson")
        assert memory_claims[0]["confidence"] > 0.0


async def test_brain_falls_back_when_no_history_exists(client, db_session_factory):
    org = await register_org(client, email="m4d3_nohist@test.co")
    org_id = org["organization"]["id"]

    async with db_session_factory() as db:
        user = await db.get(User, org["user"]["id"])
        claims = await reasoning_engine._claims_from_context(
            db,
            org_id,
            "Why is the rollout still blocked?",
            {"evidence": [], "scope_ids": []},
            user=user,
        )
        assert any(
            "No similar historical experience" in claim["claim"] for claim in claims
        )
