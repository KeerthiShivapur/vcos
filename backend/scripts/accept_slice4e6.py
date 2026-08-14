"""Slice 4E.6 acceptance â€” Universal Company Actions (live API).

Checks against the running stack (http://localhost:8999). 4E.5 turned
intelligence into operations; 4E.6 turns those operations into GOVERNED,
UNIVERSAL actions that close the loop back into company intelligence:
propose-with-lineage + risk policy + exact-once dedup, the governed state
machine with an immutable audit trail, routing through the REAL operating
services, dependency gating, the idempotent evaluate pass, outcome
intelligence, the action center, NL intents, and governance/tenant law.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
ACTIONS = f"{API}/brain/knowledge/actions"
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


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 300) -> int:
    try:
        r = await client.post(
            f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers, timeout=15
        )
        if r.status_code == 200:
            return r.json().get("processed", 0)
    except Exception:
        pass
    return -1


async def propose(client: httpx.AsyncClient, headers: dict, **body) -> dict:
    r = await client.post(ACTIONS, json=body, headers=headers, timeout=60)
    assert r.status_code == 201, r.text
    return r.json()


async def transition(client: httpx.AsyncClient, headers: dict, action_id: str, tr: str, **extra):
    return await client.post(
        f"{ACTIONS}/{action_id}/transition",
        json={"transition": tr, **extra}, headers=headers, timeout=60,
    )


async def poll(
    client: httpx.AsyncClient,
    headers: dict,
    method: str,
    url: str,
    predicate,
    params: dict | None = None,
    json: dict | None = None,
    timeout: float = 180,
    tick=None,
) -> dict:
    """Poll until the durable outcome appears. `tick` (optional async fn) runs
    between attempts so ingestion keeps flowing while we wait."""
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
async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Action Ops Co", f"actco-{t}", f"act{t}@actco.test.co", "Ops Founder")
        auth = org["headers"]

        # -------- 1. knowledge substrate: a real conflict recommendation
        me = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]
        conv = (await c.post(f"{API}/conversations", json={"type": "channel", "title": "budget", "member_ids": [me]}, headers=auth)).json()
        for msg in ("The migration budget is 5 lakh.", "The migration budget is 10 lakh."):
            await c.post(f"{API}/conversations/{conv['id']}/messages", json={"content": msg}, headers=auth)
        await dispatch(c, auth)
        recom_poll = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/recommendations",
            lambda b: any(r.get("kind") == "conflict" for r in b.get("recommendations") or []),
            timeout=420,
            tick=lambda: dispatch(c, auth),
        )
        recs = recom_poll.get("recommendations") or []
        conflict = next((r for r in recs if r["kind"] == "conflict"), None)
        check("1. the equal-authority conflict materializes a recommendation",
              conflict is not None and bool(conflict.get("id")),
              f"kinds={[r.get('kind') for r in recs][:10]} total={recom_poll.get('total')}")
        rec = conflict

        # -------- 2. propose with lineage + policy (medium -> awaiting approval)
        r = await c.post(ACTIONS, json={
            "action_type": "task", "title": "Escalate the budget conflict",
            "risk": "medium", "source_recommendation_id": rec["id"],
        }, headers=auth)
        check("2. medium-risk proposal is governed (awaiting_approval, approval policy)",
              r.status_code == 201
              and r.json()["state"] == "awaiting_approval"
              and r.json()["approval_required"] is True
              and r.json()["policy"] == "approval", r.text[:300])
        action = r.json()
        check("3. full lineage is carried (recommendation + claims + why)",
              action["source_recommendation_id"] == rec["id"]
              and action["source_claim_ids"]
              and action["why"] and action["fingerprint"], str(action)[:300])

        # -------- 3. exact-once replay
        r2 = await c.post(ACTIONS, json={
            "action_type": "task", "title": "Escalate the budget conflict",
            "risk": "medium", "source_recommendation_id": rec["id"],
        }, headers=auth)
        check("4. replay dedups to the same action (exact-once)",
              r2.status_code == 201 and r2.json()["deduplicated"] is True
              and r2.json()["id"] == action["id"], r2.text[:200])

        r3 = await c.post(ACTIONS, json={
            "action_type": "task", "title": "Fake lineage action",
            "risk": "low", "source_recommendation_id": "no-such-rec",
        }, headers=auth)
        check("5. fake lineage is refused (400)", r3.status_code == 400, r3.text[:200])

        # -------- 4. auto path: low risk routes through a REAL service
        doc = await propose(c, auth, action_type="knowledge", risk="low",
                            title="Document the settled pricing policy",
                            source_problem="capture the agreed budget stance")
        check("6. low-risk action auto-approves into ready",
              doc["state"] == "ready" and doc["approval_required"] is False
              and doc["policy"] == "auto", str(doc)[:200])
        check("7. the routed knowledge artifact truly exists",
              doc["target_type"] == "knowledge"
              and (await c.get(f"{API}/documents/{doc['target_id']}", headers=auth)).status_code == 200,
              str(doc)[:200])

        rp = await c.post(ACTIONS, json={
            "action_type": "project", "title": "Open the budget program", "risk": "low",
        }, headers=auth)
        check("8. project-type actions are always restricted + approval-mandatory",
              rp.status_code == 201 and rp.json()["policy"] == "restricted"
              and rp.json()["approval_required"] is True, rp.text[:200])

        # -------- 5. approval lifecycle + audit trail
        r = await transition(c, auth, action["id"], "approve", note="approved by lead")
        check("9. approve materializes ready + a real task",
              r.status_code == 200 and r.json()["state"] == "ready"
              and r.json()["target_type"] == "task"
              and (await c.get(f"{API}/tasks/{r.json()['target_id']}", headers=auth)).status_code == 200,
              r.text[:300])
        detail = (await c.get(f"{ACTIONS}/{action['id']}", headers=auth)).json()
        trail = [e["event"] for e in detail["events"]]
        check("10. the audit trail is ordered and immutable",
              trail[0] == "action.ready" and trail[1] == "action.approved"
              and "action.created" in trail
              and "action.validated" in trail, str(trail))
        check("11. detail shows the source recommendation",
              bool(detail["source_recommendation"])
              and detail["source_recommendation"]["id"] == rec["id"], str(detail)[:200])

        r = await transition(c, auth, action["id"], "assign", assignee_id="opsteam")
        r = await transition(c, auth, action["id"], "start", note="go")
        r = await transition(c, auth, action["id"], "complete", note="done")
        r = await transition(c, auth, action["id"], "verify", note="verified")
        check("12. assign -> start -> complete -> verify reaches verified",
              r.status_code == 200 and r.json()["state"] == "verified", r.text[:200])
        bad = await transition(c, auth, action["id"], "start")
        check("13. invalid transition is a clean 400",
              bad.status_code == 400 and "cannot 'start' from state" in bad.text, bad.text[:200])

        # -------- 6. terminal escapes
        a_rej = await propose(c, auth, action_type="task", title="Action we drop", risk="medium")
        r = await transition(c, auth, a_rej["id"], "reject", note="no need")
        check("14. reject is terminal with a recorded reason",
              r.status_code == 200 and r.json()["state"] == "rejected"
              and r.json()["rejected_reason"] == "no need", r.text[:200])
        a_fail = await propose(c, auth, action_type="task", title="Action that fails", risk="medium")
        r = await transition(c, auth, a_fail["id"], "fail", note="cannot proceed")
        check("15. fail is a legal terminal escape with the reason",
              r.status_code == 200 and r.json()["state"] == "failed"
              and r.json()["fail_reason"] == "cannot proceed", r.text[:200])

        # -------- 7. block / unblock + escalation via evaluate
        a_blk = await propose(c, auth, action_type="task", title="Action that blocks", risk="low")
        r = await transition(c, auth, a_blk["id"], "block", note="waiting on vendor")
        check("16. block is a governed state",
              r.status_code == 200 and r.json()["state"] == "blocked", r.text[:200])
        r = await transition(c, auth, a_blk["id"], "unblock", note="vendor replied")
        check("17. unblock returns to in_progress",
              r.status_code == 200 and r.json()["state"] == "in_progress", r.text[:200])

        a_due = await propose(c, auth, action_type="task", title="Overdue rollout", risk="low")
        await transition(c, auth, a_due["id"], "start", note="go",
                         due_at="2000-01-01T00:00:00Z")
        ev = (await c.post(f"{ACTIONS}/evaluate", headers=auth, timeout=30)).json()
        check("18. evaluate escalates overdue work (audited)",
              ev["escalated"] >= 1, str(ev)[:200])
        detail_due = (await c.get(f"{ACTIONS}/{a_due['id']}", headers=auth)).json()
        check("19. the escalation is visible in detail + audit",
              detail_due["escalation_level"] >= 1
              and "action.escalated" in [e["event"] for e in detail_due["events"]], str(detail_due)[:200])
        ev2 = (await c.post(f"{ACTIONS}/evaluate", headers=auth, timeout=30)).json()
        check("20. evaluate is idempotent (second pass changes nothing)",
              ev2["expired"] == 0 and ev2["escalated"] == 0, str(ev2)[:200])

        # -------- 8. dependencies gate start
        dep = await propose(c, auth, action_type="task", title="Prepare the migration runbook", risk="low")
        main = await propose(c, auth, action_type="task", title="Ship after the runbook", risk="low",
                             depends_on=[dep["id"]])
        await transition(c, auth, dep["id"], "block", note="dep blocked")
        await transition(c, auth, dep["id"], "unblock", note="dep unblocked")
        await transition(c, auth, main["id"], "assign", assignee_id="me")
        r = await transition(c, auth, main["id"], "start", note="go")
        check("21. start is refused while a dependency is open",
              r.status_code == 400 and "not completed" in r.text, r.text[:200])
        await transition(c, auth, dep["id"], "assign", assignee_id="me")
        await transition(c, auth, dep["id"], "start", note="go")
        await transition(c, auth, dep["id"], "complete", note="done")
        r = await transition(c, auth, main["id"], "start", note="go")
        check("22. start is allowed once the dependency completes",
              r.status_code == 200 and r.json()["state"] == "in_progress", r.text[:200])
        ddep = (await c.get(f"{ACTIONS}/{main['id']}", headers=auth)).json()
        check("23. detail reports dependency status",
              ddep["dependencies"] and ddep["dependencies"][0]["complete"] is True,
              str(ddep["dependencies"]))

        # -------- 9. outcomes + outcome intelligence
        a_out = await propose(c, auth, action_type="task", title="Action measured as missed", risk="low")
        await transition(c, auth, a_out["id"], "assign", assignee_id="me")
        await transition(c, auth, a_out["id"], "start", note="go")
        await transition(c, auth, a_out["id"], "complete", note="done")
        await transition(c, auth, a_out["id"], "verify", note="verified")
        for aid, otype, eff in ((action["id"], "success", 0.9), (a_out["id"], "failed", 0.2)):
            r = await c.post(f"{ACTIONS}/{aid}/outcome",
                             json={"outcome_type": otype, "effectiveness": eff,
                                   "verdict": "done" if otype == "success" else "missed"},
                             headers=auth, timeout=30)
            assert r.status_code == 200, r.text
        od = (await c.get(f"{ACTIONS}/{action['id']}", headers=auth)).json()
        check("24. outcome evidence defaults to the source claims (loop back)",
              od["outcome"]["outcome_type"] == "success"
              and bool(od["outcome"]["evidence"]), str(od["outcome"])[:300])
        oi = (await c.get(f"{ACTIONS}/outcome-intelligence", headers=auth)).json()
        by_outcome = {row["key"]: row for row in oi["by_outcome_type"]}
        check("25. outcome intelligence aggregates success rate + effectiveness",
              oi["total"] == 2 and oi["success_rate"] == 0.5
              and by_outcome["success"]["avg_effectiveness"] == 0.9
              and by_outcome["failed"]["avg_effectiveness"] == 0.2, str(oi)[:300])

        # -------- 10. action center
        center = (await c.get(ACTIONS, headers=auth)).json()
        check("26. the action center lists all governed actions with stats",
              center["total"] >= 7 and center["stats"]["open"] >= 1
              and "by_state" in center["stats"], str(center)[:300])
        only_ready = (await c.get(ACTIONS, params={"state": "ready"}, headers=auth)).json()
        check("27. center state filter works",
              all(i["state"] == "ready" for i in only_ready["items"]))
        att = (await c.get(ACTIONS, params={"attention": True}, headers=auth)).json()
        check("28. attention filter surfaces actionable items (with reasons)",
              all(i["attention_reasons"] for i in att["items"]), str(att)[:300])
        by_type = (await c.get(ACTIONS, params={"action_type": "knowledge"}, headers=auth)).json()
        check("29. center type filter works",
              all(i["action_type"] == "knowledge" for i in by_type["items"]))

        # -------- 11. NL intents through the universal query
        for q, intent in (
            ("what needs my attention", "attention"),
            ("what is blocked", "blocked"),
            ("which actions are overdue", "overdue"),
            ("show my actions", "actions"),
            ("what needs to be escalated", "escalation"),
        ):
            resp = (await c.post(f"{API}/brain/knowledge/query",
                                 json={"question": q}, headers=auth)).json()
            check(f"30. query {q!r} -> {intent}",
                  resp.get("intent") == intent and "items" in resp, str(resp)[:200])

        # -------- 12. governance: scoped readers see only their scope
        project = (await c.post(f"{API}/projects", json={"name": "Budget Program", "status": "active"}, headers=auth)).json()
        p_action = await propose(c, auth, action_type="task", title="Budget program task",
                                 risk="low", scope_type="project", scope_id=project["id"])
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Budget scope", "scope_type": "project", "entity_id": project["id"]},
                              headers=auth)).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sco{t}@actco.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite",
                               json={"token": emp["token"], "email": f"sco{t}@actco.test.co",
                                     "full_name": "Scoped Mgr", "password": "StrongPass123!"},
                               headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(f"{API}/governance/assignments",
                         json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
                         headers=auth)
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)
        dg = await c.post(f"{API}/governance/delegations",
                          json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.6"},
                          headers=auth)
        assert dg.status_code == 201, dg.text
        s_c = (await c.get(ACTIONS, headers=scoped)).json()
        check("31. scoped reader sees only their project-scope actions",
              s_c["scope"] == "project"
              and all(i["scope_type"] == "project" and i["scope_id"] == project["id"] for i in s_c["items"]),
              str(s_c)[:300])
        s_d = await c.get(f"{ACTIONS}/{doc['id']}", headers=scoped)
        check("32. an action outside the scope is 404 for the scoped reader",
              s_d.status_code == 404, f"status={s_d.status_code}")

        # -------- 13. tenant isolation
        rival = await register(c, "Rival Ops Co", f"rivop-{t}", f"r{t}@rivop.test.co", "Riv Founder")
        await dispatch(c, rival["headers"])
        rc = (await c.get(ACTIONS, headers=rival["headers"])).json()
        rd = await c.get(f"{ACTIONS}/{action['id']}", headers=rival["headers"])
        rt = await transition(c, rival["headers"], action["id"], "cancel", note="x")
        check("33. tenant isolation: a rival sees nothing and steers nothing",
              rc["total"] == 0 and rd.status_code == 404 and rt.status_code == 404,
              f"center={rc['total']} detail={rd.status_code} transition={rt.status_code}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

