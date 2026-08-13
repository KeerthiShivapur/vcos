"""Slice 4D.6 — one answer, every source: knowledge + memory + pattern +
insight + graph compose through the unified brain.

The canonical scenario: a project with blocked tasks, a pending decision, a
recurring pattern, a company insight, a historical memory and indexed
knowledge. One question assembles them; related/evidence endpoints connect
the graph.

No parallel store: the same pattern/insight/memory rows the 4D.4/4D.5/4D.3
engines produce are the ones composed here.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _rich_scenario(client, db_session_factory, email):
    org = await register_org(client, email=email)
    headers = org["headers"]
    org_id = org["organization"]["id"]
    proj = await h.blocked_project(client, headers, count=3, name="Rich Scenario")
    tasks = (await client.get(
        "/api/v1/tasks",
        params={"project_id": proj["id"], "limit": 50},
        headers=headers,
    )).json()
    tasks = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
    await h.decision(client, headers, proj["id"], "approve finance approval")
    await h.seed_memory(client, headers, proj["id"], "Project Orion approval delay")
    await h.seed_knowledge(client, db_session_factory, headers, org_id, project_id=proj["id"])
    await h.drive_full_stack(client, db_session_factory)
    task_ids = [t["id"] for t in (tasks if isinstance(tasks, list) else [])]
    await h.sync_task_graph(db_session_factory, org_id, task_ids)
    return org, headers, proj, task_ids


async def test_one_answer_composes_pattern_memory_insight_knowledge(client, db_session_factory):
    org, headers, proj, task_ids = await _rich_scenario(client, db_session_factory, "p4d6_comp@test.co")

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project behind on the approval policy review?",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=headers,
        )
    ).json()

    # pattern (4D.4) participates
    assert any(p["pattern_type"] == "repeated_delay" for p in answer["patterns"]), answer["patterns"]
    # insight (4D.5) participates, anchored to the project
    assert any(i["insight_type"] == "execution_bottleneck" and i["url"] for i in answer["insights"])
    # memory (4D.3) participates — history-shaped question
    assert answer["memories"], answer["memories"]
    assert any("blocked" in m["title"].lower() for m in answer["memories"]), answer["memories"]
    # knowledge (4D.2) participates via the anchored project question
    assert any("approval" in k["title"].lower() for k in answer["knowledge"]), answer["knowledge"]
    # sources tell the composition story
    assert {"patterns", "insights", "memory", "knowledge", "context"} <= set(answer["sources_consulted"])

    # graph participates: related view connects project -> tasks
    related = (
        await client.get(f"/api/v1/brain/related/project/{proj['id']}", headers=headers)
    ).json()
    assert related["source"]["id"] == proj["id"]
    related_types = {item["type"] for item in related["related"]}
    assert "task" in related_types, related
    assert len(related["related"]) <= 8
    # cross-source linkage visible in the evidence drawer
    drawer = (
        await client.get(f"/api/v1/brain/evidence/project/{proj['id']}", headers=headers)
    ).json()
    assert drawer["links"]["patterns"] >= 1
    assert drawer["links"]["insights"] >= 1
    assert drawer["links"]["memories"] >= 1
    for item in drawer["evidence"]:
        assert item["type"] in ("pattern", "insight", "memory", "knowledge")


async def test_same_rows_are_the_canonical_producers(client, db_session_factory):
    """No parallel store: composed rows are the exact 4D.4/4D.5/4D.3 rows."""
    org, headers, proj, task_ids = await _rich_scenario(client, db_session_factory, "p4d6_no_store@test.co")

    insights_api = (
        await client.get("/api/v1/brain/insights", params={"limit": 50}, headers=headers)
    ).json()
    patterns_api = (
        await client.get("/api/v1/brain/patterns", params={"limit": 50}, headers=headers)
    ).json()
    memory_api = (
        await client.get("/api/v1/brain/memory/feed", params={"limit": 50}, headers=headers)
    ).json()
    insight_ids_api = {i["id"] for i in insights_api["insights"]}
    pattern_ids_api = {p["id"] for p in patterns_api["patterns"]}
    memory_ids_api = {m["id"] for m in memory_api["memories"]}

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind?"},
            headers=headers,
        )
    ).json()
    assert {i["id"] for i in answer["insights"]} <= insight_ids_api
    assert {p["id"] for p in answer["patterns"]} <= pattern_ids_api
    assert {m["id"] for m in answer["memories"]} <= memory_ids_api


async def test_history_followup_connects_current_to_memory(client, db_session_factory):
    org, headers, proj, task_ids = await _rich_scenario(client, db_session_factory, "p4d6_followup@test.co")

    first = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind?"},
            headers=headers,
        )
    ).json()
    followup = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "has this happened before?"},
            headers=headers,
        )
    ).json()
    assert first["memories"] and followup["memories"]
    # both answers are connected by the same historical memory
    first_ids = {m["id"] for m in first["memories"]}
    followup_ids = {m["id"] for m in followup["memories"]}
    assert first_ids & followup_ids