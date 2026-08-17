"""Slice 4F.6 acceptance — Organizational Capability & Capacity Intelligence (live API).

Checks against the running stack (http://localhost:8999). 4F.6 extends the
4F.2 capability substrate: org-level capability records discovered change-
driven from the SAME durable events, deterministic lifecycle (emerging ->
established -> strong), capacity as potential - committed - reserved from
real project/task membership (never fake hour math), demand from active
projects, concentration/gap/single-point advisory signals, integration
counts (ownership/teams/knowledge), governed scoped surfaces, and the Brain
intents including the CEO "can we take this on?" readiness question.

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


async def invite_scoped_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Capability Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Capability Reader",
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4f.6 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Capability Co", f"capco-{t}", f"cap{t}@capco.test.co", "Cap Founder")
        auth = org["headers"]
        oid = org["organization"]["id"]

        dept = (await c.post(f"{API}/departments", json={"name": "Engineering", "code": "eng"}, headers=auth)).json()
        data_team = (await c.post(f"{API}/teams", json={"name": "Data", "code": "data", "department_id": dept["id"]}, headers=auth)).json()
        web_team = (await c.post(f"{API}/teams", json={"name": "Web", "code": "web", "department_id": dept["id"]}, headers=auth)).json()
        ada = await hire(c, auth, f"ada{t}@capco.test.co", "Ada", "Alvarez",
                         team_id=data_team["id"], department_id=dept["id"])
        bo = await hire(c, auth, f"bo{t}@capco.test.co", "Bo", "Mercer",
                        team_id=web_team["id"], department_id=dept["id"])
        await dispatch(c, auth)

        # -------- 1. change-driven discovery: one event -> one capability
        view0 = (await c.get(f"{BRAIN}/capabilities/overview", headers=auth)).json()
        check("1. a fresh org starts with zero capability rows",
              view0["total"] == 0 and view0["capabilities"] == [],
              f"total={view0.get('total')}")
        await complete_task(c, auth, ada["id"], "Deploy the kubernetes cluster hard")
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: d.get("total", 0) >= 1, timeout=180,
                          tick=lambda: dispatch(c, auth))
        kube = next((k for k in view["capabilities"] if k["name"] == "Kubernetes"), None)
        check("2. a task completion creates the capability, emerging with 1 expert",
              kube is not None and kube["lifecycle"] == "emerging"
              and kube["expert_count"] == 1 and kube["evidence_count"] >= 1
              and kube["confidence"] > 0 and "Kubernetes" in kube["explain"],
              f"kube={kube}")

        # -------- 2. evidence-backed detail + explain + integration counts
        detail = (await c.get(f"{BRAIN}/capabilities/{kube['skill_id']}", headers=auth)).json()
        check("3. detail explains every number and never hides factors",
              detail["name"] == "Kubernetes" and detail["confidence"] > 0
              and bool(detail["explain"])
              and bool(detail["factors"])
              and detail["expert_count"] == 1
              and any(e["name"] == "Ada Alvarez" for e in detail["experts"]),
              f"detail={ {k: detail.get(k) for k in ('name','expert_count','confidence')} }")

        # -------- 3. lifecycle climbs with a second expert
        for i in range(5):
            await complete_task(c, auth, bo["id"], f"Kubernetes rollout and monitoring {i}")
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: next((k for k in d["capabilities"] if k["name"] == "Kubernetes"),
                                         {}).get("expert_count", 0) >= 2,
                          timeout=180, tick=lambda: dispatch(c, auth))
        kube = next((k for k in view["capabilities"] if k["name"] == "Kubernetes"), None)
        check("4. a second expert with evidence moves the lifecycle forward",
              kube["expert_count"] == 2
              and kube["lifecycle"] in ("established", "strong")
              and kube["evidence_count"] >= kube["evidence_count"],
              f"lifecycle={kube['lifecycle']} experts={kube['expert_count']}")

        # -------- 4. demand + capacity from real project/task membership
        project = (await c.post(f"{API}/projects",
                                json={"name": "Kube Ops", "code": f"ko{t%1000}", "status": "active"},
                                headers=auth)).json()
        await complete_task(c, auth, ada["id"], "Kubernetes cluster operations", project_id=project["id"])
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: next((k for k in d["capabilities"] if k["name"] == "Kubernetes"),
                                         {}).get("demand_count", 0) >= 1,
                          timeout=180, tick=lambda: dispatch(c, auth))
        kube = next((k for k in view["capabilities"] if k["name"] == "Kubernetes"), None)
        check("5. tasks inside a project create demand (active projects only)",
              kube["demand_count"] == 1 and kube["demand_state"] in ("low", "moderate", "high"),
              f"demand={kube['demand_count']} state={kube['demand_state']}")

        await c.post(f"{API}/projects/{project['id']}/members",
                     json={"employee_id": ada["id"]}, headers=auth)
        await complete_task(c, auth, ada["id"], "Kubernetes monitoring dashboards", project_id=project["id"])
        await c.post(f"{API}/tasks", json={
            "title": "Open kubernetes maintenance", "assignee_id": bo["id"],
            "status": "in_progress", "project_id": project["id"]}, headers=auth)
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: next((k for k in d["capabilities"] if k["name"] == "Kubernetes"),
                                         {}).get("capacity_committed", 0) >= 1,
                          timeout=180, tick=lambda: dispatch(c, auth))
        kube = next((k for k in view["capabilities"] if k["name"] == "Kubernetes"), None)
        p, co, r, av = (kube["capacity_potential"], kube["capacity_committed"],
                        kube["capacity_reserved"], kube["capacity_available"])
        check("6. capacity = potential - committed - reserved (no fake hours)",
              p == 2 and co >= 1 and av == max(p - co - r, 0)
              and kube["capacity_state"] in ("available", "stretched", "constrained"),
              f"p={p} c={co} r={r} a={av} state={kube['capacity_state']}")

        proj_surface = (await c.get(f"{BRAIN}/capabilities/projects/{project['id']}", headers=auth)).json()
        check("7. the project surface names the demand-capabilities",
              any(x["skill_name"] == "Kubernetes" for x in proj_surface["capabilities"])
              and proj_surface["total"] >= 1,
              str(proj_surface)[:200])

        # one expert + demand on a SECOND capability (Docker) so the
        # concentration + single-point advisories exist BEFORE the project
        # completes
        await complete_task(c, auth, ada["id"], "Docker container packaging for production")
        await complete_task(c, auth, ada["id"], "Docker image hardening", project_id=project["id"])
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: next((c for c in d["capabilities"] if c["name"] == "Docker"),
                                         {}).get("expert_count", 0) >= 1,
                          timeout=180, tick=lambda: dispatch(c, auth))
        docker = next((c for c in view["capabilities"] if c["name"] == "Docker"), None)
        check("8. a single-expert capability in demand is concentrated",
              docker["expert_count"] == 1 and docker["concentration_share"] >= 0.6
              and docker["demand_count"] >= 1,
              f"docker={docker}")

        # -------- 6. advisory signals: acknowledged, never auto-mutating
        signals = (await c.get(f"{BRAIN}/capabilities/signals", headers=auth)).json()
        concent = next((s for s in signals["signals"] if s["kind"] == "concentration"), None)
        single = next((s for s in signals["signals"] if s["kind"] == "single_point_dependency"), None)
        check("9. concentration and single-point signals surface from evidence",
              concent is not None and single is not None and signals["total"] >= 2,
              str([s["kind"] for s in signals["signals"]])[:200])
        ack = await c.patch(f"{BRAIN}/capabilities/signals/{single['signal_id']}/acknowledge", headers=auth)
        after_ack = (await c.get(f"{BRAIN}/capabilities/signals", headers=auth)).json()
        check("10. acknowledging a signal is explicit and persistent",
              ack.status_code == 200
              and next((s for s in after_ack["signals"] if s["signal_id"] == single["signal_id"]),
                       {}).get("status") in ("acknowledged", "resolved"),
              f"ack={ack.status_code}")

        # -------- 5. project completion closes demand
        closed = await c.post(f"{API}/projects/{project['id']}/lifecycle",
                              json={"action": "complete"}, headers=auth)
        assert closed.status_code == 200, closed.text
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: next((k for k in d["capabilities"] if k["name"] == "Kubernetes"),
                                         {}).get("demand_count", 1) == 0,
                          timeout=180, tick=lambda: dispatch(c, auth))
        kube = next((k for k in view["capabilities"] if k["name"] == "Kubernetes"), None)
        docker_after = next((c for c in view["capabilities"] if c["name"] == "Docker"), None)
        check("11. completing the project closes its demand",
              kube["demand_count"] == 0 and kube["demand_state"] == "none"
              and docker_after["demand_count"] == 0,
              f"kube={kube['demand_count']} docker={docker_after['demand_count']}")

        # -------- 7. CEO question: evidence-backed readiness, never a guess
        for i in range(6):
            await complete_task(c, auth, ada["id"], f"Python platform delivery work {i}")
        for i in range(6):
            await complete_task(c, auth, bo["id"], f"Python platform delivery work {i}")
        await drain(c, auth)
        ceo = await c.post(f"{BRAIN}/capabilities/initiative",
                           json={"question": "Can we take on this python platform initiative?"},
                           headers=auth)
        assert ceo.status_code == 200, ceo.text
        body = ceo.json()
        py = next((a for a in body["answers"] if a["skill_name"] == "Python"), None)
        check("12. the CEO readiness answer is deterministic and evidence-backed",
              py is not None and py["readiness"] == "ready"
              and py["capacity_available"] >= 1 and body["answer"],
              f"py={py}")

        # -------- 8. brain intents route to the capability surface
        q1 = (await c.post(f"{KNOW}/query",
                           json={"question": "what are we really good at?"}, headers=auth)).json()
        q2 = (await c.post(f"{KNOW}/query",
                           json={"question": "which emerging capabilities are we getting good at?"},
                           headers=auth)).json()
        q3 = (await c.post(f"{KNOW}/query",
                           json={"question": "are we capacity constrained anywhere?"}, headers=auth)).json()
        check("13. capability brain questions route deterministically",
              q1.get("intent") == "capability_strength" and q1.get("total", 0) >= 1
              and "Python" in str(q1.get("answer", ""))
              and q2.get("intent") in ("capability_emerging", "expertise")
              and q3.get("intent") in ("capability_constraint", "expertise"),
              f"q1={q1.get('intent')} q2={q2.get('intent')} q3={q3.get('intent')}")

        # -------- 9. governance: scoped readers 404 on org-wide surfaces
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Data scope", "scope_type": "team",
                                    "entity_id": data_team["id"]}, headers=auth)).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"scop{t}@capco.test.co")
        scoped_overview = await c.get(f"{BRAIN}/capabilities/overview", headers=scoped)
        scoped_detail = await c.get(f"{BRAIN}/capabilities/{kube['skill_id']}", headers=scoped)
        scoped_signals = await c.get(f"{BRAIN}/capabilities/signals", headers=scoped)
        scoped_q = (await c.post(f"{KNOW}/query",
                                 json={"question": "what are we really good at?"},
                                 headers=scoped)).json()
        check("14. scoped callers never reach org-wide capability surfaces",
              scoped_overview.status_code == 404
              and scoped_detail.status_code == 404
              and scoped_signals.status_code == 404
              and scoped_q.get("scope") in ("project", "org"),
              f"ov={scoped_overview.status_code} detail={scoped_detail.status_code} "
              f"sig={scoped_signals.status_code} scope={scoped_q.get('scope')}")

        # -------- 10. reads never mutate: no enqueued signals after reading
        await drain(c, auth, rounds=12)
        before = (await c.get(f"{BRAIN}/capabilities/overview", headers=auth)).json()["total"]
        for url in (f"{BRAIN}/capabilities/overview", f"{BRAIN}/capabilities/signals"):
            r = await c.get(url, headers=auth)
            assert r.status_code == 200, r.text
        swept = await drain(c, auth, rounds=12)
        after = (await c.get(f"{BRAIN}/capabilities/overview", headers=auth)).json()["total"]
        check("15. read paths never fabricate capabilities or enqueue signals",
              swept == 0 and before == after,
              f"swept={swept} before={before} after={after}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))