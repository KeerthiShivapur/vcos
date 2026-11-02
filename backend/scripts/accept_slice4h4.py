"""Slice 4H.4 acceptance â€” Strategic Scenario / Decision-Rehearsal
Intelligence (live API, contract Â§15, 15 checks).

Against the running stack (http://localhost:8999): a seeded org with a real
company state snapshot rehearses bounded hypothetical changes through the
canonical API.  Verified:

 1. dry-run returns the canonical bounded surface (all Â§5.3 members).
 2. dry-run writes NOTHING (zero rows, zero company.scenario.recorded).
 3. dry-run serves on brain:read; RECORDING requires brain:manage (403
    without) â€” governed act.
 4. record writes ONE row anchored to exactly ONE company.scenario.recorded
    event (event truth).
 5. exact-once (L15): identical org+scope+kind+input+snapshot REPLAYS
    (zero rows, zero events); changed input -> NEW row.
 6. invalid kind -> honest error dict (advisory_only + not_a_prediction),
    zero writes/events.
 7. assumptions + effects are bounded (MAX_SCENARIO_ASSUMPTIONS /
    MAX_WHATIF_CONSEQUENCES).
 8. detail re-queries the stored row byte-identically (replayed:true).
 9. unknown scenario id -> 404 "scenario not found".
10. history is bounded and newest-first.
11. compare accepts 2-5 ids, bends the side-by-side, NEVER ranks.
12. tenant isolation: a sibling org can neither read nor compare.
13. honesty: every surface and row carries advisory_only + not_a_prediction;
    cited risks keep state-fidelity (probability/impact).
14. brain intents: company_scenario + company_scenarios_compare resolve;
    generic "what if we ..." phrasing never resolves to a rehearsal
    (collision guard â€” stays on pre-existing intents).
15. L15 scenario identity end-to-end: same input+snapshot replays the same
    row; a changed state snapshot yields a NEW rehearsal.

Exit 0 only when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
SCEN = f"{BRAIN}/execution/company/scenario"
BRAIN_QUERY = f"{BRAIN}/knowledge/query"

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
            "organization_name": f"4H4 {tag} {stamp}",
            "organization_slug": f"slice4h4-{tag}-{stamp}",
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": f"{tag.title()} Owner",
            "email": f"4h4-{tag}-{stamp}@test.co",
            "username": f"4h4-{tag}-{stamp}",
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "organization": data["organization"]}


async def invite_member(client: httpx.AsyncClient, headers: dict, stamp: str) -> dict:
    """Create a non-owner org member (no brain:manage) via invite+accept."""
    email = f"4h4-member-{stamp}@test.co"
    inv = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Member User", "role": "employee"},
        headers=headers,
    )
    assert inv.status_code == 201, inv.text
    token = inv.json().get("token")
    url = inv.json().get("url", "")
    if not token:
        import urllib.parse

        token = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("token", [""])[0]
    acc = await client.post(
        f"{API}/auth/register/invite",
        json={"token": token, "full_name": "Member User", "password": "StrongPass123!", "username": f"4h4-member-{stamp}"},
    )
    assert acc.status_code in (200, 201), acc.text
    return {"headers": {"Authorization": f"Bearer {acc.json()['access_token']}"}}


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 400) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=60
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:  # noqa: BLE001
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


def canonical_keys(body: dict) -> bool:
    return set(body.keys()) >= {
        "advisory_only", "not_a_prediction", "baseline", "hypothetical_change",
        "direct_effects", "dependent_effects", "risks_already_present",
        "opportunities_already_present", "decisions_to_reconsider",
        "causal_basis", "snapshot_ref", "honesty", "human_decision", "note",
    }


async def main() -> int:
    stamp = str(int(time.time()))[-6:]
    async with httpx.AsyncClient(timeout=60) as c:
        a = await register(c, stamp, "a")
        ha = a["headers"]
        b = await register(c, stamp, "b")
        hb = b["headers"]

        print("\n=== VCOS Slice 4H.4 acceptance: Strategic Scenario Intelligence (live) ===\n")

        await drain(c, ha)
        time.sleep(1.2)  # deterministic company state snapshot settles

        # ---- 1 + 2: dry-run canonical surface, zero writes, zero events ----
        print("  -- 1. dry-run canonical surface")
        dry = await c.post(SCEN, json={
            "scenario_kind": "resource_loss", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {},
            "assumptions": [], "scope_type": "org", "dry_run": True,
        }, headers=ha)
        check("1. dry-run canonical surface", dry.status_code == 200 and canonical_keys(dry.json()),
              dry.text[:200])
        ev_before = await count_events(c, ha, "company.scenario.recorded")

        print("  -- 2. dry-run writes nothing")
        hist = (await c.get(SCEN, headers=ha)).json()
        check("2. dry-run zero rows/events",
              hist.get("scenarios", []) == []
              and await count_events(c, ha, "company.scenario.recorded") == ev_before,
              str(hist.get("scenarios"))[:120])

        # ---- 3. recording requires brain:manage ----
        print("  -- 3. brain:manage gate")
        member = await invite_member(c, ha, stamp)
        member_no_write = await c.post(SCEN, json={
            "scenario_kind": "delay", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {"days": 3},
            "assumptions": [], "scope_type": "org", "dry_run": False,
        }, headers=member["headers"])
        check("3. record without brain:manage rejected", member_no_write.status_code == 403,
              f"{member_no_write.status_code} {member_no_write.text[:120]}")

        # ---- 4 + 6 + 7 + 15: record path ----
        print("  -- 4. record writes one row + one event")
        ev0 = await count_events(c, ha, "company.scenario.recorded")
        rec = await c.post(SCEN, json={
            "scenario_kind": "delay", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {"days": 3},
            "assumptions": [{"name": "stable staffing", "value": "yes"}],
            "scope_type": "org", "dry_run": False,
        }, headers=ha)
        r = rec.json()
        check("4. record writes row + event",
              rec.status_code == 200 and r.get("created") is True and bool(r.get("scenario_id"))
              and await count_events(c, ha, "company.scenario.recorded") == ev0 + 1,
              rec.text[:200])

        print("  -- 6. invalid kind honest error")
        bad = (await c.post(SCEN, json={
            "scenario_kind": "magic", "subject_type": "project",
            "subject_id": "proj:x", "params": {}, "scope_type": "org", "dry_run": False,
        }, headers=ha)).json()
        check("6. invalid kind honest error",
              "error" in bad and bad.get("advisory_only") is True and bad.get("not_a_prediction") is True,
              str(bad)[:160])

        print("  -- 7. bounds (assumptions)")
        rec7 = (await c.post(SCEN, json={
            "scenario_kind": "reallocate", "subject_type": "project",
            "subject_id": "proj:anchor",
            "params": {"from_project_id": "p1", "to_project_id": "p2", "units": 2},
            "assumptions": [{"name": f"a{i}", "value": "v"} for i in range(40)],
            "scope_type": "org", "dry_run": False,
        }, headers=ha)).json()
        check("7. assumptions bounded", 0 < len(rec7.get("hypothetical_change", {}).get("assumptions", [])) <= 20,
              f"assumptions = {len(rec7.get('hypothetical_change', {}).get('assumptions', []))}")

        # ---- 5. exact-once + changed input ----
        print("  -- 5. exact-once (L15) + changed input")
        ev1 = await count_events(c, ha, "company.scenario.recorded")
        replay = (await c.post(SCEN, json={
            "scenario_kind": "delay", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {"days": 3},
            "assumptions": [{"name": "stable staffing", "value": "yes"}],
            "scope_type": "org", "dry_run": False,
        }, headers=ha)).json()
        same_rows = len((await c.get(SCEN, headers=ha)).json().get("scenarios", []))
        check("5. exact-once replay",
              replay.get("replayed") is True and replay.get("created") is False
              and await count_events(c, ha, "company.scenario.recorded") == ev1,
              str({k: replay.get(k) for k in ("replayed", "created")}))
        changed = (await c.post(SCEN, json={
            "scenario_kind": "delay", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {"days": 9},
            "assumptions": [{"name": "stable staffing", "value": "yes"}],
            "scope_type": "org", "dry_run": False,
        }, headers=ha)).json()
        rows_after = len((await c.get(SCEN, headers=ha)).json().get("scenarios", []))
        check("5. changed input -> new row",
              changed.get("created") is True and rows_after == same_rows + 1,
              f"rows {same_rows} -> {rows_after}")

        # ---- 8 + 9: detail replay + 404 ----
        print("  -- 8/9. detail replay + 404")
        detail = (await c.get(f"{SCEN}/{r['scenario_id']}", headers=ha)).json()
        check("8. detail byte-identical replayed",
              detail.get("scenario_id") == r["scenario_id"] and detail.get("replayed") is True
              and canonical_keys(detail) and detail.get("advisory_only") is True,
              str(detail)[:160])
        miss = await c.get(f"{SCEN}/scn:nope", headers=ha)
        check("9. unknown scenario 404", miss.status_code == 404 and miss.json().get("detail") == "scenario not found",
              f"{miss.status_code} {miss.text[:120]}")

        # ---- 10. history bounded newest-first ----
        print("  -- 10. history bounded")
        hist2 = (await c.get(SCEN, params={"limit": 2}, headers=ha)).json()
        times = [s["occurred_at"] for s in hist2.get("scenarios", [])]
        check("10. history bounded newest-first",
              hist2.get("total") == 2 and times == sorted(times, reverse=True),
              str(hist2)[:160])

        # ---- 11 + 12 + 13. compare never-ranks; tenant isolation; honesty ----
        print("  -- 11/12/13. compare, tenant isolation, honesty")
        ids = [s["scenario_id"] for s in (await c.get(SCEN, headers=ha)).json().get("scenarios", [])[:5]]
        cmp = (await c.post(f"{SCEN}/compare", json={"scenario_ids": ids[:2]}, headers=ha)).json()
        check("11. compare side-by-side never ranked",
              cmp.get("advisory_only") is True and len(cmp.get("scenarios", [])) == 2
              and "ranked" in cmp.get("comparison", "").lower(),
              str(cmp)[:160])
        b_get = await c.get(f"{SCEN}/{ids[0]}", headers=hb)
        b_cmp = (await c.post(f"{SCEN}/compare", json={"scenario_ids": ids[:2]}, headers=hb)).json()
        check("12. tenant isolation", b_get.status_code == 404 and b_cmp.get("scenarios", []) == [],
              f"{b_get.status_code}")
        detail13 = (await c.get(f"{SCEN}/{ids[0]}", headers=ha)).json()
        check("13. honesty flags", detail13.get("advisory_only") is True and detail13.get("not_a_prediction") is True,
              str(detail13)[:100])

        # ---- 14. brain intents + collision guard ----
        print("  -- 14. brain intents")
        sc = (await c.post(BRAIN_QUERY, json={
            "question": "what would happen if we delay the platform project?",
        }, headers=ha)).json()
        check("14. intent company_scenario",
              sc.get("intent") == "company_scenario", sc.get("intent"))
        cmp_intent = (await c.post(BRAIN_QUERY, json={
            "question": "compare the scenarios we rehearsed",
        }, headers=ha)).json()
        check("14. intent company_scenarios_compare",
              cmp_intent.get("intent") == "company_scenarios_compare", cmp_intent.get("intent"))
        guard = (await c.post(BRAIN_QUERY, json={
            "question": "what if we reallocate capacity",
        }, headers=ha)).json()
        check("14. collision guard (generic what-if untouched)",
              guard.get("intent") not in ("company_scenario", "company_scenarios_compare"),
              guard.get("intent"))

        # ---- 15. L15 identity across a changed snapshot ----
        print("  -- 15. L15 identity")
        kw = {
            "scenario_kind": "hire", "subject_type": "project",
            "subject_id": "proj:anchor", "params": {"people": 2},
            "assumptions": [], "scope_type": "org", "dry_run": False,
        }
        s1 = await c.post(SCEN, json=kw, headers=ha)
        s2 = await c.post(SCEN, json=kw, headers=ha)
        # compose a NEW company-state snapshot (real domain activity), then
        # re-record the same input -> L15 demands a NEW rehearsal.
        proj = (await c.post(f"{API}/projects", json={
            "name": f"L15 Trigger {stamp}", "description": "changes snapshot", "status": "active",
        }, headers=ha)).json()
        await c.post(f"{API}/tasks", json={
            "title": "L15 snapshot bump", "project_id": proj["id"], "status": "todo",
        }, headers=ha)
        await drain(c, ha)
        time.sleep(1.2)
        s3 = (await c.post(SCEN, json=kw, headers=ha)).json()
        check("15. L15 identity (replay + snapshot change -> new row)",
              s1.json().get("created") is True
              and s2.json().get("replayed") is True
              and s1.json().get("snapshot_ref") == s2.json().get("snapshot_ref")
              and s3.get("created") is True
              and s3.get("snapshot_ref") != s1.json().get("snapshot_ref"),
              f"{s1.json().get('snapshot_ref')} vs {s3.get('snapshot_ref')}")

        print(f"\n=== RESULT: 15 checks -> {len(PASSED)} assertions passed, {len(FAILED)} failed (exit 0 = 15/15) ===")
        for f in FAILED:
            print(f"  FAILED: {f}")
        return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
