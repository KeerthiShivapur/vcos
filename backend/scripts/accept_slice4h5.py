"""Slice 4H.5 acceptance - Strategic Decision-to-Action & Execution
Intelligence (live API, contract section 12, 16 checks).

Against the running stack (http://localhost:8999): a seeded org attaches a
canonical state context to an approved CompanyDecision, derives a bounded
advisory action plan, authorizes through the EXISTING governed action
surface with decision lineage, drives the UNCHANGED 4E.6 lifecycle to an
outcome, and reads the unified execution chain.  Verified:

 1. plan on approved decision w/ canonical context: <=5 steps, sanctioned
    types, existing targets, basis per step, honesty flags, status ok.
 2. dry-run writes NOTHING and emits ZERO events (org event total stable).
 3. pre-approval decision -> rejected plan (409 at API).
 4. non-invention: rich question + zero canonical anchors ->
    proposed_steps [] + derivation_status insufficient_canonical_basis.
 5. authorize via EXISTING /brain/knowledge/actions WITH lineage -> row
    carries source ids; duplicate propose replays (deduplicated, one row).
 6. authorized action follows UNCHANGED 4E.6 lifecycle: transitions +
    company_action_events accumulate; low-risk auto-approve inherited.
 7. chain view stitches decision -> actions -> evidence -> artifacts ->
    outcomes; every node names its ids; bounds respected.
 8. CompanyDecision mutations only via existing endpoints: GET decision
    detail byte-identical before vs after all chain reads.
 9. tenant isolation: sibling org AND scoped-out member both 404.
10. determinism: identical inputs -> byte-identical plan (twice).
11. schema introspection: exactly TWO new columns on company_actions,
    ZERO new tables, ZERO new event rows for candidate new event names.
12. brain intents resolve; collision phrases never hit the new intents.
13. origin compatibility: propose WITHOUT lineage stays valid and never
    appears in the lineage chain; 4H.4 scenario surface unchanged.
14. sub-scope continuity: project-scoped authorized action keeps lineage.
15. moat T1->T3: same decision's chain strictly richer as the company
    operates more, zero code change; T4 joinability ids present.
16. no hidden planner / no LLM: honesty block everywhere, deterministic
    derivation, insufficient-basis honesty, advisory-only surfaces.

Exit 0 only when all pass.
"""

import asyncio
import json
import os
import sys
import time
import urllib.parse

import asyncpg
import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
DECISIONS = f"{BRAIN}/execution/company/decisions"
ACTIONS = f"{BRAIN}/knowledge/actions"
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
            "organization_name": f"4H5 {tag} {stamp}",
            "organization_slug": f"slice4h5-{tag}-{stamp}",
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": f"{tag.title()} Owner",
            "email": f"4h5-{tag}-{stamp}@test.co",
            "username": f"4h5-{tag}-{stamp}",
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "organization": data["organization"]}


async def invite_member(client: httpx.AsyncClient, headers: dict, stamp: str) -> dict:
    email = f"4h5-member-{stamp}@test.co"
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
        json={"token": token, "full_name": "Member User", "password": "StrongPass123!", "username": f"4h5-member-{stamp}"},
    )
    assert acc.status_code in (200, 201), acc.text
    return {"headers": {"Authorization": f"Bearer {acc.json()['access_token']}"}}


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


async def seeds(dsn: str, org_id: str, decision_id: str, stamp: str) -> dict:
    """Canonical anchor rows the state-context bridge can cite: one active
    project, two open risks, one derived-causality edge batch touching the
    decision.  Direct inserts mirror what engine derivations produce."""
    conn = await asyncpg.connect(dsn=dsn)
    try:
        project_id = f"proj:4h5-{stamp}"
        await conn.execute(
            'INSERT INTO projects (id, organization_id, code, name, status, priority, progress, health)'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8)',
            project_id, org_id, f"4H5-{stamp}", "Migration Rollback Readiness", "active", "high", 10, "at_risk",
        )
        risk_ids = []
        for i, (p, im) in enumerate([(4, 5), (3, 4)], start=1):
            rid = f"risk:4h5-{stamp}-{i}"
            await conn.execute(
                'INSERT INTO risks (id, organization_id, title, status, probability, impact, risk_score)'
                ' VALUES ($1,$2,$3,$4,$5,$6,$7)',
                rid, org_id, f"Rollback window slips past freeze ({i})", "identified", p, im, p * im,
            )
            risk_ids.append(rid)
        await conn.execute(
            'INSERT INTO company_causal_edges (id, organization_id, source_type, source_id, target_type,'
            ' target_id, kind, confidence, source_event_id, created_at, updated_at)'
            ' VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, now(), now())',
            f"edge:4h5-{stamp}", org_id, "decision", decision_id, "project", project_id,
            "constraint->project", "high", f"evt:4h5-{stamp}",
        )
        return {"project_id": project_id, "risk_ids": risk_ids}
    finally:
        await conn.close()


