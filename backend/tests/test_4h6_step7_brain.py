"""Slice 4H.6 - Step 7: Brain routes + narrow performance intents.

Under test (contract §7/§8, L20-L28):

Routes (governance identical to 4H.5: brain:read + org-wide only):
1.  GET  /execution/company/decisions/{id}/performance -> Step 4 assessment.
2.  GET  /execution/company/performance/cohort?kind=&state= -> Step 5 cohort.
3.  POST /execution/company/decisions/compare -> Step 6 comparison;
    engine rejections surface as 409, never silent truncation.
4.  Tenant isolation: unknown AND foreign decision ids -> 404 on the
    single-decision route; foreign ids inside an otherwise-valid comparison
    land in not_found while the valid pair still compares.
5.  Scoped callers get 404 "scope not found" before any engine work.
6.  Deterministic responses at the HTTP layer.

Intents (conservative; appended LAST in _INTENT_RULES):
7.  "how did ... perform"            -> company_decision_performance
8.  "did the decision improve ..."   -> company_measured_change
9.  "compare the outcomes of these decisions" -> company_decision_comparison
    (cohort context + canonical compare route, no verdict)
10. Collision guards: protected phrasings keep their original intents -
    "action plan" (4H.5), "did we act on" chain (4H.5), what-if (4G.7),
    my actions/action center (4E.6), track record/precedent (4H.2),
    outcome intelligence (4E.6).
11. Rule-level order-independence proof: no earlier rule captures the 4H.6
    questions; none of the 4H.6 keywords is a substring of any protected
    phrase.
12. Intent queries write nothing and emit nothing.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.models.business_performance import (
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceLink,
)
from app.models.company_operating import CompanyDecision, CompanyDecisionTrack
from app.models.notification import Event as EventRow
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
BRAIN_QUERY = f"{BRAIN}/knowledge/query"
PERF = "/api/v1/brain/execution/company/decisions/{did}/performance"
COHORT = "/api/v1/brain/execution/company/performance/cohort"
COMPARE = "/api/v1/brain/execution/company/decisions/compare"

_ANCHOR_KW = {"kind": "delay_project", "title": "Delay the platform migration"}


async def _seed_decision(db_session_factory, org_id, decision_id, **kw):
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=decision_id,
            kind=kw.pop("kind", "hire"), title=kw.pop(
                "title", f"Perf {decision_id}"),
            state=kw.pop("state", "approved"),
            approved_at=kw.pop("approved_at", None),
            source_event_id=f"evt:{decision_id}", **kw,
        ))
        await db.commit()


async def _table_stats(db_session_factory, org_id):
    async with db_session_factory() as db:
        stats = {}
        for model in (CompanyDecision, BusinessMetric, BusinessMetricObservation,
                      BusinessPerformanceLink, CompanyDecisionTrack, EventRow):
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "organization_id"):
                stmt = stmt.where(model.organization_id == org_id)
            stats[model.__tablename__] = int(
                (await db.execute(stmt)).scalar_one() or 0)
        return stats


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def test_route_assessment_happy_path(client, db_session_factory):
    org = await register_org(client, email=f"4h6s7_r1_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s7-r1-a",
                         outcome_kind="successful", effectiveness=0.8)

    resp = await client.get(PERF.format(did="dec:s7-r1-a"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"]["decision_id"] == "dec:s7-r1-a"
    assert body["assessed"]["recorded_effectiveness"] == pytest.approx(0.8)
    assert body["observed"]["outcome_record"]["outcome_kind"] == "successful"
    assert body["honesty"]["no_scores"] is True


async def test_route_assessment_404_unknown_and_foreign(client, db_session_factory):
    org = await register_org(client, email=f"4h6s7_r2_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    other = await register_org(client, email=f"4h6s7_r2b_{uuid.uuid4().hex[:6]}@test.co")
    await _seed_decision(db_session_factory,
                         other["organization"]["id"], "dec:s7-foreign")

    resp = await client.get(PERF.format(did="dec:missing"), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "decision not found"

    # tenant isolation: a foreign primary key must not resolve here either
    async with db_session_factory() as db:
        foreign_pk = str((await db.execute(
            select(CompanyDecision.id).where(
                CompanyDecision.decision_id == "dec:s7-foreign")
        )).scalar_one())

    for did in ("dec:s7-foreign", foreign_pk):
        resp = await client.get(PERF.format(did=did), headers=headers)
        assert resp.status_code == 404, did


async def test_route_cohort_filter_and_shape(client, db_session_factory):
    org = await register_org(client, email=f"4h6s7_r3_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s7-r3-a",
                         outcome_kind="successful", effectiveness=0.8)
    await _seed_decision(db_session_factory, org_id, "dec:s7-r3-b",
                         kind="pricing")

    resp = await client.get(COHORT, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cohort"]["decision_count"] == 2
    assert body["cohort"]["derived_on_read"] is True
    assert body["honesty"]["track_infrastructure_untouched"] is True

    resp = await client.get(f"{COHORT}?kind=pricing", headers=headers)
    assert resp.json()["cohort"]["decision_count"] == 1

    resp = await client.get(f"{COHORT}?kind=nope", headers=headers)
    assert resp.json()["cohort"]["decision_count"] == 0


async def test_route_comparison_neutral_and_ordered(client, db_session_factory):
    org = await register_org(client, email=f"4h6s7_r4_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s7-r4-a",
                         outcome_kind="successful", effectiveness=0.9)
    await _seed_decision(db_session_factory, org_id, "dec:s7-r4-b")

    resp = await client.post(COMPARE, json={
        "decision_ids": ["dec:s7-r4-a", "dec:s7-r4-b"],
    }, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["comparison"]["decision_ids"] == ["dec:s7-r4-a", "dec:s7-r4-b"]
    assert body["comparison"]["compare_not_rank"] is True
    assert body["honesty"]["no_ranking_or_winner"] is True


async def test_route_comparison_rejections_are_409_not_truncation(
    client, db_session_factory,
):
    org = await register_org(client, email=f"4h6s7_r5_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    ids = []
    for i in range(6):
        did = f"dec:s7-r5-{i}"
        ids.append(did)
        await _seed_decision(db_session_factory, org_id, did)

    resp = await client.post(COMPARE, json={"decision_ids": ids}, headers=headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["reason"] == "too_many_decisions"
    assert detail["received"] == 6

    resp = await client.post(COMPARE, json={"decision_ids": [ids[0]]},
                             headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason"] == \
        "at_least_two_unique_decisions_required"

    resp = await client.post(COMPARE, json={"decision_ids": [
        ids[0], "dec:ghost-1", "dec:ghost-2"]}, headers=headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["reason"] == "fewer_than_two_resolvable_decisions"
    assert detail["not_found"] == ["dec:ghost-1", "dec:ghost-2"]

    # foreign id inside an otherwise-valid pair: proceeds, id reported
    other = await register_org(client, email=f"4h6s7_r5b_{uuid.uuid4().hex[:6]}@test.co")
    await _seed_decision(db_session_factory,
                         other["organization"]["id"], "dec:s7-r5-foreign")
    resp = await client.post(COMPARE, json={"decision_ids": [
        ids[0], ids[1], "dec:s7-r5-foreign"]}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["comparison"]["not_found"] == ["dec:s7-r5-foreign"]


async def test_route_scoped_caller_blocked_before_engine_work(client):
    org = await register_org(client, email="4h6s7_scope@test.co")
    headers = org["headers"]
    scoped = await invite_scoped_reader(
        client, headers, str(uuid.uuid4()), "4h6s7scoped@test.co")

    resp = await client.get(PERF.format(did="dec:any"), headers=scoped)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "scope not found"
    resp = await client.get(COHORT, headers=scoped)
    assert resp.status_code == 404
    resp = await client.post(COMPARE, json={"decision_ids": ["a", "b"]},
                             headers=scoped)
    assert resp.status_code == 404


async def test_routes_deterministic(client, db_session_factory):
    org = await register_org(client, email=f"4h6s7_r7_{uuid.uuid4().hex[:6]}@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s7-r7-a",
                         outcome_kind="partial", effectiveness=0.6)

    a = (await client.get(PERF.format(did="dec:s7-r7-a"), headers=headers)).json()
    b = (await client.get(PERF.format(did="dec:s7-r7-a"), headers=headers)).json()
    assert a == b


# ---------------------------------------------------------------------------
# Intents + collision guards
# ---------------------------------------------------------------------------

async def _org_with_named_decision(client, db_session_factory, suffix):
    org = await register_org(
        client, email=f"4h6s7_{suffix}_{uuid.uuid4().hex[:6]}@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(
        db_session_factory, org_id, f"dec:s7-{suffix}",
        kind="delay_project", title="Vendor invoicing overhaul",
        outcome_kind="successful", effectiveness=0.85,
    )
    return org, org_id, f"dec:s7-{suffix}"


async def test_intent_performance_resolves_to_assessment(
    client, db_session_factory,
):
    org, _, decision_id = await _org_with_named_decision(
        client, db_session_factory, "ipf")
    res = (await client.post(BRAIN_QUERY, json={"question":
             "how did the decision perform for the vendor invoicing overhaul?"},
             headers=org["headers"])).json()
    assert res["intent"] == "company_decision_performance", res.get("intent")
    assert res["resolved_anchor"]["decision_id"] == decision_id
    assert res["assessed"]["recorded_effectiveness"] == pytest.approx(0.85)


async def test_intent_measured_change_resolves(client, db_session_factory):
    org, org_id, decision_id = await _org_with_named_decision(
        client, db_session_factory, "imc")
    metric = BusinessMetric(
        organization_id=org_id, key="cycle_time", label="Cycle Time",
        kind="velocity", direction="down_is_good", unit="days",
        scope="org_wide", last_value=0.0,
        source_event_id="evt:s7-imc-m")
    async with db_session_factory() as db:
        db.add(metric)
        await db.commit()

    res = (await client.post(BRAIN_QUERY, json={"question":
             "did the decision improve cycle time after the vendor "
             "invoicing overhaul?"}, headers=org["headers"])).json()
    assert res["intent"] == "company_measured_change", res.get("intent")
    assert res["resolved_anchor"]["decision_id"] == decision_id
    assert res["measured"]["metric_count"] >= 0  # honest even when unlinked


async def test_intent_comparison_resolves_to_cohort_and_route_pointer(
    client, db_session_factory,
):
    org, _, _ = await _org_with_named_decision(client, db_session_factory, "icm")
    res = (await client.post(BRAIN_QUERY, json={"question":
             "compare the outcomes of these decisions about the vendor "
             "invoicing overhaul"}, headers=org["headers"])).json()
    assert res["intent"] == "company_decision_comparison", res.get("intent")
    assert res["honesty"]["compare_not_rank"] is True
    assert res["canonical_route"]["path"].endswith("/decisions/compare")
    assert res["cohort"]["cohort"]["decision_count"] == 1
    assert "winner" not in repr(res["canonical_route"]).lower()


async def test_intent_collision_guards_protected_phrases(client):
    org = await register_org(client, email="4h6s7_coll@test.co")
    headers = org["headers"]

    expectations = {
        "what is the action plan for the vendor invoicing overhaul decision?":
            "company_execution_plan",
        "did we act on the vendor invoicing overhaul decision?":
            "company_execution_chain",
        "show me my actions": None,
        "open the action center": None,
        "what if we delay the platform project": None,
        "show me the track record for hiring": None,
        "do we have precedents for this decision": None,
        "show outcome intelligence for this quarter": None,
    }
    for question, expected in expectations.items():
        res = (await client.post(BRAIN_QUERY, json={"question": question},
                                 headers=headers)).json()
        got = res.get("intent")
        assert got not in (
            "company_decision_performance", "company_measured_change",
            "company_decision_comparison",
        ), f"{question!r} stolen by {got}"
        if expected is not None:
            assert got == expected, f"{question!r} -> {got}"


def test_rule_level_collision_proof():
    from app.knowledge.intelligence_engine import _INTENT_RULES

    mine = ("company_decision_performance", "company_measured_change",
            "company_decision_comparison")
    first_idx = min(i for i, (n, _) in enumerate(_INTENT_RULES) if n in mine)
    my_questions = (
        "how did the decision perform",
        "how did that decision perform",
        "did the decision improve customer retention",
        "compare the outcomes of these decisions",
        "performance of the decision",
        "measured change after the decision",
    )
    # conservative placement: nothing EARLIER captures the 4H.6 questions...
    for q in my_questions:
        for name, keywords in _INTENT_RULES[:first_idx]:
            hit = [k for k in keywords if k in q]
            assert not hit, f"{q!r} pre-captured by {name}: {hit}"
    # ...and the full scan resolves them to the 4H.6 intents
    for q in my_questions:
        intent = next(
            n for n, keywords in _INTENT_RULES
            if any(k in q for k in keywords)
        )
        assert intent in mine, q

    protected = (
        "my actions", "action center", "what if we hire", "action plan for",
        "execution chain", "what happened after we decided", "track record",
        "precedent", "outcome intelligence", "next steps for decision",
    )
    my_keywords = [
        k for n, keywords in _INTENT_RULES if n in mine for k in keywords]
    for phrase in protected:
        hits = [k for k in my_keywords if k in phrase]
        assert not hits, f"4H.6 keyword(s) {hits} inside protected {phrase!r}"
        # wherever the phrase routes today, it must NOT route to 4H.6
        for name, keywords in _INTENT_RULES:
            if any(k in phrase.lower() for k in keywords):
                assert name not in mine, \
                    f"{phrase!r} resolves to 4H.6 intent {name}"
                break


async def test_intent_queries_write_nothing(client, db_session_factory):
    org, org_id, decision_id = await _org_with_named_decision(
        client, db_session_factory, "ro")
    headers = org["headers"]
    before = await _table_stats(db_session_factory, org_id)
    for question in (
        "how did the decision perform for the vendor invoicing overhaul?",
        "did the decision improve anything for the vendor invoicing overhaul?",
        "compare these decisions about the vendor invoicing overhaul",
    ):
        res = (await client.post(BRAIN_QUERY, json={"question": question},
                                 headers=headers)).json()
        assert res.get("intent") in (
            "company_decision_performance", "company_measured_change",
            "company_decision_comparison",
        ), res.get("intent")
    after = await _table_stats(db_session_factory, org_id)
    assert before == after
