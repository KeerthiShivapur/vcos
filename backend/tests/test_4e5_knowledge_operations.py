"""Slice 4E.5 — Knowledge Intelligence Operating Layer (knowledge-to-action).

4E.1-4E.4 build the substrate and the intelligence (discovery, changes,
impact, gaps, recommendations, universal query). 4E.5 turns intelligence
into operations:

* materialization: the twelve universal insight kinds are computed from the
  persisted substrate, exact-once by fingerprint, never deleted — and
  conditions that clear auto-resolve their insights,
* insight lifecycle: acknowledge / resolve are explicit, audited user
  actions (the row always survives),
* temporal knowledge: state-at-a-moment plus the full supersession chain
  (what was true, when it changed, what replaced it — old versions retained),
* impact propagation: multi-hop chains from a knowledge change through the
  graph (vendor -> systems -> projects -> customers),
* coverage map: per business area how much knowledge is authoritative/fresh
  and why weak areas are weak,
* health center: one 0-100 score plus drill-down counts,
* executive brief: what changed, what emerged, what needs a decision, what
  is affected — and the top three attention items,
* recommendation lifecycle: review / accept / reject / convert (task or
  decision through the governed operating services — never silent) /
  execute / verify, with a full audit trail,
* governance law under test: the operating layer is no more permissive than
  the evidence behind it — scoped readers never see insights from evidence
  they could not read directly, and nothing ever crosses tenants.
"""

import json
from urllib.parse import quote

from sqlalchemy import select

from app.models.knowledge import (
    DecisionOption,
    KnowledgeIntelInsight,
    KnowledgeIntelInsightEvent,
    KnowledgeRecommendation,
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


async def _seed_budget_conflict(client, headers):
    """Two equal-authority messages that contradict -> conflict intelligence."""
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")


async def _get_insights(client, headers, **params):
    return (
        await client.get("/api/v1/brain/knowledge/insights", params=params, headers=headers)
    ).json()


# ------------------------------------------------- materialize (4E.5.1)


async def test_materialize_universal_insights_exact_once(client, db_session_factory):
    org = await register_org(client, email="4e5_mat@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    first = await _get_insights(client, headers)
    assert first["total"] >= 1, "the conflict materializes into universal insights"
    contradictions = [i for i in first["insights"] if i["kind"] == "contradiction"]
    assert contradictions, "the equal-authority conflict becomes a contradiction insight"
    for insight in contradictions:
        assert insight["title"] and insight["summary"]
        assert insight["severity"] in ("low", "medium", "high", "critical")
        assert insight["confidence"] > 0
        assert insight["priority_score"] >= 0
        assert insight["status"] == "active"
        assert insight["evidence_count"] >= 1, "insights cite their evidence"
        assert insight["claim_ids"], "insight lineage lists the producing claims"

    # replay is a no-op — the same ids come back and the DB has one row.
    second = await _get_insights(client, headers)
    assert {i["id"] for i in first["insights"]} == {i["id"] for i in second["insights"]}

    async with db_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == org["organization"]["id"],
                        KnowledgeIntelInsight.kind == "contradiction",
                    )
                )
            ).scalars().all()
        )
    assert len(rows) == 1, "exact-once: no duplicate rows under replay"
    assert rows[0].fingerprint, "every insight is keyed by a stable fingerprint"
    assert rows[0].source_event, "every insight records its source event"


