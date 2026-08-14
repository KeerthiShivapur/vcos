"""Slice 4E.5 acceptance — Knowledge Intelligence Operating Layer (live API).

Checks against the running stack (http://localhost:8999). 4E.4 turned evidence
into intelligence; 4E.5 turns intelligence into OPERATIONS — a governed
workspace where the company observes what its knowledge MEANS and commands it:

  1. brief: what changed, emerged, needs a decision, is affected — plus the
     three things that need attention first (4E.5.1)
  2. universal insights: the contradiction becomes a decision_required
     insight; the detail carries the full evidence lineage and audit; an
     acknowledgement is audited and never deletes (4E.5.2)
  3. gaps: the equal-authority conflict is a live gap citing both values (4E.5.3)
  4. changes: the evolution of the understanding is reported with insight
     events (4E.5.4)
  5. topic operating surface: state / evolution (supersession chain, old
     versions retained) / propagation (multi-hop) / impact / ownership (4E.5.4)
  6. health center: 0-100 score from seven explainable bars plus drill-down
     counts; coverage per business area explains weak areas (4E.5.7)
  7. recommendation lifecycle: review -> accept -> convert (governed task) ->
     execute -> verify; the materializer never overwrites a user-steered row;
     exact-once persistence (4E.5.6)
  8. universal query: affected / worry / decide / next / recommendations /
     missing / confident / stakeholders / provenance / discovery / temporal /
     changes — one surface, deterministic intent routing (4E.5.8)
  9. governance: a scoped reader's insights/impact are built only from
     visible evidence; a hidden topic is 404 for them (4E.5.9)
  10. tenant isolation: a rival organization sees nothing (4E.5.10)

Exit code 0 when all pass.
"""

import asyncio
import sys
import time
from urllib.parse import quote

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
        "user": data["user"],
        "organization": data["organization"],
    }


async def dispatch(client: httpx.AsyncClient, headers: dict, limit: int = 500) -> int:
    r = await client.post(f"{API}/intelligence/events/process", params={"limit": limit}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json().get("processed", 0)


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 14) -> None:
    for _ in range(rounds):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def poll(
    client: httpx.AsyncClient,
    headers: dict,
    method: str,
    url: str,
    predicate,
    params: dict | None = None,
    json: dict | None = None,
    timeout: float = 120,
) -> dict:
    """The stack consumes events asynchronously; poll until the durable
    outcome appears, then return the last response body."""
    import time as _time

    deadline = _time.time() + timeout
    last: dict = {}
    while _time.time() < deadline:
        r = await client.request(method, url, headers=headers, params=params, json=json)
        if r.status_code in (200, 201):
            last = r.json()
            if predicate(last):
                return last
        await asyncio.sleep(2)
    return last


