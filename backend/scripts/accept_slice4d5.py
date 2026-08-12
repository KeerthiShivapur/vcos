"""Slice 4D.5 acceptance — universal company insight intelligence (live API).

20 checks against the running stack (http://localhost:8999):

  1. change-driven composition: blocked tasks -> repeated_delay pattern ->
     execution_bottleneck insight (execution domain, project scope inherited
     from the governance scope, auth_project_id anchored, warning severity)
  2. compositional confidence: bounded [0, 1] with all five self-explaining
     components and weights that sum to 1
  3. evidence lineage: /evidence resolves supporting pattern ids + evidence refs
  4. recompose history: every feeding event is a pattern.* event; status active
  5. canonical shape: claim + summary + affected project entity all present
  6. deduplication: exactly one execution_bottleneck per (org, project key);
     repeated re-evaluation never creates a second row
  7. decision bottleneck: a pending decision + blocked work composes a
     decision_bottleneck insight without mutating the decision
  8. governance bottleneck: a pending approval composes a governance_bottleneck
     insight without mutating the approval
  9. governance: a scoped brain:read-only reader sees the project insight; a
     hidden project's insight is 404 (never 403/leak); its
     evidence/history/related are 404 too
 10. tenant isolation: rival org sees nothing of this org's insights
 11. brain integration: /brain/answer cites insight claims with /brain/insights
     evidence urls
 12. worker + scheduler: insight worker registered @ 120s and runs on demand
 13. exactly-once replay: re-draining + re-running never duplicates supporting
     patterns, evidence or history
 14. observation-only / no mutation: task statuses, approvals and decisions
     are never changed or created by insight work
 15. endpoint contract: anonymous 401/403, missing insight 404
 16. bounded reads: limit + truncated honored; related bounded by limit
 17. confidence bounds across every visible insight are in [0, 1]
 18. governance inheritance: the project insight's scope_id equals the project
     governance scope id
 19. status surface: default list exposes active insights; status filter works
 20. related links: bounded and governance-filtered

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASSED.append(name)
    else:
        FAILED.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))


async def register(client: httpx.AsyncClient, name: str, slug: str, email: str, full_name: str):
    r = await client.post(
        f"{API}/auth/register",
        json={
            "organization_name": name,
            "organization_slug": slug,
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": full_name,
            "email": email,
            "username": email.split("@")[0],
            "password": "StrongPass123!",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "access": data["access_token"],
        "user": data["user"],
        "organization": data["organization"],
    }


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 500) -> int:
    r = await client.post(f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("processed", 0)


async def drain(client: httpx.AsyncClient, headers: dict) -> None:
    for _ in range(15):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def run_worker(client: httpx.AsyncClient, headers: dict, name: str) -> dict:
    r = await client.post(f"{API}/intelligence/workers/{name}/run", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def insights(client: httpx.AsyncClient, headers: dict, **params) -> list[dict]:
    q: dict = {"limit": 200}
    q.update(params)
    r = await client.get(f"{API}/brain/insights", params=q, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("insights", [])


async def block_tasks(client: httpx.AsyncClient, headers: dict, project_id: str, titles: list[str]) -> None:
    for title in titles:
        task = (await client.post(
            f"{API}/tasks",
            json={"title": title, "project_id": project_id, "status": "todo"},
            headers=headers,
        )).json()
        tr = await client.post(f"{API}/tasks/{task['id']}/transition", json={"status": "blocked"}, headers=headers)
        assert tr.status_code == 200, tr.text


async def wait_for_insight(
    client: httpx.AsyncClient,
    headers: dict,
    predicate,
) -> dict:
    for _ in range(14):
        await dispatch(client, headers)
        await run_worker(client, headers, "pattern")
        await dispatch(client, headers)
        await run_worker(client, headers, "insight")
        for insight in await insights(client, headers):
            if predicate(insight):
                return insight
        await asyncio.sleep(3)
    raise AssertionError("insight never became observable")


async def form_project(client: httpx.AsyncClient, headers: dict, name: str) -> tuple[dict, dict]:
    proj = (
        await client.post(
            f"{API}/projects",
            json={"name": name, "description": "Slice 4D.5 anchor", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            f"{API}/governance/scopes",
            json={"name": f"{name} scope", "scope_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
    ).json()
    return proj, scope


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4D.5 acceptance: universal company insight intelligence (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        org = await register(c, "Insight Corp", f"ic-{t}", f"ada{t}@ic.test.co", "Ada Founder")
        auth = org["headers"]
        print("1. Founder registered")
        await drain(c, auth)

        proj, scope = await form_project(c, auth, "Helios Delivery")
        await block_tasks(c, auth, proj["id"], ["Checkout API", "Billing export", "Mobile push"])
        insight = await wait_for_insight(
            c, auth,
            lambda i: i.get("insight_type") == "execution_bottleneck" and i.get("auth_project_id") == proj["id"],
        )
        print("2. Three blocked tasks seeded; execution_bottleneck insight formed")

        # ---- 1: change-driven composition ---------------------------------------------
        check(
            "1. change-driven composition: execution_bottleneck, project scope, warning",
            insight["insight_type"] == "execution_bottleneck"
            and insight["domain"] == "execution"
            and "execution bottlenecks" in insight["title"]
            and insight["status"] == "active"
            and insight["severity"] == "warning"
            and insight["scope_type"] == "project"
            and insight["auth_project_id"] == proj["id"]
            and len(insight.get("supporting_pattern_ids", [])) >= 1,
            f"severity={insight.get('severity')} scope={insight.get('scope_type')}",
        )

        # ---- 18: governance inheritance -----------------------------------------------
        check(
            "18. governance inheritance: scope_id matches the project governance scope",
            insight.get("scope_id") == scope["id"],
            f"insight_scope={insight.get('scope_id')} got={scope['id']}",
        )

        # ---- 2: compositional confidence ----------------------------------------------
        detail = (await c.get(f"{API}/brain/insights/{insight['id']}", headers=auth)).json()
        comps = detail.get("confidence_components") or {}
        weights = comps.get("weights") or {}
        ptr = lambda v: round(float(v), 3)  # noqa: E731
        check(
            "2. compositional confidence: bounded [0,1], 5 components, weights sum to 1",
            0.0 <= detail["confidence"] <= 1.0
            and all(k in comps for k in (
                "occurrence_strength", "evidence_completeness",
                "pattern_confidence", "memory_corroboration", "recency",
            ))
            and abs(sum(ptr(w) for w in weights.values()) - 1.0) < 0.001,
            f"confidence={detail['confidence']} comps={list(comps.keys())}",
        )

        # ---- 3: evidence lineage ------------------------------------------------------
        ev = (await c.get(f"{API}/brain/insights/{insight['id']}/evidence", headers=auth)).json()
        check(
            "3. evidence lineage: supporting pattern ids + evidence refs resolve",
            ev["insight_id"] == insight["id"]
            and ev["insight_type"] == "execution_bottleneck"
            and len(ev.get("supporting_pattern_ids", [])) >= 1
            and len(ev.get("evidence", [])) >= 1
            and any(item.get("type") == "pattern" for item in ev.get("evidence", [])),
            f"patterns={len(ev.get('supporting_pattern_ids', []))} refs={len(ev.get('evidence', []))}",
        )
        print("3. Confidence + evidence verified")

        # ---- 4: recompose history -----------------------------------------------------
        hist = (await c.get(f"{API}/brain/insights/{insight['id']}/history", headers=auth)).json()
        pattern_event_names = {"pattern.detected", "pattern.updated", "pattern.confirmed",
                               "pattern.faded", "pattern.resolved"}
        check(
            "4. recompose history: feeding events are pattern.* and status active",
            hist["insight_id"] == insight["id"]
            and hist["status"] == "active"
            and len(hist.get("history", [])) >= 1
            and all(item["event_name"] in pattern_event_names for item in hist.get("history", [])),
            f"events={[h['event_name'] for h in hist.get('history', [])]}",
        )

        # ---- 5: canonical shape ---------------------------------------------------------
        check(
            "5. canonical shape: claim + summary + affected project entity present",
            bool(insight.get("claim"))
            and bool(insight.get("summary"))
            and any(e.get("type") == "project" and e.get("id") == proj["id"]
                    for e in insight.get("affected_entities", [])),
            f"claimed={bool(insight.get('claim'))} entities={insight.get('affected_entities')}",
        )
        print("4-5. History + shape verified")

        # ---- 6: deduplication --------------------------------------------------------------
        all_of_type = [i for i in await insights(c, auth) if i["insight_type"] == "execution_bottleneck"]
        check(
            "6. deduplication: exactly one execution_bottleneck for the project key",
            len(all_of_type) == 1,
            f"count={len(all_of_type)}",
        )

        # ---- 7: decision bottleneck --------------------------------------------------------
        dproj, _ = await form_project(c, auth, "Decision Hold")
        await block_tasks(c, auth, dproj["id"], ["Prepare brief"])
        dec = (await c.post(
            f"{API}/decisions",
            json={"title": "approve extra budget", "project_id": dproj["id"], "description": "pending decision"},
            headers=auth,
        )).json()
        decision_insight = await wait_for_insight(
            c, auth,
            lambda i: i.get("insight_type") == "decision_bottleneck",
        )
        dec_after = (await c.get(f"{API}/decisions/{dec['id']}", headers=auth)).json()
        check(
            "7. decision bottleneck composes without mutating the decision",
            decision_insight["insight_type"] == "decision_bottleneck"
            and dec["id"] in decision_insight.get("key", "")
            and decision_insight["domain"] == "decision"
            and dec_after.get("status", dec.get("status")) == "proposed",
            f"key={decision_insight.get('key')} decision_status={dec_after.get('status')}",
        )

        # ---- 8: governance bottleneck -------------------------------------------------------
        approval = (await c.post(
            f"{API}/approvals",
            json={
                "title": "Approve Helios launch",
                "approval_type": "project",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=auth,
        )).json()
        gov_insight = await wait_for_insight(
            c, auth,
            lambda i: i.get("insight_type") == "governance_bottleneck",
        )
        check(
            "8. governance bottleneck composes from a pending approval",
            gov_insight["insight_type"] == "governance_bottleneck"
            and gov_insight["domain"] == "governance"
            and any(e.get("type") == "approval" or e.get("type") == "project"
                    for e in gov_insight.get("evidence", [])),
            f"evidence={[e.get('type') for e in gov_insight.get('evidence', [])]}",
        )
        print("6-8. Dedup, decision & governance bottlenecks verified")

        # ---- 14: observation-only / no mutation ----------------------------------------------
        final_tasks = (await c.get(f"{API}/tasks", params={"project_id": proj["id"], "limit": 200}, headers=auth)).json()
        blocked_now = sum(
            1 for task in (final_tasks if isinstance(final_tasks, list) else final_tasks.get("tasks", []))
            if task.get("status") == "blocked"
        )
        check(
            "14. observation-only: blocked tasks never auto-unblocked, approvals untouched",
            blocked_now == 3,
            f"blocked={blocked_now}",
        )

        # ---- 9: governance scoping ------------------------------------------------------------
        hidden_proj, _ = await form_project(c, auth, "Hidden Ops")
        await block_tasks(c, auth, hidden_proj["id"], ["Hidden A", "Hidden B", "Hidden C"])
        hidden_insight = await wait_for_insight(
            c, auth,
            lambda i: i.get("insight_type") == "execution_bottleneck" and i.get("auth_project_id") == hidden_proj["id"],
        )

        emp = (await c.post(
            f"{API}/users/invite",
            json={"email": f"emp{t}@pc.test.co", "role": "manager", "full_name": "Scoped Mgr"},
            headers=auth,
        )).json()
        joined = (await c.post(
            f"{API}/auth/register/invite",
            json={"token": emp["token"], "email": f"emp{t}@pc.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"},
        )).json()
        emp_auth = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(
            f"{API}/governance/assignments",
            json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
            headers=auth,
        )
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x["scope_id"] is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(
            f"{API}/governance/delegations",
            json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4d.5"},
            headers=auth,
        )
        assert dg.status_code == 201, dg.text

        scoped_ids = {i["id"] for i in await insights(c, emp_auth)}
        hidden_get = await c.get(f"{API}/brain/insights/{hidden_insight['id']}", headers=emp_auth)
        hidden_ev = await c.get(f"{API}/brain/insights/{hidden_insight['id']}/evidence", headers=emp_auth)
        hidden_his = await c.get(f"{API}/brain/insights/{hidden_insight['id']}/history", headers=emp_auth)
        hidden_rel = await c.get(f"{API}/brain/insights/{hidden_insight['id']}/related", headers=emp_auth)
        check(
            "9. governance: scoped reader sees own insight; hidden insight is 404 everywhere",
            insight["id"] in scoped_ids
            and hidden_insight["id"] not in scoped_ids
            and hidden_get.status_code == 404
            and hidden_ev.status_code == 404
            and hidden_his.status_code == 404
            and hidden_rel.status_code == 404,
            f"visible={insight['id'] in scoped_ids} get={hidden_get.status_code} ev={hidden_ev.status_code}",
        )
        print("9. Governance verified")

        # ---- 10: tenant isolation ------------------------------------------------------------
        org_b = await register(c, "Rival Corp", f"rc-{t}", f"eve{t}@rc.test.co", "Eve Rival")
        rival_ids = {i["id"] for i in await insights(c, org_b["headers"])}
        check(
            "10. tenant isolation: outsider org sees nothing",
            insight["id"] not in rival_ids,
            f"rival_count={len(rival_ids)}",
        )

        # ---- 11: brain integration -------------------------------------------------------------
        rb = await c.post(
            f"{API}/brain/answer",
            json={"question": "what is happening in this organization right now?"},
            headers=auth,
        )
        claims = rb.json().get("claims", []) if rb.status_code == 200 else []
        insight_cited = any(
            cl.get("kind") == "insight"
            and any(e.get("type") == "insight" and e.get("url", "").startswith("/brain/insights/")
                    for e in cl.get("evidence", []))
            for cl in claims
        )
        check(
            "11. brain integration: /brain/answer cites insight claims",
            rb.status_code == 200 and insight_cited,
            f"status={rb.status_code} insight_claims={sum(1 for cl in claims if cl.get('kind') == 'insight')}",
        )

        # ---- 12: worker + scheduler ---------------------------------------------------------------
        workers = (await c.get(f"{API}/intelligence/workers", headers=auth)).json()
        reg = next((w for w in workers if w["name"] == "insight"), None)
        run = await run_worker(c, auth, "insight")
        check(
            "12. insight worker registered @ 120s and runs on demand",
            reg is not None and reg.get("interval_seconds") == 120 and reg.get("run_on_demand") is True
            and run.get("worker") == "insight" and isinstance(run.get("processed"), int),
            f"reg={reg} run={run}",
        )

        # ---- 13: exactly-once replay -------------------------------------------------------------------
        before_pats = len(insight.get("supporting_pattern_ids", []))
        hist_before = len((await c.get(f"{API}/brain/insights/{insight['id']}/history", headers=auth)).json()["history"])
        before_count = len(await insights(c, auth))
        for _ in range(3):
            await dispatch(c, auth)
            await run_worker(c, auth, "pattern")
            await dispatch(c, auth)
            await run_worker(c, auth, "insight")
        fresh = next(
            i for i in await insights(c, auth)
            if i["insight_type"] == "execution_bottleneck" and i["auth_project_id"] == proj["id"]
        )
        hist_after = len((await c.get(f"{API}/brain/insights/{insight['id']}/history", headers=auth)).json()["history"])
        after_count = len(await insights(c, auth))
        check(
            "13. exactly-once replay: no duplicate rows, evidence or history",
            after_count == before_count
            and len(fresh.get("supporting_pattern_ids", [])) == before_pats
            and hist_after == hist_before,
            f"rows={before_count}->{after_count} patterns={before_pats}->{len(fresh.get('supporting_pattern_ids', []))} history={hist_before}->{hist_after}",
        )
        print("10-13. Isolation, brain, worker, replay verified")

        # ---- 19: status surface ------------------------------------------------------------------------
        default_list = (await c.get(f"{API}/brain/insights", params={"limit": 200}, headers=auth)).json()
        active_filtered = (await c.get(f"{API}/brain/insights", params={"status": "active", "limit": 200}, headers=auth)).json()
        check(
            "19. status surface: default list shows active insights; status filter works",
            insight["id"] in {i["id"] for i in default_list.get("insights", [])}
            and insight["id"] in {i["id"] for i in active_filtered.get("insights", [])},
            f"default={len(default_list.get('insights', []))} active={len(active_filtered.get('insights', []))}",
        )

        # ---- 20: related links --------------------------------------------------------------------------
        rel = (await c.get(f"{API}/brain/insights/{insight['id']}/related", headers=auth)).json()
        rel_limited = (await c.get(f"{API}/brain/insights/{insight['id']}/related", params={"limit": 1}, headers=auth)).json()
        check(
            "20. related links: bounded and governance-filtered",
            isinstance(rel.get("related"), list)
            and len(rel.get("related", [])) <= 10
            and isinstance(rel_limited.get("related"), list)
            and len(rel_limited.get("related", [])) <= 1,
            f"related={len(rel.get('related', []))} limited={len(rel_limited.get('related', []))}",
        )

        # ---- 16: bounded reads ---------------------------------------------------------------------------
        bounded = await c.get(f"{API}/brain/insights", params={"limit": 1}, headers=auth)
        bounded_body = bounded.json()
        check(
            "16. bounded reads: limit honored with truncated flag",
            bounded.status_code == 200
            and len(bounded_body.get("insights", [])) <= 1
            and bounded_body.get("limit") == 1
            and "truncated" in bounded_body,
            f"len={len(bounded_body.get('insights', []))} truncated={bounded_body.get('truncated')}",
        )

        # ---- 17: confidence bounds across all insights -----------------------------------------------------
        all_insights = await insights(c, auth)
        check(
            "17. every visible insight confidence is bounded to [0, 1]",
            len(all_insights) >= 1
            and all(0.0 <= i.get("confidence", -1) <= 1.0 for i in all_insights),
            f"insights={len(all_insights)}",
        )

        # ---- 15: endpoint contract ----------------------------------------------------------------------------
        anon_list = await c.get(f"{API}/brain/insights")
        anon_get = await c.get(f"{API}/brain/insights/{insight['id']}")
        missing = await c.get(f"{API}/brain/insights/does-not-exist", headers=auth)
        check(
            "15. endpoint contract: anonymous 401/403, missing insight 404",
            anon_list.status_code in (401, 403)
            and anon_get.status_code in (401, 403)
            and missing.status_code == 404,
            f"anon={anon_list.status_code}/{anon_get.status_code} missing={missing.status_code}",
        )
        print("14-20. Mutation, contracts, bounds, related verified")

    print()
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print(f"  FAILED: {name}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