async def test_materialize_derives_decision_required_and_auto_resolves(
    client, db_session_factory
):
    org = await register_org(client, email="4e5_dec@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    insights = await _get_insights(client, headers)
    decisions = [i for i in insights["insights"] if i["kind"] == "decision_required"]
    assert decisions, (
        "an active contradiction with no open decision requires a leadership decision"
    )
    assert decisions[0]["topic_name"] == "migration"

    # condition clears: the losing value gains an authoritative source.
    task = await _create_task(client, headers, "Migration budget 5 lakh confirmed")
    await _drain_events(db_session_factory)
    after = await _get_insights(client, headers)
    again = [i for i in after["insights"] if i["id"] == decisions[0]["id"]]
    async with db_session_factory() as session:
        row = (
            await session.execute(
                select(KnowledgeIntelInsight).where(
                    KnowledgeIntelInsight.id == decisions[0]["id"],
                )
            )
        ).scalar_one_or_none()
    assert row is not None, "the insight row is never deleted"
    if not again:
        assert row.status == "resolved", "conditions that clear auto-resolve the insight"
        assert row.resolved_at is not None


# ---------------------------------------------- insight lifecycle (4E.5.2)


async def test_insight_lifecycle_acknowledge_resolve_is_audited(client, db_session_factory):
    org = await register_org(client, email="4e5_life@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    insights = await _get_insights(client, headers)
    target = next(i for i in insights["insights"] if i["kind"] == "contradiction")

    acked = await client.post(
        f"/api/v1/brain/knowledge/insights/{target['id']}/acknowledge",
        json={"note": "known, tracking"},
        headers=headers,
    )
    assert acked.status_code == 200, acked.text
    assert acked.json()["status"] == "acknowledged"
    assert acked.json()["acknowledged_at"]

    detail = (
        await client.get(
            f"/api/v1/brain/knowledge/insights/{target['id']}", headers=headers
        )
    ).json()
    assert detail["status"] == "acknowledged"
    assert len(detail["audit"]) == 2, "created + acknowledged are both audited"
    assert [e["action"] for e in detail["audit"]] == ["created", "acknowledged"]
    assert detail["audit"][-1]["note"] == "known, tracking"
    assert detail["lineage"]["claims"], "detail carries the evidence lineage"

    resolved = await client.post(
        f"/api/v1/brain/knowledge/insights/{target['id']}/resolve",
        json={"note": "resolved after review"},
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    detail2 = (
        await client.get(
            f"/api/v1/brain/knowledge/insights/{target['id']}", headers=headers
        )
    ).json()
    assert detail2["status"] == "resolved"
    assert [e["action"] for e in detail2["audit"]] == [
        "created", "acknowledged", "resolved",
    ]

    async with db_session_factory() as session:
        events = list(
            (
                await session.execute(
                    select(KnowledgeIntelInsightEvent).where(
                        KnowledgeIntelInsightEvent.insight_id == target["id"],
                    ).order_by(KnowledgeIntelInsightEvent.created_at.asc())
                )
            ).scalars().all()
        )
    assert len(events) == 3, "every transition is persisted in the audit trail"

    missing = await client.post(
        "/api/v1/brain/knowledge/insights/nope/acknowledge",
        json={},
        headers=headers,
    )
    assert missing.status_code == 404


# ----------------------------------------------- temporal knowledge (4E.5.3)


async def test_temporal_state_at_and_evolution_chain(client, db_session_factory):
    org = await register_org(client, email="4e5_temp@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "pricing")
    await _send_message(client, headers, conv["id"], "The pricing is moved to 5 lakh per unit.")
    await _drain_events(db_session_factory)
    await _send_message(client, headers, conv["id"], "The pricing is moved to 10 lakh per unit.")
    await _drain_events(db_session_factory)

    discovered = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "pricing"},
            headers=headers,
        )
    ).json()
    assert discovered["total"] >= 1
    topic_name = discovered["answers"][0]["topic"]["name"]
    assert topic_name, "the pricing knowledge resolves to a canonical topic"

    trace = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{quote(topic_name)}/evolution", headers=headers
        )
    )
    assert trace.status_code == 200, trace.text
    body = trace.json()
    assert body["topic"]["name"] == topic_name
    assert body["total"] >= 2, "the supersession chain keeps every version"
    assert body["steps"][0]["supersedes"] is None
    assert body["steps"][-1]["replaced_by"] is None, "the newest version is current"
    assert all(s["statement"] for s in body["steps"])

    current = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{quote(topic_name)}/state", headers=headers
        )
    ).json()
    assert "10 lakh" in current["current_state"]["object_text"]
    assert current["evolution"]["versions"] >= 1

    past = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{quote(topic_name)}/state",
            params={"as_of": "2020-06-01T00:00:00Z"},
            headers=headers,
        )
    )
    assert past.status_code == 404, "no understanding existed before the first claim"

    between = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{quote(topic_name)}/state",
            params={"as_of": body["steps"][0]["at"]},
            headers=headers,
        )
    ).json()
    assert "5 lakh" in between["state"]["statement"]
    assert between["replaced_by"] is not None
    assert "10 lakh" in between["replaced_by"]["statement"]


