"""Slice 4H.3 — Living Company State engine + surfaces.

Under test:

* composition: one exact-once company_state_history snapshot per source
  event, 8 typed dimensions, delta diffing (add only, provenance cited),
  no-op compositions write nothing and emit nothing.
* read laws: as_of strict/partial, byte-identical determinism, bounded
  shapes (MAX_STATE_*), explain provenance.
* surfaces: dependencies walk (unknown -> 404), risk exposure bands
  (closed excluded), opportunities, affected-decisions intersection.
* state-context bridge: created/changed/no-op replay/exact-once and the
  409 detail.rejected law past outcome_recorded.
* event truth: company.state.composed / company.state.changed fire ONLY on
  real writes; reads, replays and rejected writes emit zero.
* tenant isolation + the five brain intents (company_state / company_changes
  / company_dependencies / company_risks / company_opportunities) with the
  4H.2 decision intents still resolving.
"""

from sqlalchemy import func, select

from app.core.timeutils import ensure_aware

from app.models.company_operating import (
    CompanyStateHistory,
    MAX_STATE_DECISIONS,
    MAX_STATE_DELTA,
    MAX_STATE_OPPORTUNITIES,
    MAX_STATE_RISKS,
    MAX_STATE_SIGNALS,
    STATE_DIMENSIONS,
)
from app.models.notification import Event as EventRow
from tests.conftest import register_org

S0 = "/api/v1/brain/execution/company/state"
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


async def _publish_refresh(
    db_session_factory, org_id, name="project.started", count=1, replay_last=False,
):
    """Publish a real event row and run the 4G.7/4H.3 bridge refresh against
    it directly (deterministic, no worker dependency)."""
    from app.events.publisher import publish_event
    from app.intelligence.company_operating_engine import company_operating_engine

    events = []
    for i in range(count):
        async with db_session_factory() as db:
            event = await publish_event(
                db, name=name, organization_id=org_id,
                payload={"organization_id": org_id, "event_name": name, "seq": i},
            )
            await company_operating_engine.refresh(
                db, organization_id=org_id, event=event,
                payload={"organization_id": org_id},
            )
            await db.commit()
            events.append(event)
        if i < count - 1:
            import asyncio

            await asyncio.sleep(0.005)
    if replay_last:
        async with db_session_factory() as db:
            await company_operating_engine.refresh(
                db, organization_id=org_id, event=events[-1],
                payload={"organization_id": org_id},
            )
            await db.commit()
    return events


async def _state_count(db_session_factory, org_id, scope_type="org"):
    async with db_session_factory() as db:
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(CompanyStateHistory).where(
                        CompanyStateHistory.organization_id == org_id,
                        CompanyStateHistory.scope_type == scope_type,
                    )
                )
            ).scalar_one() or 0
        )


async def _state_rows(db_session_factory, org_id, scope_type="org"):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CompanyStateHistory)
                    .where(
                        CompanyStateHistory.organization_id == org_id,
                        CompanyStateHistory.scope_type == scope_type,
                    )
                    .order_by(CompanyStateHistory.occurred_at.asc())
                )
            ).scalars().all()
        )


async def _living(db_session_factory, org_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        return await company_operating_engine.living_state(
            db, organization_id=org_id, **kw,
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
                "source_kind": "event",
                "source_summary": "company change signal",
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
            }
        ],
    }
    if extra:
        body.update(extra)
    return body


# ---------------------------------------------------------------------------
# 1. composition (L2): one snapshot per source event, 8 typed dimensions
# ---------------------------------------------------------------------------

