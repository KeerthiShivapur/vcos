"""Slice 4E.4 — Knowledge Intelligence.

4E.1-4E.3 build the canonical substrate (sources -> claims -> topics ->
synthesized understanding). 4E.4 turns it into intelligence:

* discovery: a question ("why are enterprise customers delaying renewals?")
  is answered with ranked topics + the exact evidence chain behind each,
* relationship intelligence: the knowledge graph is traversable with typed
  edges, and every neighbor resolves to its canonical claims and topics,
* change intelligence: what changed in our understanding recently, with the
  old understanding preserved ("what was true, what is true now"),
* impact analysis: if this knowledge changes, what else changes (affected
  entities by family, dependent knowledge claims),
* gap intelligence: stale authoritative knowledge, unresolved equal-authority
  contradictions, undocumented processes, thin evidence,
* explainable confidence: every factor behind a confidence score is stated,
* ownership intelligence: who owns a topic's knowledge and with what
  authority/verification,
* knowledge health: seven explainable bars plus what is dragging it down,
* recommendations: deterministic, evidence-backed, persisted exactly-once and
  auto-resolved when the condition clears,
* universal query: natural questions route to the matching intelligence.

Governance law under test: NO intelligence may be more permissive than the
evidence used to produce it — scoped readers never see derived insights from
evidence they could not read directly.
"""

import json

from sqlalchemy import select

from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeRecommendation,
    KnowledgeSource,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _drain_events(db_session_factory, limit=400):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _create_conversation(client, headers, title="ops-room"):
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    created = await client.post(
        "/api/v1/conversations",
        json={"type": "channel", "title": title, "member_ids": [me]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _send_message(client, headers, conversation_id, content):
    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )
    assert sent.status_code in (200, 201), sent.text
    return sent.json()


async def _create_task(client, headers, title, project_id=None):
    payload = {"title": title}
    if project_id:
        payload["project_id"] = project_id
    created = await client.post("/api/v1/tasks", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _record_memory(client, headers, title, content, tags):
    recorded = await client.post(
        "/api/v1/brain/memory",
        json={
            "memory_type": "lesson",
            "title": title,
            "content": content,
            "tags": tags,
            "importance": "medium",
        },
        headers=headers,
    )
    assert recorded.status_code in (200, 201), recorded.text
    return recorded.json()


async def _create_policy(client, headers, title, content):
    created = await client.post(
        "/api/v1/policies",
        json={"title": title, "content": content, "category": "renewal"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    await client.post(f"/api/v1/policies/{policy['id']}/submit", headers=headers)
    approved = await client.post(
        f"/api/v1/policies/{policy['id']}/approve", headers=headers
    )
    assert approved.status_code == 200, approved.text
    return policy


# ------------------------------------------------------------ discovery (4.4.1)


async def test_discovery_connects_cross_family_evidence(client, db_session_factory):
    org = await register_org(client, email="4e4_disc@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Enterprise Renewal Program")
    await _create_task(
        client, headers,
        "Enterprise renewals are increasingly delayed by legal review",
        project["id"],
    )
    conv = await _create_conversation(client, headers, "renewals")
    await _send_message(
        client, headers, conv["id"],
        "Two enterprise customers pushed their renewals out this quarter "
        "and the review window was extended.",
    )
    await _record_memory(
        client, headers, "Renewal delays",
        "Renewals are increasingly delayed — correlates with the new pricing review process.",
        ["renewal", "delay"],
    )
    await _drain_events(db_session_factory)

    result = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "why are enterprise customers delaying renewals?"},
            headers=headers,
        )
    ).json()
    assert result["intent"] == "discovery"
    assert result["total"] >= 1
    top = result["answers"][0]
    assert top["statement"], "the discovery answer carries the understanding"
    assert top["claim_id"], "the answer links to the synthesis claim"
    assert top["confidence"] is not None
    assert "renewal" in top["topic"]["name"].lower()
    assert set(top["families"]) >= {"task", "message", "memory"}, (
        "cross-family evidence is connected into one intelligence answer"
    )
    assert len(top["evidence"]) >= 3, "the evidence chain is attached"
    assert all(e["claim_id"] and e["excerpt"] for e in top["evidence"])
    assert top["score"] > 0, "deterministic relevance score is populated"

    empty = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "quantum cryptanalysis workshop"},
            headers=headers,
        )
    ).json()
    assert empty["total"] == 0


