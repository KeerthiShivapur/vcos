"""Slice 4D.6 — unified Company Brain: one question, composed governed answer.

Proves the canonical request flow:

    question -> context (4D.1) -> governed retrieval per source (4D.2-4D.5)
        -> bounded evidence -> one unified answer

* the /brain/answer response is additively compatible with the 4D.1 contract
  (question/claims/scope_ids/answered_at unchanged in meaning),
* patterns (4D.4), insights (4D.5), memories (4D.3) and knowledge (4D.2)
  participate as structured, governed sections,
* the deterministic summary + bounded confidence are derived only from
  retrieved evidence,
* /brain/overview returns a governed unified overview (attention + recent
  intelligence) on top of the existing living company view,
* the same question answered twice is deterministic.
"""

import asyncio

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def test_unified_answer_contract_and_determinism(client, db_session_factory):
    org = await register_org(client, email="p4d6_unified@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=3, name="Unified Project")
    await h.decision(client, headers, proj["id"])
    await h.drive_full_stack(client, db_session_factory)

    first = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind schedule?"},
            headers=headers,
        )
    ).json()
    # 4D.1 keys preserved
    assert "question" in first and "claims" in first and "scope_ids" in first and "answered_at" in first
    assert first["claims"]
    # unified additions
    assert isinstance(first["summary"], str) and first["summary"]
    assert 0.0 <= first["confidence"] <= 1.0
    assert isinstance(first["related_entities"], list)
    assert isinstance(first["patterns"], list)
    assert isinstance(first["memories"], list)
    assert isinstance(first["insights"], list)
    assert isinstance(first["knowledge"], list)
    assert first["sources_consulted"]
    assert first["scope"] == {"org_wide": True}
    assert first["generated_at"]
    assert first["metrics"]["brain_query"] == "answer"
    assert first["metrics"]["brain_query_duration_ms"] >= 0
    assert first["metrics"]["evidence_count"] >= 1
    assert first["metrics"]["answer_claim_count"] == len(first["claims"])

    # routing: a delayed-project question consults patterns + insights + memory
    assert "insights" in first["sources_consulted"]
    assert "patterns" in first["sources_consulted"]
    assert any(i["insight_type"] == "execution_bottleneck" for i in first["insights"])

    # determinism: asking again yields the same claims and confidence
    second = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind schedule?"},
            headers=headers,
        )
    ).json()
    assert [c["claim"] for c in second["claims"]] == [c["claim"] for c in first["claims"]]
    assert second["confidence"] == first["confidence"]


async def test_memory_participates_when_history_is_asked(client, db_session_factory):
    org = await register_org(client, email="p4d6_mem@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=3, name="Memory Project")
    await h.seed_memory(client, headers, proj["id"], "Project Orion approval delay")
    await h.drive_full_stack(client, db_session_factory)

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "have we experienced this sort of delay before?"},
            headers=headers,
        )
    ).json()
    assert answer["memories"], answer
    # the blocked tasks formed canonical 4D.3 experience memories about the project
    assert any(
        "blocked" in f"{m.get('title', '')} {m.get('summary', '')}".lower()
        for m in answer["memories"]
    ), answer["memories"]
    assert "memory" in answer["sources_consulted"]


async def test_knowledge_participates_when_policy_is_asked(client, db_session_factory):
    org = await register_org(client, email="p4d6_know@test.co")
    headers = org["headers"]
    await h.blocked_project(client, headers, count=2, name="Knowledge Project")
    await h.seed_knowledge(
        client, db_session_factory, headers, org["organization"]["id"]
    )

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "what is the company's approval policy for this?"},
            headers=headers,
        )
    ).json()
    assert "knowledge" in answer["sources_consulted"]
    assert answer["knowledge"], answer
    assert any("approval" in item["title"].lower() for item in answer["knowledge"])
    # every knowledge item carries a deep link and a bounded score
    for item in answer["knowledge"]:
        assert item["id"] and item["url"] and 0.0 <= item["score"] <= 1.0


async def test_overview_is_governed_and_bounded(client, db_session_factory):
    org = await register_org(client, email="p4d6_ov@test.co")
    headers = org["headers"]
    await h.blocked_project(client, headers, count=3, name="Overview Project")
    await h.seed_memory(client, headers, org["organization"]["id"] or "x")
    await h.drive_full_stack(client, db_session_factory)

    overview = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    # existing living-company keys stay
    assert "state" in overview and "health" in overview and "graph" in overview
    # 4D.6 unified sections
    assert "attention" in overview and isinstance(overview["attention"], list)
    assert len(overview["attention"]) >= 1
    recent = overview["recent_intelligence"]
    assert set(recent.keys()) == {"insights", "patterns", "memories"}
    assert recent["insights"]["count"] >= 1
    assert len(recent["insights"]["latest"]) <= 3
    assert overview["scope"] == {"org_wide": True}
    assert overview["generated_at"]
    for item in overview["attention"]:
        assert item["source"] in ("insight", "pattern", "memory")
        assert item["id"] and item["url"] and 0.0 <= item["confidence"] <= 1.0


async def test_entity_anchored_answer_focuses_related(client, db_session_factory):
    org = await register_org(client, email="p4d6_anchor@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=3, name="Anchored Project")
    await h.drive_full_stack(client, db_session_factory)

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this behind?",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=headers,
        )
    ).json()
    related = answer["related_entities"]
    assert related
    assert any(r["type"] == "project" and r["id"] == proj["id"] for r in related)
    assert len(related) <= 8
    for item in related:
        assert item["id"] and item["type"] and item["url"]