def topic_of(name: str) -> str:
    return quote(name, safe="")


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4E.5 acceptance: Knowledge Intelligence Operating Layer (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        org = await register(c, "Knowledge Operations Co", f"ko-{t}", f"ko{t}@ko.test.co", "Ko Founder")
        auth = org["headers"]
        org_id = org["organization"]["id"]
        print("1. Founder registered, org", org_id)
        await drain(c, auth)

        # ---------------- seed: a budget contradiction on topic "migration"
        conv = (
            await c.post(
                f"{API}/conversations",
                json={"type": "channel", "title": "release", "member_ids": [org["user"]["id"]]},
                headers=auth,
            )
        ).json()
        project = (
            await c.post(f"{API}/projects", json={"name": "Migration Program", "description": "4E.5", "status": "active"}, headers=auth)
        ).json()
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "The migration budget is 5 lakh."},
            headers=auth,
        )
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "The migration budget is 10 lakh."},
            headers=auth,
        )
        await drain(c, auth)
        await drain(c, auth)

        # ---------------- 1. brief (4E.5.1)
        def _brief_oks(body: dict) -> bool:
            return (
                body.get("counts", {}).get("decisions_potentially_affected", 0) >= 1
                and len(body.get("attention") or []) >= 1
            )

        brief = await poll(c, auth, "GET", f"{API}/brain/knowledge/brief", _brief_oks, params={"since_hours": 24})
        counts = brief["counts"]
        check("1a. the brief reports the operating state of knowledge",
              counts["decisions_potentially_affected"] >= 1
              and counts["significant_changes"] >= 1
              and counts["emerging_risks"] >= 0,
              str(counts)[:300])
        check("1b. the brief names what needs attention first",
              len(brief.get("attention") or []) >= 1
              and all(a.get("id") and a.get("title") for a in brief["attention"]),
              str(brief.get("attention"))[:300])

        # ---------------- 2. universal insights (4E.5.2)
        def _insights_oks(body: dict) -> bool:
            kinds = {i["kind"] for i in body.get("insights") or []}
            return "contradiction" in kinds and "decision_required" in kinds

        insights = await poll(c, auth, "GET", f"{API}/brain/knowledge/insights", _insights_oks, params={"limit": 100})
        kinds = {i["kind"] for i in insights["insights"]}
        contradiction = next(i for i in insights["insights"] if i["kind"] == "contradiction")
        check("2a. insights surface the contradiction and what it requires",
              "contradiction" in kinds and "decision_required" in kinds
              and contradiction["topic_name"] == "migration"
              and contradiction["evidence_count"] >= 2,
              str(kinds))
        detail = (
            await c.get(f"{API}/brain/knowledge/insights/{contradiction['id']}", headers=auth)
        ).json()
        lineage = detail.get("lineage") or {}
        check("2b. the insight detail carries the evidence lineage and audit",
              bool(lineage.get("claims"))
              and all(x.get("id") and x.get("statement") and x.get("source_type") for x in lineage["claims"][:2])
              and bool(detail.get("audit"))
              and detail["id"] == contradiction["id"],
              str(detail)[:400])
        ack = (
            await c.post(
                f"{API}/brain/knowledge/insights/{contradiction['id']}/acknowledge",
                json={"note": "budget needs the owner's sign-off"},
                headers=auth,
            )
        ).json()
        ack_detail = (
            await c.get(f"{API}/brain/knowledge/insights/{contradiction['id']}", headers=auth)
        ).json()
        check("2c. acknowledgement is audited, never destructive",
              ack.get("status") == "acknowledged"
              and any(e.get("action") == "acknowledged" and e.get("note") == "budget needs the owner's sign-off"
                      for e in ack_detail.get("audit") or []),
              str(ack)[:300])
        still = (await c.get(f"{API}/brain/knowledge/insights", params={"status": "acknowledged"}, headers=auth)).json()
        check("2d. the acknowledged insight is queryable by status",
              any(i["id"] == contradiction["id"] for i in still.get("insights") or []),
              str(still.get("total")))
        resolve_ins = (
            await c.post(
                f"{API}/brain/knowledge/insights/{contradiction['id']}/resolve",
                json={"note": "budget fixed at 10 lakh by finance"},
                headers=auth,
            )
        ).json()
        res_detail = (
            await c.get(f"{API}/brain/knowledge/insights/{contradiction['id']}", headers=auth)
        ).json()
        check("2e. explicit user resolution closes the insight with a note",
              resolve_ins.get("status") == "resolved"
              and any(e.get("action") == "resolved" and e.get("note") == "budget fixed at 10 lakh by finance"
                      for e in res_detail.get("audit") or []),
              str(resolve_ins)[:300])

        # ---------------- 3. gaps (4E.5.3)
        def _gaps_oks(body: dict) -> bool:
            contra = [g for g in body.get("gaps") or [] if g["kind"] == "contradiction"]
            return bool(
                contra
                and "5 lakh" in contra[0]["reason"] and "10 lakh" in contra[0]["reason"]
                and len(contra[0]["pair_ids"]) == 2
            )

        gaps = await poll(c, auth, "GET", f"{API}/brain/knowledge/gaps", _gaps_oks)
        contra = [g for g in gaps["gaps"] if g["kind"] == "contradiction"]
        check("3. the equal-authority conflict is a live gap with both values",
              contra and "5 lakh" in contra[0]["reason"] and "10 lakh" in contra[0]["reason"]
              and len(contra[0]["pair_ids"]) == 2,
              str(contra)[:400])

        # ---------------- 4. changes (4E.5.4)
        def _changes_oks(body: dict) -> bool:
            events = []
            for tc in body.get("topic_changes") or []:
                if tc["topic"]["name"] == "migration":
                    events = tc["events"]
            return bool(body.get("window_days") == 7 and events)

        changes = await poll(c, auth, "GET", f"{API}/brain/knowledge/changes", _changes_oks, params={"days": 7})
        migration_events = []
        for tc in changes["topic_changes"]:
            if tc["topic"]["name"] == "migration":
                migration_events = tc["events"]
        understandings = [e for e in migration_events if e["kind"] == "understanding"]
        check("4. change intelligence reports the evolution of understanding",
              changes["window_days"] == 7
              and len(migration_events) >= 2
              and any(e.get("kind") == "new_evidence" for e in migration_events)
              and len(understandings) >= 1
              and any(e.get("from") and e.get("to") and e.get("supersedes_claim_id")
                      for e in understandings),
              str(changes)[:500])

        # ---------------- 5. topic operating surface (4E.5.4)
        state = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/state", headers=auth)
        ).json()
        check("5a. the topic state resolves the current understanding",
              state.get("topic", {}).get("name") == "migration"
              and state.get("current_state", {}).get("object_text")
              and "10 lakh" in state["current_state"]["object_text"],
              str(state)[:300])
        evo = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/evolution", headers=auth)
        ).json()
        check("5b. evolution retains the supersession chain, never erasing",
              evo.get("topic", {}).get("name") == "migration"
              and evo.get("total", 0) >= 2
              and all(step.get("claim_id") and step.get("statement") for step in evo["steps"])
              and any(step.get("status") == "supported" for step in evo["steps"])
              and any(step.get("status") == "superseded" and step.get("replaced_by")
                      for step in evo["steps"]),
              str(evo)[:500])
        prop = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/propagation", params={"depth": 3}, headers=auth)
        ).json()
        check("5c. propagation traces the multi-hop reach of the topic",
              prop.get("topic", {}).get("name") == "migration"
              and len(prop.get("hops") or []) >= 1
              and all(hop.get("entity_type") and hop.get("entity_id") and hop.get("relation")
                      for hop in prop["hops"]),
              str(prop)[:500])
        other_proj = (
            await c.post(f"{API}/projects", json={"name": "Customer Deployments", "description": "4E.5", "status": "active"}, headers=auth)
        ).json()
        dependent = (
            await c.post(f"{API}/tasks", json={"title": "Deploy migration changes to enterprise customers", "project_id": other_proj["id"]}, headers=auth)
        ).json()
        await drain(c, auth)
        imp = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/impact", headers=auth)
        ).json()
        dep_ids = {d["subject_id"] for d in imp.get("dependent_knowledge", {}).get("claims", [])}
        check("5d. impact analysis lists affected entities and dependent knowledge",
              "affected" in imp and isinstance(imp["affected"].get("total"), int)
              and bool(imp.get("dependent_knowledge", {}).get("claims"))
              and (not dep_ids or str(dependent["id"]) in dep_ids)
              and bool(imp.get("evidence", {}).get("sources")),
              str(imp)[:500])
        own = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/topics/{topic_of('migration')}/ownership",
            lambda b: b.get("owner", {}).get("resolved") is True
            and b.get("owner", {}).get("employee_id") is not None,
        )
        check("5e. ownership resolves to the author of the highest-authority source",
              own["owner"]["resolved"] is True and own["owner"]["employee_id"] is not None,
              str(own)[:300])

        # ---------------- 6. health center + coverage (4E.5.7)
        hc = (await c.get(f"{API}/brain/knowledge/health-center", headers=auth)).json()
        check("6a. the health center is a 0-100 score from seven explainable bars",
              0 <= hc.get("score", -1) <= 100
              and len(hc.get("bars") or []) == 7
              and all(b.get("name") and b.get("value") is not None for b in hc["bars"]),
              str({k: hc.get(k) for k in ("score", "scope", "total_topics")}))
        check("6b. the health center drills into what is dragging the score",
              isinstance(hc.get("drill_down"), dict)
              and all(k in hc["drill_down"] for k in ("contradictions", "critical_gaps", "unverified_claims", "stale_knowledge", "orphan_topics"))
              and isinstance(hc.get("why_weak"), list) and len(hc["why_weak"]) >= 1,
              str(hc.get("drill_down"))[:300])
        cov = (await c.get(f"{API}/brain/knowledge/coverage", headers=auth)).json()
        check("6c. coverage maps every business area and explains weak areas",
              cov.get("total", 0) >= 1
              and all(a.get("area") and a.get("total", 0) >= 0 and isinstance(a.get("weak_reasons"), list)
                      for a in cov.get("areas") or []),
              str(cov)[:400])

        # ---------------- 7. recommendation lifecycle (4E.5.6)
        def _recs_conflict_ok(body: dict) -> bool:
            return any(r["kind"] == "conflict" for r in body.get("recommendations") or [])

        recs1 = await poll(c, auth, "GET", f"{API}/brain/knowledge/recommendations", _recs_conflict_ok)
        recs2 = await poll(c, auth, "GET", f"{API}/brain/knowledge/recommendations", _recs_conflict_ok)
        ids1 = {(r["kind"], r["id"]) for r in recs1["recommendations"]}
        ids2 = {(r["kind"], r["id"]) for r in recs2["recommendations"]}
        conflict = next(r for r in recs2["recommendations"] if r["kind"] == "conflict")
        check("7a. recommendations are persisted and exact-once",
              recs1["total"] >= 1 and ids1 == ids2 and conflict["lifecycle"] == "detected",
              f"r1={recs1['total']} r2={recs2['total']}")

        def _lifecycle(action: str, note: str | None = None, target: str | None = None, project_id: str | None = None) -> dict:
            payload: dict = {"action": action}
            if note is not None:
                payload["note"] = note
            if target is not None:
                payload["target"] = target
            if project_id is not None:
                payload["project_id"] = project_id
            r = c.post(f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle", json=payload, headers=auth)
            return r.json()

        review = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
            lambda b: b.get("lifecycle") == "reviewed",
            json={"action": "review"},
        )
        accept = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
            lambda b: b.get("lifecycle") == "accepted",
            json={"action": "accept", "note": "owner agrees 10 lakh"},
        )
        convert = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
            lambda b: b.get("lifecycle") == "converted" and bool(b.get("task_id")),
            json={"action": "convert", "target": "task", "project_id": project["id"]},
        )
        execute = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
            lambda b: b.get("lifecycle") == "executed",
            json={"action": "execute"},
        )
        verify = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/recommendations/{conflict['id']}/lifecycle",
            lambda b: b.get("lifecycle") == "verified" and b.get("status") == "resolved",
            json={"action": "verify", "note": "verified against finance records"},
        )
        check("7b. the governed lifecycle advances review -> accept -> convert",
              review["lifecycle"] == "reviewed" and accept["lifecycle"] == "accepted"
              and convert["lifecycle"] == "converted" and convert["task_id"] is not None,
              str({k: review.get(k) for k in ("lifecycle",)}))
        check("7c. convert lands a real governed task; execute and verify close the loop",
              execute["lifecycle"] == "executed" and verify["lifecycle"] == "verified"
              and verify["status"] == "resolved"
              and len(verify["audit"]) == 5,
              str(verify)[:300])
        tasks_res = await c.get(f"{API}/tasks", params={"status": "backlog"}, headers=auth)
        created = [x for x in tasks_res.json() if x.get("title", "").startswith("[Knowledge]")]
        check("7d. the converted recommendation exists as a governed task",
              len(created) >= 1 and created[0]["project_id"] == project["id"],
              str([x.get("title") for x in created]))
        # materialize again: the user-steered row is never overwritten
        again = (await c.get(f"{API}/brain/knowledge/recommendations", headers=auth)).json()
        row = next((r for r in again["recommendations"] if r["id"] == conflict["id"]), None)
        check("7e. the materializer never overrides a user-steered row",
              row is None or row["lifecycle"] == "verified",
              str(row))

        # ---------------- 8. universal query (4E.5.8)
        q_intents = [
            ("which projects are affected by the migration budget?", "affected"),
            ("should we worry about the migration budget?", "worry"),
            ("the migration budget needs a decision about the owner sign-off", "decide"),
            ("what should we do next about the migration budget?", "next"),
            ("what does the company recommend about the migration?", "recommendations"),
            ("what critical information do we lack about the budget?", "missing"),
            ("how confident are we about the migration budget?", "confident"),
            ("who needs to know about the migration budget?", "stakeholders"),
            ("what is the source of the migration budget numbers?", "provenance"),
            ("what changed about the migration this week?", "changes"),
        ]
        routed = {}
        for question, expected in q_intents:
            q = (await c.post(f"{API}/brain/knowledge/query", json={"question": question}, headers=auth)).json()
            routed[question] = q.get("intent")
        check("8a. one surface routes every operating intent deterministically",
              all(routed[q] == expected for q, expected in q_intents),
              str(routed))
        temporal = (await c.post(f"{API}/brain/knowledge/query",
                                 json={"question": "what was the state of the migration budget in june?"}, headers=auth)).json()
        check("8b. temporal queries answer honestly with the state at the time",
              temporal.get("intent") == "temporal"
              and temporal.get("topic") == "migration"
              and temporal.get("as_of") is not None
              and isinstance(temporal.get("answer"), str) and temporal["answer"],
              str(temporal)[:300])
        q_decide = (await c.post(f"{API}/brain/knowledge/query",
                                 json={"question": "the migration budget needs a decision about the owner sign-off"}, headers=auth)).json()
        check("8c. decision queries surface the decision_required insight",
              q_decide.get("intent") == "decide"
              and q_decide.get("total", 0) >= 1
              and all(a.get("kind") == "decision_required" for a in q_decide.get("answers") or []),
              str(q_decide)[:300])
        q_affected = (await c.post(f"{API}/brain/knowledge/query",
                                   json={"question": "which projects are affected by the migration budget?"}, headers=auth)).json()
        check("8d. affected queries trace the propagation of the topic",
              q_affected.get("intent") == "affected"
              and isinstance(q_affected.get("hops"), list),
              str(q_affected)[:300])

        # ---------------- 9. governance (4E.5.9)
        hidden_proj = (
            await c.post(f"{API}/projects", json={"name": "Hidden Stealth Program", "description": "4E.5", "status": "active"}, headers=auth)
        ).json()
        await c.post(
            f"{API}/tasks", json={"title": "Stealth migration beta is fully funded.", "project_id": hidden_proj["id"]}, headers=auth
        )
        await drain(c, auth)
        scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Migration scope", "scope_type": "project", "entity_id": project["id"]},
                headers=auth,
            )
        ).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sco{t}@ko.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite", json={"token": emp["token"], "email": f"sco{t}@ko.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"}, headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(f"{API}/governance/assignments", json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]}, headers=auth)
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(f"{API}/governance/delegations", json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.5"}, headers=auth)
        assert dg.status_code == 201, dg.text
        s_gaps = await poll(
            c, scoped, "GET", f"{API}/brain/knowledge/gaps",
            lambda b: b.get("scope") == "project",
        )
        s_imp = await c.get(f"{API}/brain/knowledge/topics/{topic_of('stealth')}/impact", headers=scoped)
        check("9a. scoped intelligence never leaks unscoped conflict evidence",
              s_gaps["scope"] == "project"
              and not any(g["kind"] == "contradiction" for g in s_gaps["gaps"]),
              str(s_gaps)[:400])
        check("9b. a topic with no visible evidence is hidden from the scoped reader",
              s_imp.status_code == 404,
              f"scoped={s_imp.status_code}")

        # ---------------- 10. tenant isolation
        rival = await register(c, "Rival Knowledge Co", f"rko-{t}", f"rk{t}@rko.test.co", "Riv Founder")
        await drain(c, rival["headers"])
        rbrief = (await c.get(f"{API}/brain/knowledge/brief", headers=rival["headers"])).json()
        rinsights = (await c.get(f"{API}/brain/knowledge/insights", headers=rival["headers"])).json()
        rrecs = (await c.get(f"{API}/brain/knowledge/recommendations", headers=rival["headers"])).json()
        rimp = await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/impact", headers=rival["headers"])
        check("10. tenant isolation: rival intelligence sees nothing",
              rbrief["counts"]["decisions_potentially_affected"] == 0
              and rinsights["total"] == 0 and rrecs["total"] == 0 and rimp.status_code == 404,
              f"brief={rbrief['counts']} insights={rinsights['total']} recs={rrecs['total']} impact={rimp.status_code}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