async def test_discovery_governance_constrains_intelligence(client, db_session_factory):
    org = await register_org(client, email="4e4_discgov@test.co")
    headers = org["headers"]
    visible_proj = await h.project(client, headers, "Visible Renewal Program")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.project(client, headers, "Shadow Renewal Program")
    visible_task = await _create_task(client, headers, "Enterprise renewal delay analysis", visible_proj["id"])
    hidden_task = await _create_task(client, headers, "Stealth renewal delay review", hidden_proj["id"])
    await _drain_events(db_session_factory)

    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4e4_discgov_u@test.co")

    visible = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "enterprise renewal delay"},
            headers=scoped,
        )
    ).json()
    assert visible["total"] >= 1
    for answer in visible["answers"]:
        for item in answer["evidence"]:
            assert item["subject_id"] == visible_task["id"], (
                "no derived insight from evidence outside the scope"
            )

    org_wide = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "enterprise renewal delay"},
            headers=headers,
        )
    ).json()
    assert org_wide["total"] >= 1
    ids = {item["subject_id"] for a in org_wide["answers"] for item in a["evidence"]}
    assert ids == {visible_task["id"], hidden_task["id"]}, (
        "org-wide intelligence sees all evidence"
    )


# ------------------------------------------------ relationship intelligence (4.4.2)


async def test_relationship_intelligence_traverses_typed_edges(client, db_session_factory):
    org = await register_org(client, email="4e4_rel@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    task = await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration window is confirmed for 2am.")
    await _record_memory(
        client, headers, "Migration go-live",
        "The migration go-live has been agreed for Monday.",
        ["migration"],
    )
    await _drain_events(db_session_factory)

    result = (
        await client.get(
            f"/api/v1/brain/knowledge/entities/task/{task['id']}/relations",
            headers=headers,
        )
    ).json()
    assert result["entity"] == {"type": "task", "id": task["id"]}
    assert result["total"] >= 2, "the graph around the task resolves"
    by_type = {n["type"] for n in result["neighbors"]}
    assert by_type >= {"message", "memory"}, "typed edges reach other families"
    message_neighbor = next(n for n in result["neighbors"] if n["type"] == "message")
    assert message_neighbor["relations"], "every neighbor carries its edge relation"
    assert any(r["relation"] == "relates_to" for r in message_neighbor["relations"])
    assert message_neighbor["topics"], "neighbor resolves to its canonical topics"


# --------------------------------------------------- change intelligence (4.4.3)


async def test_change_intelligence_shows_old_and_new(client, db_session_factory):
    org = await register_org(client, email="4e4_chg@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration is scheduled for Friday.")
    await _drain_events(db_session_factory)
    await _send_message(client, headers, conv["id"], "The migration is moved to next Monday.")
    await _drain_events(db_session_factory)

    result = (
        await client.get(
            "/api/v1/brain/knowledge/changes", params={"days": 30}, headers=headers
        )
    ).json()
    assert result["total"] >= 1
    entry = result["topic_changes"][0]
    assert entry["topic"]["name"] == "migration"
    events = [e for e in entry["events"] if e["kind"] == "understanding"]
    assert events, "the understanding evolution is surfaced"
    change = events[-1]
    assert "Friday" in change["from"] and "Monday" in change["to"], (
        "old understanding is preserved next to the new one"
    )
    assert change["claim_id"] and change["supersedes_claim_id"]


# ------------------------------------------------------- impact analysis (4.4.3)


