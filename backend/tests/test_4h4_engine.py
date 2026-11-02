"""Slice 4H.4 — Strategic Scenario / Decision-Rehearsal Intelligence.

Under test (contract §15, 15 checks):

1. engine dry-run returns the canonical bounded surface.
2. dry-run writes nothing and emits zero events.
3. API dry-run path serves on brain:read with zero rows written.
4. engine record writes ONE row anchored to exactly ONE
   company.scenario.recorded event.
5. exact-once: identical org+scope+kind+input+snapshot REPLAYS (no row, no
   event); changed input -> NEW row + event (L15 Scenario Identity).
6. invalid kind / missing subject -> honest error dict, zero writes/events.
7. assumptions + effects are bounded (MAX_SCENARIO_ASSUMPTIONS /
   MAX_WHATIF_CONSEQUENCES).
8. API detail re-queries the stored row byte-identically (replayed flag).
9. API 404 for unknown scenario id.
10. API history is bounded and ordered newest-first.
11. API compare accepts 2-5 ids, never ranks, is tenant-scoped.
12. tenant isolation: a sibling org can neither read nor compare.
13. honesty: advisory_only + not_a_prediction on every surface and row;
    cited risks keep their state-fidelity (probability/impact).
14. brain intents: company_scenario + company_scenarios_compare resolve;
    generic "what if we reallocate/delay/hire" STILL routes to the existing
    what-if (collision guard).
15. L15 scenario identity end-to-end: identical rehearsal+snapshot replays
    the identical row; a changed snapshot produces a new rehearsal.
"""

import asyncio

from sqlalchemy import func, select

from app.models.company_operating import (
    MAX_SCENARIO_ASSUMPTIONS,
    MAX_SCENARIOS_SHOWN,
    MAX_WHATIF_CONSEQUENCES,
    CompanyCausalEdge,
    CompanyScenarioRun,
)
from app.models.notification import Event as EventRow
from tests.conftest import register_org

S4 = "/api/v1/brain/execution/company/scenario"
BRAIN_QUERY = "/api/v1/brain/knowledge/query"


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


async def _publish_refresh(db_session_factory, org_id, name="project.started", count=1):
    """Publish real domain events and run the 4H.3 composition bridge so the
    company has a deterministic state snapshot to anchor rehearsals to."""
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
            await asyncio.sleep(0.005)
    return events


async def _count(db_session_factory, org_id, name):
    async with db_session_factory() as db:
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(EventRow).where(
                        EventRow.organization_id == org_id,
                        EventRow.name == name,
                    )
                )
            ).scalar_one() or 0
        )


async def _rows(db_session_factory, org_id):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CompanyScenarioRun)
                    .where(CompanyScenarioRun.organization_id == org_id)
                    .order_by(CompanyScenarioRun.occurred_at.asc())
                )
            ).scalars().all()
        )