async def test_composition_writes_snapshot_with_typed_dimensions(client, db_session_factory):
    org = await register_org(client, email="4h3_compose@test.co")
    org_id = org["organization"]["id"]

    events = await _publish_refresh(db_session_factory, org_id, count=1)
    assert await _state_count(db_session_factory, org_id) == 1

    surface = await _living(db_session_factory, org_id)
    assert surface["advisory_only"] is True
    assert surface["state_key"] is not None
    assert surface["snapshot_ref"] == events[0].id
    dims = surface["dimensions"]
    assert len(dims) == len(STATE_DIMENSIONS) == 8
    for d in dims:
        assert d["type"] in ("observed", "derived")
        assert d["op"] in ("improved", "declined", "stable")
        assert d["state"] in ("healthy", "concerned", "at_risk", "critical")
    assert surface["signals"], "first snapshot must cite its own signal"
    assert all(s.get("id") for s in surface["signals"])
    assert surface["dependencies"] is not None
    assert surface["risks"] is not None
    assert surface["opportunities"] is not None
    assert surface["next"] is not None
    assert await _count_events(db_session_factory, org_id, "company.state.composed") == 1
    assert await _count_events(db_session_factory, org_id, "company.state.changed") == 1


# ---------------------------------------------------------------------------
# 2. delta (L1/L2): second change lists only NEW signals, with provenance
# ---------------------------------------------------------------------------

