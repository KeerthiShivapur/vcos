"""Slice 4E.7 — the Universal Knowledge Operating Loop.

The final bridge of the Knowledge Intelligence family: NOT another isolated
silver — it makes 4E.1..4E.6 behave as one company-wide intelligence system.

* learning loop: verified outcome -> assessment -> lesson with evidence ->
  canonical knowledge lifecycle (tested/confirmed) -> recommendation feedback,
  exact-once under replay,
* knowledge lifecycle: claims advance discovered -> candidate -> supported ->
  authoritative -> superseded (`KnowledgeClaimLifecycle` stage ledger) and are
  never deleted,
* temporal memory: company changes are materialized deterministically from the
  governed substrate (action verified / learning recorded / decisions /
  customer impact / high-severity risk), grouped critical / important / normal,
* dependency graph + impact analysis: 'if we change X what does it reach?' —
  bounded BFS over claim links and governed actions, persisted,
* contradiction -> resolution -> learning: settle by authority, losing evidence
  stays as historical truth,
* decision & recommendation feedback: expected vs actual -> measured decision
  outcome + recommendation quality by kind,
* What-Changed + Company Health: explainable only — every signal carries
  metric / evidence / window / confidence / explanation, no fake scores,
* Universal Action Center: one consolidated governed board with ten
  categories, resolvable by humans (never deleted),
* risk ladder: LOW automatic / MEDIUM approval / HIGH explicit human,
* governance & tenant isolation: scoped readers only ever see what their
  governance grants them; tenant boundaries hold,
* the universal query answers 'what changed / what did we learn / company
  health / why' from the SAME canonical knowledge model.
"""

import datetime
import json

from sqlalchemy import select, update