async def _rehearse(db_session_factory, org_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.scenario_rehearse(
            db, organization_id=org_id, **kw,
        )
        await db.commit()
        return result


def _canonical_keys(surface: dict) -> set:
    return set(surface.keys()) >= {
        "advisory_only", "not_a_prediction", "baseline", "hypothetical_change",
        "direct_effects", "dependent_effects", "risks_already_present",
        "opportunities_already_present", "decisions_to_reconsider",
        "causal_basis", "snapshot_ref", "honesty", "human_decision",
        "note", "generated_at",
    }


# ---------------------------------------------------------------------------
# 1 + 2. engine dry-run: canonical surface, zero writes, zero events
# ---------------------------------------------------------------------------

async def test_1_2_engine_dry_run_canonical_and_eventless(client, db_session_factory):
    org = await register_org(client, email="4h4_dry@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    surf = await _rehearse(
        db_session_factory, org_id,
        scenario_kind="resource_loss", subject_type="project",
        subject_id="proj:anchor", params={}, assumptions=[],
        dry_run=True,
    )
    assert _canonical_keys(surf), surf.keys()
    assert surf["advisory_only"] is True
    assert surf["not_a_prediction"] is True
    assert surf["dry_run"] is True
    assert surf["scenario_id"] is None
    assert await _rows(db_session_factory, org_id) == []
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 0


# ---------------------------------------------------------------------------
# 4. engine record: one row + exactly one event
# ---------------------------------------------------------------------------

async def test_4_engine_record_writes_row_and_event(client, db_session_factory):
    org = await register_org(client, email="4h4_rec@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    out = await _rehearse(
        db_session_factory, org_id,
        scenario_kind="delay", subject_type="project",
        subject_id="proj:anchor", params={"days": 10}, assumptions=[],
        dry_run=False,
    )
    assert out["created"] is True
    assert out["replayed"] is False
    assert out["dry_run"] is False
    assert out["scenario_id"]
    rows = await _rows(db_session_factory, org_id)
    assert len(rows) == 1
    assert rows[0].source_event_id
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 1


# ---------------------------------------------------------------------------
# 5. exact-once / changed input -> new row (L15)
# ---------------------------------------------------------------------------

async def test_5_exact_once_and_changed_input(client, db_session_factory):
    org = await register_org(client, email="4h4_once@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    kw = dict(scenario_kind="hire", subject_type="project",
              subject_id="proj:anchor", params={"people": 3}, assumptions=[],
              dry_run=False)
    first = await _rehearse(db_session_factory, org_id, **kw)
    assert first["created"] is True
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 1

    replay = await _rehearse(db_session_factory, org_id, **kw)
    assert replay["replayed"] is True
    assert replay["created"] is False
    assert await _rows(db_session_factory, org_id) and len(await _rows(db_session_factory, org_id)) == 1
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 1

    changed = await _rehearse(
        db_session_factory, org_id, scenario_kind="hire", subject_type="project",
        subject_id="proj:anchor", params={"people": 5}, assumptions=[],
        dry_run=False,
    )
    assert changed["created"] is True
    assert await _rows(db_session_factory, org_id) and len(await _rows(db_session_factory, org_id)) == 2
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 2


# ---------------------------------------------------------------------------
# 6. invalid kind / missing subject: honest error, zero writes/events
# ---------------------------------------------------------------------------

async def test_6_invalid_kind_and_subject_honest_errors(client, db_session_factory):
    org = await register_org(client, email="4h4_err@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    bad = await _rehearse(
        db_session_factory, org_id, scenario_kind="magic",
        subject_type="project", subject_id="proj:x", dry_run=False,
    )
    assert "error" in bad
    assert bad["advisory_only"] is True
    assert bad["not_a_prediction"] is True

    missing = await _rehearse(
        db_session_factory, org_id, scenario_kind="delay",
        subject_type="project", subject_id="", dry_run=False,
    )
    assert "error" in missing

    assert await _rows(db_session_factory, org_id) == []
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 0


# ---------------------------------------------------------------------------
# 7. bounds: assumptions + effects capped
# ---------------------------------------------------------------------------

async def test_7_bounded_assumptions_and_effects(client, db_session_factory):
    org = await register_org(client, email="4h4_bnd@test.co")
    org_id = org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    assumptions = [{"name": f"a{i}", "value": f"v{i}"} for i in range(60)]
    out = await _rehearse(
        db_session_factory, org_id, scenario_kind="reallocate",
        subject_type="project", subject_id="proj:anchor",
        params={"from_project_id": "proj:a", "to_project_id": "proj:b", "units": 2},
        assumptions=assumptions, dry_run=False,
    )
    rows = await _rows(db_session_factory, org_id)
    assert len(rows[0].assumptions_json or []) == MAX_SCENARIO_ASSUMPTIONS
    assert len(out["direct_effects"]) <= MAX_WHATIF_CONSEQUENCES
    assert len(out["dependent_effects"]) <= MAX_WHATIF_CONSEQUENCES
    assert out["causal_basis"]["hop_count"] <= 60  # MAX_CAUSAL_EDGES


# ---------------------------------------------------------------------------
# 8 + 9. API detail re-queries stored row; 404 for unknown id
# ---------------------------------------------------------------------------

async def test_8_9_api_detail_replay_and_404(client, db_session_factory):
    org = await register_org(client, email="4h4_det@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    out = await _rehearse(
        db_session_factory, org_id, scenario_kind="dependency_break",
        subject_type="project", subject_id="proj:anchor",
        params={}, assumptions=[], dry_run=False,
    )
    sid = out["scenario_id"]

    detail = (await client.get(f"{S4}/{sid}", headers=headers)).json()
    assert detail["scenario_id"] == sid
    assert detail["replayed"] is True
    assert detail["dry_run"] is False
    assert _canonical_keys(detail)
    assert detail["advisory_only"] is True
    assert detail["not_a_prediction"] is True

    miss = await client.get(f"{S4}/scn:nope", headers=headers)
    assert miss.status_code == 404
    assert miss.json()["detail"] == "scenario not found"


# ---------------------------------------------------------------------------
# 10. API history bounded + newest-first
# ---------------------------------------------------------------------------

async def test_10_api_history_bounded(client, db_session_factory):
    org = await register_org(client, email="4h4_hist@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    for n in range(4):
        await _rehearse(
            db_session_factory, org_id,
            scenario_kind="delay", subject_type="project",
            subject_id="proj:anchor", params={"days": n + 1}, assumptions=[],
            dry_run=False,
        )

    hist2 = (await client.get(f"{S4}?limit=2", headers=headers)).json()
    assert hist2["advisory_only"] is True
    assert len(hist2["scenarios"]) == 2
    assert hist2["total"] == 2
    times = [s["occurred_at"] for s in hist2["scenarios"]]
    assert times == sorted(times, reverse=True)

    hist_all = (await client.get(S4, headers=headers)).json()
    assert len(hist_all["scenarios"]) == 4
    assert hist_all["scenarios"][0]["scenario_kind"] == "delay"


# ---------------------------------------------------------------------------
# 11 + 12 + 13. compare (never ranks, tenant-scoped) + honesty of risks
# ---------------------------------------------------------------------------

async def test_11_12_13_compare_tenant_and_honesty(client, db_session_factory):
    a = await register_org(client, email="4h4_cmp@test.co")
    ha, a_id = a["headers"], a["organization"]["id"]
    b = await register_org(client, email="4h4_cmpb@test.co")
    hb, b_id = b["headers"], b["organization"]["id"]

    await _publish_refresh(db_session_factory, a_id, count=1)
    await _publish_refresh(db_session_factory, b_id, count=1)

    from app.models.approval import Risk

    async with db_session_factory() as db:
        db.add(Risk(
            organization_id=a_id, project_id="proj:anchor",
            title="Key anchor risk", status="identified",
            probability=7, impact=6, risk_score=42,
        ))
        await db.commit()

    ids = []
    for days in (2, 4):
        out = await _rehearse(
            db_session_factory, a_id, scenario_kind="delay",
            subject_type="project", subject_id="proj:anchor",
            params={"days": days}, assumptions=[], dry_run=False,
        )
        ids.append(out["scenario_id"])

    cmp = (await client.post(
        f"{S4}/compare", json={"scenario_ids": ids}, headers=ha,
    )).json()
    assert cmp["advisory_only"] is True
    assert cmp["not_a_prediction"] is True
    assert len(cmp["scenarios"]) == 2
    assert sorted(s["scenario_id"] for s in cmp["scenarios"]) == sorted(ids)
    assert cmp["baseline"]["snapshot_ref"]
    assert "ranked" in cmp["comparison"].lower()
    assert "human decides" in cmp["comparison"].lower()

    # honesty: risks cited keep their state-fidelity (probability/impact).
    detail = (await client.get(f"{S4}/{ids[0]}", headers=ha)).json()
    assert detail["risks_already_present"], "expected the seeded risk to intersect"
    for r in detail["risks_already_present"]:
        assert r.get("probability") == 7 and r.get("impact") == 6

    # tenant isolation: B can neither read nor compare A's scenarios.
    b_get = await client.get(f"{S4}/{ids[0]}", headers=hb)
    assert b_get.status_code == 404
    b_cmp = (await client.post(
        f"{S4}/compare", json={"scenario_ids": ids}, headers=hb,
    )).json()
    assert b_cmp["scenarios"] == []
    b_hist = (await client.get(S4, headers=hb)).json()
    assert b_hist["scenarios"] == []


# ---------------------------------------------------------------------------
# 3. API dry-run serves on brain:read and writes nothing
# ---------------------------------------------------------------------------

async def test_3_api_dry_run_writes_nothing(client, db_session_factory):
    org = await register_org(client, email="4h4_apdry@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)

    r = await client.post(
        S4, json={
            "scenario_kind": "resource_loss", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {}, "assumptions": [],
            "scope_type": "org", "dry_run": True,
        }, headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["created"] is False
    assert body["scenario_id"] is None
    assert await _rows(db_session_factory, org_id) == []
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 0


# ---------------------------------------------------------------------------
# 14. brain intents + collision guard
# ---------------------------------------------------------------------------

async def test_14_brain_intents_and_collision(client, db_session_factory):
    org = await register_org(client, email="4h4_brain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish_refresh(db_session_factory, org_id, count=1)
    from datetime import datetime, timezone

    async with db_session_factory() as db:
        db.add(CompanyCausalEdge(
            organization_id=org_id,
            source_type="project", source_id="proj:anchor",
            target_type="project", target_id="proj:downstream",
            kind="blocked_by", confidence="high",
            source_event_id="evt:4h4-seed",
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()

    await _rehearse(
        db_session_factory, org_id, scenario_kind="delay",
        subject_type="project", subject_id="proj:anchor",
        params={"days": 3}, assumptions=[], dry_run=False,
    )
    await _rehearse(
        db_session_factory, org_id, scenario_kind="hire",
        subject_type="project", subject_id="proj:anchor",
        params={"people": 2}, assumptions=[], dry_run=False,
    )

    rehearse = (await client.post(
        BRAIN_QUERY, json={"question": "what would happen if we delay the platform project?"},
        headers=headers,
    )).json()
    assert rehearse["intent"] == "company_scenario", rehearse.get("intent")
    assert rehearse.get("advisory_only") is True
    assert rehearse.get("dry_run") is True

    compare = (await client.post(
        BRAIN_QUERY, json={"question": "compare the scenarios we rehearsed"},
        headers=headers,
    )).json()
    assert compare["intent"] == "company_scenarios_compare", compare.get("intent")
    assert len(compare.get("scenarios", [])) == 2

    # collision guard: generic "what if we ..." phrasing never resolves to a
    # 4H.4 rehearsal — it stays with the pre-existing intent machinery
    # ("what if we reallocate ..." is the 4G.4 capacity meaning).
    for q, expect in (
        ("what if we reallocate capacity", "capacity"),
        ("what if we delay the platform project", None),
        ("what if we hire 5 engineers", None),
    ):
        res = (await client.post(
            BRAIN_QUERY, json={"question": q}, headers=headers,
        )).json()
        assert res["intent"] not in (
            "company_scenario", "company_scenarios_compare",
        ), f"{q} -> {res.get('intent')}"
        if expect is not None:
            assert res["intent"] == expect, f"{q} -> {res.get('intent')}"


# ---------------------------------------------------------------------------
# 15. L15 scenario identity end-to-end
# ---------------------------------------------------------------------------

async def test_15_l15_identity_snapshot_change(client, db_session_factory):
    org = await register_org(client, email="4h4_l15@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    e1 = await _publish_refresh(db_session_factory, org_id, count=1)
    kw = dict(scenario_kind="reallocate", subject_type="project",
              subject_id="proj:anchor",
              params={"from_project_id": "proj:a", "to_project_id": "proj:b", "units": 1},
              assumptions=[], dry_run=False)
    first = await _rehearse(db_session_factory, org_id, **kw)
    assert first["replayed"] is False and first["created"] is True
    sref1 = first["snapshot_ref"]

    replay = await _rehearse(db_session_factory, org_id, **kw)
    assert replay["replayed"] is True
    assert replay["snapshot_ref"] == sref1

    # changed snapshot (new company.state snapshot) -> NEW rehearsal (L15).
    await _publish_refresh(db_session_factory, org_id, name="task.completed", count=1)
    after = await _rehearse(db_session_factory, org_id, **kw)
    assert after["created"] is True
    assert after["snapshot_ref"] != sref1
    rows = await _rows(db_session_factory, org_id)
    assert len(rows) == 2
    refs = {r.snapshot_ref for r in rows}
    assert len(refs) == 2
    assert await _count(db_session_factory, org_id, "company.scenario.recorded") == 2

    detail = (await client.get(f"{S4}/{first['scenario_id']}", headers=headers)).json()
    assert detail["snapshot_ref"] == sref1
    assert detail["scenario_id"] == first["scenario_id"]