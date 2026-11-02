"""Slice 4H.2 — Universal Organizational Decision Intelligence engine.

Under test:

* advisory evaluate -> recommended flow, evidence lineage + alternative
  seeds, exact-once replay convergence.
* the §4 state-machine law at the API boundary: pre-approval states NEVER
  execute and never emit company.action.executed / company.outcome.recorded
  events (409 before publish).
* governed 4H.1 approval -> execution -> outcome closes the 4H.2 loop:
  outcome_recorded quality snapshot + cohort track rollups + reconciliation.
* first-class reads: list/detail/alternatives/why-not/prediction/quality/
  precedents/contradictions/impact/tracks/free recall, advisory-only.
* bounds: MAX_DECISION_EVIDENCE (40), MAX_ALTERNATIVES (5).
* as_of strict/partial evidence semantics on captured_at.
* tenant isolation.
"""

from sqlalchemy import func, select

from app.models.notification import Event as EventRow
from tests.conftest import register_org

CAP = "/api/v1/brain/execution/company/decisions"


async def _drain(db_session_factory, limit=200, rounds=6):
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


async def _count_events(db_session_factory, organization_id, name):
    async with db_session_factory() as db:
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(EventRow).where(
                        EventRow.organization_id == organization_id,
                        EventRow.name == name,
                    )
                )
            ).scalar_one() or 0
        )


def _evaluate_body(extra=None):
    body = {
        "kind": "hire",
        "title": "Adopt the new data platform",
        "rationale": "revenue forecast said growth",
        "impact_label": "revenue growth",
        "expected_improvement": "faster forecasting",
        "scope_type": "org",
        "scope_id": "org-root",
        "evidence": [
            {
                "evidence_type": "metric",
                "source_kind": "revenue.forecast",
                "source_summary": "growth expected",
                "captured_at": "2026-08-01T00:00:00Z",
                "weight": 0.8,
            }
        ],
        "alternatives": [
            {
                "alternative_key": "alt:01",
                "label": "Adopt",
                "chosen": True,
                "why_chosen": "best roi",
                "expected_outcome": {"kind": "improvement"},
            },
            {
                "alternative_key": "alt:02",
                "label": "Wait a quarter",
                "chosen": False,
                "why_not": "risk of losing momentum",
                "preferable_if": "if revenue dips",
            },
        ],
    }
    if extra:
        body.update(extra)
    return body


# ---------------------------------------------------------------------------
# 1. evaluate -> recommended + all first-class reads
# ---------------------------------------------------------------------------

