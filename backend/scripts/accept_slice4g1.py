"""Slice 4G.1 acceptance — Project & Execution Intelligence (live API).

Checks against the running stack (http://localhost:8999). The full journey:
real projects/tasks/dependencies through the real API -> durable events ->
the canonical execution record -> deterministic health with primary cause,
real CPM critical path with slack, blocker chains, the "what should happen
next" prioritization, the human-only outcome record, the universal query
routing, and Governance scope separation for the command surfaces.

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
    client: httpx.AsyncClient, headers: dict, method: str, url: str, predicate,
    params: dict | None = None, json: dict | None = None, timeout: float = 120,
) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = await client.request(method, url, headers=headers, params=params, json=json)
        if r.status_code in (200, 201):
            last = r.json()
            if predicate(last):
                return last
        await asyncio.sleep(2)
    return last


async def hire(client: httpx.AsyncClient, headers: dict, email: str, first: str, last: str) -> dict:
    r = await client.post(
        f"{API}/employees",
        json={"first_name": first, "last_name": last, "email": email},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def project(client: httpx.AsyncClient, headers: dict, name: str, code: str) -> dict:
    r = await client.post(
        f"{API}/projects",
        json={"name": name, "code": code, "status": "draft"},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def start_project(client: httpx.AsyncClient, headers: dict, pid: str) -> None:
    r = await client.post(
        f"{API}/projects/{pid}/lifecycle", json={"action": "start"}, headers=headers
    )
    assert r.status_code == 200, r.text


async def task(client: httpx.AsyncClient, headers: dict, project_id: str, title: str,
               estimate_hours: float | None = None, due: str | None = None) -> dict:
    body: dict = {"title": title, "project_id": project_id, "status": "todo"}
    if estimate_hours:
        body["estimate_hours"] = estimate_hours
    if due:
        body["due_date"] = due
    r = await client.post(f"{API}/tasks", json=body, headers=headers, timeout=60)
    assert r.status_code == 201, r.text
    return r.json()


async def depend(client: httpx.AsyncClient, headers: dict, task_id: str, on: str, kind: str = "finish_to_start") -> None:
    r = await client.post(
        f"{API}/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": on, "kind": kind},
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def transition(client: httpx.AsyncClient, headers: dict, task_id: str, status: str) -> None:
    r = await client.post(
        f"{API}/tasks/{task_id}/transition",
        json={"status": status}, headers=headers,
    )
    assert r.status_code == 200, r.text


async def detail(client: httpx.AsyncClient, headers: dict, pid: str) -> dict:
    r = await client.get(f"{BRAIN}/execution/projects/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def ask(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{KNOW}/query", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def invite_project_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Execution Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Execution Reader",
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4g.1 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Execution Co", f"exec4g1-{t}", f"g1{t}@exec.co", "Exec Founder")
        auth = org["headers"]
        await hire(c, auth, f"g1a{t}@exec.co", "Ada", "Lovelace")
        await dispatch(c, auth)

        # -------- 1. change-driven record from REAL API events
        clean = await project(c, auth, "Clean Room", f"clr{t % 9000}")
        await drain(c, auth)
        cmd = (await c.get(f"{BRAIN}/execution/command", headers=auth)).json()
        row = next((r for r in cmd["projects"] if r["project_id"] == clean["id"]), None)
        check("1. project.created fed the command center from the real event stream",
              cmd["total_projects"] == 1 and row is not None
              and row["health_status"] == "healthy" and row["health_score"] == 80
              and "No adverse signals" in row["explain"],
              f"total={cmd.get('total_projects')} status={row and row.get('health_status')}")

        # -------- 2. real tasks + dependencies -> CPM critical path
        p = await project(c, auth, "Atlas Launch", f"atl{t % 9000}")
        await start_project(c, auth, p["id"])
        a = await task(c, auth, p["id"], "A: spec the launch", 4)
        b = await task(c, auth, p["id"], "B: build the payload", 2,
                       due=(time.strftime("%Y-%m-%d", time.localtime(time.time() - 3 * 86400))))
        cc = await task(c, auth, p["id"], "C: launch the atlas", 3)
        await depend(c, auth, b["id"], a["id"])
        await depend(c, auth, cc["id"], b["id"])
        await drain(c, auth)

        execd = await detail(c, auth, p["id"])
        cpath = execd["critical_path"]
        check("2. the real critical path is computed with slack and projected finish",
              cpath["total_hours"] == 9.0 and cpath["min_slack"] == 0.0
              and set(cpath["critical_task_ids"]) == {a["id"], b["id"], cc["id"]}
              and cpath["projected_finish_hours"] == 9.0,
              f"hours={cpath.get('total_hours')} slack={cpath.get('min_slack')}")

        # -------- 3. overdue critical work -> Timeline pressure, deterministic
        check("3. the overdue critical task drives the primary cause and explain",
              execd["primary_cause"] == "Timeline pressure"
              and execd["counts"]["critical_overdue_tasks"] == 1
              and execd["health_score"] < 80
              and "critical-path task(s) past due" in execd["explain"],
              f"cause={execd.get('primary_cause')} score={execd.get('health_score')}")

        # -------- 4. a blocked task on the path -> blocker chain + next action
        await depend(c, auth, cc["id"], a["id"], kind="blocking")
        await transition(c, auth, cc["id"], "blocked")
        await drain(c, auth)
        execd = await detail(c, auth, p["id"])
        check("4. blocker analysis names the root cause chain",
              len(execd["blockers"]) == 1
              and execd["blockers"][0]["task_id"] == cc["id"]
              and execd["blockers"][0]["chain"][-1]["title"] == "A: spec the launch"
              and execd["health_score"] < 80,
              f"blockers={len(execd.get('blockers', []))}")

        # -------- 5. what should happen next, prioritized and bounded
        nxt = (await c.get(f"{BRAIN}/execution/next", headers=auth)).json()
        check("5. execution next prioritizes the overdue critical-path work",
              nxt["total"] >= 1 and any(
                  x["kind"] == "critical" and x["project_name"] == "Atlas Launch"
                  for x in nxt["items"]),
              f"total={nxt.get('total')} kinds={[x['kind'] for x in nxt.get('items', [])]}")

        # -------- 6. the mandatory outcome record: human write, advisory-only
        out = (await c.post(
            f"{BRAIN}/execution/projects/{p['id']}/outcome",
            json={"status": "partial",
                  "planned_outcome": "Ship the atlas payload",
                  "actual_outcome": "Ship the probe only",
                  "assessment": "Blocked by the dependency chain"},
            headers=auth)).json()
        execd = await detail(c, auth, p["id"])
        check("6. the outcome record is written by a human and never rewrites the project",
              out["status"] == "partial" and execd["outcome"]["assessment"] == "Blocked by the dependency chain"
              and execd["status"] == "active",
              f"outcome={execd.get('outcome')}")

        # -------- 7. universal query routing (deterministic)
        q1 = await ask(c, auth, "is the Atlas Launch project on track?")
        q2 = await ask(c, auth, "what should we do next?")
        check("7. the universal query routes execution questions to the execution record",
              q1["intent"] == "execution" and q1["project"]["name"] == "Atlas Launch"
              and q2["intent"] == "execution_next" and q2["total"] >= 1,
              f"intent1={q1.get('intent')} intent2={q2.get('intent')}")

        # -------- 8. governance: org-wide surfaces are org-wide only
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Atlas scope", "scope_type": "project",
                                    "entity_id": p["id"]},
                              headers=auth)).json()
        scoped = await invite_project_reader(c, auth, scope["id"], f"g1s{t}@exec.co")
        cmd_scoped = await c.get(f"{BRAIN}/execution/command", headers=scoped)
        nxt_scoped = await c.get(f"{BRAIN}/execution/next", headers=scoped)
        in_scope = await c.get(f"{BRAIN}/execution/projects/{p['id']}", headers=scoped)
        out_scope = await c.get(f"{BRAIN}/execution/projects/{clean['id']}", headers=scoped)
        check("8. scoped callers: command/next 404, own project visible, others invisible",
              cmd_scoped.status_code == 404 and nxt_scoped.status_code == 404
              and in_scope.status_code == 200 and out_scope.status_code == 404,
              f"cmd={cmd_scoped.status_code} next={nxt_scoped.status_code} "
              f"in={in_scope.status_code} out={out_scope.status_code}")

        # -------- 9. a clean project stays healthy; snapshots keep history
        execd = await detail(c, auth, p["id"])
        history = execd["history"]
        names = {h["event_name"] for h in history}
        check("9. snapshot history answers 'what changed' over time",
              len(history) >= 4 and {"project.started", "task.created",
                                     "task.transitioned", "task.blocked"} <= names,
              f"events={sorted(names)}")

        # -------- 10. replayed events never duplicate records
        before = (await c.get(f"{BRAIN}/execution/projects/{p['id']}", headers=auth)).json()
        again = await drain(c, auth)
        after = (await c.get(f"{BRAIN}/execution/projects/{p['id']}", headers=auth)).json()
        check("10. replay is exact-once: the execution record is stable under replay",
              before["health_score"] == after["health_score"]
              and len(before["history"]) == len(after["history"]),
              f"again={again}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
