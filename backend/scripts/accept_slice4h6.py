"""Slice 4H.6 acceptance - Outcome & Performance Intelligence (live API,
contract section 12, 16 checks).

Against the running stack (http://localhost:8999): a seeded org records
decision outcomes through the EXISTING 4H.1 surface, canonical metrics and
observations are seeded directly (mirroring what the existing 4G.6 writers
produce), and the NEW read-only composition surfaces are exercised:

 1. recorded outcome verbatim (L20): effectiveness 0.8 round-trips
    UNCHANGED into the assessment; prediction compare aligned.
 2. unknown stays unknown: missing outcome -> truth unknown +
    no_outcome_recorded; single-observation metric -> unknown
    (no_actual_observation_pair), NEVER zero-filled.
 3. derived measurement cites its basis: delta over an actual-only
    observation pair carries BOTH observation ids; value is plain
    arithmetic over the pair.
 4. temporal basis explicit everywhere: anchor + anchor_basis at the top,
    per-measurement anchor/baseline_as_of/comparison_as_of/window.
 5. attribution honesty: evidence_indicates link -> SUPPORTED;
    linked_to-only -> ASSOCIATED association_link_only (never upgraded).
 6. determinism: identical canonical rows -> byte-identical assessment /
    cohort / comparison payloads (generated_at stripped).
 7. cohort composition + Track untouched: histogram counts, derived mean
    effectiveness citing both decision ids, honesty flag
    track_infrastructure_untouched, company_decision_tracks row count
    stable across every read.
 8. comparison neutral (L23): side-by-side columns + factual contrasts;
    NO winner/rank/score/probability/forecast/recommendation KEYS
    anywhere in the payload.
 9. bounded rejections, never truncation: <2 unique -> 409
    at_least_two_unique_decisions_required; 6 ids -> 409
    too_many_decisions (received=6, max=5); duplicates deduped.
10. not_found + tenant isolation: missing id -> comparison.not_found while
    the resolvable pair still compares; sibling org GET -> 404, empty
    cohort, cross-org compare -> 409 fewer_than_two_resolvable.
11. moat T1->T3 with ZERO code change: the same decision's assessment
    strictly enriches as the company operates more (unknown outcome ->
    recorded outcome -> derived measurement appears).
12. runtime read-only: org event total identical across a pure-read phase;
    decision detail byte-identical before/after; observation/link/track/
    edge row counts stable across reads.
13. schema introspection: candidate 4H.6 event names = 0 rows; no new
    performance/scoring/analytics tables; no banned columns.
14. brain intents: perform/measured-change/comparison questions route to
    the new intents with anchors; protected older phrasings never hit them.
15. honesty surfaces everywhere: advisory_only/read_only/no_scores/
    no_forecasting/no_people_scoring on every new payload.
16. frontend static parity: typed windows + fetchers in lib/api.ts and
    the PerformancePanel in company-tab.tsx exist (tsc is the build gate).

Exit 0 only when all pass.
"""

import asyncio
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
DECISIONS = f"{BRAIN}/execution/company/decisions"
BRAIN_QUERY = f"{BRAIN}/knowledge/query"
COHORT = f"{BRAIN}/execution/company/performance/cohort"
COMPARE = f"{BRAIN}/execution/company/decisions/compare"

NEW_INTENTS = {
    "company_decision_performance",
    "company_measured_change",
    "company_decision_comparison",
}
CANDIDATE_EVENTS = [
    "company.decision.performance.read", "company.performance.read",
    "company.performance.cohort.read", "company.decisions.compared",
    "company.decision.measured_change", "company.performance.compared",
]
FORBIDDEN_KEYS = {
    "winner", "winners", "rank", "ranking", "ranked", "score", "scores",
    "probability", "forecast", "forecasted", "recommendation",
    "recommendations", "prediction_score",
}

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