async def test_second_change_delta_only_new_signals(client, db_session_factory):
    org = await register_org(client, email="4h3_delta@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, name="project.started", count=1)
    events = await _publish_refresh(db_session_factory, org_id, name="task.completed", count=1)

    rows = await _state_rows(db_session_factory, org_id)
    assert len(rows) == 2
    delta = rows[-1].delta_json or []
    assert delta, "the second composition must carry a delta"
    assert len(delta) <= MAX_STATE_DELTA
    assert len(rows[-1].signals_json or []) <= MAX_STATE_SIGNALS
    ev_ids = {str(events[0].id)} | {str(r.source_event_id) for r in rows[:-1]}
    new_ids = {d["id"] for d in delta if d["op"] == "added"}
    assert all(i in new_ids for i in {str(events[0].id)})
    for item in delta:
        assert item["id"] and item["label"] and item["kind"]
        assert item["signal_ids"]
        assert item["evidence_count"] >= 0


# ---------------------------------------------------------------------------
# 3. exact-once (L5): replay of the same source event -> no row, no events
# ---------------------------------------------------------------------------

async def test_exact_once_replay_no_extra_row_no_events(client, db_session_factory):
    org = await register_org(client, email="4h3_replay@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1, replay_last=True)
    assert await _state_count(db_session_factory, org_id) == 1
    assert await _count_events(db_session_factory, org_id, "company.state.composed") == 1
    assert await _count_events(db_session_factory, org_id, "company.state.changed") == 1

    # a read-oriented recompose with an already-composed source event is a
    # no-op by construction: nothing new, nothing emitted.
    before = await _state_count(db_session_factory, org_id)
    await _living(db_session_factory, org_id)
    assert await _state_count(db_session_factory, org_id) == before
    assert await _count_events(db_session_factory, org_id, "company.state.composed") == 1


# ---------------------------------------------------------------------------
# 4. explain (L1/L4): every cited signal carries its provenance
# ---------------------------------------------------------------------------

async def test_explain_expands_signal_provenance(client, db_session_factory):
    org = await register_org(client, email="4h3_explain@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    plain = await _living(db_session_factory, org_id, explain=False)
    assert all("why" not in s for s in plain["signals"])

    expanded = await _living(db_session_factory, org_id, explain=True)
    assert len(expanded["signals"]) == len(plain["signals"])
    assert all("why" in s and s.get("id") for s in expanded["signals"])


# ---------------------------------------------------------------------------
# 5. temporal as-of (L3): strict excludes later snapshots; include_partial
#    lists them as late; re-query is byte-identical
# ---------------------------------------------------------------------------

async def test_as_of_strict_and_partial(client, db_session_factory):
    org = await register_org(client, email="4h3_asof@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, name="project.started", count=1)
    await _publish_refresh(db_session_factory, org_id, name="task.completed", count=1)
    rows = await _state_rows(db_session_factory, org_id)
    assert len(rows) == 2
    # anchor strictly BETWEEN the two snapshots (deterministic midpoint)
    gap = rows[1].occurred_at - rows[0].occurred_at
    assert gap.total_seconds() > 0
    anchor = (rows[0].occurred_at + gap / 2).isoformat()

    strict = await _living(db_session_factory, org_id, as_of=anchor)
    assert strict["snapshot_ref"] == rows[0].source_event_id
    assert strict["snapshot_ts"] == ensure_aware(rows[0].snapshot_ts).isoformat()
    assert "late_snapshots" not in strict

    partial = await _living(
        db_session_factory, org_id, as_of=anchor, include_partial=True,
    )
    assert partial["snapshot_ref"] == rows[0].source_event_id
    assert len(partial["late_snapshots"]) == 1
    assert partial["late_snapshots"][0]["snapshot_ref"] == rows[1].source_event_id

    # byte-identical re-query (5.2)
    partial2 = await _living(
        db_session_factory, org_id, as_of=anchor, include_partial=True,
    )
    assert partial == partial2


# ---------------------------------------------------------------------------
# 6. delta + bounds (L1/L6): the state_delta surface and all caps
# ---------------------------------------------------------------------------

async def test_delta_surface_and_bounded_signals(client, db_session_factory):
    org = await register_org(client, email="4h3_bounds@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=3)
    rows = await _state_rows(db_session_factory, org_id)
    assert len(rows) == 3
    latest = rows[-1].delta_json or []
    assert len(latest) <= MAX_STATE_DELTA == 30
    assert len(rows[-1].signals_json or []) <= MAX_STATE_SIGNALS == 30

    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        dsurface = await company_operating_engine.state_delta(
            db, organization_id=org_id,
        )
    assert dsurface["advisory_only"] is True
    assert len(dsurface["delta"]) <= MAX_STATE_DELTA
    assert len(dsurface["signals"]) <= MAX_STATE_SIGNALS
    assert dsurface["snapshot_ref"] == rows[-1].source_event_id

    async with db_session_factory() as db:
        risks = await company_operating_engine.state_risks(db, organization_id=org_id)
        opps = await company_operating_engine.state_opportunities(db, organization_id=org_id)
        affected = await company_operating_engine.state_affected_decisions(
            db, organization_id=org_id,
        )
    assert len(risks["risks"]) <= MAX_STATE_RISKS == 10
    assert len(opps["opportunities"]) <= MAX_STATE_OPPORTUNITIES == 10
    assert len(affected["affected_decisions"]) <= MAX_STATE_DECISIONS == 20


# ---------------------------------------------------------------------------
# 7. dependencies (L1/L6): causal walk reuses the canonical chain; unknown
#    entity -> 404
# ---------------------------------------------------------------------------

async def test_dependencies_walk_and_unknown_404(client, db_session_factory):
    from app.models.approval import Risk

    org = await register_org(client, email="4h3_deps@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    missing = await client.get(
        f"{S0}/dependencies",
        params={"entity_type": "team", "entity_id": "team:missing"},
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    async with db_session_factory() as db:
        db.add(Risk(
            organization_id=org_id, project_id="proj:alpha",
            title="Critical vendor dependency", status="identified",
            probability=5, impact=5, risk_score=25,
        ))
        await db.commit()
    await _publish_refresh(db_session_factory, org_id, count=1)

    async with db_session_factory() as db:
        risk_row = (
            await db.execute(select(Risk).where(Risk.organization_id == org_id))
        ).scalars().first()

    walked = await client.get(
        f"{S0}/dependencies",
        params={"entity_type": "risk", "entity_id": risk_row.id, "depth": 3},
        headers=headers,
    )
    assert walked.status_code == 200, walked.text
    body = walked.json()
    assert body["subject"]["id"] == risk_row.id
    assert any(h["kind"] == "risk->project" for h in body["hops"])
    assert body["advisory_only"] is True
    assert body["depth"] == 3


# ---------------------------------------------------------------------------
# 8. risks (L1/L4/L6): open risks compose into bands; closed are excluded
# ---------------------------------------------------------------------------

async def test_risk_exposure_bands_closed_excluded(client, db_session_factory):
    from app.models.approval import Risk

    org = await register_org(client, email="4h3_risks@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    async with db_session_factory() as db:
        db.add_all([
            Risk(organization_id=org_id, project_id="proj:a", title="High risk",
                 status="identified", probability=5, impact=5, risk_score=25),
            Risk(organization_id=org_id, project_id="proj:b", title="Medium risk",
                 status="mitigating", probability=4, impact=3, risk_score=12),
            Risk(organization_id=org_id, project_id="proj:c", title="Closed risk",
                 status="closed", probability=5, impact=5, risk_score=30),
        ])
        await db.commit()

    res = await client.get(f"{S0}/risks", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["advisory_only"] is True
    assert len(body["risks"]) == 2
    bands = {r["band"] for r in body["risks"]}
    assert bands == {"HIGH", "MEDIUM"}
    assert all(r["affected"] for r in body["risks"])
    assert len(body["risks"]) <= MAX_STATE_RISKS


# ---------------------------------------------------------------------------
# 9. opportunities (L1/L6): patterns surface with source ids + counts
# ---------------------------------------------------------------------------

async def test_opportunities_pattern_derivation(client, db_session_factory):
    from datetime import datetime as _dt, timezone as _tz

    from app.models.intelligence import PatternDetection

    org = await register_org(client, email="4h3_opps@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    now = _dt.now(_tz.utc)
    async with db_session_factory() as db:
        db.add(PatternDetection(
            organization_id=org_id, pattern_type="repeated_delay",
            key="4h3:repeated_delay", title="Repeated delivery delays",
            status="confirmed", count=7,
            evidence_json=[{"type": "event", "id": "ev:1"}],
            first_seen=now, last_seen=now,
        ))
        await db.commit()

    res = await client.get(f"{S0}/opportunities", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["advisory_only"] is True
    assert len(body["opportunities"]) == 1
    item = body["opportunities"][0]
    assert item["source"] == "pattern"
    assert item["source_id"]
    assert item["evidence_count"] == 1
    assert len(body["opportunities"]) <= MAX_STATE_OPPORTUNITIES


# ---------------------------------------------------------------------------
# 10. affected decisions (L1/L5.4): deterministic delta intersection
# ---------------------------------------------------------------------------

async def test_affected_decisions_intersection(client, db_session_factory):
    org = await register_org(client, email="4h3_affected@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, name="project.started", count=1)

    hit_body = _evaluate_body({"title": "Decision that intersects the delta"})
    accepted = await client.post(f"{CAP}/evaluate", json=hit_body, headers=headers)
    assert accepted.status_code == 200, accepted.text
    hit_id = accepted.json()["decision_id"]
    await client.post(f"{CAP}/{hit_id}/recommend", json={}, headers=headers)

    miss_body = _evaluate_body()
    miss_body["evidence"][0]["source_kind"] = "finance.forecast"
    miss_body["title"] = "Unrelated decision"
    miss = await client.post(f"{CAP}/evaluate", json=miss_body, headers=headers)
    miss_id = miss.json()["decision_id"]
    await client.post(f"{CAP}/{miss_id}/recommend", json={}, headers=headers)

    await _publish_refresh(db_session_factory, org_id, name="task.completed", count=1)

    res = await client.get(f"{S0}/decisions", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["advisory_only"] is True
    ids = [d["decision_id"] for d in body["affected_decisions"]]
    assert hit_id in ids
    assert miss_id not in ids
    for d in body["affected_decisions"]:
        assert d["state"] and d["kind"] and d["why"]


# ---------------------------------------------------------------------------
# 11. state-context bridge (L5): created / changed / no-op replay / 409
# ---------------------------------------------------------------------------

async def test_state_context_bridge_lifecycle(client, db_session_factory):
    org = await register_org(client, email="4h3_bridge@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    unknown = await client.post(
        f"{CAP}/dec:missing/state-context", json={}, headers=headers,
    )
    assert unknown.status_code == 404, unknown.text

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    decision_id = evaluated.json()["decision_id"]
    await client.post(f"{CAP}/{decision_id}/recommend", json={}, headers=headers)

    attached = await client.post(
        f"{CAP}/{decision_id}/state-context", json={}, headers=headers,
    )
    assert attached.status_code == 200, attached.text
    first = attached.json()
    assert first["accepted"] is True
    # evaluate already anchored the state context (§3.2) — the bridge replay
    # is an exact no-op: created:false, changed:false, nothing re-emitted.
    assert first["created"] is False
    assert first["changed"] is False
    assert first["already_attached"] is True
    assert first["state_context"]["snapshot_refs"]

    replayed = await client.post(
        f"{CAP}/{decision_id}/state-context", json={}, headers=headers,
    )
    second = replayed.json()
    assert second["created"] is False
    assert second["changed"] is False
    assert second["already_attached"] is True
    assert replayed.status_code == 200

    # a governed approval decision (no evaluate-time anchor) is the genuine
    # create path: first attach created:true, replay created:false.
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
    governed_id = approved.json()["decision_id"]
    await _drain(db_session_factory)

    created = await client.post(
        f"{CAP}/{governed_id}/state-context", json={}, headers=headers,
    )
    assert created.status_code == 200, created.text
    assert created.json()["created"] is True
    assert created.json()["changed"] is True
    replay = await client.post(
        f"{CAP}/{governed_id}/state-context", json={}, headers=headers,
    )
    assert replay.json()["created"] is False
    assert replay.json()["changed"] is False

    # governed loop advances the decision to outcome_recorded
    await client.post(
        f"{CAP}/{governed_id}/execute",
        json={"executed_by_label": "Ada Owner"}, headers=headers,
    )
    await _drain(db_session_factory)
    await client.post(
        f"{CAP}/{governed_id}/outcome",
        json={"outcome_kind": "successful", "effectiveness": 0.8},
        headers=headers,
    )
    await _drain(db_session_factory)

    rejected = await client.post(
        f"{CAP}/{governed_id}/state-context", json={}, headers=headers,
    )
    assert rejected.status_code == 409, rejected.text
    detail = rejected.json()["detail"]
    assert detail["rejected"] is True
    assert detail["state"] in ("outcome_recorded", "assessed")


# ---------------------------------------------------------------------------
# 12. decision surface integration (L3): additive state_context on reads
# ---------------------------------------------------------------------------

async def test_decision_reads_expose_state_context(client, db_session_factory):
    org = await register_org(client, email="4h3_attach_read@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)
    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    decision_id = evaluated.json()["decision_id"]
    await client.post(f"{CAP}/{decision_id}/recommend", json={}, headers=headers)

    # §3.2 anchors at evaluate/recommend time — the read surfaces expose it
    # additively (L3), and the explicit bridge replay stays a no-op.
    before = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert before.get("state_context") is not None
    assert before["state_context"]["snapshot_refs"]

    await client.post(f"{CAP}/{decision_id}/state-context", json={}, headers=headers)

    detail = (await client.get(f"{CAP}/{decision_id}", headers=headers)).json()
    assert detail["state_context"]["snapshot_refs"]
    assert detail["state_context"]["dependencies"] is not None

    prediction = (
        await client.get(f"{CAP}/{decision_id}/prediction", headers=headers)
    ).json()
    assert prediction["state_context"]["snapshot_refs"]


# ---------------------------------------------------------------------------
# 13. event truth (L5): reads / replays / rejections emit zero events
# ---------------------------------------------------------------------------

async def test_events_only_on_real_writes(client, db_session_factory):
    org = await register_org(client, email="4h3_evtruth@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=2)
    assert await _count_events(db_session_factory, org_id, "company.state.composed") == 2
    assert await _count_events(db_session_factory, org_id, "company.state.changed") == 2

    await _living(db_session_factory, org_id)
    await _living(db_session_factory, org_id, explain=True)
    assert await _count_events(db_session_factory, org_id, "company.state.composed") == 2
    assert await _count_events(db_session_factory, org_id, "company.state.changed") == 2


# ---------------------------------------------------------------------------
# 14. tenant isolation (L7): org B sees empty/404, never org A
# ---------------------------------------------------------------------------

async def test_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="4h3_tenant_a@test.co")
    headers_a = org_a["headers"]
    org_id = org_a["organization"]["id"]
    await _publish_refresh(db_session_factory, org_id, count=1)

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers_a,
    )
    decision_id = evaluated.json()["decision_id"]

    org_b = await register_org(
        client, name="Other Labs", slug="other-4h3", email="4h3_tenant_b@test.co",
    )
    headers_b = org_b["headers"]

    state_b = await client.get(f"{S0}?explain=true", headers=headers_b)
    assert state_b.status_code == 200
    assert state_b.json()["state_key"] is None

    risks_b = (await client.get(f"{S0}/risks", headers=headers_b)).json()
    assert risks_b["risks"] == []
    opps_b = (await client.get(f"{S0}/opportunities", headers=headers_b)).json()
    assert opps_b["opportunities"] == []
    decs_b = (await client.get(f"{S0}/decisions", headers=headers_b)).json()
    assert decs_b["affected_decisions"] == []

    attach_b = await client.post(
        f"{CAP}/{decision_id}/state-context", json={}, headers=headers_b,
    )
    assert attach_b.status_code == 404, attach_b.text


# ---------------------------------------------------------------------------
# 15. brain intents (L1): the five 4H.3 intents + 4H.2 no-regression
# ---------------------------------------------------------------------------

async def test_brain_intents_route(client, db_session_factory):
    from app.models.approval import Risk

    org = await register_org(client, email="4h3_brain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)
    async with db_session_factory() as db:
        db.add(Risk(
            organization_id=org_id, project_id="proj:alpha",
            title="Key vendor risk", status="identified",
            probability=5, impact=5, risk_score=25,
        ))
        await db.commit()

    pairs = [
        ("what is the state of the company?", "company_state"),
        ("what changed in the company recently?", "company_changes"),
        ("what are the key risks?", "company_risks"),
        ("where should we focus?", "company_opportunities"),
        ("what depends on the current vendor risk?", "company_dependencies"),
    ]
    for question, intent in pairs:
        res = await client.post(
            "/api/v1/brain/knowledge/query", json={"question": question},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["intent"] == intent, f"{question} -> {body.get('intent')}"
        assert body.get("advisory_only") is True or body.get("scope") == "org"

    evaluated = await client.post(
        f"{CAP}/evaluate", json=_evaluate_body(), headers=headers,
    )
    decision_id = evaluated.json()["decision_id"]
    await _drain(db_session_factory)

    reason = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "why did we decide to adopt the platform?"},
        headers=headers,
    )
    assert reason.status_code == 200, reason.text
    assert reason.json()["intent"] in ("decision_reason", "company_operating")

    alternatives = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "what alternatives we considered for the platform?"},
        headers=headers,
    )
    assert alternatives.status_code == 200, alternatives.text
    alt = alternatives.json()
    assert alt["intent"] == "decision_alternatives"
    assert alt.get("decision_id") == decision_id


# ---------------------------------------------------------------------------
# 16. determinism (L3/5.2): byte-identical modulo generated_at + scoped
#     state read renders the identical parameterized shape (§11)
# ---------------------------------------------------------------------------

async def test_byte_identical_and_scoped_shape(client, db_session_factory):
    org = await register_org(client, email="4h3_determ@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=2)

    first = (await client.get(f"{S0}?explain=true", headers=headers)).json()
    second = (await client.get(f"{S0}?explain=true", headers=headers)).json()
    first.pop("generated_at", None)
    second.pop("generated_at", None)
    assert first == second

    scoped = (
        await client.get(
            f"{S0}?explain=true&scope_type=team&scope_id=team:labs",
            headers=headers,
        )
    ).json()
    assert scoped["advisory_only"] is True
    assert scoped["scope_type"] == "team"
    assert set(scoped.keys()) >= {
        "advisory_only", "state_key", "scope_type", "scope_id",
        "snapshot_ref", "dimensions", "delta", "signals", "dependencies",
        "risks", "opportunities", "affected_decisions", "attention", "next",
    }
    assert len(scoped["dimensions"]) == 8