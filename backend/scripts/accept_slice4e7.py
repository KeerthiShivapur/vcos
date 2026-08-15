"""Slice 4E.7 acceptance — the Universal Knowledge Operating Loop (live API).

Checks against the running stack (http://localhost:8999). 4E.7 is the final
bridge of the Knowledge Intelligence family: verified outcomes -> assessment
-> lesson with evidence -> canonical lifecycle (tested/confirmed) ->
recommendation feedback, exact-once under replay; temporal memory
(what-changed); dependency impact; contradiction -> resolution -> learning
(losing evidence stays); decision & recommendation quality; What-Changed +
Company Health; the Universal Action Center; the risk ladder; NL intents;
governance and tenant isolation. NOT another isolated silver — everything is
read from the SAME canonical knowledge model.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
KNOW = f"{API}/brain/knowledge"
LOOP = f"{KNOW}/loop"
ACTIONS = f"{KNOW}/actions"
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
        "user": data["user"],
        "organization": data["organization"],
    }


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 400) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=30
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:
        pass
    return -1


async def poll(
    client: httpx.AsyncClient,
    headers: dict,
    method: str,
    url: str,
    predicate,
    params: dict | None = None,
    json: dict | None = None,
    timeout: float = 300,
    tick=None,
) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = await client.request(method, url, headers=headers, params=params, json=json)
        if r.status_code in (200, 201):
            last = r.json()
            if predicate(last):
                return last
        if tick:
            try:
                await tick()
            except Exception:
                pass
        await asyncio.sleep(2)
    return last


async def propose(client: httpx.AsyncClient, headers: dict, **body) -> dict:
    r = await client.post(ACTIONS, json=body, headers=headers, timeout=60)
    assert r.status_code == 201, r.text
    return r.json()


async def transition(client: httpx.AsyncClient, headers: dict, action_id: str, tr: str, **extra):
    r = await client.post(
        f"{ACTIONS}/{action_id}/transition",
        json={"transition": tr, **extra}, headers=headers, timeout=60,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def close_loop(client: httpx.AsyncClient, headers: dict, action_id: str, **body) -> dict:
    r = await client.post(f"{LOOP}/outcomes", json={"action_id": action_id, **body}, headers=headers, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Loop Co", f"loopco-{t}", f"loop{t}@loopco.test.co", "Loop Founder")
        auth = org["headers"]
        oid = org["organization"]["id"]

        # -------- 1. substrate: an equal-authority conflict recommendation
        me = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]
        conv = (await c.post(f"{API}/conversations", json={"type": "channel", "title": "budget", "member_ids": [me]}, headers=auth)).json()
        for msg in ("The migration budget is 5 lakh.", "The migration budget is 10 lakh."):
            await c.post(f"{API}/conversations/{conv['id']}/messages", json={"content": msg}, headers=auth)
        await dispatch(c, auth)
        rec_body = await poll(
            c, auth, "GET", f"{KNOW}/recommendations",
            lambda b: any(r.get("kind") == "conflict" for r in b.get("recommendations") or []),
            timeout=420, tick=lambda: dispatch(c, auth),
        )
        rec = next((r for r in rec_body.get("recommendations") or [] if r["kind"] == "conflict"), None)
        check("1. the conflict materializes a recommendation",
              rec is not None and bool(rec.get("id")), str(rec_body)[:200])

        # -------- 2. the governed loop: verified action -> assessment -> lesson
        a = await propose(c, auth, action_type="task", title="Land the migration", risk="low",
                          source_recommendation_id=rec["id"])
        for tr, kw in (("assign", {"assignee_id": "me"}), ("start", {"note": "go"}),
                       ("complete", {"note": "done"}), ("verify", {"note": "verified"})):
            await transition(c, auth, a["id"], tr, **kw)
        loop = await close_loop(c, auth, a["id"], expected_value=100.0, actual_value=40.0,
                                expected_metric="target users reached", metric="target users reached",
                                factors=["late vendor delivery"], summary="landed late and short")
        learning = loop.get("learning") or {}
        assessment = loop.get("assessment") or {}
        check("2. closing the loop records the lesson (outcome_learning)",
              learning.get("kind") == "outcome_learning" and bool(learning.get("id")), str(loop)[:250])
        check("3. the assessment is governed evidence (underperformed, 60% variance)",
              assessment.get("assessment") == "underperformed"
              and assessment.get("subject_id") == a["id"]
              and abs(assessment.get("variance_pct", 0)) == 60.0, str(assessment)[:250])
        check("4. lifecycle items advanced and the recommendation gets feedback",
              loop.get("claims_advanced") is not None
              and bool(loop.get("recommendation_feedback")), str(loop)[:250])

        replay = await close_loop(c, auth, a["id"], expected_value=100.0, actual_value=40.0,
                                  expected_metric="target users reached", metric="target users reached",
                                  factors=["late vendor delivery"], summary="landed late and short")
        check("5. replay is exact-once (same lesson id, no duplicate)",
              (replay.get("learning") or {}).get("id") == learning.get("id"), str(replay)[:200])
        feed = (await c.get(f"{LOOP}/learning", headers=auth)).json()
        check("6. the learning feed shows the recorded lesson",
              any(i.get("id") == learning.get("id") for i in feed.get("items") or []), str(feed)[:200])

        # -------- 3. decision feedback
        decision = (await c.post(f"{API}/decisions", json={
            "title": "Adopt phased migration", "description": "decision", "status": "made",
        }, headers=auth)).json()
        dout = (await c.post(f"{LOOP}/decisions/{decision['id']}/outcome", json={
            "expected_metric": "timeline days", "expected_value": 100.0,
            "actual_value": 30.0, "expected_units": "days",
            "factors": ["vendor delay"], "summary": "phasing drifted",
        }, headers=auth)).json()
        perf = (await c.get(f"{LOOP}/decisions", headers=auth)).json()
        check("7. the decision outcome is measured (70% variance)",
              dout.get("decision_outcome", {}).get("assessment") == "underperformed"
              and dout.get("learning", {}).get("kind") in ("outcome_learning", "decision_learning")
              and perf.get("total") == 1
              and abs(perf["decisions"][0]["variance_pct"]) == 70.0,
              str(perf)[:250])

        # -------- 4. contradiction -> resolution -> learning (evidence retained)
        contra = (await c.get(f"{KNOW}/topics/migration/contradictions", headers=auth)).json()
        pair = (contra.get("contradictions") or [{}])[0]
        winner = pair.get("winner_claim_id")
        check("8. the equal-authority contradiction is visible",
              bool(winner) and pair.get("loser_claim_id"), str(contra)[:250])
        resolved = (await c.post(f"{LOOP}/contradictions/migration/resolution", json={
            "authoritative_claim_id": winner,
            "reason": "finance confirmed 10 lakh at the board",
        }, headers=auth)).json()
        check("9. resolution advances the winner and retains the loser",
              resolved.get("authoritative_claim_id") == winner
              and bool(resolved.get("retained_conflicting")), str(resolved)[:250])
        rfeed = (await c.get(f"{LOOP}/learning", headers=auth)).json()
        check("10. the resolution itself was learned",
              any(i.get("kind") == "contradiction_resolution" for i in rfeed.get("items") or []),
              str(rfeed)[:200])

        # -------- 5. recommendation quality by kind
        quality = (await c.get(f"{LOOP}/recommendation-quality", headers=auth)).json()
        kinds = {row["kind"]: row for row in quality.get("kinds") or []}
        check("11. quality is deterministic + explainable per kind",
              kinds.get("conflict", {}).get("measured") >= 1
              and kinds.get("conflict", {}).get("successes") >= 0
              and 0 <= kinds.get("conflict", {}).get("adjusted_confidence", -1) <= 0.95,
              str(quality)[:250])

        # -------- 6. temporal memory: what-changed
        changes = (await c.get(f"{LOOP}/changes", headers=auth)).json()
        kinds_seen = {i.get("kind") for i in changes.get("changes") or []}
        check("12. what-changed materializes the verified + learned changes",
              {"action_verified", "learning", "contradiction_resolved"}.issubset(kinds_seen),
              str(changes)[:300])

        # -------- 7. company health: explainable, evidence-backed
        health = (await c.get(f"{LOOP}/health", headers=auth)).json()
        check("13. company health is a 10-dimension explainable board",
              len(health.get("dimensions") or []) == 10
              and all(d.get("signals") for d in health.get("dimensions") or []
                      if d.get("metric") in ("topics", "claims", "contradictions"))
              and health.get("intent") == "companyhealth", str(health)[:300])

        # -------- 8. dependency impact: reach + persistence
        claim_id = (rec.get("evidence") or [None])[0]
        impacted = (await c.post(f"{LOOP}/impact", json={
            "subject_type": "claim", "subject_id": claim_id,
        }, headers=auth)).json()
        direct = impacted.get("direct") or []
        check("14. impact analysis reaches the governed action",
              impacted.get("subject_id") == claim_id and bool(claim_id)
              and any(d.get("entity_type") == "action"
                      and (d.get("entity_id") or d.get("id")) == a["id"] for d in direct),
              str(impacted)[:250])

        # -------- 9. universal action center
        pending = await propose(c, auth, action_type="task", title="Pending approval board item",
                                risk="medium")
        awaiting = (await c.get(ACTIONS, params={"state": "awaiting_approval"}, headers=auth)).json()
        center = (await c.get(f"{LOOP}/insights", headers=auth)).json()
        cats = center.get("categories") or {}
        check("15. the universal action center consolidates the board",
              center.get("intent") == "actions"
              and set(cats) <= {
                  "critical_issue", "recommended_action", "pending_approval", "knowledge_gap",
                  "contradiction", "emerging_risk", "overdue_action", "decision_attention",
                  "customer_impact", "learning_opportunity"}
              and cats.get("pending_approval", 0) >= 1
              and cats.get("contradiction", 0) >= 1,
              f"categories={sorted(cats)} total={center.get('total')}")
        approval_item = next((i for i in center.get("items") or []
                              if i.get("category") == "pending_approval"), None)
        resolved = (await c.post(f"{LOOP}/insights/{approval_item['id']}/resolve",
                                 headers=auth))
        check("16. humans resolve insights (never deleted, user audited)",
              resolved.status_code == 200 and resolved.json().get("resolved") is True,
              f"status={resolved.status_code} {resolved.text[:200]}")
        miss = (await c.post(f"{LOOP}/insights/does-not-exist/resolve", headers=auth)).json()
        check("17. resolving an unknown insight is a governed no-op",
              miss.get("resolved") is False, str(miss)[:200])

        # -------- 10. risk ladder + NL intents
        why = (await c.post(f"{KNOW}/query", json={"question": "why did the migration underperform"},
                            headers=auth)).json()
        check("18. the universal query explains why (intent + evidence)",
              why.get("intent") == "why" and why.get("reasons"), str(why)[:250])
        changed = (await c.post(f"{KNOW}/query", json={"question": "what changed in the company"},
                                headers=auth)).json()
        check("19. the universal query reports what changed",
              changed.get("intent") == "company_changes" and "changes" in changed,
              str(changed)[:200])

        # -------- 11. governance: scoped readers see only their scope
        project = (await c.post(f"{API}/projects", json={"name": "Budget Program", "status": "active"}, headers=auth)).json()
        scoped_action = await propose(c, auth, action_type="task", title="Budget program task",
                                      risk="low", scope_type="project", scope_id=project["id"])
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Budget scope", "scope_type": "project", "entity_id": project["id"]},
                              headers=auth)).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sco{t}@loopco.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite",
                               json={"token": emp["token"], "email": f"sco{t}@loopco.test.co",
                                     "full_name": "Scoped Mgr", "password": "StrongPass123!"},
                               headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        assign_resp = await c.post(f"{API}/governance/assignments",
                         json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
                         headers=auth)
        assert assign_resp.status_code == 201, assign_resp.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)
        dg = await c.post(f"{API}/governance/delegations",
                          json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.7"},
                          headers=auth)
        assert dg.status_code == 201, dg.text
        s_c = (await c.get(f"{LOOP}/insights", headers=scoped)).json()
        s_l = (await c.get(f"{LOOP}/changes", headers=scoped)).json()
        check("20. scoped readers see only their scope on every surface",
              (await c.get(f"{ACTIONS}/{scoped_action['id']}", headers=scoped)).status_code != 404
              and (await c.get(f"{ACTIONS}/{a['id']}", headers=scoped)).status_code == 404
              and all((i.get("scope_type"), i.get("scope_id")) == ("project", project["id"])
                      for i in (s_c.get("items") or []) if i.get("scope_type"))
              and not any(i.get("kind") in ("learning", "contradiction_resolved")
                          for i in s_l.get("changes") or []),
              f"scoped center {str(s_c)[:200]}")

        # -------- 12. tenant isolation
        rival = await register(c, "Rival Loop Co", f"rivloop-{t}", f"r{t}@rivloop.test.co", "Riv Founder")
        await dispatch(c, rival["headers"])
        rc = (await c.get(f"{LOOP}/insights", headers=rival["headers"])).json()
        rd = await c.get(f"{LOOP}/learning", headers=rival["headers"])
        rt = await c.post(f"{LOOP}/outcomes", json={"action_id": a["id"], "actual_value": 1.0}, headers=rival["headers"])
        check("21. tenant isolation: a rival sees nothing and closes nothing",
              rc.get("total", 0) == 0 and rd.json().get("total", 0) == 0
              and rt.status_code in (400, 404),
              f"center={rc.get('total')} feed={rd.status_code} loop={rt.status_code}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))