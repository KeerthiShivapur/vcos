"""Slice 4D.7 — the canonical unified answer contract.

Every answer retains the 4D.1 claim shape (claim/evidence/confidence/
auth_scope/timestamp) and adds the unified additions: persona-aware scope,
an evidence-backed timeline, deterministic recommended next questions, a
causal reasoning chain for why-shaped questions, and cross-source related
projections — all bounded, all governed.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _rich_scenario(client, db_session_factory, email, name="Rich 4D7"):
    org = await register_org(client, email=email)
    headers = org["headers"]
    org_id = org["organization"]["id"]
    proj = await h.blocked_project(client, headers, count=2, name=name)
    tasks = (await client.get(
        "/api/v1/tasks", params={"project_id": proj["id"], "limit": 50}, headers=headers
    )).json()
    tasks = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
    await h.decision(client, headers, proj["id"], "approve finance approval")
    await h.seed_memory(client, headers, proj["id"], f"{name} approval delay")
    await h.drive_full_stack(client, db_session_factory)
    return org, headers, proj, tasks


async def test_claims_retain_canonical_shape(client, db_session_factory):
    org, headers, proj, _ = await _rich_scenario(
        client, db_session_factory, "p4d7_shape@test.co", name="Contract Shape"
    )
    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=headers,
        )
    ).json()
    for claim in answer["claims"]:
        assert set(("claim", "evidence", "confidence", "auth_scope", "timestamp")) <= set(claim), claim
        assert isinstance(claim["confidence"], (int, float)) and 0 <= claim["confidence"] <= 1
        assert isinstance(claim["auth_scope"], dict) and isinstance(claim["auth_scope"].get("scope_ids"), list)
        for ref in claim["evidence"]:
            assert set(("type", "id", "title", "url")) <= set(ref), ref


async def test_answer_carries_persona_timeline_next_questions_chain(client, db_session_factory):
    org, headers, proj, _ = await _rich_scenario(
        client, db_session_factory, "p4d7_unified@test.co", name="Unified Contract"
    )
    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=headers,
        )
    ).json()

# persona-aware scope (4D.7 additive keys; the 4D.6 scope contract holds)
    assert answer["scope"]["org_wide"] is True
    assert answer["scope"] == {"org_wide": True}
    assert "persona" not in answer["scope"]
    assert answer["persona"]["org_wide"] is True
    assert "visible_project_count" in answer["persona"]

    # evidence-backed timeline — every entry references a real row
    assert answer.get("timeline"), answer.get("timeline")
    assert len(answer["timeline"]) <= 6
    for entry in answer["timeline"]:
        assert set(("kind", "id", "title", "url", "occurred_at")) <= set(entry), entry
        assert entry["url"]
    # project anchor should surface its own project timeline rows
    kinds = {e["kind"] for e in answer["timeline"]}
    assert "project_timeline" in kinds or "memory" in kinds

    # deterministic recommended next questions (bounded, never the same question)
    next_qs = answer.get("recommended_next_questions", [])
    assert 1 <= len(next_qs) <= 3
    assert all("who knows" in q.lower() or "happened before" in q.lower() or "changed" in q.lower() for q in next_qs)
    for q in next_qs:
        assert q.lower() not in "why is this project delayed?"

    # causal reasoning chain for a why-shaped question
    chain = answer.get("reasoning_chain", [])
    assert chain, chain
    assert len(chain) <= 6
    for step in chain:
        assert set(("step", "label", "claim", "evidence", "confidence")) <= set(step), step
        assert isinstance(step["step"], int) and step["step"] >= 1
    assert "Current state" in {step["label"] for step in chain}

    # related projections anchored to the entity (when linked intelligence exists)
    assert "related_patterns" in answer or "related_memories" in answer or "related_insights" in answer

    # metrics report the unified composition
    assert answer["metrics"]["timeline_entries"] == len(answer.get("timeline", []))
    assert answer["metrics"]["reasoning_chain_steps"] == len(chain)
    assert answer["metrics"]["recommended_next_questions"] == len(next_qs)


async def test_non_why_question_has_no_chain_but_has_next_questions(client, db_session_factory):
    org, headers, proj, _ = await _rich_scenario(
        client, db_session_factory, "p4d7_nonwhy@test.co", name="Non-Why 4D7"
    )
    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "what changed this week?", "entity_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
    ).json()
    assert "reasoning_chain" not in answer
    assert answer.get("recommended_next_questions")
    # change-shaped questions consult the memory stream and the digest
    assert answer.get("what_changed"), answer.get("what_changed")
    categories = {c["category"] for c in answer["what_changed"]["categories"]}
    assert "new_tasks" in categories
    for category in answer["what_changed"]["categories"]:
        assert "count" in category and "category" in category


async def test_same_question_deterministic_answer(client, db_session_factory):
    org, headers, proj, _ = await _rich_scenario(
        client, db_session_factory, "p4d7_determ@test.co", name="Determinism 4D7"
    )
    payload = {"question": "why is this project delayed?", "entity_type": "project", "entity_id": proj["id"]}
    first = (await client.post("/api/v1/brain/answer", json=payload, headers=headers)).json()
    second = (await client.post("/api/v1/brain/answer", json=payload, headers=headers)).json()
    assert first["summary"] == second["summary"]
    assert first["confidence"] == second["confidence"]
    assert [c["claim"] for c in first["claims"]] == [c["claim"] for c in second["claims"]]
    assert [t["id"] for t in first.get("timeline", [])] == [t["id"] for t in second.get("timeline", [])]
    assert first.get("recommended_next_questions") == second.get("recommended_next_questions")