async def test_impact_analysis_finds_affected_entities(client, db_session_factory):
    org = await register_org(client, email="4e4_impact@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    task = await _create_task(client, headers, "Migration runbook", project["id"])
    other_proj = await h.project(client, headers, "Customer Deployments")
    dependent = await _create_task(
        client, headers, "Deploy migration changes to enterprise customers",
        other_proj["id"],
    )
    decision = await h.decision(
        client, headers, other_proj["id"], "approve migration rollout"
    )
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration window is confirmed for 2am.")
    await _drain_events(db_session_factory)

    result = (
        await client.get(
            "/api/v1/brain/knowledge/topics/migration/impact", headers=headers
        )
    ).json()
    assert result["topic"]["name"] == "migration"
    assert result["evidence"]["total"] >= 3
    dependent_ids = {d["subject_id"] for d in result["dependent_knowledge"]["claims"]}
    assert dependent["id"] in dependent_ids, (
        "dependent work that quotes the knowledge is listed"
    )
    assert result["dependent_knowledge"]["total"] >= 1
    assert result["affected"]["total"] >= 1
    families = set(result["affected"]["by_family"])
    assert "project" in families, (
        "entities anchored to the evidence (belongs_to) are grouped by family"
    )
    assert result["affected"]["by_family"]["project"]["count"] >= 1
    assert result["affected"]["by_family"]["project"]["entities"], (
        "affected entities resolve with their edge relations"
    )


# ------------------------------------------------------ gap intelligence (4.4.4)


async def test_gaps_surface_unresolved_conflict_and_undocumented_process(
    client, db_session_factory
):
    org = await register_org(client, email="4e4_gaps@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")
    await _drain_events(db_session_factory)

    gaps = (
        await client.get("/api/v1/brain/knowledge/gaps", headers=headers)
    ).json()
    contradiction_gaps = [g for g in gaps["gaps"] if g["kind"] == "contradiction"]
    assert contradiction_gaps, "the equal-authority conflict is a live gap"
    gap = contradiction_gaps[0]
    assert "5 lakh" in gap["reason"] and "10 lakh" in gap["reason"]
    assert gap["severity"] == "medium"
    assert len(gap["pair_ids"]) == 2

    # undocumented process: repeated behavior (pattern family) with no
    # documented procedure on the same topic.
    blocked = await h.blocked_project(client, headers, count=3, name="Incident Handling")
    await h.drain_events(db_session_factory)
    await h.run_patterns(db_session_factory)
    await _drain_events(db_session_factory)
    async with db_session_factory() as session:
        patterns = list(
            (
                await session.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == org["organization"]["id"],
                        KnowledgeSource.source_type == "pattern",
                    )
                )
            ).scalars().all()
        )
    assert patterns, "the pattern pipeline produced canonical pattern sources"

    gaps = (
        await client.get("/api/v1/brain/knowledge/gaps", headers=headers)
    ).json()
    undocumented = [g for g in gaps["gaps"] if g["kind"] == "undocumented_process"]
    assert undocumented, "repeated behavior without a documented procedure is a gap"


async def test_gaps_surface_stale_authoritative_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e4_stale@test.co")
    headers = org["headers"]
    policy = await _create_policy(
        client, headers, "Enterprise renewal policy",
        "Enterprise renewals require a 90 day notice period.",
    )
    await _drain_events(db_session_factory)
    async with db_session_factory() as session:
        source = (
            await session.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.organization_id == org["organization"]["id"],
                    KnowledgeSource.source_type == "policy",
                    KnowledgeSource.source_id == policy["id"],
                )
            )
        ).scalar_one()
        assert source.authority_level == 5, "approved policy is official knowledge"
        source.freshness_score = 10
        source.freshness_label = "stale"
        source.last_verified_at = None
        await session.commit()

    gaps = (
        await client.get("/api/v1/brain/knowledge/gaps", headers=headers)
    ).json()
    stale = [g for g in gaps["gaps"] if g["kind"] == "stale"]
    assert stale, "stale authoritative knowledge is surfaced"
    assert stale[0]["topic"]["name"] == "renewal"
    assert "official" in stale[0]["reason"] or "authoritative" in stale[0]["reason"]
    assert stale[0]["severity"] == "high"