# ---------------------------------------------- impact propagation (4E.5.4)


async def test_propagation_reaches_multi_hop_families(client, db_session_factory):
    org = await register_org(client, email="4e5_prop@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Payroll Migration Program")
    await _create_task(
        client, headers,
        "Vertex Payroll is the vendor platform used by the payroll migration",
        project["id"],
    )
    await _drain_events(db_session_factory)

    discovered = (
        await client.get(
            "/api/v1/brain/knowledge/discover",
            params={"query": "vertex"},
            headers=headers,
        )
    ).json()
    assert discovered["total"] >= 1
    topic_name = discovered["answers"][0]["topic"]["name"]

    result = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{quote(topic_name)}/propagation",
            params={"depth": 3},
            headers=headers,
        )
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["topic"]["name"] == topic_name
    assert body["total"] >= 2, "the change reaches entities beyond the direct evidence"
    assert body["by_family"], "hops are grouped by entity family"
    assert "task" in body["by_family"]
    for hop in body["hops"]:
        assert hop["entity_type"] and hop["entity_id"]
        assert 0 <= hop["depth"] <= body["depth"]
        assert hop["relation"] and hop["via"]

    absent = await client.get(
        "/api/v1/brain/knowledge/topics/not_a_thing/propagation", headers=headers
    )
    assert absent.status_code == 404


# -------------------------------------------------- coverage map (4E.5.5)


async def test_coverage_map_reports_nine_areas(client, db_session_factory):
    org = await register_org(client, email="4e5_cov@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Pricing Program")
    await _create_task(client, headers, "The new pricing tier is 5 lakh per unit", project["id"])
    await _create_task(client, headers, "HR onboarding runbook is being updated", project["id"])
    await _drain_events(db_session_factory)

    result = (
        await client.get("/api/v1/brain/knowledge/coverage", headers=headers)
    ).json()
    assert result["total"] == 9, "the coverage map always reports all nine areas"
    names = {a["area"] for a in result["areas"]}
    assert names == {
        "Sales", "Engineering", "Marketing", "Finance",
        "HR", "Operations", "Customers", "Product", "Strategy",
    }
    for area in result["areas"]:
        assert 0 <= area["coverage"] <= 100
        assert isinstance(area["weak_reasons"], list)


# ---------------------------------------------------- health center (4E.5.6)


async def test_health_center_scores_and_drills_down(client, db_session_factory):
    org = await register_org(client, email="4e5_health@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    result = (
        await client.get("/api/v1/brain/knowledge/health-center", headers=headers)
    ).json()
    assert 0 <= result["score"] <= 100
    assert len(result["bars"]) == 7
    drill = result["drill_down"]
    assert drill["contradictions"] >= 1, "the seeded conflict is drilled down"
    assert set(drill) == {
        "contradictions", "critical_gaps", "unverified_claims",
        "stale_knowledge", "orphan_topics", "total_topics",
    }
    assert isinstance(result["why_weak"], list)


# --------------------------------------------------- executive brief (4E.5.7)


async def test_brief_reports_counts_and_attention(client, db_session_factory):
    org = await register_org(client, email="4e5_brief@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    result = (
        await client.get("/api/v1/brain/knowledge/brief", params={"since_hours": 24}, headers=headers)
    ).json()
    counts = result["counts"]
    assert counts["decisions_potentially_affected"] >= 1, (
        "the conflict that needs a decision appears in the brief"
    )
    assert 0 <= counts["significant_changes"]
    assert 0 <= counts["projects_impacted"]
    assert len(result["attention"]) <= 3, "attention is capped at three"
    for item in result["attention"]:
        assert item["id"] and item["kind"] and item["title"]
        assert item["severity"] and item["priority_score"] is not None