from app.models.company_actions import CompanyAction
from app.models.knowledge import KnowledgeClaim
from app.models.organizational_learning import (
    CompanyChange,
    CompanyHealthSignal,
    DecisionOutcome,
    KnowledgeClaimLifecycle,
    OrganizationalLearning,
    OutcomeAssessment,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

API = "/api/v1/brain/knowledge"
LOOP = f"{API}/loop"
ACTIONS = "/api/v1/brain/knowledge/actions"


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


async def _seed_conflict(client, headers):
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")


async def _propose(client, headers, action_type="task", title="Act on the conflict",
                   risk="medium", **extra):
    body = {"action_type": action_type, "title": title, "risk": risk, **extra}
    return await client.post(ACTIONS, json=body, headers=headers)


async def _conflict_recommendation(client, headers):
    recs = (
        await client.get(f"{API}/recommendations", headers=headers)
    ).json()
    return next(r for r in recs["recommendations"] if r["kind"] == "conflict")


async def _transition(client, headers, action_id, transition, **extra):
    return await client.post(
        f"{ACTIONS}/{action_id}/transition",
        json={"transition": transition, **extra}, headers=headers,
    )


async def _verify_action(client, headers, action):
    for tr, kw in (("assign", {"assignee_id": "me"}), ("start", {"note": "go"}),
                   ("complete", {"note": "done"}), ("verify", {"note": "verified"})):
        r = await _transition(client, headers, action["id"], tr, **kw)
        assert r.status_code in (200, 201), r.text
    return (await client.get(f"{ACTIONS}/{action['id']}", headers=headers)).json()


async def _close_loop(client, headers, action_id, actual, expected=100.0,
                      metric="the intended result", factors=None, summary=None):
    return await client.post(
        f"{LOOP}/outcomes",
        json={"action_id": action_id, "expected_metric": metric,
              "expected_value": expected, "actual_value": actual,
              "factors": factors or [], "summary": summary},
        headers=headers,
    )


# ---------------------------------------------------------------- learning loop


async def test_outcome_learning_closes_the_loop(client, db_session_factory):
    org = await register_org(client, email="4e7_loop@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    action = (await _propose(client, headers, title="Land the migration", risk="low")).json()
    await _verify_action(client, headers, action)

    r = await _close_loop(client, headers, action["id"], actual=40.0, expected=100.0,
                          metric="target users reached", factors=["late vendor delivery"],
                          summary="rollout landed late and short")
    assert r.status_code == 200, r.text
    learning = r.json()["learning"]
    assert learning["kind"] == "outcome_learning"
    assert learning["status"] in ("active", "learned")

    assessment = r.json()["assessment"]
    assert assessment["assessment"] == "underperformed"
    assert assessment["subject_type"] == "action"
    assert assessment["subject_id"] == action["id"]
    assert 50.0 <= abs(assessment["variance_pct"]) <= 70.0, "|40-100|/100"

    assert r.json()["claims_advanced"] is not None, "lifecycle items advanced"
    assert "recommendation_feedback" in r.json()

    # evidence trail persisted
    async with db_session_factory() as session:
        row = (
            await session.execute(
                select(OrganizationalLearning).where(
                    OrganizationalLearning.organization_id == org_id,
                    OrganizationalLearning.id == learning["id"]))
        ).scalar_one_or_none()
        assert row is not None
        ev = json.loads(row.evidence_json)
        assert "assessment" in ev, ev
        assert "action" in ev, ev
        await session.rollback()

    # the same action is a learning opportunity in the Universal Action Center
    center = (await client.get(f"{LOOP}/insights", headers=headers)).json()
    assert any(c == "learning_opportunity" for c in center["categories"]), center["by_category"]


async def test_learning_rejected_when_action_not_verified(client):
    org = await register_org(client, email="4e7_notver@test.co")
    headers = org["headers"]
    action = (await _propose(client, headers, title="Never finished", risk="low")).json()
    r = await _close_loop(client, headers, action["id"], actual=10.0)
    assert r.status_code == 400, "learning requires a verified action"


async def test_learning_is_exact_once_under_replay(client, db_session_factory):
    org = await register_org(client, email="4e7_replay@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    action = (await _propose(client, headers, title="Idempotent action", risk="low")).json()
    await _verify_action(client, headers, action)

    first = (await _close_loop(client, headers, action["id"], actual=55.0)).json()
    second = (await _close_loop(client, headers, action["id"], actual=55.0)).json()
    assert first["learning"]["id"] == second["learning"]["id"], "replay returns the same lesson"

    async with db_session_factory() as session:
        nl = len(
            (
                await session.execute(
                    select(OrganizationalLearning).where(
                        OrganizationalLearning.organization_id == org_id))
            ).scalars().all()
        )
        na = len(
            (
                await session.execute(
                    select(OutcomeAssessment).where(
                        OutcomeAssessment.organization_id == org_id))
            ).scalars().all()
        )
        nc = len(
            (
                await session.execute(
                    select(CompanyChange).where(
                        CompanyChange.organization_id == org_id))
            ).scalars().all()
        )
        assert nl == 1, "one lesson ever"
        assert na == 1, "one assessment ever"
        await session.rollback()
    # replay must not fabricate new change feed rows
    assert nc == 1, "one company change row (post-verification learning)"


async def test_learning_advances_canonical_claim_lifecycle(client, db_session_factory):
    org = await register_org(client, email="4e7_lifecycle@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _seed_conflict(client, headers)
    await _drain_events(db_session_factory)
    rec = await _conflict_recommendation(client, headers)

    claim_ids = rec.get("evidence", [])
    async with db_session_factory() as session:
        pre = {
            c.id: c.status
            for c in (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org_id,
                        KnowledgeClaim.id.in_(claim_ids)))
            ).scalars().all()
        }
        await session.rollback()
    assert pre, "the recommendation's evidence claims exist"

    action = (await _propose(client, headers, source_recommendation_id=rec["id"])).json()
    await _transition(client, headers, action["id"], "approve", note="ok")
    for tr, kw in (("assign", {"assignee_id": "me"}), ("start", {"note": "go"}),
                   ("complete", {"note": "done"}), ("verify", {"note": "verified"})):
        await _transition(client, headers, action["id"], tr, **kw)
    r = await _close_loop(client, headers, action["id"], actual=95.0, expected=100.0)
    assert r.status_code == 200, r.text

    async with db_session_factory() as session:
        stages = (
            await session.execute(
                select(KnowledgeClaimLifecycle).where(
                    KnowledgeClaimLifecycle.organization_id == org_id))
        ).scalars().all()
        stage_rows = {s.claim_id: s for s in stages if s.claim_id in claim_ids}
        assert stage_rows, "lifecycle ledger records the claims involved"
        for claim_id, old_status in pre.items():
            assert stage_rows[claim_id].stage == "confirmed", (
                claim_id, old_status, stage_rows[claim_id].stage)
            assert stage_rows[claim_id].reason, "reason recorded"
            assert stage_rows[claim_id].evidence_json, "evidence linkage"
            assert stage_rows[claim_id].learning_id, "learning linkage"
        await session.rollback()


async def test_assess_without_learning_is_idempotent_upsert(client, db_session_factory):
    org = await register_org(client, email="4e7_assess@test.co")
    headers = org["headers"]
    action = (await _propose(client, headers, title="Assessable action",
                             risk="low")).json()

    body = {"subject_type": "action", "subject_id": action["id"],
            "expected_metric": "messages", "expected_value": 50.0,
            "actual_value": 48.0, "summary": "slightly under"}
    r1 = await client.post(f"{LOOP}/assessments", json=body, headers=headers)
    r2 = await client.post(f"{LOOP}/assessments", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"], "exact-once upsert"
    assert r1.json()["assessment"] == "met"

    ledger = (await client.get(f"{LOOP}/assessments", headers=headers)).json()
    assert ledger["total"] == 1, "upsert, never a duplicate"
    assert abs(ledger["assessments"][0]["variance_pct"]) == 4.0


# ------------------------------------------------------- decision & recommendation


async def test_decision_feedback_loop(client, db_session_factory):
    org = await register_org(client, email="4e7_decision@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    created = await client.post(
        "/api/v1/decisions",
        json={"title": "Adopt phased migration", "description": "decision", "status": "made"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    decision_id = created.json()["id"]

    r = await client.post(
        f"{LOOP}/decisions/{decision_id}/outcome",
        json={"expected_metric": "timeline days", "expected_value": 100.0,
              "actual_value": 30.0, "expected_units": "days",
              "factors": ["vendor delay"], "summary": "phasing drifted"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_outcome"]["decision_id"] == decision_id
    assert body["decision_outcome"]["assessment"] == "underperformed"
    assert body["learning"]["kind"] in ("outcome_learning", "decision_learning")

    performance = (await client.get(f"{LOOP}/decisions", headers=headers)).json()
    assert performance["total"] == 1
    assert abs(performance["decisions"][0]["variance_pct"]) == 70.0, "|30-100|/100"

    # idempotent: replaying the feedback replaces nothing and duplicates nothing
    r2 = await client.post(
        f"{LOOP}/decisions/{decision_id}/outcome",
        json={"expected_metric": "timeline days", "expected_value": 100.0,
              "actual_value": 30.0, "expected_units": "days"},
        headers=headers,
    )
    assert r2.status_code == 200
    async with db_session_factory() as session:
        n = len(
            (
                await session.execute(
                    select(DecisionOutcome).where(
                        DecisionOutcome.organization_id == org_id))
            ).scalars().all()
        )
        assert n == 1
        await session.rollback()


async def test_recommendation_quality_from_outcomes(client, db_session_factory):
    org = await register_org(client, email="4e7_recq@test.co")
    headers = org["headers"]
    await _seed_conflict(client, headers)
    conv2 = await _create_conversation(client, headers, "lease")
    await _send_message(client, headers, conv2["id"], "The office lease budget is 5 lakh.")
    await _send_message(client, headers, conv2["id"], "The office lease budget is 10 lakh.")
    await _drain_events(db_session_factory)
    rec = await _conflict_recommendation(client, headers)

    async def _loop(rec_id, title, actual, expected):
        a = (await _propose(client, headers, title=title, risk="low",
                            source_recommendation_id=rec_id)).json()
        for tr, kw in (("assign", {"assignee_id": "me"}), ("start", {"note": "go"}),
                       ("complete", {"note": "done"}), ("verify", {"note": "v"})):
            await _transition(client, headers, a["id"], tr, **kw)
        r = await _close_loop(client, headers, a["id"], actual=actual, expected=expected)
        assert r.status_code == 200
        return r.json()["recommendation_feedback"]

    recs = (await client.get(f"{API}/recommendations", headers=headers)).json()
    recs = [r for r in recs["recommendations"] if r["kind"] == "conflict"]
    assert len(recs) >= 2, recs
    met = await _loop(recs[0]["id"], "Well-met recommendation", 95.0, 100.0)
    miss = await _loop(recs[1]["id"], "Missed recommendation", 20.0, 100.0)
    assert met is not None and miss is not None
    assert met["success"] is True and miss["success"] is False

    quality = (await client.get(f"{LOOP}/recommendation-quality", headers=headers)).json()
    assert quality["generated_at"]
    kinds = {row["kind"]: row for row in quality["kinds"]}
    assert kinds["conflict"]["measured"] == 2, kinds
    assert kinds["conflict"]["successes"] == 1
    assert kinds["conflict"]["success_rate"] == 0.5
    assert kinds["conflict"]["adjusted_confidence"] == 0.5
    assert quality["total_measured"] == 2


# ------------------------------------------------ contradiction resolution


async def test_contradiction_resolution_is_learned(client, db_session_factory):
    org = await register_org(client, email="4e7_contra@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _seed_conflict(client, headers)
    await _drain_events(db_session_factory)
    rec = await _conflict_recommendation(client, headers)

    claims = (
        await client.get(f"{API}/claims", headers=headers)
    ).json()
    budget_claims = [c for c in claims["claims"] if "migration budget" in c["object_text"]]
    assert len(budget_claims) >= 2, "two conflicting claims exist"

    contra = (
        await client.get(f"{API}/topics/migration/contradictions", headers=headers)
    ).json()
    assert contra["total"] >= 1, contra
    pair = contra["contradictions"][0]
    authoritative = pair["winner_claim_id"]
    challenger = pair["loser_claim_id"]
    assert authoritative != challenger

    r = await client.post(
        f"{LOOP}/contradictions/migration/resolution",
        json={"authoritative_claim_id": authoritative,
              "reason": "finance confirmed 10 lakh at the board"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authoritative_claim_id"] == authoritative
    assert body["retained_conflicting"], "losing claims remain as historical evidence"
    assert authoritative in body["claims_advanced"], body["claims_advanced"]

    # the authoritative claim advanced to confirmed in the lifecycle ledger
    async with db_session_factory() as session:
        stage = (
            await session.execute(
                select(KnowledgeClaimLifecycle).where(
                    KnowledgeClaimLifecycle.organization_id == org_id,
                    KnowledgeClaimLifecycle.claim_id == authoritative))
        ).scalar_one_or_none()
        assert stage is not None and stage.stage in ("confirmed", "authoritative")
        # losing evidence is retained as historical truth — never deleted
        challenger_row = (
            await session.execute(
                select(KnowledgeClaim).where(
                    KnowledgeClaim.id == challenger))
        ).scalar_one_or_none()
        assert challenger_row is not None, "losing evidence stays"
        await session.rollback()

    # the resolution itself was learned
    feed = (await client.get(f"{LOOP}/learning", headers=headers)).json()
    assert any(i["kind"] == "contradiction_resolution" for i in feed["items"])

    # settling again with the same winner is a clean idempotent replay
    r2 = await client.post(
        f"{LOOP}/contradictions/migration/resolution",
        json={"authoritative_claim_id": authoritative, "reason": "same"},
        headers=headers,
    )
    assert r2.status_code == 200


# --------------------------------------------------------- what-changed & health


async def test_company_changes_what_changed_feed(client, db_session_factory):
    org = await register_org(client, email="4e7_changes@test.co")
    headers = org["headers"]

    action = (await _propose(client, headers, title="Verified in the window", risk="low")).json()
    await _verify_action(client, headers, action)
    await _close_loop(client, headers, action["id"], actual=80.0)

    feed = (await client.get(f"{LOOP}/changes", headers=headers)).json()
    assert feed["intent"] == "company_changes"
    assert feed["scope"] == "org"
    assert "groups" in feed and {"critical", "important", "normal"} == set(feed["groups"])
    by_kind = {c["kind"]: c for c in feed["changes"]}
    assert "action_verified" in by_kind, by_kind.keys()
    assert by_kind["action_verified"]["change_type"] == "normal"
    assert "learning" in by_kind, "closing the loop materializes the lesson change"

    # critical escalation floods in as critical
    overdue = (await _propose(client, headers, title="Critical overdue", risk="high")).json()
    await _transition(client, headers, overdue["id"], "approve", note="ok")
    r = await _transition(client, headers, overdue["id"], "start", note="go",
                          due_at="2000-01-01T00:00:00Z")
    (await client.post(f"{ACTIONS}/evaluate", headers=headers)).json()
    detail = (await client.get(f"{ACTIONS}/{overdue['id']}", headers=headers)).json()
    assert detail["escalation_level"] >= 1, r.text
    feed2 = (await client.get(f"{LOOP}/changes", headers=headers)).json()
    assert any(c["change_type"] == "critical" for c in feed2["changes"]), feed2["groups"]


async def test_company_health_explainable_ten_dimensions(client):
    org = await register_org(client, email="4e7_health@test.co")
    headers = org["headers"]

    health = (await client.get(f"{LOOP}/health", headers=headers)).json()
    assert health["intent"] == "companyhealth"
    dimensions = health["dimensions"]
    assert len(dimensions) == 10, [d["dimension"] for d in dimensions]
    for dimension in dimensions:
        assert 0.0 <= dimension["score"] <= 100.0
        assert dimension["trend"] in ("up", "down", "flat")
        for signal in dimension["signals"]:
            assert signal["metric"] and signal["value"] is not None
            assert signal["confidence"] > 0.0, "confidence is honest"
            assert signal["evidence"], "evidence is never fabricated"
            assert signal["time_window_hours"] > 0
            assert signal["explanation"], "every signal explains itself"

    execution = next(d for d in dimensions if d["dimension"] == "execution")
    assert any(s["metric"] == "execution_flow" for s in execution["signals"])

    # health also answers through the universal query
    q = (await client.post(
        f"{API}/query", json={"question": "how is company health?"},
        headers=headers)).json()
    assert q["intent"] == "companyhealth"
    assert q["dimensions"], "explainable dimensions, not a fake single number"


async def test_company_health_persists_signal_ledger(client, db_session_factory):
    org = await register_org(client, email="4e7_healthdb@test.co")
    headers = org["headers"]
    await client.get(f"{LOOP}/health", headers=headers)
    async with db_session_factory() as session:
        signals = (
            await session.execute(
                select(CompanyHealthSignal).where(
                    CompanyHealthSignal.organization_id == org["organization"]["id"]))
        ).scalars().all()
        assert len(signals) == 10, "signal ledger rows persisted per dimension"
        assert all(s.value is not None for s in signals)
        await session.rollback()


# ------------------------------------------------------------- impact analysis


async def test_impact_analysis_reach_and_persistence(client, db_session_factory):
    org = await register_org(client, email="4e7_impact@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    conv = await _create_conversation(client, headers, "launch")
    await _send_message(client, headers, conv["id"], "The launch date is June 1.")
    await _drain_events(db_session_factory)
    claims = (await client.get(f"{API}/claims", headers=headers)).json()
    claim = next(c for c in claims["claims"] if "launch date" in c["object_text"])

    action = (await _propose(
        client, headers, title="Move the launch date",
        source_claim_ids=[claim["id"]], risk="low")).json()
    assert action["state"] == "ready"

    r = await client.post(
        f"{LOOP}/impact",
        json={"subject_type": "claim", "subject_id": claim["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject_id"] == claim["id"]
    assert body["subject_type"] == "claim"
    direct = {d.get("entity_id") or d.get("id"): d for d in body["direct"]}
    assert action["id"] in direct, "the governed action directly references the claim"
    assert direct[action["id"]]["entity_type"] in ("action", "task"), direct[action["id"]]
    assert body["indirect"] is not None and body["risks"] is not None
    assert isinstance(body["mitigations"], list)

    async with db_session_factory() as session:
        from app.models.organizational_learning import ImpactAssessment

        persisted = (
            await session.execute(
                select(ImpactAssessment).where(
                    ImpactAssessment.organization_id == org_id,
                    ImpactAssessment.subject_type == "claim",
                    ImpactAssessment.subject_id == claim["id"]))
        ).scalar_one_or_none()
        assert persisted is not None, "impact analysis is persisted, not recomputed silently"
        await session.rollback()


# ------------------------------------------------------ universal action center


async def test_universal_action_center_consolidates(client, db_session_factory):
    org = await register_org(client, email="4e7_center@test.co")
    headers = org["headers"]
    await _seed_conflict(client, headers)
    await _drain_events(db_session_factory)
    await _conflict_recommendation(client, headers)  # -> recommended_action insight

    await _propose(client, headers, title="Pending approval board item")  # awaiting approval
    center = (await client.get(f"{LOOP}/insights", headers=headers)).json()
    assert center["intent"] == "actions"
    assert set(center["categories"]) <= {
        "critical_issue", "recommended_action", "pending_approval", "knowledge_gap",
        "contradiction", "emerging_risk", "overdue_action", "decision_attention",
        "customer_impact", "learning_opportunity",
    }
    assert center["categories"]["pending_approval"] >= 1
    assert center["categories"]["contradiction"] >= 1, "the 4E.4 conflict is on the board"
    assert center["categories"]["recommended_action"] >= 1, "the conflict recommendation is actionable"

    # each item is a real, resolvable insight reference
    approval_item = next(
        i for i in center["items"] if i["category"] == "pending_approval"
    )
    assert approval_item["id"]
    detail = (await client.get(f"{LOOP}/insights/{approval_item['id']}", headers=headers)).json()
    assert detail["id"] == approval_item["id"]
    assert detail["status"] == "active"
    assert detail["category"] == "pending_approval"
    assert detail["why"], "an insight explains itself"


async def test_insight_resolve_is_governed_and_never_deleted(client):
    org = await register_org(client, email="4e7_resolve@test.co")
    headers = org["headers"]
    await _propose(client, headers, title="Resolvable board item")

    center = (await client.get(f"{LOOP}/insights", headers=headers)).json()
    item = next(i for i in center["items"] if i["category"] == "pending_approval")

    r = await client.post(f"{LOOP}/insights/{item['id']}/resolve", headers=headers)
    assert r.status_code == 200
    assert r.json()["resolved"] is True

    detail = (await client.get(f"{LOOP}/insights/{item['id']}", headers=headers)).json()
    assert detail["status"] == "resolved", "resolution is recorded, the row never dies"
    assert detail["resolved_by"], "the acting user is audited"

    # resolving an unknown insight is a governed no-op (never a crash)
    miss = (
        await client.post(f"{LOOP}/insights/does-not-exist/resolve", headers=headers)
    ).json()
    assert miss["resolved"] is False


# ---------------------------------------------------------- why / risk / query


async def test_why_explains_with_evidence(client):
    org = await register_org(client, email="4e7_why@test.co")
    headers = org["headers"]
    action = (await _propose(client, headers, title="Explainable action",
                             risk="low",
                             source_problem="a governed reason exists")).json()

    exp = (await client.get(
        f"{LOOP}/explain",
        params={"subject_type": "action", "subject_id": action["id"]},
        headers=headers)).json()
    assert exp["found"] is True
    assert "reasons" in exp and "evidence" in exp

    blocked = (await _propose(client, headers, title="Why is this blocked?",
                              risk="low")).json()
    await _transition(client, headers, blocked["id"], "block", note="waiting on finance")
    exp2 = (await client.get(
        f"{LOOP}/explain",
        params={"subject_type": "action", "subject_id": blocked["id"]},
        headers=headers)).json()
    assert any(r["kind"] == "blocked" for r in exp2["reasons"])


async def test_risk_authorization_ladder(client):
    org = await register_org(client, email="4e7_risk@test.co")
    headers = org["headers"]
    ladder = {}
    for risk in ("low", "medium", "high"):
        r = (await client.get(
            f"{LOOP}/authorization", params={"risk": risk}, headers=headers)).json()
        ladder[risk] = r["level"]
    assert ladder == {"low": "auto", "medium": "approval", "high": "human"}, ladder
    bad = await client.get(f"{LOOP}/authorization", params={"risk": "extreme"}, headers=headers)
    assert bad.status_code == 400


async def test_universal_query_answers_loop_intents(client, db_session_factory):
    org = await register_org(client, email="4e7_qloop@test.co")
    headers = org["headers"]

    action = (await _propose(client, headers, title="Q loop action", risk="low")).json()
    await _verify_action(client, headers, action)
    await _close_loop(client, headers, action["id"], actual=70.0)

    for question, intent in (
        ("what changed in the company", "company_changes"),
        ("what did we learn from the last rollout", "learned"),
        ("why did that action escalate", "why"),
        ("which decisions should we revisit", "decisions"),
    ):
        resp = (await client.post(
            f"{API}/query", json={"question": question}, headers=headers)).json()
        assert resp["intent"] == intent, f"{question!r} -> {resp['intent']}"
        assert resp["generated_at"]


# ---------------------------------------------------- governance & isolation


async def test_governance_scoped_reader_sees_only_own_project(client, db_session_factory):
    org = await register_org(client, email="4e7_gov@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects", json={"name": "Scoped delivery project"},
        headers=headers)).json()
    scope = await h.scope_for_project(client, headers, project["id"])
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], "4e7_scoped_reader@test.co",
    )

    # org-scoped action: company-wide visibility
    organ = (await _propose(client, headers, title="Org-wide shift", risk="low")).json()
    await _verify_action(client, headers, organ)
    await _close_loop(client, headers, organ["id"], actual=60.0)
    # project-scoped action (visible only inside the scoped reader's project)
    await _propose(client, headers, title="Project pivot",
                   scope_type="project", scope_id=project["id"])

    org_feed = (await client.get(f"{LOOP}/changes", headers=headers)).json()
    scoped_feed = (await client.get(f"{LOOP}/changes", headers=scoped)).json()
    assert org_feed["scope"] == "org"
    assert scoped_feed["scope"] == "project"

    # a scoped reader inherits neither the org-wide action surface
    # nor the org-wide learning feed
    scoped_titles = json.dumps(scoped_feed["changes"])
    assert "Org-wide shift" not in scoped_titles

    scoped_learning = (await client.get(f"{LOOP}/learning", headers=scoped)).json()
    assert scoped_learning["scope"] == "project"

    # Universal Action Center: org action hidden, project action visible
    scoped_center = (await client.get(f"{LOOP}/insights", headers=scoped)).json()
    assert "Org-wide shift" not in json.dumps(scoped_center)

    full_center = (await client.get(f"{LOOP}/insights", headers=headers)).json()
    assert "Org-wide shift" in json.dumps(full_center)


async def test_tenant_isolation_extends_to_loop(client, db_session_factory):
    org_a = await register_org(client, email="4e7_iso_a@test.co")
    ha = org_a["headers"]
    action = (await _propose(client, ha, title="Tenant A lesson", risk="low")).json()
    await _verify_action(client, ha, action)
    await _close_loop(client, ha, action["id"], actual=30.0)

    org_b = await register_org(client, email="4e7_iso_b@test.co")
    hb = org_b["headers"]
    assert (await client.get(f"{LOOP}/learning", headers=hb)).json()["total"] == 0
    assert (await client.get(f"{LOOP}/changes", headers=hb)).json()["total"] == 0
    assert (await client.get(f"{LOOP}/insights", headers=hb)).json()["total"] == 0
    assert (
        await client.post(
            f"{LOOP}/contradictions/migration budget/resolution",
            json={"authoritative_claim_id": "x"}, headers=hb)
    ).status_code == 400
    assert (
        await client.post(
            f"{LOOP}/impact",
            json={"subject_type": "claim", "subject_id": "nope"}, headers=hb)
    ).status_code == 400