# ----------------------------------------------- explainable confidence (4.4.6)


async def test_confidence_breakdown_explains_factors(client, db_session_factory):
    org = await register_org(client, email="4e4_conf@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "ops")
    await _send_message(client, headers, conv["id"], "The migration is scheduled for 2am.")
    await _drain_events(db_session_factory)

    async with db_session_factory() as session:
        claims = list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org["organization"]["id"],
                        KnowledgeClaim.claim_type == "synthesis",
                    )
                )
            ).scalars().all()
        )
    assert len(claims) == 1
    detail = (
        await client.get(
            f"/api/v1/brain/knowledge/claims/{claims[0].id}/confidence",
            headers=headers,
        )
    ).json()
    assert detail["claim_id"] == claims[0].id
    names = {f["name"] for f in detail["factors"]}
    assert names >= {
        "authority", "evidence strength", "freshness", "agreement",
        "consistency", "source diversity", "staleness penalty",
    }
    for factor in detail["factors"]:
        assert "detail" in factor and "weight" in factor and "sign" in factor
    assert detail["confidence"] == detail["recorded_confidence"], (
        "the breakdown recomputes the recorded confidence"
    )
    assert "0.35" in detail["explanation"]

    hidden = await client.get(
        f"/api/v1/brain/knowledge/claims/{claims[0].id}/confidence",
        headers={"Authorization": "Bearer invalid"},
    )
    assert hidden.status_code in (401, 403)


# ------------------------------------------------------- ownership (4.4.6)


async def test_ownership_resolves_author_and_reports_missing(client, db_session_factory):
    org = await register_org(client, email="4e4_own@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Onboarding Program")
    await _create_task(client, headers, "Onboarding runbook", project["id"])
    conv = await _create_conversation(client, headers, "general")
    await _send_message(client, headers, conv["id"], "Onboarding now starts with a buddy check-in and the first week plan was approved by operations.")
    await _record_memory(
        client, headers, "Procurement delays",
        "Procurement is holding up the rollout.",
        ["procurement"],
    )
    await _drain_events(db_session_factory)

    owned = (
        await client.get(
            "/api/v1/brain/knowledge/topics/onboarding/ownership", headers=headers
        )
    ).json()
    assert owned["topic"]["name"] == "onboarding"
    assert owned["owner"]["resolved"] is True, (
        "the author falls back to the highest-authority source that has one"
    )
    assert owned["owner"]["employee_id"], "the owner resolves to a real employee"
    assert owned["authority"]["level"] == 2
    assert owned["freshness_label"] in ("very_high", "high")
    assert owned["last_verified_at"]

    missing = (
        await client.get(
            "/api/v1/brain/knowledge/topics/procurement/ownership", headers=headers
        )
    ).json()
    assert missing["owner"]["resolved"] is False, (
        "memory carries no author — ownership is reported missing"
    )
    assert missing["source"]["type"] == "memory"

    absent = await client.get(
        "/api/v1/brain/knowledge/topics/missing_thing/ownership", headers=headers
    )
    assert absent.status_code == 404


# ----------------------------------------------------------- health (4.4.6)