async def test_evaluate_recommend_and_reads(client, db_session_factory):
    org = await register_org(client, email="4h2_reads@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    assert evaluated.status_code == 200, evaluated.text
    ev = evaluated.json()
    assert ev["accepted"] is True
    assert ev["state"] == "evaluated"
    assert ev["evidence_written"] == 1
    decision_id = ev["decision_id"]

    recommended = await client.post(
        f"{CAP}/{decision_id}/recommend", json={}, headers=headers,
    )
    assert recommended.status_code == 200, recommended.text
    assert recommended.json()["state"] == "recommended"

    listing = (await client.get(f"{CAP}", headers=headers)).json()
    assert listing["total"] == 1
    row = listing["decisions"][0]
    assert row["evidence_count"] == 1
    assert row["decision_id"] == decision_id
    assert row["state"] == "recommended"

    detail = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert detail["advisory_only"] is True
    assert detail["evidence_count"] == 1
    assert len(detail["alternatives"]) == 2
    assert {q["stage"] for q in detail["quality"]} == {"evaluated", "recommended"}
    assert detail["prediction"]["confidence_band"] in (
        "low", "medium", "high", "not_recorded",
    )
    assert detail["scope_type"] == "org"

    alts = (await client.get(f"{CAP}/{decision_id}/alternatives", headers=headers)).json()
    assert alts["total"] == 2
    assert alts["chosen"]["alternative_key"] == "alt:01"
    assert alts["chosen"]["why_chosen"] == "best roi"

    why_not = (await client.get(f"{CAP}/{decision_id}/why-not", headers=headers)).json()
    assert why_not["total"] == 1
    assert why_not["why_not"][0]["why_not"] == "risk of losing momentum"
    assert why_not["why_not"][0]["preferable_if"] == "if revenue dips"

    prediction = (
        await client.get(f"{CAP}/{decision_id}/prediction", headers=headers)
    ).json()
    assert prediction["advisory_only"] is True
    assert prediction["supporting_evidence_count"] == 1

    quality = (await client.get(f"{CAP}/{decision_id}/quality", headers=headers)).json()
    assert quality["advisory_only"] is True
    assert quality["evidence_count"] == 1
    assert quality["risk_band"] == "MEDIUM"
    assert len(quality["snapshots"]) == 2

    precedents = (
        await client.get(f"{CAP}/{decision_id}/precedents", headers=headers)
    ).json()
    assert precedents["total"] == 0

    contradictions = (
        await client.get(f"{CAP}/{decision_id}/contradictions", headers=headers)
    ).json()
    assert contradictions["total"] == 0

    impact = (
        await client.get(f"{CAP}/{decision_id}/impact", headers=headers)
    ).json()
    assert impact["advisory_only"] is True
    assert impact["observed_edges"] == []
    assert impact["inferred_relationships"] == []

    tracks = (
        await client.get(
            f"/api/v1/brain/execution/company/tracks?cohort=kind&value=infrastructure",
            headers=headers,
        )
    ).json()
    assert tracks["advisory_only"] is True
    assert tracks["snapshots"] == []

    recall = (
        await client.get("/api/v1/brain/execution/company/precedents", headers=headers)
    ).json()
    assert recall["total"] == 0

    # advisory writes are audited through the fabric (engine background
    # events), and they never enqueue jobs: nothing subscribes to them.
    assert await _count_events(db_session_factory, org_id, "company.decision.evaluated") == 1
    assert await _count_events(db_session_factory, org_id, "company.decision.recommended") == 1
    assert await _count_events(db_session_factory, org_id, "company.decision.quality.composed") == 2
    assert await _count_events(db_session_factory, org_id, "company.decision.alternatives.recorded") == 1
    assert await _count_events(db_session_factory, org_id, "company.decision.why_not.recorded") == 1


# ---------------------------------------------------------------------------
# 2. §4 state-machine law: no execution and no false events pre-approval
# ---------------------------------------------------------------------------

async def test_pre_approval_states_never_execute(client, db_session_factory):
    org = await register_org(client, email="4h2_gate@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    decision_id = evaluated.json()["decision_id"]
    await client.post(f"{CAP}/{decision_id}/recommend", json={}, headers=headers)

    executed = await client.post(
        f"{CAP}/{decision_id}/execute", json={}, headers=headers,
    )
    assert executed.status_code == 409, executed.text
    assert executed.json()["detail"]["rejected"] is True
    assert executed.json()["detail"]["state"] == "recommended"

    outcome = await client.post(
        f"{CAP}/{decision_id}/outcome",
        json={"outcome_kind": "successful"}, headers=headers,
    )
    assert outcome.status_code == 409, outcome.text
    assert outcome.json()["detail"]["rejected"] is True

    assert await _count_events(db_session_factory, org_id, "company.action.executed") == 0
    assert await _count_events(db_session_factory, org_id, "company.outcome.recorded") == 0


# ---------------------------------------------------------------------------
# 3. governed loop closes 4H.2: outcome quality snapshot + tracks
# ---------------------------------------------------------------------------

async def test_governed_lifecycle_closes_the_loop(client, db_session_factory):
    org = await register_org(client, email="4h2_loop@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    approved = await client.post(
        f"{CAP}",
        json={
            "kind": "hire",
            "title": "Hire for the platform bottleneck",
            "predicted_outcome": {"expected_outcome": "successful"},
            "prediction_confidence": 0.7,
            "confidence": 0.8,
            "owner_label": "Leadership",
        },
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    decision_id = approved.json()["decision_id"]
    await _drain(db_session_factory)

    executed = await client.post(
        f"{CAP}/{decision_id}/execute",
        json={"executed_by_label": "Ada Owner"}, headers=headers,
    )
    assert executed.status_code == 200, executed.text
    await _drain(db_session_factory)

    outcome = await client.post(
        f"{CAP}/{decision_id}/outcome",
        json={
            "outcome_kind": "successful",
            "effectiveness": 0.8,
            "lesson": "scoped predictions survive scrutiny",
        },
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["actual_outcome_compare"]["aligned"] is True
    await _drain(db_session_factory)

    quality = (
        await client.get(f"{CAP}/{decision_id}/quality", headers=headers)
    ).json()
    stages = {q["stage"] for q in quality["snapshots"]}
    assert "outcome_recorded" in stages  # advise + approve + outcome all audited

    tracks = (
        await client.get(
            f"/api/v1/brain/execution/company/tracks?cohort=kind&value=hire",
            headers=headers,
        )
    ).json()
    assert any(
        t["cohort_key"] == "kind:hire" and t["decisions_measured"] >= 1
        for t in tracks["snapshots"]
    )

    prediction = (
        await client.get(f"{CAP}/{decision_id}/prediction", headers=headers)
    ).json()
    assert prediction["reconciliation"]["aligned"] is True
    assert prediction["not_yet_measurable"] is False

    assert await _count_events(db_session_factory, org_id, "company.decision.track.updated") >= 1


# ---------------------------------------------------------------------------
# 4. exact-once replay convergence
# ---------------------------------------------------------------------------

async def test_replay_convergence(client, db_session_factory):
    org = await register_org(client, email="4h2_replay@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    first = await client.post(f"{CAP}/evaluate", json=_evaluate_body(), headers=headers)
    decision_id = first.json()["decision_id"]
    assert first.json()["evidence_written"] == 1

    # replay delivers the SAME payload + decision_id (contract test 12: the
    # same natural keys) and must converge exact-once — no new rows/events.
    replay_body = _evaluate_body()
    replay_body["decision_id"] = decision_id
    second = await client.post(f"{CAP}/evaluate", json=replay_body, headers=headers)
    assert second.json()["accepted"] is True
    assert second.json()["evidence_written"] == 0

    detail = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert detail["evidence_count"] == 1
    assert len(detail["alternatives"]) == 2

    await client.post(f"{CAP}/{decision_id}/recommend", json={}, headers=headers)
    await client.post(f"{CAP}/{decision_id}/recommend", json={}, headers=headers)

    detail_after = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert detail_after["state"] == "recommended"
    assert len(detail_after["quality"]) == 2
    assert len(detail_after["alternatives"]) == 2
    assert await _count_events(db_session_factory, org_id, "company.decision.recommended") == 1
    assert await _count_events(db_session_factory, org_id, "company.decision.quality.composed") == 2


# ---------------------------------------------------------------------------
# 5. why-not endpoint
# ---------------------------------------------------------------------------

async def test_why_not_endpoint(client, db_session_factory):
    org = await register_org(client, email="4h2_whynot@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    decision_id = evaluated.json()["decision_id"]

    updated = await client.post(
        f"{CAP}/{decision_id}/alternatives/alt:02/why-not",
        json={"why_not": "market conditions have shifted", "preferable_if": "if demand recovers"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["changed"] is True

    why_not = (await client.get(f"{CAP}/{decision_id}/why-not", headers=headers)).json()
    assert why_not["why_not"][0]["why_not"] == "market conditions have shifted"

    unchanged = await client.post(
        f"{CAP}/{decision_id}/alternatives/alt:02/why-not",
        json={"why_not": "market conditions have shifted", "preferable_if": "if demand recovers"},
        headers=headers,
    )
    assert unchanged.json()["changed"] is False
    assert await _count_events(db_session_factory, org_id, "company.decision.why_not.recorded") == 2

    rejected = await client.post(
        f"{CAP}/{decision_id}/alternatives/alt:01/why-not",
        json={"why_not": "cannot have why-not on the chosen alternative"},
        headers=headers,
    )
    assert rejected.status_code == 400, rejected.text

    empty = await client.post(
        f"{CAP}/{decision_id}/alternatives/alt:02/why-not",
        json={"why_not": ""},
        headers=headers,
    )
    assert empty.status_code == 400, empty.text


# ---------------------------------------------------------------------------
# 6. bounds
# ---------------------------------------------------------------------------

async def test_bounds(client, db_session_factory):
    org = await register_org(client, email="4h2_bounds@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    body = _evaluate_body()
    body["evidence"] = [
        {
            "evidence_type": "metric",
            "source_kind": "metric.a",
            "source_summary": f"row {i}",
            "captured_at": f"2026-07-{(i % 28) + 1:02d}T00:00:00Z",
        }
        for i in range(50)
    ]
    body["alternatives"] = [
        {"alternative_key": f"alt:{i:02d}", "label": f"Option {i}",
         "chosen": (i == 0), "why_chosen": "first" if i == 0 else "",
         "why_not": "" if i == 0 else f"rejected {i}"}
        for i in range(8)
    ]
    evaluated = await client.post(f"{CAP}/evaluate", json=body, headers=headers)
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evidence_written"] == 40

    detail = (
        await client.get(f"{CAP}/{evaluated.json()['decision_id']}", headers=headers)
    ).json()
    assert detail["evidence_count"] == 40


# ---------------------------------------------------------------------------
# 7. as_of strict/partial evidence semantics on captured_at
# ---------------------------------------------------------------------------

async def test_as_of_evidence_semantics(client, db_session_factory):
    org = await register_org(client, email="4h2_asof@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    body = _evaluate_body()
    body["evidence"] = [
        {
            "evidence_type": "metric",
            "source_kind": "revenue.july",
            "source_summary": "july read",
            "captured_at": "2026-07-01T00:00:00Z",
        },
        {
            "evidence_type": "metric",
            "source_kind": "revenue.august",
            "source_summary": "august read",
            "captured_at": "2026-08-01T00:00:00Z",
        },
    ]
    evaluated = await client.post(f"{CAP}/evaluate", json=body, headers=headers)
    decision_id = evaluated.json()["decision_id"]

    strict = (
        await client.get(f"{CAP}/{decision_id}?as_of=2026-07-15T00:00:00Z", headers=headers)
    ).json()
    assert strict["evidence_count"] == 1
    assert strict["evidence"][0]["source_kind"] == "revenue.july"

    partial = (
        await client.get(
            f"{CAP}/{decision_id}?as_of=2026-07-15T00:00:00Z&include_partial=true",
            headers=headers,
        )
    ).json()
    assert len(partial["evidence_incomplete"]) == 1

    full = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert full["evidence_count"] == 2


# ---------------------------------------------------------------------------
# 8. tenant isolation
# ---------------------------------------------------------------------------

async def test_tenant_isolation(client, db_session_factory):
    org = await register_org(client, email="4h2_tenant_a@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    evaluated = await client.post(f"{CAP}/evaluate", json=_evaluate_body(), headers=headers)
    decision_id = evaluated.json()["decision_id"]

    other = await register_org(
        client, name="Other Labs", slug="other-4h2",
        email="4h2_tenant_b@test.co",
    )
    other_headers = other["headers"]

    listing = (await client.get(f"{CAP}", headers=other_headers)).json()
    assert listing["total"] == 0

    detail = (await client.get(f"{CAP}/{decision_id}", headers=other_headers))
    assert detail.status_code == 404

    executed = await client.post(
        f"{CAP}/{decision_id}/execute", json={}, headers=other_headers,
    )
    assert executed.status_code == 404


# ---------------------------------------------------------------------------
# 9. brain answer routing reaches the 4H.2 decision surfaces
# ---------------------------------------------------------------------------

async def test_brain_answer_routing(client, db_session_factory):
    org = await register_org(client, email="4h2_brain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    evaluated = await client.post(f"{CAP}/evaluate", json=_evaluate_body(), headers=headers)
    decision_id = evaluated.json()["decision_id"]
    await _drain(db_session_factory)

    answered = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "why did we decide to adopt the platform?"},
        headers=headers,
    )
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["intent"] in ("decision_reason", "company_operating", "company_universal")
    assert body.get("scoped") is True or body.get("scope") in ("org", "company")

    alternatives = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "what alternatives we considered for the platform?"},
        headers=headers,
    )
    assert alternatives.status_code == 200, alternatives.text
    alt_body = alternatives.json()
    assert alt_body["intent"] == "decision_alternatives"
    assert alt_body.get("decision_id") == decision_id
    assert len(alt_body.get("alternatives", [])) >= 2