def forbidden_key_hits(obj, prefix: str = "") -> list[str]:
    """Exact-name scan for banned concept keys. Honesty NEGATION flags
    (no_scores, not_a_prediction, compare_not_rank, ...) are required by
    the contract and are skipped; only positive occurrences violate
    L23/L27."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if not (kl.startswith("no_") or kl.startswith("not_") or "not_rank" in kl):
                if kl in FORBIDDEN_KEYS or kl.endswith("_rank") or kl.endswith("_score"):
                    hits.append(f"{prefix}{k}")
            hits += forbidden_key_hits(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += forbidden_key_hits(v, f"{prefix}[{i}].")
    return hits


async def register(client: httpx.AsyncClient, stamp: str, tag: str) -> dict:
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": f"4H6 {tag} {stamp}",
            "organization_slug": f"slice4h6-{tag}-{stamp}",
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": f"{tag.title()} Owner",
            "email": f"4h6-{tag}-{stamp}@test.co",
            "username": f"4h6-{tag}-{stamp}",
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "organization": data["organization"]}


async def invite_member(client: httpx.AsyncClient, headers: dict, stamp: str) -> dict:
    """Scoped reader per the ratified 4D.6 helper sequence: invite as
    employee, DROP the default org-wide assignment, grant a project-scoped
    manager role + brain:read delegation — otherwise the member is
    org-wide and the governance gate cannot be exercised."""
    email = f"4h6-member-{stamp}@test.co"
    inv = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Member User", "role": "employee"},
        headers=headers,
    )
    assert inv.status_code == 201, inv.text
    token = inv.json().get("token")
    url = inv.json().get("url", "")
    if not token:
        token = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("token", [""])[0]
    acc = await client.post(
        f"{API}/auth/register/invite",
        json={"token": token, "full_name": "Member User", "password": "StrongPass123!", "username": f"4h6-member-{stamp}"},
    )
    assert acc.status_code in (200, 201), acc.text
    hmem = {"Authorization": f"Bearer {acc.json()['access_token']}"}
    user_id = acc.json()["user"]["id"]

    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")
    scope = await client.post(f"{API}/governance/scopes", json={
        "name": f"Scoped reader project {stamp}", "scope_type": "project"},
        headers=headers)
    assert scope.status_code in (200, 201), scope.text
    scope_id = scope.json()["id"]
    assign = await client.post(f"{API}/governance/assignments", json={
        "user_id": user_id, "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers)
    assert assign.status_code in (200, 201), assign.text
    assignments = (await client.get(f"{API}/governance/assignments",
                                    params={"user_id": user_id}, headers=headers)).json()
    org_wide = next(a for a in assignments if a.get("scope_id") is None)
    dele = await client.delete(f"{API}/governance/assignments/{org_wide['id']}",
                               headers=headers)
    assert dele.status_code in (200, 204), dele.text
    deleg = await client.post(f"{API}/governance/delegations", json={
        "granted_to_user": user_id, "permission_code": "brain:read",
        "reason": "4h6 acceptance scoped reader"}, headers=headers)
    assert deleg.status_code in (200, 201), deleg.text
    return {"headers": hmem}


def first_diffs(a, b, prefix: str = "", limit: int = 5) -> list[str]:
    """First few differing paths between two JSON-ish structures."""
    out: list[str] = []
    if type(a) is not type(b):
        return [f"{prefix}: type {type(a).__name__} vs {type(b).__name__}"]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if len(out) >= limit:
                break
            if k not in a or k not in b:
                out.append(f"{prefix}.{k}: present={k in a}/{k in b}")
            else:
                out += first_diffs(a[k], b[k], f"{prefix}.{k}", limit - len(out))
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{prefix}: len {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            if len(out) >= limit:
                break
            out += first_diffs(x, y, f"{prefix}[{i}]", limit - len(out))
    elif a != b:
        out.append(f"{prefix}: {str(a)[:60]!r} vs {str(b)[:60]!r}")
    return out


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 6) -> int:
    total = 0
    for _ in range(rounds):
        try:
            r = await client.post(
                f"{API}/intelligence/events/process", params={"limit": 400}, headers=headers, timeout=60
            )
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200:
            continue
        n = int(r.json().get("processed", 0) or 0)
        if n <= 0:
            break
        total += n
    return total


async def org_event_total(client: httpx.AsyncClient, headers: dict) -> int:
    r = await client.get(f"{API}/events", params={"page_size": 1}, headers=headers)
    if r.status_code != 200:
        return -1
    return int(r.json().get("total", 0) or 0)


def db_dsn() -> str:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    url = ""
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    assert url, "DATABASE_URL not found in backend/.env"
    return url.replace("+asyncpg", "")


async def seed_metric(dsn: str, org_id: str, metric_id: str, key: str, label: str,
                      direction: str = "up_is_good", unit: str = "pct") -> None:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(
            'INSERT INTO business_metrics (id, organization_id, key, label, kind,'
            ' direction, unit, status, visibility, period_granularity, scope,'
            ' source_event_id, created_at, updated_at)'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$13)',
            metric_id, org_id, key, label, "operational", direction, unit,
            "active", "internal", "monthly", "org_wide", f"evt:{metric_id}",
            datetime.now(timezone.utc),
        )
    finally:
        await conn.close()


async def seed_observation(dsn: str, org_id: str, metric_id: str, value: float,
                           days_ago: int, seq: int) -> str:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        when = datetime.now(timezone.utc) - timedelta(days=days_ago)
        oid = f"obs:4h6-{seq}-{metric_id[-6:]}"
        await conn.execute(
            'INSERT INTO business_metric_observations (id, organization_id,'
            ' metric_id, value, observed_at, unit, label, source, provenance,'
            ' source_event_id, created_at, updated_at)'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11) RETURNING id',
            oid, org_id, metric_id, value, when, "pct", "actual", "manual",
            "seeded by accept_slice4h6", f"evt:{oid}", datetime.now(timezone.utc),
        )
        return oid
    finally:
        await conn.close()


async def seed_link(dsn: str, org_id: str, metric_id: str, decision_id: str,
                    kind: str, tag: str) -> None:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(
            'INSERT INTO business_performance_links (id, organization_id,'
            ' entity_type, entity_id, target_type, target_id, kind, weight,'
            ' evidence_count, reasoning, source, source_event_id,'
            ' created_at, updated_at)'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$13)',
            f"lnk:4h6-{tag}-{metric_id[-6:]}", org_id, "business_metric", metric_id,
            "decision", decision_id, kind,
            0.9 if kind == "evidence_indicates" else 0.4, 1,
            "seeded by acceptance", "manual", f"evt:lnk-4h6-{tag}-{metric_id[-6:]}",
            datetime.now(timezone.utc),
        )
    finally:
        await conn.close()


async def db_counts(dsn: str, org_id: str) -> dict:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        out = {}
        for table in ("business_metric_observations", "business_performance_links",
                      "company_decision_tracks", "company_causal_edges",
                      "company_action_outcomes"):
            out[table] = int(await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE organization_id=$1", org_id))
        return out
    finally:
        await conn.close()


def find_item(payload: dict, key: str) -> dict | None:
    for it in payload.get("measured", {}).get("items", []):
        if it.get("metric", {}).get("key") == key:
            return it
    return None


async def main() -> int:
    stamp = str(int(time.time()))[-6:]
    dsn = db_dsn()
    async with httpx.AsyncClient(timeout=60) as c:
        a = await register(c, stamp, "a")
        ha = a["headers"]
        org_id = a["organization"]["id"]
        member = await invite_member(c, ha, stamp)
        hmem = member["headers"]
        b = await register(c, stamp, "b")
        hb = b["headers"]

        print("\n=== VCOS Slice 4H.6 acceptance: Outcome & Performance Intelligence (live) ===\n")

        await drain(c, ha)
        time.sleep(1.0)

        # ---- Phase A: writes ONLY through pre-existing surfaces ----
        made: dict[str, str] = {}
        # Kinds chosen so dec:{kind}:{hex12} <= 32 chars: company_memory
        # .entity_id is VARCHAR(32) (pre-existing platform limitation for
        # long-kind decision ids on live Postgres - see verification report);
        # 4H.6 ratification forbids schema changes in this slice.
        titles = {
            "d1": ("hire", "Vendor invoicing overhaul wave"),
            "d2": ("delay_project", "Warehouse consolidation pilot"),
            "d3": ("change_priority", "Support staffing rebalance"),
        }
        for name, (kind, title) in titles.items():
            r = await c.post(DECISIONS, json={
                "kind": kind, "title": title,
                "rationale": "Acceptance seeding for outcome intelligence.",
                "predicted_outcome": {"expected_outcome": "successful"},
                "prediction_confidence": 0.6,
            }, headers=ha)
            assert r.status_code in (200, 201), r.text
            made[name] = r.json()["decision_id"]
        await drain(c, ha)
        time.sleep(0.8)

        for name in ("d1", "d2", "d3"):
            r = await c.post(f"{DECISIONS}/{made[name]}/execute",
                             json={"executed_by_label": "Ops Lead"}, headers=ha)
            assert r.status_code == 200, r.text
            await drain(c, ha)
            time.sleep(0.4)
        await drain(c, ha)

        r = await c.post(f"{DECISIONS}/{made['d1']}/outcome", json={
            "outcome_kind": "successful", "effectiveness": 0.8,
            "lesson": "invoicing overhaul landed on time"}, headers=ha)
        assert r.status_code == 200, r.text
        r = await c.post(f"{DECISIONS}/{made['d2']}/outcome", json={
            "outcome_kind": "partial", "effectiveness": 0.55,
            "lesson": "consolidation partially adopted"}, headers=ha)
        assert r.status_code == 200, r.text
        await drain(c, ha)
        time.sleep(0.5)

        d1, d2, d3 = made["d1"], made["d2"], made["d3"]

        # canonical metrics/observations/links (mirror 4G.6 writer output).
        # Measurement windows look FORWARD from the decision anchor
        # [anchor, anchor+90d]: baseline = latest actual <= anchor,
        # comparison = earliest actual > anchor - so pairs straddle it.
        await seed_metric(dsn, org_id, f"met:4h6-{stamp}-1", "on_time_payment_rate",
                          "On-Time Payment Rate")
        obs_base = await seed_observation(dsn, org_id, f"met:4h6-{stamp}-1", 120.0, 20, 1)
        obs_comp = await seed_observation(dsn, org_id, f"met:4h6-{stamp}-1", 150.0, -5, 2)
        await seed_link(dsn, org_id, f"met:4h6-{stamp}-1", d1, "evidence_indicates", "sup")
        await seed_metric(dsn, org_id, f"met:4h6-{stamp}-3", "csat_after_rebalance",
                          "CSAT After Rebalance")
        await seed_observation(dsn, org_id, f"met:4h6-{stamp}-3", 42.0, 8, 3)
        await seed_link(dsn, org_id, f"met:4h6-{stamp}-3", d3, "linked_to", "assoc")

        counts_after_writes = await db_counts(dsn, org_id)

        perf1 = (await c.get(f"{DECISIONS}/{d1}/performance", headers=ha))
        assert perf1.status_code == 200, perf1.text
        p1 = perf1.json()
        perf3 = (await c.get(f"{DECISIONS}/{d3}/performance", headers=ha)).json()
        cohort1 = (await c.get(COHORT, headers=ha))
        assert cohort1.status_code == 200, cohort1.text
        c1 = cohort1.json()

        # ---- 1: recorded outcome verbatim (L20) ----
        print("  -- 1. recorded outcome round-trips verbatim (no recomputation)")
        orec = p1["observed"]["outcome_record"]
        check("recorded_outcome_verbatim",
              orec["truth"] == "recorded" and orec["outcome_kind"] == "successful"
              and orec["effectiveness"] == 0.8
              and p1["assessed"]["recorded_effectiveness"] == 0.8
              and (orec.get("actual_outcome_compare") or {}).get("aligned") is True,
              json.dumps(orec))

        # ---- 2: unknown stays unknown, never zero ----
        print("  -- 2. unknowns are named, never zero-filled")
        orec3 = perf3["observed"]["outcome_record"]
        item3 = find_item(perf3, "csat_after_rebalance")
        meas3 = (item3 or {}).get("measurement", {})
        comp3 = meas3.get("comparison") or {}
        check("unknown_stays_unknown",
              orec3["truth"] == "unknown" and orec3["reason"] == "no_outcome_recorded"
              and orec3["outcome_kind"] is None
              and meas3.get("truth") == "unknown"
              and meas3.get("reason") == "comparison_observation_missing"
              and meas3.get("value") is None
              and comp3.get("truth_level") == "unknown"
              and perf3["unknown"]["count"] >= 2,
              json.dumps({"orec3": orec3, "meas3": meas3}))

        # ---- 3: derived measurement cites both observation ids ----
        print("  -- 3. derived delta cites its observation basis")
        item1 = find_item(p1, "on_time_payment_rate")
        meas1 = (item1 or {}).get("measurement", {})
        basis = meas1.get("basis", {})
        check("derived_cites_observation_pair",
              meas1.get("truth") == "derived" and meas1.get("value") == 30.0
              and basis.get("baseline_observation_id") == obs_base
              and basis.get("comparison_observation_id") == obs_comp
              and (meas1.get("baseline", {}).get("observation_id") == obs_base),
              json.dumps(meas1))

        # ---- 4: explicit temporal basis ----
        print("  -- 4. temporal basis explicit (anchor/as-of/window)")
        tb_item = meas1.get("temporal_basis", {})
        check("temporal_basis_explicit",
              p1["temporal_basis"].get("anchor")
              and p1["temporal_basis"].get("anchor_basis") == "executed_at"
              and tb_item.get("anchor") and tb_item.get("baseline_as_of")
              and tb_item.get("comparison_as_of")
              and isinstance(tb_item.get("window_days"), int),
              json.dumps({"top": p1["temporal_basis"], "item": tb_item}))

        # ---- 5: attribution levels honest ----
        print("  -- 5. attribution SUPPORTED vs ASSOCIATED (never upgraded)")
        att1 = (item1 or {}).get("attribution", {})
        att3 = (item3 or {}).get("attribution", {})
        check("attribution_levels_honest",
              att1.get("level") == "SUPPORTED"
              and any(x.get("type") == "business_performance_link" for x in att1.get("basis", []))
              and att3.get("level") == "ASSOCIATED"
              and att3.get("reason") == "association_link_only",
              json.dumps({"att1": att1, "att3": att3}))

        # ---- 7: cohort composition, tracks untouched ----
        print("  -- 7. cohort histogram + derived aggregate + tracks untouched")
        agg = c1["effectiveness_aggregate"]
        check("cohort_composition",
              c1["cohort"]["decision_count"] == 3
              and c1["recorded_outcomes"]["by_kind"]["successful"] == 1
              and c1["recorded_outcomes"]["by_kind"]["partial"] == 1
              and c1["recorded_outcomes"]["without_outcome_record"] == 1
              and agg["truth_level"] == "derived" and abs(agg["value"] - 0.675) < 1e-9
              and sorted(agg["basis"]) == sorted([d1, d2])
              and c1["honesty"]["track_infrastructure_untouched"] is True,
              json.dumps({"by_kind": c1["recorded_outcomes"], "agg": agg}))
        tracks_before = counts_after_writes["company_decision_tracks"]

        # ---- 8: neutral comparison, no banned keys ----
        print("  -- 8. comparison is side-by-side evidence, never a ranking")
        comp = (await c.post(COMPARE, json={"decision_ids": [d1, d2, d3]}, headers=ha))
        assert comp.status_code == 200, comp.text
        cp = comp.json()
        hits = forbidden_key_hits(cp)
        check("comparison_neutral_no_rank_keys",
              cp["comparison"]["compared"] == 3
              and len(cp["columns"]) == 3
              and set(cp["contrasts"]) == {"outcome_record_present",
                                           "derived_measurement_present",
                                           "supported_attribution_present"}
              and cp["honesty"]["compare_not_rank"] is True
              and cp["honesty"]["no_winner_field"] is True
              and not hits,
              f"banned keys: {hits}")

        # ---- 9: bounded rejections, never truncated ----
        print("  -- 9. bounds REJECT, they never silently truncate")
        r_one = await c.post(COMPARE, json={"decision_ids": [d1]}, headers=ha)
        r_six = await c.post(COMPARE, json={
            "decision_ids": ["dec:x1", "dec:x2", "dec:x3", "dec:x4", "dec:x5", "dec:x6"]},
            headers=ha)
        r_dup = await c.post(COMPARE, json={"decision_ids": [d1, d1, d2]}, headers=ha)
        dup_ok = r_dup.status_code == 200 and r_dup.json()["comparison"]["requested"] == 2 \
            and r_dup.json()["comparison"]["compared"] == 2
        check("bounded_rejections_never_truncated",
              r_one.status_code == 409
              and r_one.json()["detail"].get("reason") == "at_least_two_unique_decisions_required"
              and r_six.status_code == 409
              and r_six.json()["detail"].get("reason") == "too_many_decisions"
              and r_six.json()["detail"].get("received") == 6
              and r_six.json()["detail"].get("max_decisions") == 5
              and dup_ok,
              f"one={r_one.text[:140]} six={r_six.text[:140]} dup={r_dup.text[:140]}")

        # ---- 10: not_found + tenant isolation ----
        print("  -- 10. tenant isolation + honest not_found")
        r_nf = await c.post(COMPARE, json={"decision_ids": [d1, d2, "dec:missing-xyz"]},
                            headers=ha)
        sib_perf = await c.get(f"{DECISIONS}/{d1}/performance", headers=hb)
        sib_cohort = (await c.get(COHORT, headers=hb)).json()
        cross_ok = r_nf.status_code == 200 \
            and r_nf.json()["comparison"]["not_found"] == ["dec:missing-xyz"] \
            and r_nf.json()["comparison"]["compared"] == 2
        br = await c.post(DECISIONS, json={
            "kind": "hire", "title": "Sibling org decision",
            "predicted_outcome": {"expected_outcome": "successful"}}, headers=hb)
        assert br.status_code in (200, 201), br.text
        bd1 = br.json()["decision_id"]
        await drain(c, hb)
        r_cross = await c.post(COMPARE, json={"decision_ids": [bd1, d1]}, headers=hb)
        check("not_found_and_tenant_isolation",
              cross_ok and sib_perf.status_code == 404
              and sib_cohort["cohort"]["decision_count"] == 0
              and r_cross.status_code == 409
              and r_cross.json()["detail"].get("reason") == "fewer_than_two_resolvable_decisions"
              and d1 in (r_cross.json()["detail"].get("not_found") or []),
              f"nf={r_nf.status_code} sib={sib_perf.status_code} cross={r_cross.status_code} {r_cross.text[:180]}")

        # ---- 11: moat T1->T3 with zero code change ----
        print("  -- 11. moat: same decision strictly enriches, zero code change")
        r = await c.post(f"{DECISIONS}/{d3}/outcome", json={
            "outcome_kind": "successful", "effectiveness": 0.7,
            "lesson": "rebalance held"}, headers=ha)
        assert r.status_code == 200, r.text
        await drain(c, ha)
        time.sleep(0.5)
        t2 = (await c.get(f"{DECISIONS}/{d3}/performance", headers=ha)).json()
        await seed_observation(dsn, org_id, f"met:4h6-{stamp}-3", 51.0, -2, 4)
        t3 = (await c.get(f"{DECISIONS}/{d3}/performance", headers=ha)).json()
        t3_item = find_item(t3, "csat_after_rebalance") or {}
        t3_meas = t3_item.get("measurement", {})
        check("moat_t1_to_t3_zero_code_change",
              t2["observed"]["outcome_record"]["truth"] == "recorded"
              and t2["observed"]["outcome_record"]["effectiveness"] == 0.7
              and t3_meas.get("truth") == "derived" and t3_meas.get("value") == 9.0
              and len(t3["measured"]["items"]) == len(perf3["measured"]["items"]),
              json.dumps({"t2truth": t2["observed"]["outcome_record"]["truth"],
                          "t3meas": t3_meas}))

        # ---- Phase D: PURE reads only from here ----
        # The moat phase's legitimate writes (D3 outcome events -> track
        # rollups) have settled; everything below must touch nothing.
        counts_pure_start = await db_counts(dsn, org_id)
        counts_pure_start["business_metric_observations"] -= 1  # moat seed write
        events_get_start = await org_event_total(c, ha)
        detail_before = (await c.get(f"{DECISIONS}/{d1}", headers=ha)).json()

        p_get = (await c.get(f"{DECISIONS}/{d1}/performance", headers=ha)).json()
        (await c.get(f"{DECISIONS}/{d3}/performance", headers=ha))
        c_get = (await c.get(COHORT, headers=ha)).json()
        (await c.get(COHORT, params={"kind": "hire"}, headers=ha))
        detail_after = (await c.get(f"{DECISIONS}/{d1}", headers=ha)).json()
        events_get_end = await org_event_total(c, ha)

        # ---- 12: runtime read-only ----
        # The pre-existing 4H.2 decision-detail route embeds its own
        # generated_at; 4H.6 surfaces never do (proven by check 6). Strip
        # that volatile field before the immutability comparison.
        def strip_volatile(obj):
            if isinstance(obj, dict):
                return {k: strip_volatile(v) for k, v in obj.items()
                        if k != "generated_at"}
            if isinstance(obj, list):
                return [strip_volatile(x) for x in obj]
            return obj

        print("  -- 12. reads emit nothing, mutate nothing")
        diffs = first_diffs(strip_volatile(detail_before), strip_volatile(detail_after))
        check("runtime_read_only",
              events_get_end == events_get_start and not diffs,
              f"GET-phase events {events_get_start}->{events_get_end}; "
              f"detail diffs: {diffs}")

        # ---- 6: determinism ----
        print("  -- 6. byte-identical compositions on repeat reads")
        p1b = (await c.get(f"{DECISIONS}/{d1}/performance", headers=ha)).json()
        c1b = (await c.get(COHORT, headers=ha)).json()
        cpb = (await c.post(COMPARE, json={"decision_ids": [d1, d2]}, headers=ha)).json()
        cpb2 = (await c.post(COMPARE, json={"decision_ids": [d1, d2]}, headers=ha)).json()
        check("determinism_byte_identical",
              json.dumps(p_get, sort_keys=True) == json.dumps(p1b, sort_keys=True)
              and json.dumps(c_get, sort_keys=True) == json.dumps(c1b, sort_keys=True)
              and json.dumps(cpb, sort_keys=True) == json.dumps(cpb2, sort_keys=True),
              "repeat reads diverged")

        # writes-nothing proof for POST reads + intents: canonical row counts
        r_cmp_ro = await c.post(COMPARE, json={"decision_ids": [d1, d2]}, headers=ha)
        assert r_cmp_ro.status_code == 200, r_cmp_ro.text

        # ---- 13: schema gate vs ratified Phase-E baseline ----
        print("  -- 13. schema gate: zero structural delta vs baseline")

        async def ask(question: str, headers: dict) -> dict:
            return (await c.post(BRAIN_QUERY, json={"question": question},
                                 headers=headers)).json()

        i_perf = await ask("how did the decision perform for the vendor invoicing overhaul?", ha)
        i_meas = await ask("did the decision improve on-time payment rate after the vendor "
                           "invoicing overhaul?", ha)
        i_comp = await ask("compare the outcomes of these decisions about the vendor "
                           "invoicing overhaul", ha)
        guards = []
        for phrase in ("what is the action plan for the vendor invoicing overhaul decision?",
                       "did we act on the vendor invoicing overhaul decision?",
                       "show me my actions", "open the action center",
                       "what if we delay the platform project",
                       "show me the track record for hiring",
                       "show me the execution chain for the vendor invoicing overhaul"):
            res = await ask(phrase, ha)
            if res.get("intent") in NEW_INTENTS:
                guards.append((phrase, res.get("intent")))
        sm = await c.post(BRAIN_QUERY, json={"question":
                          "how did the decision perform for the vendor invoicing overhaul?"},
                          headers=hmem)
        try:
            sm_body = sm.json()
        except Exception:  # noqa: BLE001
            sm_body = {"raw": sm.text[:200]}
        scoped_ok = (
            sm.status_code in (200, 403)
            and sm_body.get("intent") not in NEW_INTENTS
            and "resolved_anchor" not in sm_body
        )
        counts_final = await db_counts(dsn, org_id)
        counts_final["business_metric_observations"] -= 1  # moat seed write
        post_intents_clean = counts_final == counts_pure_start
        check("post_reads_and_intents_write_nothing",
              post_intents_clean,
              f"counts {counts_pure_start} -> {counts_final}")

        baseline = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))),
            "SLICE4H6_SCHEMA_BASELINE.json"), encoding="utf-8"))
        conn = await asyncpg.connect(dsn=dsn)
        try:
            table_count = int(await conn.fetchval(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))
            ca_cols = sorted(r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name='company_actions'"))
            new_events = int(await conn.fetchval(
                "SELECT count(*) FROM events WHERE name = ANY($1)", CANDIDATE_EVENTS))
        finally:
            await conn.close()
        check("schema_introspection_clean",
              table_count == baseline["public_table_count"]
              and ca_cols == sorted(baseline["company_actions_columns"])
              and new_events == 0,
              f"tables {table_count} vs {baseline['public_table_count']}; "
              f"company_actions delta="
              f"{set(ca_cols) ^ set(baseline['company_actions_columns'])}; events={new_events}")

        # ---- 14: intents + collision guards ----
        print("  -- 14. intents resolve; protected phrasings untouched")
        check("intents_resolve_guards_hold",
              i_perf.get("intent") == "company_decision_performance"
              and i_perf.get("resolved_anchor", {}).get("decision_id") == d1
              and i_meas.get("intent") == "company_measured_change"
              and i_comp.get("intent") == "company_decision_comparison"
              and i_comp.get("canonical_route", {}).get("path", "").endswith("/decisions/compare")
              and not guards and scoped_ok,
              f"intents={i_perf.get('intent')}/{i_meas.get('intent')}/{i_comp.get('intent')} "
              f"guards={guards} scoped={sm.status_code}:{str(sm_body)[:140]}")

        # ---- 15: honesty surfaces everywhere ----
        print("  -- 15. honesty blocks present on every new surface")
        hon = [
            p1["honesty"], perf3["honesty"], t3["honesty"], c1["honesty"], cp["honesty"],
        ]
        check("honesty_surfaces_everywhere",
              all(h.get("advisory_only") is True and h.get("read_only") is True
                  and h.get("no_scores") is True and h.get("no_forecasting") is True
                  and h.get("no_people_scoring") is True for h in hon),
              json.dumps([h for h in hon if h.get("advisory_only") is not True]))

        # ---- 16: frontend static parity ----
        print("  -- 16. frontend typed windows + panel exist (tsc is the gate)")
        fe_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "frontend")
        api_ts = os.path.join(fe_root, "lib", "api.ts")
        tab_tsx = os.path.join(fe_root, "app", "(app)", "execution", "company-tab.tsx")
        api_src = open(api_ts, encoding="utf-8").read() if os.path.exists(api_ts) else ""
        tab_src = open(tab_tsx, encoding="utf-8").read() if os.path.exists(tab_tsx) else ""
        check("frontend_static_parity",
              all(s in api_src for s in (
                  "CompanyPerformanceAssessment", "getCompanyDecisionPerformance",
                  "getCompanyPerformanceCohort", "CompanyPerformanceComparisonResponse"))
              and "PerformancePanel" in tab_src,
              f"api.ts hits missing, tab path={tab_tsx} exists={os.path.exists(tab_tsx)}")

    print(f"\n==== 4H.6 acceptance: {len(PASSED)} passed / {len(FAILED)} failed ====")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