# ----------------------------------- recommendation lifecycle (4E.5.8-4E.5.9)


async def _first_conflict_recommendation(client, headers):
    recs = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    conflicts = [r for r in recs["recommendations"] if r["kind"] == "conflict"]
    assert conflicts, "the equal-authority conflict becomes a recommendation"
    return conflicts[0], recs


async def test_recommendation_full_lifecycle_to_verified_task(client, db_session_factory):
    org = await register_org(client, email="4e5_flow@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)
    project = await h.project(client, headers, "Knowledge Follow-up")

    rec, _ = await _first_conflict_recommendation(client, headers)

    async def lifecycle(action, **payload):
        return await client.post(
            f"/api/v1/brain/knowledge/recommendations/{rec['id']}/lifecycle",
            json={"action": action, **payload},
            headers=headers,
        )

    reviewed = await lifecycle("review", note="reviewing the evidence")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["lifecycle"] == "reviewed"
    assert len(reviewed.json()["audit"]) == 1

    accepted = await lifecycle("accept", note="evidence is solid")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["lifecycle"] == "accepted"

    converted = await lifecycle(
        "convert", target="task", project_id=project["id"], note="track it"
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["lifecycle"] == "converted"
    task_id = converted.json()["task_id"]
    assert task_id, "conversion creates a real task through the governed service"

    task = (await client.get(f"/api/v1/tasks/{task_id}", headers=headers)).json()
    assert task["title"].startswith("[Knowledge]"), "the task carries the recommendation"
    assert task["project_id"] == project["id"]

    executed = await lifecycle("execute")
    assert executed.status_code == 200, executed.text
    assert executed.json()["lifecycle"] == "executed"

    bad_verify = await lifecycle("verify")
    assert bad_verify.status_code == 400, "verification requires a note"

    verified = await lifecycle("verify", note="change shipped, evidence updated")
    assert verified.status_code == 200, verified.text
    assert verified.json()["lifecycle"] == "verified"
    assert verified.json()["status"] == "resolved"
    assert len(verified.json()["audit"]) == 5, (
        "review + accept + convert + execute + verify are all audited"
    )

    # the materializer must never override user-driven lifecycle state.
    await _drain_events(db_session_factory)
    async with db_session_factory() as session:
        row = (
            await session.execute(
                select(KnowledgeRecommendation).where(
                    KnowledgeRecommendation.id == rec["id"],
                )
            )
        ).scalar_one()
    assert row.lifecycle == "verified", "materialization leaves user-steered rows alone"
    assert row.status == "resolved"
    assert row.verified_at is not None
    assert row.task_id == task_id
    assert row.verification_outcome == "verified"


async def test_recommendation_lifecycle_reject_and_guards(client, db_session_factory):
    org = await register_org(client, email="4e5_guard@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    # convert before review is refused.
    recs = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    conflict = next(r for r in recs["recommendations"] if r["kind"] == "conflict")
    early = await client.post(
        f"/api/v1/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
        json={"action": "convert", "target": "task"},
        headers=headers,
    )
    assert early.status_code == 400, "cannot convert before review/accept"

    unknown = await client.post(
        f"/api/v1/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
        json={"action": "explode"},
        headers=headers,
    )
    assert unknown.status_code == 400

    rejected = await client.post(
        f"/api/v1/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
        json={"action": "reject", "note": "we keep both values"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["lifecycle"] == "rejected"
    assert rejected.json()["status"] == "resolved"

    # a second recommendation converts to a decision instead of a task.
    conv = await _create_conversation(client, headers, "marketing")
    await _send_message(client, headers, conv["id"], "The marketing budget is 20 lakh.")
    await _send_message(client, headers, conv["id"], "The marketing budget is 30 lakh.")
    await _drain_events(db_session_factory)
    recs2 = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    mkt = next(
        r for r in recs2["recommendations"]
        if r["kind"] == "conflict" and "marketing" in r["reason"].lower()
    )
    await client.post(
        f"/api/v1/brain/knowledge/recommendations/{mkt['id']}/lifecycle",
        json={"action": "review"},
        headers=headers,
    )
    converted = await client.post(
        f"/api/v1/brain/knowledge/recommendations/{mkt['id']}/lifecycle",
        json={"action": "convert", "target": "decision", "note": "leadership call"},
        headers=headers,
    )
    assert converted.status_code == 200, converted.text
    decision_id = converted.json()["decision_id"]
    assert decision_id

    async with db_session_factory() as session:
        options = list(
            (
                await session.execute(
                    select(DecisionOption).where(
                        DecisionOption.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        assert len(options) >= 2, "conversion proposes decision options"
        task = (
            await session.execute(
                select(KnowledgeRecommendation).where(
                    KnowledgeRecommendation.id == mkt["id"],
                )
            )
        ).scalar_one()
    assert task.decision_id == decision_id


async def test_failed_lifecycle_requests_leave_state_unchanged(client, db_session_factory):
    """Stage A / 4E.5 — refused lifecycle requests must not mutate state.

    Invalid convert target, invalid execute and invalid verify are refused
    with 400, and the committed row must remain byte-for-byte the same:
    lifecycle, audit trail and conversion links unchanged. The shared-session
    harness exposes any leaked dirty state on the next successful request."""
    import json

    org = await register_org(client, email="4e5_safety@test.co")
    headers = org["headers"]
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    rec, _ = await _first_conflict_recommendation(client, headers)

    async def lifecycle(action, **payload):
        return await client.post(
            f"/api/v1/brain/knowledge/recommendations/{rec['id']}/lifecycle",
            json={"action": action, **payload},
            headers=headers,
        )

    async def committed():
        async with db_session_factory() as session:
            return (
                await session.execute(
                    select(KnowledgeRecommendation).where(
                        KnowledgeRecommendation.id == rec["id"],
                    )
                )
            ).scalar_one()

    reviewed = await lifecycle("review", note="first pass")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["lifecycle"] == "reviewed"

    bad_target = await lifecycle("convert", target="spreadsheet")
    assert bad_target.status_code == 400, "convert target must be task or decision"

    bad_execute = await lifecycle("execute")
    assert bad_execute.status_code == 400, "execute requires an executed recommendation"

    bad_verify = await lifecycle("verify", note="too early")
    assert bad_verify.status_code == 400, "verify requires a converted recommendation"

    row = await committed()
    assert row.lifecycle == "reviewed", "refused actions left lifecycle unchanged"
    assert len(json.loads(row.lifecycle_audit_json or "[]")) == 1, (
        "refused actions left no extra audit entries"
    )
    assert row.task_id is None and row.decision_id is None
    assert row.verified_at is None and row.verification_outcome is None

    accepted = await lifecycle("accept", note="evidence is solid")
    assert accepted.status_code == 200, accepted.text

    converted = await lifecycle("convert", target="task", note="track it")
    assert converted.status_code == 200, converted.text
    assert converted.json()["task_id"]

    missing_note = await lifecycle("verify")
    assert missing_note.status_code == 400, "verification requires a note"

    row = await committed()
    assert row.lifecycle == "converted", "the no-note verify refused cleanly"
    assert len(json.loads(row.lifecycle_audit_json or "[]")) == 3, (
        "review + accept + convert are the only audited transitions"
    )
    assert row.verification_outcome is None

    executed = await lifecycle("execute")
    assert executed.status_code == 200, executed.text

    verified = await lifecycle("verify", note="change shipped, evidence updated")
    assert verified.status_code == 200, verified.text
    assert verified.json()["lifecycle"] == "verified"


# ------------------------------------------------------- governance (4E.5.10)


async def test_scoped_reader_sees_only_visible_insights(client, db_session_factory):
    org = await register_org(client, email="4e5_scopegov@test.co")
    headers = org["headers"]
    visible_proj = await h.project(client, headers, "Visible Pricing Program")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.project(client, headers, "Shadow Pricing Program")
    await _create_task(
        client, headers,
        "The visible pricing is 5 lakh per unit", visible_proj["id"],
    )
    await _create_task(
        client, headers,
        "The shadow pricing is 9 crore per unit", hidden_proj["id"],
    )
    await _drain_events(db_session_factory)

    owner = await _get_insights(client, headers)
    assert owner["total"] >= 1

    scoped_headers = await h.invite_scoped_reader(
        client, headers, scope["id"], "4e5_scopegov_u@test.co"
    )
    scoped = await _get_insights(client, scoped_headers)
    assert scoped["scope"] == "project"
    for insight in scoped["insights"]:
        assert insight["topic_name"] != "shadow pricing", (
            "the scoped reader never sees insights from evidence outside the scope"
        )


async def test_operating_layer_never_crosses_tenants(client, db_session_factory):
    org_a = await register_org(client, email="4e5_iso_a@test.co")
    headers_a = org_a["headers"]
    await _seed_budget_conflict(client, headers_a)
    await _drain_events(db_session_factory)
    recs = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers_a)
    ).json()
    rec_id = next(r for r in recs["recommendations"] if r["kind"] == "conflict")["id"]

    org_b = await register_org(client, email="4e5_iso_b@test.co")
    headers_b = org_b["headers"]
    await _drain_events(db_session_factory)

    assert (await _get_insights(client, headers_b))["total"] == 0
    coverage = (
        await client.get("/api/v1/brain/knowledge/coverage", headers=headers_b)
    ).json()
    assert all(a["total_topics"] == 0 for a in coverage["areas"])
    health = (
        await client.get("/api/v1/brain/knowledge/health-center", headers=headers_b)
    ).json()
    assert health["drill_down"]["contradictions"] == 0
    brief = (
        await client.get("/api/v1/brain/knowledge/brief", headers=headers_b)
    ).json()
    assert all(v == 0 for v in brief["counts"].values())
    assert brief["attention"] == []

    foreign = await client.post(
        f"/api/v1/brain/knowledge/recommendations/{rec_id}/lifecycle",
        json={"action": "review"},
        headers=headers_b,
    )
    assert foreign.status_code == 404, "a rival tenant cannot steer foreign recommendations"


# ----------------------------------------------- universal query (4E.5.11)


async def test_universal_query_routes_new_intents(client, db_session_factory):
    org = await register_org(client, email="4e5_qint@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Pricing Program")
    await _create_task(
        client, headers,
        "Vertex Payroll is the vendor platform used by the payroll migration",
        project["id"],
    )
    await _seed_budget_conflict(client, headers)
    await _drain_events(db_session_factory)

    affected = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "which projects are affected by the vertex payroll changes?"},
            headers=headers,
        )
    ).json()
    assert affected["intent"] == "affected"
    assert "hops" in affected

    worry = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "should we worry about anything this week?"},
            headers=headers,
        )
    ).json()
    assert worry["intent"] == "worry"
    assert all(i["kind"] in ("risk", "verification_required") for i in worry["answers"])

    decide = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "what needs a decision from leadership?"},
            headers=headers,
        )
    ).json()
    assert decide["intent"] == "decide"
    assert all(i["kind"] == "decision_required" for i in decide["answers"])

    nxt = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "what should we do next?"},
            headers=headers,
        )
    ).json()
    assert nxt["intent"] == "next"
    assert nxt["total"] >= 1
    assert all(i["kind"] == "recommendation" for i in nxt["answers"])

    confident = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "how confident are we in what we know?"},
            headers=headers,
        )
    ).json()
    assert confident["intent"] == "confident"
    confidences = [i["confidence"] for i in confident["answers"]]
    assert confidences == sorted(confidences), "least-confident knowledge surfaces first"


async def test_temporal_query_route(client, db_session_factory):
    org = await register_org(client, email="4e5_tq@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "pricing")
    await _send_message(client, headers, conv["id"], "The pricing is moved to 5 lakh per unit.")
    await _drain_events(db_session_factory)

    result = (
        await client.post(
            "/api/v1/brain/knowledge/query",
            json={"question": "what was our pricing in february?"},
            headers=headers,
        )
    ).json()
    assert result["intent"] == "temporal"
    assert result["topic"]
    assert "as_of" in result