async def test_health_reports_seven_bars_and_why_weak(client, db_session_factory):
    org = await register_org(client, email="4e4_health@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "ops")
    await _send_message(client, headers, conv["id"], "The migration is delayed by 2 days.")
    await _drain_events(db_session_factory)

    result = (
        await client.get("/api/v1/brain/knowledge/health", headers=headers)
    ).json()
    assert result["total_topics"] >= 1
    assert len(result["bars"]) == 7
    names = {b["name"] for b in result["bars"]}
    assert names == {
        "coverage", "freshness", "evidence_quality",
        "contradiction_resolution", "ownership", "documentation",
        "cross_team_consistency",
    }
    for bar in result["bars"]:
        assert 0 <= bar["value"] <= 100
        assert bar["detail"]
    assert 0 <= result["health_score"] <= 100
    assert isinstance(result["why_weak"], list)


# ------------------------------------------- recommendations (4.4.7, exact-once)


async def test_recommendations_persist_exactly_once_and_resolve(client, db_session_factory):
    org = await register_org(client, email="4e4_rec@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")
    await _drain_events(db_session_factory)

    first = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    conflicts = [r for r in first["recommendations"] if r["kind"] == "conflict"]
    assert conflicts, "the equal-authority conflict becomes a recommendation"
    conflict = conflicts[0]
    assert conflict["reason"], "every recommendation states why"
    assert len(conflict["evidence"]) == 2, "recommendations cite their claims"
    assert conflict["risk"] == "medium"

    second = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    again = [r for r in second["recommendations"] if r["id"] == conflict["id"]]
    assert again, "re-materialization is a no-op — exact-once"
    async with db_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == org["organization"]["id"],
                        KnowledgeRecommendation.kind == "conflict",
                    )
                )
            ).scalars().all()
        )
    assert len(rows) == 1, "no duplicate rows under replay"

    # condition clears: the losing value gains an authoritative source.
    task = await _create_task(client, headers, "Migration budget 5 lakh confirmed")
    await _drain_events(db_session_factory)
    resolved = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    remaining = [
        r for r in resolved["recommendations"]
        if r["kind"] == "conflict" and r["fingerprint"] == conflict["fingerprint"]
    ]
    if not remaining:
        async with db_session_factory() as session:
            row = (
                await session.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.organization_id == org["organization"]["id"],
                        KnowledgeRecommendation.kind == "conflict",
                    )
                )
            ).scalar_one()
            assert row.status == "resolved", (
                "a condition that clears resolves the recommendation"
            )
            assert row.resolved_at is not None


# --------------------------------------------------- universal query (4.4.8)


async def test_universal_query_routes_intents(client, db_session_factory):
    org = await register_org(client, email="4e4_query@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration window is confirmed for 2am.")
    await _drain_events(db_session_factory)

    changed = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "what changed in our understanding this week?"},
            headers=headers,
        )
    ).json()
    assert changed["intent"] == "changes"
    assert changed["window_days"] == 7

    known = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "what do we know about the migration?"},
            headers=headers,
        )
    ).json()
    assert known["intent"] == "discovery"
    assert known["total"] >= 1
    assert known["answers"][0]["topic"]["name"] == "migration"

    owner = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "who owns the migration knowledge?"},
            headers=headers,
        )
    ).json()
    assert owner["intent"] == "ownership"
    assert owner["owner"]["resolved"] is True

    health = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "how healthy is our knowledge?"},
            headers=headers,
        )
    ).json()
    assert health["intent"] == "health"
    assert len(health["bars"]) == 7


# ----------------------------------------------------------- tenant isolation


async def test_intelligence_never_crosses_tenants(client, db_session_factory):
    org_a = await register_org(client, email="4e4_iso_a@test.co")
    headers_a = org_a["headers"]
    conv = await _create_conversation(client, headers_a, "release")
    await _send_message(client, headers_a, conv["id"], "The migration is happening Friday.")
    await _drain_events(db_session_factory)

    org_b = await register_org(client, email="4e4_iso_b@test.co")
    headers_b = org_b["headers"]
    await _drain_events(db_session_factory)

    discovered = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "migration"},
            headers=headers_b,
        )
    ).json()
    assert discovered["total"] == 0, "rival tenant discovers nothing"
    gaps = (await client.get("/api/v1/brain/knowledge/gaps", headers=headers_b)).json()
    assert gaps["total"] == 0
    health = (await client.get("/api/v1/brain/knowledge/health", headers=headers_b)).json()
    assert health["total_topics"] == 0
    recs = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers_b)
    ).json()
    assert recs["total"] == 0

    state = (
        await client.get(
            "/api/v1/brain/knowledge/topics/migration/impact", headers=headers_b
        )
    )
    assert state.status_code == 404
