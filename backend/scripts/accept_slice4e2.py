"""Slice 4E.2 acceptance — Universal Knowledge Ingestion (live API).

Checks against the running stack (http://localhost:8999). The universal
ingestion contract turns every meaningful activity event into exactly one
canonical KnowledgeSource with a claim + primary evidence, governed by the
4E.1 canonical model (temporal supersession, exact-once, tenant isolation,
project-scoped visibility).

  1. conversation message -> canonical message source (candidate claim,
     authority 1, lifecycle validated) with primary evidence; noisy messages
     never become knowledge
  2. task lifecycle -> temporal claim chain: every transition lands, older
     claims are superseded in hop order, the final completed claim is current
  3. meeting completion -> canonical meeting source (status completed)
  4. decision -> canonical decision claim naming the chosen option
  5. memory record -> canonical memory source (validated/active, authority 3)
  6. pattern: repeated project-scoped blocked tasks -> pattern worker detects
     a candidate pattern -> pattern.detected -> canonical pattern source with
     a supported "signals" claim
  7. exact-once: replaying drains and re-running the pattern worker changes
     nothing (no new sources, no new claims, no lifecycle bumps)
  8. bounded reconcile: /brain/knowledge/reconcile processes capped batches
     and reports typed items (entity_type/entity_id)
  9. tenant isolation: a rival organization sees total 0 and source detail 404
 10. governance: a project-scoped brain:read reader sees the anchored task's
     source but never the unanchored message source
 11. registry contract: by_kind is a map of known families, scope is org
 12. vocabulary legality: source lifecycles and claim statuses stay inside the
     model vocabularies, and all families share one canonical shape

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
PASSED: list[str] = []
FAILED: list[str] = []

SOURCE_LIFECYCLES = {"discovered", "extracted", "validated", "active", "updated", "superseded", "archived"}
CLAIM_STATES = {"candidate", "supported", "authoritative", "contested", "superseded"}
FAMILIES = {"message", "task", "meeting", "decision", "memory", "pattern", "document", "policy", "insight", "approval", "risk"}


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


async def drain(client: httpx.AsyncClient, headers: dict, rounds: int = 12) -> None:
    for _ in range(rounds):
        if await dispatch(client, headers) == 0:
            break
        await asyncio.sleep(1)


async def registry(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.get(f"{API}/brain/knowledge", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def source_detail(client: httpx.AsyncClient, headers: dict, source_type: str, source_id: str):
    return await client.get(f"{API}/brain/knowledge/sources/{source_type}/{source_id}", headers=headers)


async def main() -> int:
    t = int(time.time() * 1000) % 10**8
    print("=== VCOS Slice 4E.2 acceptance: Universal Knowledge Ingestion (live) ===")

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        org = await register(c, "Universal Ingest Co", f"ui-{t}", f"uni{t}@ui.test.co", "Una Founder")
        auth = org["headers"]
        org_id = org["organization"]["id"]
        print("1. Founder registered, org", org_id)
        await drain(c, auth)

        # ---- 1. message (meaningful vs noise) ----
        conv = (
            await c.post(
                f"{API}/conversations",
                json={"type": "channel", "title": "war-room", "member_ids": [org["user"]["id"]]},
                headers=auth,
            )
        ).json()
        noise = (
            await c.post(
                f"{API}/conversations/{conv['id']}/messages",
                json={"content": "Cutover is 9pm."},
                headers=auth,
            )
        ).json()
        msg = (
            await c.post(
                f"{API}/conversations/{conv['id']}/messages",
                json={"content": "The production migration has been moved to Friday."},
                headers=auth,
            )
        ).json()
        await drain(c, auth)
        mdetail = (await source_detail(c, auth, "message", msg["id"])).json()
        mclaim = mdetail["claims"][0]
        nres = await source_detail(c, auth, "message", noise["id"])
        check("1. meaningful message becomes a canonical source",
              mdetail["source"]["source_type"] == "message" and mdetail["source"]["source_id"] == msg["id"]
              and mdetail["source"]["lifecycle"] == "active" and mdetail["source"]["source_status"] == "sent"
              and mdetail["source"]["authority_level"] == 1, str(mdetail)[:300])
        check("1b. message claim is a candidate statement with primary evidence",
              mclaim["claim_type"] == "statement" and mclaim["predicate"] == "stated"
              and "moved to Friday" in mclaim["object_text"]
              and mclaim["status"] == "candidate" and mclaim["authority_level"] == 1
              and len(mclaim["evidence"]) == 1 and mclaim["evidence"][0]["role"] == "primary",
              str(mclaim)[:300])
        check("1c. message noise never becomes knowledge",
              nres.status_code == 404, f"status={nres.status_code}")

        # ---- 2. task temporal chain ----
        task = (
            await c.post(f"{API}/tasks", json={"title": "Backfill ledger", "description": "Reconcile June."}, headers=auth)
        ).json()
        for st in ("in_progress", "blocked", "completed"):
            r = await c.post(f"{API}/tasks/{task['id']}/transition", json={"status": st}, headers=auth)
            assert r.status_code == 200, r.text
        await drain(c, auth)
        tdetail = (await source_detail(c, auth, "task", task["id"])).json()
        tclaims = tdetail["claims"]  # newest first (valid_from.desc)
        live_statuses = []
        for cl in tclaims:
            live_statuses.append(cl["object_text"].split("status=")[-1])
        superseded_idx = [i for i, cl in enumerate(tclaims) if cl["status"] == "superseded"]
        current_idx = [i for i, cl in enumerate(tclaims) if cl["status"] in ("candidate", "supported")]
        hop_ok = all(
            tclaims[i]["superseded_by"] == tclaims[i - 1]["id"] and tclaims[i]["valid_to"] is not None
            for i in range(1, len(tclaims))
        )
        check("2. every task event lands one claim on one canonical source",
              len(tclaims) == 4 and live_statuses == ["completed", "blocked", "in_progress", "backlog"]
              and tdetail["source"]["lifecycle"] == "updated", str(tclaims)[:400])
        check("2b. supersession is hop-chained, final claim is current",
              len(superseded_idx) == 3 and len(current_idx) == 1
              and tclaims[current_idx[0]]["object_text"].endswith("status=completed")
              and tclaims[current_idx[0]]["valid_to"] is None and tclaims[current_idx[0]]["superseded_by"] is None
              and hop_ok, str(tclaims)[:400])

        # ---- 3. meeting completion ----
        meeting = (
            await c.post(f"{API}/meetings", json={"title": "Cutover walkthrough", "meeting_type": "team"}, headers=auth)
        ).json()
        assert (await c.post(f"{API}/meetings/{meeting['id']}/complete", headers=auth)).status_code == 200
        await drain(c, auth)
        md2 = (await source_detail(c, auth, "meeting", meeting["id"])).json()
        mc = md2["claims"][0]
        check("3. completed meeting becomes canonical knowledge",
              md2["source"]["authority_level"] == 2
              and mc["claim_type"] == "fact" and mc["predicate"] == "occurred"
              and "status=completed" in mc["object_text"], str(md2)[:300])

        # ---- 4. decision ----
        decision = (
            await c.post(
                f"{API}/decisions",
                json={"title": "Pick queue", "context": "Messaging.", "content": "Evaluate.",
                      "options": [{"title": "Redis"}, {"title": "SQS"}], "participants": []},
                headers=auth,
            )
        ).json()
        options = (await c.get(f"{API}/decisions/{decision['id']}/options", headers=auth)).json()
        assert (await c.post(
            f"{API}/decisions/{decision['id']}/choose",
            json={"option_id": options[1]["id"], "reason": "Managed"},
            headers=auth,
        )).status_code == 200
        await drain(c, auth)
        dd = (await source_detail(c, auth, "decision", decision["id"])).json()
        check("4. decision claim names the chosen option",
              dd["source"]["authority_level"] >= 4 and "SQS" in dd["claims"][-1]["object_text"],
              str(dd)[:300])

        # ---- 5. memory ----
        mem = (
            await c.post(
                f"{API}/brain/memory",
                json={"memory_type": "lesson", "title": "Staging flakiness",
                      "content": "E2E suite fails every Monday.", "importance": "medium"},
                headers=auth,
            )
        ).json()
        await drain(c, auth)
        mdetail = (await source_detail(c, auth, "memory", mem["id"])).json()
        mclaim = mdetail["claims"][0]
        check("5. memory record lands a validated active source",
              mdetail["source"]["lifecycle"] == "validated" and mdetail["source"]["source_status"] == "active"
              and mdetail["source"]["authority_level"] == 3 and mclaim["predicate"] == "remembers"
              and mclaim["status"] == "supported" and mclaim["authority_level"] == 3,
              str(mdetail)[:300])

        # ---- 6. pattern: repeated blocked tasks in a project ----
        me = (await c.get(f"{API}/employees/me", headers=auth)).json()["id"]
        proj = (
            await c.post(f"{API}/projects", json={"name": "Cutover Project", "description": "Slice 4E.2 anchor", "status": "active"}, headers=auth)
        ).json()
        ptask = (
            await c.post(
                f"{API}/tasks",
                json={"title": "Database migration", "project_id": proj["id"], "assignee_id": me},
                headers=auth,
            )
        ).json()
        await c.post(f"{API}/tasks/{ptask['id']}/transition", json={"status": "in_progress"}, headers=auth)
        await c.post(f"{API}/tasks/{ptask['id']}/transition", json={"status": "blocked"}, headers=auth)
        await c.post(f"{API}/tasks/{ptask['id']}/transition", json={"status": "blocked"}, headers=auth)
        await drain(c, auth, rounds=6)
        run = await c.post(f"{API}/intelligence/workers/pattern/run", headers=auth)
        assert run.status_code == 200, run.text
        patterns_raw = (await c.get(f"{API}/intelligence/patterns", headers=auth)).json()
        patterns = patterns_raw if isinstance(patterns_raw, list) else patterns_raw.get("patterns", patterns_raw.get("items", []))
        await drain(c, auth, rounds=6)
        check("6. pattern worker detects a candidate pattern from repeats",
              len(patterns) >= 1 and patterns[0]["status"] in ("candidate", "emerging")
              and patterns[0]["count"] >= 2, str(patterns)[:300])
        pat = patterns[0]
        pdetail = (await source_detail(c, auth, "pattern", pat["id"])).json()
        pclaim = pdetail["claims"][0]
        check("6b. pattern event makes a canonical supported source",
              pdetail["source"]["lifecycle"] == "validated" and pdetail["source"]["source_status"] == "candidate"
              and pdetail["source"]["authority_level"] == 3 and pdetail["source"]["source_id"] == pat["id"]
              and pclaim["claim_type"] == "pattern" and pclaim["predicate"] == "signals"
              and pclaim["status"] == "supported", str(pdetail)[:300])

        # ---- 7. exact-once: replay changes nothing ----
        reg0 = await registry(c, auth)
        total0, n_claims0 = reg0["total"], sum(reg0["by_status"].values())
        await drain(c, auth, rounds=4)
        await drain(c, auth, rounds=4)
        await c.post(f"{API}/intelligence/workers/pattern/run", headers=auth)
        await drain(c, auth, rounds=6)
        reg1 = await registry(c, auth)
        n_claims1 = sum(reg1["by_status"].values())
        changed = reg0["by_kind"] != reg1["by_kind"] or total0 != reg1["total"] or n_claims0 != n_claims1
        check("7. exact-once: replay is a no-op",
              not changed and reg1["by_status"].get("validated", 0) >= 1,
              f"before={reg0['by_kind']} after={reg1['by_kind']}")

        # ---- 8. bounded reconcile ----
        rec = (await c.post(f"{API}/brain/knowledge/reconcile", json={"limit": 5}, headers=auth)).json()
        check("8. reconcile is bounded, capped and typed",
              rec["processed"] <= 5 and rec["processed"] == len(rec["items"])
              and all(set(item) <= {"entity_type", "entity_id", "lifecycle", "status"} for item in rec["items"]),
              str(rec)[:300])

        # ---- 9. tenant isolation ----
        rival = await register(c, "Rival Universal Co", f"ru-{t}", f"riv{t}@ru.test.co", "Riv Founder")
        await drain(c, rival["headers"])
        rreg = (await registry(c, rival["headers"]))
        rhidden = await source_detail(c, rival["headers"], "task", task["id"])
        check("9. tenant isolation",
              rreg["total"] == 0 and rhidden.status_code == 404,
              f"reg={rreg['total']} detail={rhidden.status_code}")

        # ---- 10. governance: scoped reader ----
        scope = (
            await c.post(
                f"{API}/governance/scopes",
                json={"name": "Cutover scope", "scope_type": "project", "entity_id": proj["id"]},
                headers=auth,
            )
        ).json()
        emp = (await c.post(f"{API}/users/invite", json={"email": f"sc{t}@ui.test.co", "role": "manager", "full_name": "Scoped Mgr"}, headers=auth)).json()
        joined = (await c.post(f"{API}/auth/register/invite", json={"token": emp["token"], "email": f"sc{t}@ui.test.co", "full_name": "Scoped Mgr", "password": "StrongPass123!"}, headers=auth)).json()
        scoped = {"Authorization": f"Bearer {joined['access_token']}"}
        roles = (await c.get(f"{API}/roles", headers=auth)).json()
        manager_role = next(r for r in roles if r["code"] == "manager")
        a = await c.post(f"{API}/governance/assignments", json={"user_id": joined["user"]["id"], "role_id": manager_role["id"], "scope_id": scope["id"]}, headers=auth)
        assert a.status_code == 201, a.text
        assignments = (await c.get(f"{API}/governance/assignments", params={"user_id": joined["user"]["id"]}, headers=auth)).json()
        org_wide = next(x for x in assignments if x.get("scope_id") is None)
        assert (await c.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=auth)).status_code == 200
        dg = await c.post(f"{API}/governance/delegations", json={"granted_to_user": joined["user"]["id"], "permission_code": "brain:read", "reason": "slice 4e.2"}, headers=auth)
        assert dg.status_code == 201, dg.text
        sreg = (await registry(c, scoped))
        s_anchored = await source_detail(c, scoped, "task", ptask["id"])
        s_unanchored = await source_detail(c, scoped, "message", msg["id"])
        check("10. scoped reader sees anchored work, never unanchored messages",
              sreg["total"] >= 1 and sreg["scope"] == "project"
              and s_anchored.status_code == 200 and s_unanchored.status_code == 404,
              f"reg={sreg['total']} task={s_anchored.status_code} message={s_unanchored.status_code}")

        # ---- 11. registry contract ----
        check("11. registry families are known canonical families",
              set(reg1["by_kind"]) <= FAMILIES and reg1["scope"] == "org", str(reg1["by_kind"]))

        # ---- 12. vocabulary legality across every family ----
        vocab_ok = True
        for stype, sid in (("message", msg["id"]), ("task", task["id"]), ("meeting", meeting["id"]),
                           ("memory", mem["id"]), ("pattern", pat["id"])):
            det = (await source_detail(c, auth, stype, sid)).json()
            if det["source"]["lifecycle"] not in SOURCE_LIFECYCLES:
                vocab_ok = False
            for cl in det["claims"]:
                if cl["status"] not in CLAIM_STATES:
                    vocab_ok = False
        check("12. canonical vocabularies respected across all live families", vocab_ok)

        # ---- 13. one internal language: uniform shape per family ----
        shape_ok = True
        checks = {
            "message": (msg["id"], "stated"), "task": (task["id"], "status"),
            "meeting": (meeting["id"], "occurred"), "memory": (mem["id"], "remembers"),
            "pattern": (pat["id"], "signals"),
        }
        for stype, (sid, pred) in checks.items():
            det = (await source_detail(c, auth, stype, sid)).json()
            if "claims" not in det or det["claims"][0]["predicate"] != pred:
                shape_ok = False
        check("13. every family speaks the same canonical claim shape", shape_ok)

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))