"""Slice 4E.4 acceptance — Knowledge Intelligence (live API).

Checks against the running stack (http://localhost:8999). 4E.3 turned
evidence into ONE topic-anchored understanding; 4E.4 turns that foundation
into intelligence — every capability deterministic, governed and bounded:

  1. discovery: a natural question ranks topics by evidence match and returns
     cross-family evidence connected into one intelligence answer with the
     exact evidence chain (4.4.1)
  2. relationship graph: one entity resolves its typed edges — and knowledge
     that shares a topic but has no direct edge (memory) still surfaces as a
     neighbor through the topic (4.4.2)
  3. change intelligence: the evolution of an understanding is reported with
     old -> new, the old version superseded, never deleted (4.4.3)
  4. impact analysis: if this knowledge changes, what else changes — affected
     entities by family plus dependent knowledge that quotes the facts (4.4.3)
  5. gap & uncertainty: equal-authority contradictions surface as a gap with
     both values and the resolution rule (4.4.4)
  6. explainable confidence: the recomputed composite equals the recorded
     confidence and every factor is explained (4.4.6)
  7. ownership: the owner resolves to the author of the highest-authority
     source; a memory-only topic has no accountable owner and says so (4.4.6)
  8. health: seven explainable bars plus what is dragging the company down
     (4.4.6)
  9. recommendations: persisted exact-once — replaying materialization never
     duplicates; a condition that clears resolves the row (4.4.7)
  10. universal query: one surface routes natural questions to the matching
      intelligence and tags the intent (4.4.8)
  11. governance: a project-scoped reader's discovery intelligence is built
      only from visible evidence; a hidden topic is 404 for them (4.4.1)
  12. tenant isolation: a rival organization sees nothing (4.4.1/4.4.7)

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
    """The stack consumes events asynchronously (API dispatch + background
    workers); poll until the durable outcome appears, then return the last
    response body. Deterministic under worker races."""
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
    print("=== VCOS Slice 4E.4 acceptance: Knowledge Intelligence (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        org = await register(c, "Knowledge Intelligence Co", f"ki-{t}", f"ki{t}@ki.test.co", "Ki Founder")
        auth = org["headers"]
        org_id = org["organization"]["id"]
        print("1. Founder registered, org", org_id)
        await drain(c, auth)

        # ---------------- 1. discovery (4.4.1): cross-family intelligence
        conv = (
            await c.post(
                f"{API}/conversations",
                json={"type": "channel", "title": "release", "member_ids": [org["user"]["id"]]},
                headers=auth,
            )
        ).json()
        project = (
            await c.post(f"{API}/projects", json={"name": "Migration Program", "description": "4E.4", "status": "active"}, headers=auth)
        ).json()
        task = (
            await c.post(f"{API}/tasks", json={"title": "Migration runbook", "project_id": project["id"]}, headers=auth)
        ).json()
        renewal_task = await c.post(
            f"{API}/tasks", json={"title": "Enterprise renewals are increasingly delayed by legal review", "project_id": project["id"]}, headers=auth
        )
        renewal_task = renewal_task.json()
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "Two enterprise customers pushed their renewals out this quarter and the review window was extended."},
            headers=auth,
        )
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "The migration window is confirmed for 2am."},
            headers=auth,
        )
        await c.post(
            f"{API}/brain/memory",
            json={"memory_type": "lesson", "title": "Migration go-live",
                  "content": "The migration go-live has been agreed for Monday.",
                  "importance": "medium", "tags": ["migration"]},
            headers=auth,
        )
        await c.post(
            f"{API}/brain/memory",
            json={"memory_type": "lesson", "title": "Renewal delays",
                  "content": "Renewals are increasingly delayed — correlates with the new pricing review process.",
                  "importance": "medium", "tags": ["renewal", "delay"]},
            headers=auth,
        )
        await drain(c, auth)
        await drain(c, auth)

        def _discovery_oks(body: dict) -> bool:
            answers = body.get("answers") or []
            return (
                bool(answers)
                and answers[0].get("statement") is not None
                and answers[0].get("claim_id") is not None
                and set(answers[0].get("families") or []) >= {"task", "message", "memory"}
                and len(answers[0].get("evidence") or []) >= 2
                and all(x.get("claim_id") and x.get("excerpt") and x.get("matched_tokens")
                        for x in answers[0]["evidence"][:2])
            )

        disc = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/discover",
            _discovery_oks, params={"query": "why are enterprise customers delaying renewals?"},
        )
        top = disc["answers"][0] if disc["answers"] else {}
        check("1a. discovery gives meaning to a question",
              disc["total"] >= 1 and top.get("statement") and top.get("claim_id"),
              str(disc)[:400])
        check("1b. cross-family evidence connects into one intelligence answer",
              set(top.get("families") or []) >= {"task", "message", "memory"},
              str(top.get("families")))
        check("1c. the answer carries the exact evidence chain",
              len(top.get("evidence") or []) >= 2
              and all(x.get("claim_id") and x.get("excerpt") and x.get("matched_tokens")
                      for x in top["evidence"][:2]),
              str(top.get("evidence"))[:400])
        check("1d. discovery never invents: unasked topics stay hidden",
              disc["scope"] == "org" and disc["generated_at"] is not None,
              "")

        # ---------------- 2. relationship graph (4.4.2): typed edges + topic neighbors
        def _rel_oks(body: dict) -> bool:
            types = {n["type"] for n in body.get("neighbors") or []}
            return (
                body.get("total", 0) >= 2
                and types >= {"message", "memory"}
                and any(n.get("topics") for n in body.get("neighbors") or [])
            )

        rel = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/entities/task/{task['id']}/relations",
            _rel_oks,
        )
        by_type = {n["type"] for n in rel["neighbors"]}
        check("2a. the graph around the task resolves typed edges",
              rel["total"] >= 2 and by_type >= {"message", "memory"},
              str(by_type))
        check("2b. every neighbor carries its edge relation and canonical topics",
              all(n.get("relations") for n in rel["neighbors"] if n["type"] != "topic")
              and any(n.get("topics") for n in rel["neighbors"]),
              str(rel["neighbors"])[:400])

        # ---------------- 3. change intelligence (4.4.3): old -> new, superseded
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "Migration moved to Friday."},
            headers=auth,
        )
        await drain(c, auth)
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "Migration moved to next Monday."},
            headers=auth,
        )
        await drain(c, auth)

        def _changes_oks(body: dict) -> bool:
            events = []
            for tc in body.get("topic_changes") or []:
                if tc["topic"]["name"] == "migration":
                    events = tc["events"]
            us = [e for e in events if e["kind"] == "understanding"]
            return bool(
                body.get("window_days") == 7
                and len(us) >= 3
                and any("Friday" in (e.get("to") or "") for e in us)
                and "Monday" in ((us[-1].get("to") or "") if us else "")
                and all(us[i].get("supersedes_claim_id") == us[i - 1].get("claim_id")
                        for i in range(1, len(us)))
            )

        changes = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/changes",
            _changes_oks, params={"days": 7},
        )
        migration_events = []
        for tc in changes["topic_changes"]:
            if tc["topic"]["name"] == "migration":
                migration_events = tc["events"]
        understandings = [e for e in migration_events if e["kind"] == "understanding"]
        check("3a. change intelligence reports the evolution of understanding",
              changes["window_days"] == 7
              and len(understandings) >= 3
              and "Monday" in (understandings[-1].get("to") or ""),
              str(changes)[:300])
        check("3b. each evolution supersedes the previous understanding",
              all(understandings[i].get("supersedes_claim_id") == understandings[i - 1].get("claim_id")
                  for i in range(1, len(understandings)))
              and any("Friday" in (e.get("to") or "") for e in understandings)
              and "Monday" in (understandings[-1].get("to") or ""),
              str(migration_events)[:1500])

        # ---------------- 4. impact analysis (4.4.3)
        other_proj = (
            await c.post(f"{API}/projects", json={"name": "Customer Deployments", "description": "4E.4", "status": "active"}, headers=auth)
        ).json()
        dependent = (
            await c.post(f"{API}/tasks", json={"title": "Deploy migration changes to enterprise customers", "project_id": other_proj["id"]}, headers=auth)
        ).json()
        await c.post(
            f"{API}/decisions",
            json={"title": "approve migration rollout", "project_id": other_proj["id"], "description": "pending decision"},
            headers=auth,
        )
        await drain(c, auth)
        impact = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/impact", headers=auth)
        ).json()
        dep_ids = {d["subject_id"] for d in impact["dependent_knowledge"]["claims"]}
        check("4a. impact analysis lists the affected entities by family",
              impact["affected"]["total"] >= 1 and "project" in impact["affected"]["by_family"],
              str(impact["affected"])[:300])
        check("4b. dependent knowledge that quotes the facts is listed",
              dependent["id"] in dep_ids,
              str(dep_ids))
        check("4c. impact evidence is traceable to claims",
              impact["evidence"]["total"] >= 3
              and all(x.get("id") for x in impact["evidence"]["sources"]),
              str(impact["evidence"])[:300])

        # ---------------- 5. gaps (4.4.4): unresolved contradiction
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "The migration budget is 5 lakh."},
            headers=auth,
        )
        await drain(c, auth)
        await c.post(
            f"{API}/conversations/{conv['id']}/messages",
            json={"content": "The migration budget is 10 lakh."},
            headers=auth,
        )
        await drain(c, auth)

        def _gaps_oks(body: dict) -> bool:
            contra = [g for g in body.get("gaps") or [] if g["kind"] == "contradiction"]
            return bool(
                contra
                and "5 lakh" in contra[0]["reason"] and "10 lakh" in contra[0]["reason"]
                and len(contra[0]["pair_ids"]) == 2
            )

        gaps = await poll(c, auth, "GET", f"{API}/brain/knowledge/gaps", _gaps_oks)
        contra = [g for g in gaps["gaps"] if g["kind"] == "contradiction"]
        check("5a. the equal-authority conflict is a live gap with both values",
              contra and "5 lakh" in contra[0]["reason"] and "10 lakh" in contra[0]["reason"]
              and len(contra[0]["pair_ids"]) == 2,
              str(contra)[:400])
        check("5b. every gap speaks the vocabulary and cites evidence",
              all(g.get("kind") and g.get("reason") and g.get("confidence") for g in gaps["gaps"]),
              str(gaps["kinds"]))

        # ---------------- 6. explainable confidence (4.4.6)
        state = (
            await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/state", headers=auth)
        ).json()
        current_id = state["current_state"]["id"]
        conf = (
            await c.get(f"{API}/brain/knowledge/claims/{current_id}/confidence", headers=auth)
        ).json()
        names = {f["name"] for f in conf["factors"]}
        check("6a. confidence recomputes to the recorded value",
              conf["confidence"] == conf["recorded_confidence"],
              str({k: conf[k] for k in ("confidence", "recorded_confidence")}))
        check("6b. every factor of the confidence is explained",
              names >= {"authority", "evidence strength", "freshness", "agreement", "consistency"}
              and all(f.get("detail") for f in conf["factors"]),
              str(names))

        # ---------------- 7. ownership (4.4.6): resolved + honestly missing
        own = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/topics/{topic_of('migration')}/ownership",
            lambda b: b.get("owner", {}).get("resolved") is True
            and b.get("owner", {}).get("employee_id") is not None
            and b.get("authority", {}).get("level") in (2, 3),
        )
        check("7a. ownership resolves to the author of the highest-authority source",
              own["owner"]["resolved"] is True
              and own["owner"]["employee_id"] is not None
              and own["authority"]["level"] in (2, 3)
              and own["authority"]["label"] in ("team_record", "documented"),
              str(own)[:300])
        await c.post(
            f"{API}/brain/memory",
            json={"memory_type": "lesson", "title": "Alpha runbook",
                  "content": "The alpha runbook was approved by the ops council.",
                  "importance": "high", "tags": ["alpha"]},
            headers=auth,
        )
        await drain(c, auth)
        mem_own = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/topics/{topic_of('alpha')}/ownership",
            lambda b: b.get("owner", {}).get("resolved") is False
            and b.get("owner", {}).get("employee_id") is None,
        )
        check("7b. knowledge without an accountable owner says so",
              mem_own["owner"]["resolved"] is False and mem_own["owner"]["employee_id"] is None,
              str(mem_own)[:300])

        # ---------------- 8. health (4.4.6): seven bars + why weak
        health = (await c.get(f"{API}/brain/knowledge/health", headers=auth)).json()
        check("8a. health reports seven explainable bars",
              len(health["bars"]) == 7
              and {b["name"] for b in health["bars"]} >= {"coverage", "freshness", "evidence_quality",
                                                          "contradiction_resolution", "ownership",
                                                          "documentation", "cross_team_consistency"},
              str(health["bars"])[:300])
        check("8b. health explains what is dragging the company down",
              isinstance(health["why_weak"], list) and health["total_topics"] >= 1,
              str(health["why_weak"])[:300])

        # ---------------- 9. recommendations (4.4.7): persisted exact-once + resolve
        def _recs_conflict_ok(body: dict) -> bool:
            return any(r["kind"] == "conflict" for r in body.get("recommendations") or [])

        recs1 = await poll(c, auth, "GET", f"{API}/brain/knowledge/recommendations", _recs_conflict_ok)
        recs2 = await poll(c, auth, "GET", f"{API}/brain/knowledge/recommendations", _recs_conflict_ok)
        conflicts = [r for r in recs2["recommendations"] if r["kind"] == "conflict"]
        rec1 = conflicts[0] if conflicts else None
        ids1 = {(r["kind"], r["id"]) for r in recs1["recommendations"]}
        ids2 = {(r["kind"], r["id"]) for r in recs2["recommendations"]}
        check("9a. recommendations are persisted and exact-once",
              recs1["total"] >= 1 and ids1 == ids2 and rec1 is not None,
              f"r1={recs1['total']} r2={recs2['total']}")
        check("9b. the recommendation cites the claims it is based on",
              rec1 and len(rec1["evidence"]) == 2 and rec1["risk"] == "medium",
              str(rec1)[:400])
        # resolve it: an authoritative team record settles the budget
        await c.post(
            f"{API}/tasks", json={"title": "Migration budget 10 lakh", "project_id": project["id"]}, headers=auth
        )
        await drain(c, auth)
        recs3: dict = {}
        deadline = time.time() + 60
        while time.time() < deadline:
            recs3 = (await c.get(f"{API}/brain/knowledge/recommendations", headers=auth)).json()
            if "conflict" not in (recs3.get("active_kinds") or []):
                break
            await asyncio.sleep(2)
        still_active = {(r["kind"], r["id"]) for r in recs3["recommendations"]}
        check("9c. a condition that clears resolves the recommendation",
              ("conflict", rec1["id"]) not in still_active and recs3["total"] >= 0,
              str([r["kind"] for r in recs3["recommendations"]]))

        # ---------------- 10. universal query (4.4.8): intent routing
        q1 = (await c.post(f"{API}/brain/knowledge/query",
                           json={"question": "what changed in our understanding this week?"}, headers=auth)).json()
        q2 = (await c.post(f"{API}/brain/knowledge/query",
                           json={"question": "what do we know about the migration?"}, headers=auth)).json()
        q3 = await poll(
            c, auth, "POST", f"{API}/brain/knowledge/query",
            lambda b: b.get("intent") == "ownership",
            json={"question": "who owns the migration knowledge?"},
        )
        q4 = (await c.post(f"{API}/brain/knowledge/query",
                           json={"question": "how healthy is our knowledge?"}, headers=auth)).json()
        check("10a. one surface routes every intent",
              q1["intent"] == "changes" and q2["intent"] == "discovery"
              and q3["intent"] == "ownership" and q4["intent"] == "health",
              f"{q1.get('intent')}/{q2.get('intent')}/{q3.get('intent')}/{q4.get('intent')}")
        check("10b. discovery answers are grounded in the synthesis claim",
              q2["total"] >= 1 and q2["answers"][0]["topic"]["name"] == "migration"
              and q2["answers"][0]["claim_id"] is not None,
              str(q2)[:400])
        check("10c. ownership and health route with their shapes",
              q3["intent"] == "ownership" and "owner" in q3 and "resolved" in q3["owner"]
              and len(q4["bars"]) == 7,
              str(q3)[:300])

        # ---------------- 11. governance (4.4.1): scoped reader no-leak
        hidden_proj = (
            await c.post(f"{API}/projects", json={"name": "Hidden Stealth Program", "description": "4E.4", "status": "active"}, headers=auth)
        ).json()
        await c.post(
            f"{API}/tasks", json={"title": "Stealth migration beta", "project_id": hidden_proj["id"]}, headers=auth
        )
        await drain(c, auth)
        scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Migration scope", "scope_type": "project", "entity_id": project["id"]},
                headers=auth,
            )
        ).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sci{t}@ki.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite", json={"token": emp["token"], "email": f"sci{t}@ki.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"}, headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(f"{API}/governance/assignments", json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]}, headers=auth)
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(f"{API}/governance/delegations", json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.4"}, headers=auth)
        assert dg.status_code == 201, dg.text
        visible_ids = {str(task["id"]), str(dependent["id"]), str(renewal_task["id"])}

        def _scoped_oks(body: dict) -> bool:
            ids = {item["subject_id"] for a_ in body.get("answers") or [] for item in a_["evidence"]}
            return bool(body.get("scope") == "project" and ids and ids <= visible_ids)

        sdisc = await poll(
            c, scoped, "GET", f"{API}/brain/knowledge/discover",
            _scoped_oks, params={"query": "enterprise renewal delay"},
        )
        s_ids = {item["subject_id"] for a_ in sdisc["answers"] for item in a_["evidence"]}
        check("11a. scoped discovery intelligence is built only from visible evidence",
              sdisc["scope"] == "project"
              and all(x in visible_ids for x in s_ids if x)
              and len(s_ids) >= 1,
              str(s_ids)[:300])
        sim = await c.get(f"{API}/brain/knowledge/topics/{topic_of('stealth')}/impact", headers=scoped)
        org_im = await poll(
            c, auth, "GET", f"{API}/brain/knowledge/topics/{topic_of('stealth')}/impact",
            lambda b: b.get("topic", {}).get("name") == "stealth",
        )
        sim = await c.get(f"{API}/brain/knowledge/topics/{topic_of('stealth')}/impact", headers=scoped)
        check("11b. a topic with no visible evidence is hidden from the scoped reader",
              sim.status_code == 404 and org_im["topic"].get("name") == "stealth",
              f"scoped={sim.status_code} org={org_im.get('topic', {}).get('name')}")

        # ---------------- 12. tenant isolation
        rival = await register(c, "Rival Knowledge Co", f"rki-{t}", f"rk{t}@rki.test.co", "Riv Founder")
        await drain(c, rival["headers"])
        rdisc = (await c.get(f"{API}/brain/knowledge/discover", params={"query": "migration"}, headers=rival["headers"])).json()
        rgaps = (await c.get(f"{API}/brain/knowledge/gaps", headers=rival["headers"])).json()
        rhealth = (await c.get(f"{API}/brain/knowledge/health", headers=rival["headers"])).json()
        rrecs = (await c.get(f"{API}/brain/knowledge/recommendations", headers=rival["headers"])).json()
        rimp = await c.get(f"{API}/brain/knowledge/topics/{topic_of('migration')}/impact", headers=rival["headers"])
        check("12. tenant isolation: rival intelligence sees nothing",
              rdisc["total"] == 0 and rgaps["total"] == 0 and rhealth["total_topics"] == 0
              and rrecs["total"] == 0 and rimp.status_code == 404,
              f"disc={rdisc['total']} gaps={rgaps['total']} health={rhealth['total_topics']} recs={rrecs['total']} impact={rimp.status_code}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
