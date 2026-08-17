"""Slice 4F.7 acceptance — People Decision Intelligence (live API).

Checks against the running stack (http://localhost:8999). 4F.7 reasons over
the 4F.2..4F.6 evidence substrate: an objective -> required capabilities ->
available people chain ends in an evidence-backed recommendation with
alternatives, trade-offs, confidence and full provenance — never a score,
never an automatic decision. Includes the human-governed lifecycle with
append-only audit, the bounded "what if" simulation, the honest negatives
("why not X"), the alternatives surface, HIGH-tier refusals, project.started
detection, read-only brain queries, and Governance scope separation.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
KNOW = f"{API}/brain/knowledge"
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


async def hire(client: httpx.AsyncClient, headers: dict, email: str, first: str, last: str, **extra) -> dict:
    r = await client.post(
        f"{API}/employees",
        json={"first_name": first, "last_name": last, "email": email, **extra},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def complete_task(client: httpx.AsyncClient, headers: dict, assignee_id: str,
                        title: str, project_id: str | None = None) -> dict:
    body = {"title": title, "assignee_id": assignee_id, "status": "todo"}
    if project_id:
        body["project_id"] = project_id
    created = await client.post(f"{API}/tasks", json=body, headers=headers, timeout=60)
    assert created.status_code == 201, created.text
    task = created.json()
    done = await client.post(
        f"{API}/tasks/{task['id']}/transition",
        json={"status": "completed"}, headers=headers, timeout=60,
    )
    assert done.status_code == 200, done.text
    return task


async def ask(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{KNOW}/query", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def invite_project_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Decision Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Decision Reader",
            "password": "B4DPass123!",
        },
    )
    assert joined.status_code == 201, joined.text
    scoped_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    user_id = joined.json()["user"]["id"]
    await client.post(
        f"{API}/governance/assignments",
        json={"user_id": user_id, "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers,
    )
    assignments = (
        await client.get(f"{API}/governance/assignments", params={"user_id": user_id}, headers=headers)
    ).json()
    org_wide = next(assignment for assignment in assignments if assignment["scope_id"] is None)
    await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        f"{API}/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4f.7 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Decision Co", f"dec4f7-{t}", f"d7{t}@dec.co", "Dec Founder")
        auth = org["headers"]
        oid = org["organization"]["id"]

        ada = await hire(c, auth, f"d7a{t}@dec.co", "Ada", "Lovelace")
        bob = await hire(c, auth, f"d7b{t}@dec.co", "Bob", "Nystrom")
        carol = await hire(c, auth, f"d7c{t}@dec.co", "Carol", "Shaw")
        await dispatch(c, auth)

        # -------- 1. evidence substrate from REAL completed work
        for i in range(7):
            await complete_task(c, auth, ada["id"], f"Deploy the kubernetes cluster hard {i}")
        for i in range(3):
            await complete_task(c, auth, bob["id"], f"Kubernetes rollout and monitoring {i}")
        await complete_task(c, auth, carol["id"], "Kubernetes support rotation")
        await drain(c, auth)
        overview = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                              lambda d: next((k for k in d["capabilities"] if k["name"] == "Kubernetes"),
                                             {}).get("expert_count", 0) >= 3,
                              timeout=180, tick=lambda: dispatch(c, auth))
        kube = next((k for k in overview["capabilities"] if k["name"] == "Kubernetes"), None)
        check("1. the capability substrate is ready: 3 kubernetes experts with evidence",
              kube is not None and kube["expert_count"] == 3 and kube["evidence_count"] >= 11,
              str(kube))

        # -------- 2. brain: who should own? evidence-backed recommendation
        q1 = await ask(c, auth, "who should own the kubernetes platform?")
        rec = q1["recommendation"]
        check("2. 'who should own' routes to people_decision with an evidence-backed recommendation",
              q1["intent"] == "people_decision" and rec["person_id"] and rec["person_label"] == "Ada Lovelace"
              and rec["confidence"] > 0 and "trusted evidence" in rec["rationale"].lower()
              and bool(q1["provenance"]) and q1["provenance"].get("chain"),
              f"intent={q1.get('intent')} person={rec.get('person_label')}")

        # -------- 3. honest negatives: why not Bob?
        q2 = await ask(c, auth, "why not Bob Nystrom?")
        check("3. 'why not X' answers with honest negative evidence, never a score",
              q2["kind"] == "why_not" and q2["person"]["name"] == "Bob Nystrom"
              and "is not recommended because" in q2["answer"],
              f"kind={q2.get('kind')} answer={q2.get('answer', '')[:160]}")

        # -------- 4. bounded what-if, explicitly not a prediction
        q3 = await ask(c, auth, "what if we assign Bob Nystrom to delivery?")
        check("4. the brain what-if is bounded to the decision context, never a prediction",
              q3["kind"] == "what_if" and q3["person"]["name"] == "Bob Nystrom"
              and "not a prediction" in q3["answer"].lower()
              and bool(q3["simulation"]) and "workload" in q3["simulation"]["deltas"],
              f"kind={q3.get('kind')} verdict={q3.get('answer', '')[:160]}")

        # -------- 5. alternatives with trade-offs
        q4 = await ask(c, auth, "what are the alternatives for kubernetes?")
        check("5. alternatives surface with the primary and trade-offs",
              q4["kind"] == "alternatives" and "Primary: Ada Lovelace" in q4["answer"]
              and "Alternative 1:" in q4["answer"],
              f"kind={q4.get('kind')} answer={q4.get('answer', '')[:160]}")

        # -------- 6. brain reads never persist
        q5 = await ask(c, auth, "should we assign Ada to the platform work?")
        listed = (await c.get(f"{BRAIN}/decisions", headers=auth)).json()
        check("6. brain queries are read-only: nothing persisted from 5 questions",
              q5["intent"] == "people_decision" and listed["total"] == 0,
              f"total={listed.get('total')}")

        # -------- 7. governed decision object + lifecycle with append-only audit
        created = (await c.post(
            f"{BRAIN}/decisions",
            json={"decision_type": "staffing",
                  "objective": "Who should staff the kubernetes delivery?",
                  "requirements": ["kubernetes"],
                  "context_type": "org"},
            headers=auth)).json()
        did = created["id"]
        check("7. a people decision is reasoned over immediately with candidates/evidence/provenance",
              created["lifecycle"] == "recommended" and created["risk_tier"] == "medium"
              and created["recommendation"]["person_id"] and len(created["candidates"]) >= 2
              and len(created["evidence"]) >= 1 and bool(created["provenance"]),
              f"state={created.get('lifecycle')} candidates={len(created.get('candidates', []))}")

        for action in ("review", "approve", "execute", "verify"):
            r = await c.post(f"{BRAIN}/decisions/{did}/lifecycle",
                             json={"action": action}, headers=auth)
            assert r.status_code == 200, r.text
        outcome = (await c.post(
            f"{BRAIN}/decisions/{did}/outcome",
            json={"status": "successful", "note": "delivery landed stable"},
            headers=auth)).json()
        actions = [a["action"] for a in outcome["audit"]]
        check("8. the human-governed lifecycle is append-only audited and outcome is recorded",
              outcome["lifecycle"] == "outcome" and outcome["outcome"]["status"] == "successful"
              and actions == ["detected", "evaluated", "recommended",
                              "review", "approve", "execute", "verify", "outcome"],
              str(actions))

        # -------- 8b. Decision -> Outcome -> Learning
        second = (await c.post(
            f"{BRAIN}/decisions",
            json={"decision_type": "staffing",
                  "objective": "Who should staff the next kubernetes release?",
                  "requirements": ["kubernetes"],
                  "context_type": "org"},
            headers=auth)).json()
        combined = " ".join(
            (x["rationale"] or "") + " " + (x["trade_off"] or "") + " " + (x["why_not"] or "")
            for x in second["candidates"]
        )
        check("9. the recorded outcome becomes evidence for the NEXT evaluation",
              "prior recommendation outcomes" in combined,
              f"combined={combined[:160]}")

        # -------- 8c. HIGH-tier people decisions are REFUSED by design
        refused = await c.post(
            f"{BRAIN}/decisions",
            json={"decision_type": "succession",
                  "objective": "Should we promote Ada to director?",
                  "requirements": ["kubernetes"], "risk_tier": "high"},
            headers=auth)
        check("10. HIGH-tier decisions (hiring/promotion/...) stay under human governance",
              refused.status_code == 400 and "human governance" in refused.json()["detail"].lower(),
              f"status={refused.status_code}")

        # -------- 8d. simulated runs are bounded per decision
        for i in range(22):
            target = bob["id"] if i % 2 else carol["id"]
            r = await c.post(f"{BRAIN}/decisions/{did}/what-if",
                             json={"person_id": target}, headers=auth)
            assert r.status_code == 200, r.text
        detail = (await c.get(f"{BRAIN}/decisions/{did}", headers=auth)).json()
        check("11. what-if runs are persisted, bounded (20 cap), newest first",
              len(detail["simulations"]) == 20
              and detail["simulations"][0]["person_id"] == bob["id"],
              f"sims={len(detail['simulations'])}")

        # -------- 9. project.started detects the decision automatically
        project = (await c.post(f"{API}/projects",
                                json={"name": "Neo Payload", "code": f"np{t % 9000}",
                                      "status": "draft"},
                                headers=auth)).json()
        started = await c.post(f"{API}/projects/{project['id']}/lifecycle",
                               json={"action": "start"}, headers=auth)
        assert started.status_code == 200, started.text
        await drain(c, auth)
        detected_list = await poll(
            c, auth, "GET", f"{BRAIN}/decisions",
            lambda d: any(x["context"]["context_type"] == "project"
                          and x["context"]["context_id"] == project["id"]
                          and x["lifecycle"] == "detected"
                          for x in d["decisions"]),
            timeout=120, tick=lambda: dispatch(c, auth))
        check("12. project.started detects a decision in the project context (exact once)",
              any(x["context"]["context_id"] == project["id"] and x["lifecycle"] == "detected"
                  and x["context"]["context_label"] == "Neo Payload"
                  for x in detected_list["decisions"]),
              str([(x["context"]["context_type"], x["lifecycle"])
                   for x in detected_list["decisions"]])[:200])

        # -------- 10. governance: scope separation for decision surfaces
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Payload scope", "scope_type": "project",
                                    "entity_id": project["id"]},
                              headers=auth)).json()
        scoped = await invite_project_reader(c, auth, scope["id"], f"d7s{t}@dec.co")

        org_create = await c.post(f"{BRAIN}/decisions",
                                  json={"decision_type": "staffing",
                                        "objective": "Who should staff kubernetes?",
                                        "requirements": ["kubernetes"],
                                        "context_type": "org"},
                                  headers=scoped)
        scoped_life = await c.post(f"{BRAIN}/decisions/{did}/lifecycle",
                                   json={"action": "reject"}, headers=scoped)
        anchored = (await c.post(
            f"{BRAIN}/decisions",
            json={"decision_type": "staffing",
                  "objective": "Who should staff the new payload delivery?",
                  "requirements": ["kubernetes"],
                  "context_type": "project", "context_id": project["id"]},
            headers=scoped)).json()
        scoped_list = (await c.get(f"{BRAIN}/decisions", headers=scoped)).json()
        check("13. scoped callers: org-wide surfaces 404, writes need employees:manage, "
              "project-anchored decisions work and stay in their own list",
              org_create.status_code == 404 and scoped_life.status_code == 403
              and anchored["id"] and len(scoped_list["decisions"]) == 2
              and scoped_list["decisions"][0]["id"] == anchored["id"]
              and any(d["lifecycle"] == "detected"
                      for d in scoped_list["decisions"]),
              f"create={org_create.status_code} life={scoped_life.status_code} "
              f"visible={len(scoped_list.get('decisions', []))}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))