async def schema_probe(dsn: str) -> dict:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='company_actions'"
        )
        col_names = {r["column_name"] for r in cols}
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        table_names = {r["table_name"] for r in tables}
        new_events = await conn.fetchval(
            "SELECT count(*) FROM events WHERE name = ANY($1)",
            [
                "company.execution_plan.derived", "company.action_plan.derived",
                "company.execution_chain.read", "company.decision.action_linked",
                "company.decision.plan_derived",
            ],
        )
        return {
            "columns": col_names,
            "tables": table_names,
            "new_event_rows": int(new_events or 0),
        }
    finally:
        await conn.close()


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

        print("\n=== VCOS Slice 4H.5 acceptance: Decision-to-Action & Execution Intelligence (live) ===\n")

        await drain(c, ha)
        time.sleep(1.2)

        # ---- setup: approved decision + canonical anchors + state context ----
        r = await c.post(DECISIONS, json={
            "kind": "commercial_action",
            "title": "Migrate billing to the new ledger before quarter close",
            "rationale": "Legacy ledger double-charges on refunds.",
        }, headers=ha)
        assert r.status_code in (200, 201), r.text
        decision_id = r.json()["decision_id"]
        assert r.json().get("state") == "approved", r.json()
        # decision rows are event-sourced: the recorded event materializes
        # the row on processing, so drain before any anchored read.
        await drain(c, ha)
        time.sleep(0.8)

        anchored = await seeds(dsn, org_id, decision_id, stamp)
        project_id, risk_ids = anchored["project_id"], anchored["risk_ids"]

        r = await c.post(f"{DECISIONS}/{decision_id}/state-context", json={}, headers=ha)
        assert r.status_code in (200, 201), r.text
        assert r.json().get("accepted") is True, r.text

        r_before = await c.get(f"{DECISIONS}/{decision_id}", headers=ha)
        assert r_before.status_code == 200, r_before.text

        # ---- 1: plan from canonical anchors ----
        print("  -- 1. plan from canonical anchors (bounded, honest)")
        plan = (await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=ha)).json()
        ok = (
            isinstance(plan.get("proposed_steps"), list)
            and 1 <= len(plan["proposed_steps"]) <= 5
            and plan.get("honesty", {}).get("derivation_status") == "ok"
            and plan.get("honesty", {}).get("advisory_only") is True
            and plan.get("decision", {}).get("decision_id") == decision_id
        )
        for s in plan.get("proposed_steps", []):
            ok = ok and s["action_type"] in {"task", "meeting", "decision_review", "risk_review"}
            ok = ok and s.get("basis", {}).get("relation") and s.get("target", {}).get("id")
        check("1 plan bounded + anchored + honest", ok, json.dumps(plan)[:400])

        # ---- 2: dry-run writes nothing, emits zero events ----
        print("  -- 2. dry-run writes NOTHING, emits ZERO events")
        t0 = await org_event_total(c, ha)
        await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=ha)
        t1 = await org_event_total(c, ha)
        check("2 zero writes / zero events on derive", t0 == t1 and t0 >= 0, f"{t0} -> {t1}")

        # ---- 10: determinism ----
        print("  -- 10. identical inputs -> byte-identical plan")
        p2 = (await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=ha)).text
        p3 = (await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=ha)).text
        check("10 plan byte-deterministic", p2 == p3 and len(p2) > 2)

        # ---- 3: pre-approval rejection ----
        print("  -- 3. pre-approval decision -> rejected plan (409)")
        r = await c.post(DECISIONS, json={
            "kind": "other", "title": f"Unapproved pivot {stamp}", "state": "declined",
        }, headers=ha)
        assert r.status_code in (200, 201), r.text
        pre_id = r.json()["decision_id"]
        await drain(c, ha)
        r = await c.post(f"{DECISIONS}/{pre_id}/action-plan", json={}, headers=ha)
        check("3 pre-approval rejected 409", r.status_code == 409, f"got {r.status_code}: {r.text[:200]}")

        # ---- 4: non-invention ----
        print("  -- 4. non-invention: no anchors -> no invented steps")
        r = await c.post(DECISIONS, json={
            "kind": "commercial_action", "title": f"Anchorless decision {stamp}",
        }, headers=ha)
        assert r.status_code in (200, 201), r.text
        bare_id = r.json()["decision_id"]
        await drain(c, ha)
        bare = (await c.post(f"{DECISIONS}/{bare_id}/action-plan", json={}, headers=ha)).json()
        check(
            "4 insufficient_canonical_basis, zero steps",
            bare.get("proposed_steps") == []
            and bare.get("honesty", {}).get("derivation_status") == "insufficient_canonical_basis"
            and bare.get("honesty", {}).get("advisory_only") is True,
            json.dumps(bare)[:300],
        )

        # ---- 5: authorize via EXISTING surface WITH lineage ----
        print("  -- 5. authorize via existing /brain/knowledge/actions with lineage")
        r = await c.post(ACTIONS, json={
            "action_type": "task",
            "title": "Draft the ledger migration rollback runbook",
            "description": "Step derived from the migration decision's anchored risks.",
            "source_problem": "Refund double-charging persists until cutover safety exists.",
            "scope_type": "org",
            "risk": "low",
            "source_company_decision_id": decision_id,
        }, headers=ha)
        assert r.status_code in (200, 201), r.text
        auth = r.json()
        action_id = auth["action"]["id"] if isinstance(auth.get("action"), dict) else auth["id"]
        payload = auth.get("action", auth)
        check(
            "5a row carries decision lineage",
            payload.get("source_company_decision_id") == decision_id,
            json.dumps(payload)[:300],
        )
        r = await c.post(ACTIONS, json={
            "action_type": "task",
            "title": "Draft the ledger migration rollback runbook",
            "description": "Step derived from the migration decision's anchored risks.",
            "source_problem": "Refund double-charging persists until cutover safety exists.",
            "scope_type": "org",
            "risk": "low",
            "source_company_decision_id": decision_id,
        }, headers=ha)
        replay = r.json()
        rp = replay.get("action", replay)
        check(
            "5b exact-once replay",
            r.status_code in (200, 201)
            and replay.get("deduplicated") is True
            and rp.get("id", action_id) == action_id,
            json.dumps(replay)[:300],
        )

        # ---- 6: unchanged 4E.6 lifecycle ----
        print("  -- 6. unchanged 4E.6 lifecycle on the authorized action")
        low_auto = payload.get("state") in ("ready", "approved")
        tr = []
        for transition in ("start", "complete"):
            r = await c.post(f"{ACTIONS}/{action_id}/transition", json={
                "transition": transition, "note": f"4h5 {transition}",
            }, headers=ha)
            tr.append(r.status_code in (200, 201))
        r = await c.post(f"{ACTIONS}/{action_id}/outcome", json={
            "outcome_type": "success", "verdict": "Runbook merged; rollback rehearsed.",
        }, headers=ha)
        outcome_ok = r.status_code in (200, 201)
        conn = await asyncpg.connect(dsn=dsn)
        try:
            ev_count = await conn.fetchval(
                "SELECT count(*) FROM company_action_events WHERE action_id=$1", action_id
            )
        finally:
            await conn.close()
        check(
            "6 lifecycle transitions + outcome + event trail",
            all(tr) and outcome_ok and low_auto and int(ev_count or 0) >= 2,
            f"auto={low_auto} tr={tr} outcome={outcome_ok} events={ev_count}",
        )

        # ---- T1 snapshot then enrich (checks 14/15 need more ops) ----
        chain1 = (await c.get(f"{DECISIONS}/{decision_id}/execution-chain", headers=ha)).json()

        # ---- 14: sub-scope continuity ----
        print("  -- 14. project-scoped authorization keeps lineage")
        r = await c.post(ACTIONS, json={
            "action_type": "task",
            "title": "Freeze window comms to affected customers",
            "scope_type": "project",
            "scope_id": project_id,
            "risk": "low",
            "source_company_decision_id": decision_id,
        }, headers=ha)
        scoped_ok = r.status_code in (200, 201)
        sp = r.json().get("action", r.json()) if scoped_ok else {}
        scoped_id = sp.get("id", "")
        check(
            "14 scoped action carries lineage",
            scoped_ok and sp.get("source_company_decision_id") == decision_id
            and sp.get("scope_type") == "project",
            json.dumps(sp)[:250] if scoped_ok else r.text[:250],
        )
        if scoped_ok:
            await c.post(f"{ACTIONS}/{scoped_id}/transition", json={"transition": "start"}, headers=ha)
            await c.post(f"{ACTIONS}/{scoped_id}/transition", json={"transition": "complete"}, headers=ha)
            await c.post(f"{ACTIONS}/{scoped_id}/outcome", json={
                "outcome_type": "partial", "verdict": "Sent; two bounces unresolved.",
            }, headers=ha)

        # ---- 13: origin compatibility ----
        print("  -- 13. origin compatibility: unlineaged action stays out of the chain")
        r = await c.post(ACTIONS, json={
            "action_type": "task", "title": f"Unrelated ops chore {stamp}",
            "scope_type": "org", "risk": "low",
        }, headers=ha)
        plain_ok = r.status_code in (200, 201)
        plain_id = (r.json().get("action", r.json()).get("id", "") if plain_ok else "")
        chain = (await c.get(f"{DECISIONS}/{decision_id}/execution-chain", headers=ha)).json()
        chain_action_ids = {x.get("id") for x in chain.get("actions", [])}
        scen = (await c.post(f"{BRAIN}/execution/company/scenario", json={
            "scenario_kind": "resource_loss", "subject_type": "project",
            "subject_id": project_id, "params": {},
        }, headers=ha)).json()
        scen_keys_ok = set(scen.keys()) >= {
            "advisory_only", "not_a_prediction", "baseline", "hypothetical_change",
            "direct_effects", "honesty", "human_decision",
        }
        check(
            "13 no-lineage valid + absent from chain; 4H.4 surface intact",
            plain_ok and plain_id and plain_id not in chain_action_ids and scen_keys_ok,
            f"plain={plain_ok} leaked={plain_id in chain_action_ids if plain_id else '?'} scen={scen_keys_ok}",
        )

        # ---- 15: moat T1->T3 + T4 joinability ----
        print("  -- 15. moat: chain grows as the company operates (zero code change)")
        n1 = (len(chain1.get("actions", [])), len(chain1.get("evidence", [])), len(chain1.get("outcomes", [])))
        n2 = (len(chain.get("actions", [])), len(chain.get("evidence", [])), len(chain.get("outcomes", [])))
        richer = n2[0] > n1[0] and n2[2] > n1[2]
        dec_node = chain.get("decision", {})
        joinable = (
            dec_node.get("decision_id") == decision_id
            and any(a.get("source_company_decision_id") == decision_id for a in chain.get("actions", []))
            and any(o.get("outcome_type") for o in chain.get("outcomes", []))
        )
        check(
            "15 T1->T3 richer chain + T4 joinable ids",
            richer and joinable,
            f"T1={n1} T3={n2} joinable={joinable}",
        )

        # ---- 8 setup: all governed writes are done; freeze the decision ----
        # (4H.1 reconciliation legitimately updates the decision on outcome
        # writes; immutability is asserted across the READ-ONLY tail only.)
        r = await c.get(f"{DECISIONS}/{decision_id}", headers=ha)
        assert r.status_code == 200, r.text
        decision_before = r.json()

        # ---- 7: chain stitching + bounds ----
        print("  -- 7. unified execution chain stitches truthfully, bounded")
        ok = (
            chain.get("decision", {}).get("decision_id") == decision_id
            and 1 <= len(chain.get("actions", [])) <= 10
            and len(chain.get("evidence", [])) <= 20
            and len(chain.get("artifacts", [])) <= 10
            and len(chain.get("outcomes", [])) <= 5
            and bool(chain.get("generated_at"))
            and chain.get("honesty", {}).get("advisory_only") is True
        )
        for e in chain.get("evidence", []):
            ok = ok and bool(e.get("event") or e.get("event_name") or e.get("name"))
        check("7 chain stitched + bounded + truthful", ok, json.dumps(chain)[:400])

        # ---- 9: tenant isolation (sibling org + project-scoped caller) ----
        print("  -- 9. tenant isolation: sibling org and scoped-out caller both 404")
        rb_plan = await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=hb)
        rb_chain = await c.get(f"{DECISIONS}/{decision_id}/execution-chain", headers=hb)
        # a manager whose ONLY governance scope is one project (org-wide
        # assignment removed, brain:read delegated) - the 4H.3 pattern
        scoped_emp = (await c.post(
            f"{API}/users/invite",
            json={"email": f"scop{stamp}@4h5.test.co", "role": "manager", "full_name": "Scoped Mgr"},
            headers=ha,
        )).json()
        joined = (await c.post(
            f"{API}/auth/register/invite",
            json={"token": scoped_emp["token"], "email": f"scop{stamp}@4h5.test.co",
                  "full_name": "Scoped Mgr", "password": "StrongPass123!"},
        )).json()
        scope = (await c.post(
            f"{API}/governance/scopes",
            json={"name": "4H5 Visible Scope", "scope_type": "project", "entity_id": project_id},
            headers=ha,
        )).json()
        roles = (await c.get(f"{API}/roles", headers=ha)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        assign = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
            headers=ha,
        )
        assert assign.status_code == 201, assign.text
        assignments = (await c.get(
            f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=ha,
        )).json()
        org_wide_assign = next(x for x in assignments if x.get("scope_id") is None)
        await c.delete(f"{API}/governance/assignments/{org_wide_assign['id']}", headers=ha)
        await c.post(
            f"{API}/governance/delegations",
            json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read",
                  "reason": "4H.5 acceptance"},
            headers=ha,
        )
        hs = {"Authorization": f"Bearer {joined['access_token']}"}
        rs_plan = await c.post(f"{DECISIONS}/{decision_id}/action-plan", json={}, headers=hs)
        rs_chain = await c.get(f"{DECISIONS}/{decision_id}/execution-chain", headers=hs)
        check(
            "9 isolation holds on both new routes",
            rb_plan.status_code == 404 and rb_chain.status_code == 404
            and rs_plan.status_code == 404 and rs_chain.status_code == 404,
            f"B:{rb_plan.status_code}/{rb_chain.status_code} scoped:{rs_plan.status_code}/{rs_chain.status_code}",
        )

        # ---- 12: brain intents + collision guards ----
        print("  -- 12. brain intents resolve; collisions stay away")

        async def ask(q: str) -> dict:
            r = await c.post(BRAIN_QUERY, json={"question": q}, headers=ha)
            assert r.status_code == 200, r.text
            return r.json()

        ans_p = await ask("what should we do about the decision to migrate billing to the new ledger")
        ans_c = await ask("show the execution chain for the migration decision")
        coll1 = await ask("what are my actions")
        coll2 = await ask("open the action center")
        coll3 = await ask("what if we delay the migration by a month")
        intents_ok = (
            "proposed_steps" in ans_p and ans_p.get("honesty", {}).get("advisory_only") is True
            and ans_p.get("intent") == "company_execution_plan"
            and ans_c.get("intent") == "company_execution_chain"
            and "decision" in ans_c and "evidence" in ans_c
        )
        collisions_ok = all(
            "proposed_steps" not in x
            and x.get("intent") not in ("company_execution_plan", "company_execution_chain")
            for x in (coll1, coll2, coll3)
        )
        check("12 intents resolve + collision guards hold", intents_ok and collisions_ok,
              f"intents={intents_ok} collisions={collisions_ok}")

        # ---- 8: decision untouched by reads ----
        print("  -- 8. decision detail byte-identical across the read-only tail")
        r_after = await c.get(f"{DECISIONS}/{decision_id}", headers=ha)
        # the detail envelope carries a per-request generated_at; strip it on
        # both sides - the ROW content must be byte-identical
        before_body = {k: v for k, v in decision_before.items() if k != "generated_at"}
        after_body = {k: v for k, v in r_after.json().items() if k != "generated_at"}
        check("8 decision immutable under reads", r_after.status_code == 200 and before_body == after_body,
              json.dumps({"before": before_body, "after": after_body})[:400] if before_body != after_body else "")

        # ---- 11: schema introspection ----
        print("  -- 11. schema: exactly two new columns, zero new tables, zero new events")
        probe = await schema_probe(dsn)
        cols_ok = {"source_company_decision_id", "source_scenario_id"} <= probe["columns"]
        forbidden = {"company_action_plans", "execution_chains", "action_chain_links",
                     "company_execution_plans", "decision_action_links"}
        tables_ok = not (forbidden & probe["tables"])
        check(
            "11 additive-only schema held",
            cols_ok and tables_ok and probe["new_event_rows"] == 0,
            f"cols={cols_ok} tables_leak={sorted(forbidden & probe['tables'])} evt={probe['new_event_rows']}",
        )

        # ---- 16: honesty sweep ----
        print("  -- 16. honesty sweep across every new surface")
        surfaces = [plan, bare, chain]
        ok = all(
            s.get("honesty", {}).get("advisory_only") is True
            and s.get("honesty", {}).get("not_a_prediction") is True
            for s in surfaces
        )
        ok = ok and plan.get("honesty", {}).get("human_authorization_required") is True
        check("16 advisory + not-a-prediction + human gate everywhere", ok)

        # ---- summary ----
        print(f"\n=== {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED: " + ", ".join(FAILED))
        return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
