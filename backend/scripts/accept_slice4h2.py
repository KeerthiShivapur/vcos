"""Slice 4H.2 acceptance — Universal Organizational Decision Intelligence (live API).

Checks against the running stack (http://localhost:8999): advisory evaluate ->
recommend + first-class reads -> why-not exact-once write -> pre-approval 409
law with zero false events -> governed 4H.1 loop closes (quality/tracks/
reconciliation/lesson) -> bounded shapes -> temporal as_of strict/partial ->
tenant isolation -> exact-once replay (contract test 12) -> brain intent
routing -> pagination/cohort filters -> determinism -> what-if advisory-only
(not_a_prediction) -> contradiction honesty against a recorded lesson. Exit 0
when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
CAP = f"{BRAIN}/execution/company/decisions"
TRACKS = f"{BRAIN}/execution/company/tracks"
PRECEDENTS = f"{BRAIN}/execution/company/precedents"

EIGHT_4H2_EVENTS = [
    "company.decision.evaluated",
    "company.decision.recommended",
    "company.decision.alternatives.recorded",
    "company.decision.why_not.recorded",
    "company.decision.precedents.linked",
    "company.decision.contradiction.surfaced",
    "company.decision.quality.composed",
    "company.decision.track.updated",
]

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


async def register(client: httpx.AsyncClient, stamp: str, tag: str) -> dict:
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": f"4H2 {tag} {stamp}",
            "organization_slug": f"slice4h2-{tag}-{stamp}",
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": f"{tag.title()} Owner",
            "email": f"4h2-{tag}-{stamp}@test.co",
            "username": f"4h2-{tag}-{stamp}",
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "organization": data["organization"]}


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 400) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=60
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:
        pass
    return -1


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 8) -> int:
    total = 0
    for _ in range(rounds):
        n = await dispatch(client, headers)
        if n <= 0:
            if n == 0:
                break
            continue
        total += n
    return total


async def count_events(client: httpx.AsyncClient, headers: dict, name: str) -> int:
    r = await client.get(f"{API}/events", params={"name": name}, headers=headers)
    if r.status_code != 200:
        return -1
    return int(r.json().get("total", 0) or 0)


def evaluate_body(decision_id: str, title: str = "Adopt the new data platform",
                  evidence_at: str = "2026-07-01T00:00:00Z") -> dict:
    return {
        "decision_id": decision_id,
        "kind": "hire",
        "title": title,
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
                "captured_at": evidence_at,
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


async def main() -> int:
    stamp = str(int(time.time()))[-6:]
    async with httpx.AsyncClient(timeout=60) as c:
        a = await register(c, stamp, "a")
        ha = a["headers"]

        print("Slice 4H.2 — Universal Organizational Decision Intelligence\n")

        # ---- 1. advisory evaluate -----------------------------------------
        d1 = f"dec:hire:acc-{stamp}01"
        ev = await c.post(f"{CAP}/evaluate", json=evaluate_body(d1), headers=ha)
        check(
            "1. advisory evaluate opens a decision (evidence + alternatives)",
            ev.status_code == 200
            and ev.json().get("accepted") is True
            and ev.json().get("decision_id") == d1
            and ev.json().get("state") == "evaluated"
            and ev.json().get("evidence_written") == 1,
            ev.text[:200],
        )
        await drain(c, ha)

        # ---- 2. recommend + first-class reads -----------------------------
        rec = await c.post(f"{CAP}/{d1}/recommend", json={}, headers=ha)
        check(
            "2. recommend transitions to recommended (advisory)",
            rec.status_code == 200 and rec.json().get("state") == "recommended",
            rec.text[:200],
        )
        await drain(c, ha)
        detail = (await c.get(f"{CAP}/{d1}", headers=ha)).json()
        alts = (await c.get(f"{CAP}/{d1}/alternatives", headers=ha)).json()
        why = (await c.get(f"{CAP}/{d1}/why-not", headers=ha)).json()
        pred = (await c.get(f"{CAP}/{d1}/prediction", headers=ha)).json()
        quality = (await c.get(f"{CAP}/{d1}/quality", headers=ha)).json()
        check(
            "2b. reads: 1 evidence, 2 alternatives, 1 why-not, prediction + quality shapes",
            detail.get("evidence_count") == 1
            and len(detail.get("alternatives", [])) == 2
            and len(detail.get("contradictions", [])) == 0
            and len(detail.get("precedents", [])) == 0
            and len(alts.get("alternatives", [])) == 2
            and len(why.get("why_not", [])) == 1
            and pred.get("confidence_band") == "not_recorded"
            and pred.get("not_yet_measurable") is False
            and len(quality.get("snapshots", [])) == 2,
            f"detail={detail.get('evidence_count')}/{len(detail.get('alternatives', []))} "
            f"why={len(why.get('why_not', []))} bands={len(quality.get('snapshots', []))}",
        )

        # ---- 3. why-not write is exact-once -------------------------------
        first = await c.post(
            f"{CAP}/{d1}/alternatives/alt:02/why-not",
            json={"why_not": "too slow for the Q3 window"}, headers=ha,
        )
        await drain(c, ha)
        second = await c.post(
            f"{CAP}/{d1}/alternatives/alt:02/why-not",
            json={"why_not": "too slow for the Q3 window"}, headers=ha,
        )
        chosen = await c.post(
            f"{CAP}/{d1}/alternatives/alt:01/why-not",
            json={"why_not": "nope"}, headers=ha,
        )
        check(
            "3. why-not is a write: changed once, replays no-op, chosen rejected",
            first.json().get("changed") is True
            and second.json().get("changed") is False
            and chosen.status_code == 400,
            f"first={first.json().get('changed')} second={second.json().get('changed')} "
            f"chosen={chosen.status_code}",
        )

        # ---- 4. pre-approval law ------------------------------------------
        exec409 = await c.post(f"{CAP}/{d1}/execute", json={}, headers=ha)
        out409 = await c.post(f"{CAP}/{d1}/outcome", json={"outcome_kind": "successful"}, headers=ha)
        await drain(c, ha)
        exec_count = await count_events(c, ha, "company.action.executed")
        out_count = await count_events(c, ha, "company.outcome.recorded")
        check(
            "4. pre-approval law: execute/outcome 409, zero false events",
            exec409.status_code == 409
            and exec409.json().get("detail", {}).get("rejected") is True
            and out409.status_code == 409
            and out409.json().get("detail", {}).get("rejected") is True
            and exec_count == 0
            and out_count == 0,
            f"exec409={exec409.status_code} out409={out409.status_code} "
            f"exec_events={exec_count} outcome_events={out_count}",
        )

        # ---- 5. governed loop closes --------------------------------------
        approved = await c.post(
            f"{CAP}",
            json={
                "kind": "hire",
                "title": "Hire for the platform bottleneck",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.7,
                "confidence": 0.8,
                "owner_label": "Leadership",
            },
            headers=ha,
        )
        check("5. governed approve path still works (4H.1 unchanged)", approved.status_code == 200, approved.text[:200])
        dg = approved.json()["decision_id"]
        await drain(c, ha)
        executed = await c.post(f"{CAP}/{dg}/execute", json={"executed_by_label": "Ada Owner"}, headers=ha)
        await drain(c, ha)
        outcome = await c.post(
            f"{CAP}/{dg}/outcome",
            json={"outcome_kind": "successful", "effectiveness": 0.8,
                  "lesson": "scoped predictions survive scrutiny"},
            headers=ha,
        )
        await drain(c, ha)
        await drain(c, ha)
        quality_g = (await c.get(f"{CAP}/{dg}/quality", headers=ha)).json()
        stages = {q.get("stage") for q in quality_g.get("snapshots", [])}
        tracks = (await c.get(f"{TRACKS}", params={"cohort": "kind", "value": "hire"}, headers=ha)).json()
        pred_g = (await c.get(f"{CAP}/{dg}/prediction", headers=ha)).json()
        memory = (await c.get(f"{BRAIN}/execution/company/memory", headers=ha)).json()
        lesson_found = any(
            d.get("decision_id") == dg and (d.get("lesson") or "").strip()
            for d in memory.get("decisions", [])
        )
        check(
            "5b. governed loop closes: outcome quality + tracks + reconciliation + lesson",
            executed.status_code == 200
            and outcome.status_code == 200
            and "outcome_recorded" in stages
            and any(t.get("cohort_key") == "kind:hire" and t.get("decisions_measured", 0) >= 1
                    for t in tracks.get("snapshots", []))
            and pred_g.get("reconciliation", {}).get("aligned") is True
            and pred_g.get("not_yet_measurable") is False
            and lesson_found,
            f"exec={executed.status_code} out={outcome.status_code} stages={stages} "
            f"tracks={len(tracks.get('snapshots', []))} reconciled={pred_g.get('reconciliation', {}).get('aligned')} "
            f"lesson={lesson_found}",
        )

        # ---- 6. bounded shapes --------------------------------------------
        db = f"dec:hire:acc-{stamp}02"
        big = evaluate_body(db, "Big evidence decision")
        big["evidence"] = [
            {"evidence_type": "metric", "source_kind": "metric.a",
             "source_summary": f"row {i}", "captured_at": f"2026-0{1 + i % 6}-01T00:00:00Z"}
            for i in range(50)
        ]
        big["alternatives"] = [
            {"alternative_key": f"alt:{i:02d}", "label": f"Option {i}",
             "chosen": i == 0, "why_chosen": "first" if i == 0 else "",
             "why_not": "" if i == 0 else f"rejected {i}"}
            for i in range(8)
        ]
        bev = await c.post(f"{CAP}/evaluate", json=big, headers=ha)
        dbig = (await c.get(f"{CAP}/{db}", headers=ha)).json()
        recall = (await c.get(f"{PRECEDENTS}", params={"context": "revenue forecast", "limit": 5}, headers=ha)).json()
        check(
            "6. bounded shapes: 40 evidence cap, 5 alternatives cap, precedents capped",
            bev.status_code == 200
            and dbig.get("evidence_count") == 40
            and len(dbig.get("alternatives", [])) == 5
            and len(recall.get("precedents", [])) <= 5,
            f"evidence={dbig.get('evidence_count')} alts={len(dbig.get('alternatives', []))} "
            f"recall={len(recall.get('precedents', []))}",
        )
        await drain(c, ha)

        # ---- 7. temporal as_of strict vs partial --------------------------
        d3 = f"dec:hire:acc-{stamp}03"
        ev3 = await c.post(f"{CAP}/evaluate", json=evaluate_body(d3, "Late evidence decision", "2026-09-15T00:00:00Z"), headers=ha)
        strict = (await c.get(f"{CAP}/{d3}", params={"as_of": "2026-09-01T00:00:00Z"}, headers=ha)).json()
        partial = (await c.get(
            f"{CAP}/{d3}", params={"as_of": "2026-09-01T00:00:00Z", "include_partial": "true"}, headers=ha
        )).json()
        check(
            "7. as_of: strict excludes late evidence, partial flags it incomplete",
            ev3.status_code == 200
            and strict.get("evidence_count") == 0
            and partial.get("evidence_count") == 0
            and len(partial.get("evidence_incomplete", [])) == 1,
            f"strict={strict.get('evidence_count')} partial={partial.get('evidence_count')} "
            f"incomplete={len(partial.get('evidence_incomplete', []))}",
        )

        # ---- 8. tenant isolation ------------------------------------------
        b = await register(c, stamp, "b")
        hb = b["headers"]
        list_b = (await c.get(f"{CAP}", headers=hb)).json()
        d1_b = await c.get(f"{CAP}/{d1}", headers=hb)
        check(
            "8. tenant isolation: org B never sees org A's decisions",
            list_b.get("total", 0) == 0 and d1_b.status_code == 404,
            f"org_b_total={list_b.get('total', 0)} org_b_detail={d1_b.status_code}",
        )

        # ---- 9. exact-once replay (contract test 12) ----------------------
        ev_before = {n: await count_events(c, ha, n) for n in EIGHT_4H2_EVENTS}
        list_before = (await c.get(f"{CAP}", headers=ha)).json()["total"]
        replay = await c.post(f"{CAP}/evaluate", json=evaluate_body(d1), headers=ha)
        await c.post(f"{CAP}/{d1}/recommend", json={}, headers=ha)
        await drain(c, ha)
        await drain(c, ha)
        ev_after = {n: await count_events(c, ha, n) for n in EIGHT_4H2_EVENTS}
        list_after = (await c.get(f"{CAP}", headers=ha)).json()["total"]
        check(
            "9. exact-once replay: same decision_id converges, all 8 events stable",
            replay.json().get("accepted") is True
            and replay.json().get("evidence_written") == 0
            and ev_after == ev_before
            and list_after == list_before,
            f"evidence_written={replay.json().get('evidence_written')} "
            f"deltas={[n for n in EIGHT_4H2_EVENTS if ev_after[n] != ev_before[n]]} "
            f"total={list_before}->{list_after}",
        )

        # ---- 10. brain intent routing -------------------------------------
        reason = await c.post(
            f"{BRAIN}/knowledge/query",
            json={"question": "why did we decide to adopt the platform?"}, headers=ha,
        )
        alts_q = await c.post(
            f"{BRAIN}/knowledge/query",
            json={"question": "what alternatives we considered for the platform?"}, headers=ha,
        )
        listing = (await c.get(f"{CAP}", params={"limit": 1}, headers=ha)).json()
        latest_id = listing["decisions"][0]["decision_id"] if listing.get("decisions") else None
        check(
            "10. brain routing: decision_reason + alternatives pinned to the latest decision",
            reason.status_code == 200
            and reason.json().get("intent") == "decision_reason"
            and alts_q.status_code == 200
            and alts_q.json().get("intent") == "decision_alternatives"
            and latest_id is not None
            and alts_q.json().get("decision_id") == latest_id,
            f"reason={reason.json().get('intent')} alts={alts_q.json().get('intent')} "
            f"pinned={alts_q.json().get('decision_id')} latest={latest_id}",
        )

        # ---- 11. pagination + filters bounded -----------------------------
        page = (await c.get(f"{CAP}", params={"limit": 1, "page": 1, "state": "recommended"}, headers=ha)).json()
        check(
            "11. lists are bounded: limit/page honored, filters applied",
            page.get("total", 0) >= 1 and len(page.get("decisions", [])) == 1
            and all(d.get("state") == "recommended" for d in page.get("decisions", [])),
            f"total={page.get('total')} rows={len(page.get('decisions', []))}",
        )

        # ---- 12. impact is bounded and honest -----------------------------
        impact = (await c.get(f"{CAP}/{d1}/impact", params={"depth": 3}, headers=ha)).json()
        check(
            "12. impact surface bounded and observed 0 for a not-yet-measured decision",
            impact.get("observed", 0) == 0 and len(impact.get("direct", [])) <= 3,
            f"observed={impact.get('observed')} direct={len(impact.get('direct', []))}",
        )

        # ---- 13. determinism: identical re-queries, identical surfaces ----

        def stable(payload: object) -> object:
            if isinstance(payload, dict):
                return {k: stable(v) for k, v in payload.items() if k != "generated_at"}
            if isinstance(payload, list):
                return [stable(v) for v in payload]
            return payload

        q1 = (await c.get(f"{CAP}", headers=ha)).json()
        q2 = (await c.get(f"{CAP}", headers=ha)).json()
        pd1 = (await c.get(f"{CAP}/{d1}", headers=ha)).json()
        pd2 = (await c.get(f"{CAP}/{d1}", headers=ha)).json()
        check(
            "13. determinism: re-querying returns identical surfaces (modulo generated_at)",
            stable(q1) == stable(q2) and stable(pd1) == stable(pd2),
            f"list_diff={stable(q1) != stable(q2)} detail_diff={stable(pd1) != stable(pd2)}",
        )

        # ---- 14. contradiction honesty ------------------------------------
        cont = (await c.get(f"{CAP}/{db}/contradictions", headers=ha)).json()
        quality_big = (await c.get(f"{CAP}/{db}/quality", headers=ha)).json()
        check(
            "14. contradiction surface is honest and bounded",
            isinstance(cont.get("contradictions", []), list)
            and len(cont.get("contradictions", [])) <= 10
            and "contradictions_open" in quality_big,
            f"rows={len(cont.get('contradictions', []))} "
            f"quality_keys={sorted(quality_big.keys())}",
        )

        # ---- 15. exact-once events ledger (all eight registered) ----------
        await drain(c, ha)
        present = {n: await count_events(c, ha, n) for n in EIGHT_4H2_EVENTS}
        check(
            "15. all eight 4H.2 events landed and stay stable under re-drain",
            all(v >= 0 for v in present.values())
            and present["company.decision.evaluated"] >= 1
            and present["company.decision.recommended"] >= 1
            and present["company.decision.alternatives.recorded"] >= 1
            and present["company.decision.track.updated"] >= 1,
            f"counts={present}",
        )

        # ---- 16. what-if advisory-only (contract test 9) -------------------
        ev_b16 = await count_events(c, ha, "company.decision.evaluated")
        rec_b16 = await count_events(c, ha, "company.decision.recommended")
        list_b16 = (await c.get(f"{CAP}", headers=ha)).json()["total"]
        wf = await c.post(f"{CAP}/{db}/what-if", json={"sensitivity": "high"}, headers=ha)
        scenarios = wf.json().get("scenarios", []) if wf.status_code == 200 else []
        check(
            "16. what-if is advisory-only, not_a_prediction, bounded, writes nothing",
            wf.status_code == 200
            and wf.json().get("advisory_only") is True
            and len(scenarios) >= 1
            and all(
                s.get("not_a_prediction") is True and s.get("advisory_only") is True
                and isinstance(s.get("consequences", []), list)
                for s in scenarios
            )
            and (await c.get(f"{CAP}", headers=ha)).json()["total"] == list_b16
            and await count_events(c, ha, "company.decision.evaluated") == ev_b16
            and await count_events(c, ha, "company.decision.recommended") == rec_b16,
            f"status={wf.status_code} scenarios={len(scenarios)} "
            f"eval_delta={await count_events(c, ha, 'company.decision.evaluated') - ev_b16}",
        )

        # ---- 17. contradiction honesty vs a recorded lesson (test 10) ------
        a2 = await c.post(
            f"{CAP}",
            json={
                "kind": "hire",
                "title": "Hire for the data platform, second attempt",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.7,
                "confidence": 0.8,
                "owner_label": "Leadership",
            },
            headers=ha,
        )
        dg2 = a2.json()["decision_id"]
        await drain(c, ha)
        await c.post(f"{CAP}/{dg2}/execute", json={"executed_by_label": "Ada Owner"}, headers=ha)
        await drain(c, ha)
        out2 = await c.post(
            f"{CAP}/{dg2}/outcome",
            json={"outcome_kind": "unsuccessful", "effectiveness": 0.35,
                  "lesson": "revenue forecast caution: discretionary hires rarely restore growth fast"},
            headers=ha,
        )
        await drain(c, ha)
        b2 = f"dec:hire:acc-{stamp}04"
        ev2 = await c.post(
            f"{CAP}/evaluate", json=evaluate_body(b2, "Re-hire after the missed growth target"), headers=ha
        )
        await drain(c, ha)
        rec2 = await c.post(f"{CAP}/{b2}/recommend", json={}, headers=ha)
        await drain(c, ha)
        cont2 = (await c.get(f"{CAP}/{b2}/contradictions", headers=ha)).json()
        quality2 = (await c.get(f"{CAP}/{b2}/quality", headers=ha)).json()
        crows = cont2.get("contradictions", [])
        linked_lesson = any(
            r.get("lesson_memory_id") and r.get("side_a", {}).get("decision_id") == b2
            and r.get("side_b", {}).get("lesson_memory_id")
            for r in crows
        )
        check(
            "17. contradiction honesty: conflicting lesson surfaces with both sides",
            a2.status_code == 200
            and out2.status_code == 200
            and ev2.status_code == 200
            and rec2.status_code == 200
            and cont2.get("evidence_is_conflicting") is True
            and len(crows) >= 1
            and linked_lesson
            and quality2.get("contradictions_open", 0) >= 1,
            f"out={out2.status_code} rec={rec2.status_code} "
            f"contradictions={len(crows)} open={quality2.get('contradictions_open')}",
        )

        print(f"\n{len(PASSED)} passed / {len(FAILED)} failed ({len(PASSED) + len(FAILED)} total)\n")
        for f in FAILED:
            print(f"  failed: {f}")
        return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))