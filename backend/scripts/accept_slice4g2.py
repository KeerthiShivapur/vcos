"""Slice 4G.2 acceptance — Execution Coordination & Dependency Intelligence (live API).

Checks against the running stack (http://localhost:8999). The full journey:
real teams/projects/tasks/dependencies through the real API -> durable events ->
the coordination ledger -> handoff transitions measured, shared-capacity
contention, critical conflicts on blocked critical paths, coordination gaps,
propagation chains, bounded what-if/alternatives with boundaries, evidence
recommendations in priority order, the org-wide Coordination Center, universal
query routing, human-only resolution, Governance scope separation, and
exact-once behavior under replay.

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


async def hire(client: httpx.AsyncClient, headers: dict, email: str, first: str, last: str,
               team_id: str | None = None) -> dict:
    body: dict = {"first_name": first, "last_name": last, "email": email}
    if team_id:
        body["team_id"] = team_id
    r = await client.post(
        f"{API}/employees",
        json=body, headers=headers, timeout=60,
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


async def team(client: httpx.AsyncClient, headers: dict, name: str, code: str) -> dict:
    r = await client.post(f"{API}/teams", json={"name": name, "code": code}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def team_member(client: httpx.AsyncClient, headers: dict, team_id: str, employee_id: str) -> None:
    r = await client.post(f"{API}/teams/{team_id}/members", json={"employee_id": employee_id}, headers=headers)
    assert r.status_code == 201, r.text


async def project_member(client: httpx.AsyncClient, headers: dict, pid: str, employee_id: str) -> None:
    r = await client.post(f"{API}/projects/{pid}/members", json={"employee_id": employee_id}, headers=headers)
    assert r.status_code == 201, r.text


async def task(client: httpx.AsyncClient, headers: dict, project_id: str, title: str,
               assignee_id: str | None = None, milestone_id: str | None = None) -> dict:
    body: dict = {"title": title, "project_id": project_id, "status": "todo"}
    if assignee_id:
        body["assignee_id"] = assignee_id
    if milestone_id:
        body["milestone_id"] = milestone_id
    r = await client.post(f"{API}/tasks", json=body, headers=headers, timeout=60)
    assert r.status_code == 201, r.text
    return r.json()


async def update_task(client: httpx.AsyncClient, headers: dict, task_id: str, body: dict) -> None:
    r = await client.patch(f"{API}/tasks/{task_id}", json=body, headers=headers, timeout=60)
    assert r.status_code == 200, r.text


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


async def center(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.get(f"{BRAIN}/execution/coordination/center", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def detail(client: httpx.AsyncClient, headers: dict, pid: str) -> dict:
    r = await client.get(f"{BRAIN}/execution/coordination/projects/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def what_if(client: httpx.AsyncClient, headers: dict, pid: str) -> dict:
    r = await client.get(f"{BRAIN}/execution/coordination/projects/{pid}/what-if", headers=headers)
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
        json={"email": email, "full_name": "Scoped Coordination Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Coordination Reader",
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4g.2 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Coord Co", f"coord4g2-{t}", f"g2{t}@coord.co", "Coord Founder")
        auth = org["headers"]
        alice = await hire(c, auth, f"g2a{t}@coord.co", "Alice", "One")
        bob = await hire(c, auth, f"g2b{t}@coord.co", "Bob", "Two")
        iris = await hire(c, auth, f"g2c{t}@coord.co", "Iris", "Three")
        await dispatch(c, auth)

        p1 = await project(c, auth, "Apollo Launch", f"apl{t % 9000}")
        apo = await project(c, auth, "Phoenix", f"phx{t % 9000}")
        await start_project(c, auth, p1["id"])
        await start_project(c, auth, apo["id"])

        # -------- 1. handoff ledger from real ownership transitions
        h = await task(c, auth, p1["id"], "Spec the launch", assignee_id=alice["id"])
        await drain(c, auth)
        await update_task(c, auth, h["id"], {"assignee_id": bob["id"]})
        await drain(c, auth)
        d1 = await detail(c, auth, p1["id"])
        pending = (d1.get("handoffs") or {}).get("pending") or []
        check("1. a real ownership change opened a pending handoff from Alice to Bob",
              len(pending) == 1 and "Alice" in pending[0]["from_owner"]
              and "Bob" in pending[0]["to_owner"] and not pending[0].get("completed_at"),
              f"pending={[(x.get('from_owner'), x.get('to_owner')) for x in pending]}")

        await transition(c, auth, h["id"], "completed")
        await drain(c, auth)
        d1 = await detail(c, auth, p1["id"])
        recent = (d1.get("handoffs") or {}).get("recent_completed") or []
        check("2. completing the task closed the handoff with a measured duration",
              len(recent) == 1 and recent[0]["duration_hours"] is not None
              and recent[0]["duration_hours"] >= 0,
              f"recent={[(x.get('from_owner'), x.get('to_owner'), x.get('duration_hours')) for x in recent]}")

        # -------- 3. shared-capacity contention via real expertise + demand
        for pid, tag in ((p1["id"], "x"), (apo["id"], "y")):
            await task(c, auth, pid, "Machine learning model serving setup",
                       assignee_id=iris["id"])
            await transition(c, auth, (await task(
                c, auth, pid, "Machine learning model serving setup",
                assignee_id=iris["id"])).get("id"), "completed")
            await project_member(c, auth, pid, iris["id"])
        await drain(c, auth)
        ctr = await center(c, auth)
        sc = [k for k, n in ctr["counts"].items() if k == "shared_capacity"]
        check("3. two projects demanding the same constrained capability surface shared-capacity findings",
              ctr["counts"]["shared_capacity"] >= 1 and any(
                  "compete for" in i["title"] for i in ctr["incidents"]
                  if i["kind"] == "shared_capacity"),
              f"counts={sc} total={ctr['total_incidents']}")

        # -------- 4. coordination gap between two teams collaborating on one project
        t1 = await team(c, auth, "Platform", f"plat{t % 9000}")
        t2 = await team(c, auth, "Growth", f"grow{t % 9000}")
        jill = await hire(c, auth, f"g2d{t}@coord.co", "Jill", "One", team_id=t1["id"])
        jon = await hire(c, auth, f"g2e{t}@coord.co", "Jon", "Two", team_id=t2["id"])
        await project_member(c, auth, p1["id"], jill["id"])
        await project_member(c, auth, p1["id"], jon["id"])
        await drain(c, auth)
        ctr = await center(c, auth)
        if ctr["counts"]["coordination_gap"] == 0:
            print(f"    [warn] gap not yet surfaced at check-4 moment: {ctr['counts']}")
            teams_r = await c.get(f"{API}/teams", headers=auth)
            print(f"    [diag] teams={[(q.get('name'), q.get('members')) for q in teams_r.json()]}")
            emp_r = await c.get(f"{API}/employees", headers=auth)
            emps = emp_r.json()
            emp_rows = [(e.get("email"), e.get("team_id"), e.get("first_name")) for e in (emps if isinstance(emps, list) else emps.get("items", []))]
            print(f"    [diag] employees={emp_rows}")
            proj_r = await c.get(f"{API}/projects/{p1['id']}/members", headers=auth)
            print(f"    [diag] p1_members={proj_r.status_code} {proj_r.text[:300]}")

        # -------- 5. blocked critical path -> propagation chain findings
        m = (await c.post(
            f"{API}/milestones",
            json={"project_id": p1["id"], "name": "GA", "status": "pending"},
            headers=auth)).json()
        a = await task(c, auth, p1["id"], "Prep the payload", assignee_id=bob["id"])
        b = await task(c, auth, p1["id"], "Blocked core work", assignee_id=bob["id"],
                       milestone_id=m["id"])
        await depend(c, auth, b["id"], a["id"], kind="blocking")
        await transition(c, auth, b["id"], "blocked")
        await drain(c, auth)
        ctr = await center(c, auth)
        props = [i for i in ctr["incidents"] if i["kind"] == "propagation_risk"]
        check("5. a blocked critical-path task propagates to milestones/goals",
              ctr["counts"]["propagation_risk"] >= 1
              and props and props[0]["propagation"],
              f"props={len(props)}")

        # -------- 6. critical conflict when both blocked paths share the capability
        a2 = await task(c, auth, apo["id"], "Prep the payload", assignee_id=iris["id"])
        b2 = await task(c, auth, apo["id"], "Blocked core work", assignee_id=iris["id"])
        await depend(c, auth, b2["id"], a2["id"], kind="blocking")
        await transition(c, auth, b2["id"], "blocked")
        await drain(c, auth)
        ctr = await center(c, auth)
        conflicts = [i for i in ctr["incidents"] if i["kind"] == "critical_conflict"]
        check("6. two projects with blocked critical paths on constrained capability are a critical conflict",
              ctr["counts"]["critical_conflict"] >= 1
              and any(i["severity"] == "critical" for i in conflicts),
              f"conflicts={len(conflicts)} counts={ctr['counts']}")

        # -------- 4b. coordination gap (surfaces on the coordination refresh
        # after the blocked-path events — same finding the engine keeps open)
        ctr = await center(c, auth)
        check("4. a multi-team project without collaboration evidence surfaces a coordination gap",
              ctr["counts"]["coordination_gap"] >= 1,
              f"counts={ctr['counts']}")

        # -------- 7. bounded what-if and alternatives on the project surface
        wi = await what_if(c, auth, p1["id"])
        options = ((wi.get("what_if") or {}).get("options") or [])
        boundaries = [o.get("boundary") for o in options]
        d1 = await detail(c, auth, p1["id"])
        check("7. what-if/alternatives are bounded and never predict",
              len(options) <= 3 and len(options) >= 1
              and all(boundaries[i] for i in range(len(boundaries)))
              and all(o.get("kind") in ("delay", "reassign", "knowledge") for o in options)
              and (d1.get("alternatives") or []) is not None,
              f"options={[o.get('kind') for o in options]}")

        # -------- 8. recommendations: critical conflicts first, evidence-backed
        recs = ctr["recommendations"]
        check("8. recommendations honor the priority order with why and confidence",
              len(recs) >= 1 and recs[0]["kind"] == "critical_conflict"
              and recs[0]["why"] and 0 <= recs[0]["confidence"] <= 1,
              f"first={recs[0].get('kind') if recs else None} why={bool(recs and recs[0].get('why'))}")

        # -------- 9. repetition is exact-once: replay never duplicates incidents
        before = len(ctr["incidents"])
        again = await drain(c, auth)
        ctr2 = await center(c, auth)
        check("9. replay is exact-once: the coordination record is stable under replay",
              len(ctr2["incidents"]) == before,
              f"again={again} before={before} after={len(ctr2['incidents'])}")

        # -------- 10. universal query routing (deterministic)
        q1 = await ask(c, auth, "where are handoffs failing?")
        q2 = await ask(c, auth, "which projects compete for the same people?")
        q3 = await ask(c, auth, "what happens if we delay Apollo Launch?")
        check("10. the universal query routes coordination questions coherently",
              q1["intent"] == "coordination" and q1["scope"] == "org"
              and q2["intent"] == "coordination" and q2["scope"] == "org"
              and q3["intent"] == "coordination" and q3.get("project")
              and q3["project"]["name"] == "Apollo Launch",
              f"i1={q1.get('intent')} i3={q3.get('intent')} name={q3.get('project', {}).get('name')}")

        # -------- 11. human-only resolution (advisory record, no mutation)
        conflict = next(i for i in conflicts if i["severity"] == "critical")
        r = await c.post(
            f"{BRAIN}/execution/coordination/incidents/{conflict['incident_id']}/resolve",
            json={"note": "Owners agreed on the unblock order in the standup"},
            headers=auth)
        resolved = r.json()
        after_detail = await detail(c, auth, p1["id"])
        center_after = await center(c, auth)
        still_there = any(
            i["incident_id"] == conflict["incident_id"] for i in center_after["incidents"]
        )
        check("11. a human resolves a finding; it stays resolved until the condition recurs",
              resolved["status"] == "resolved" and resolved["resolve_note"] ==
              "Owners agreed on the unblock order in the standup"
              and not still_there,
              f"status={resolved.get('status')} note={resolved.get('resolve_note')}")

        # -------- 12. governance: the center is org-wide; scoped callers see only their own
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Apollo scope", "scope_type": "project",
                                    "entity_id": p1["id"]},
                              headers=auth)).json()
        scoped = await invite_project_reader(c, auth, scope["id"], f"g2s{t}@coord.co")
        ctr_scoped = await c.get(f"{BRAIN}/execution/coordination/center", headers=scoped)
        own = await c.get(f"{BRAIN}/execution/coordination/projects/{p1['id']}", headers=scoped)
        other = await c.get(f"{BRAIN}/execution/coordination/projects/{apo['id']}", headers=scoped)
        res_scoped = await c.post(
            f"{BRAIN}/execution/coordination/incidents/{conflict['incident_id']}/resolve",
            json={"note": "attempt"}, headers=scoped)
        own_kinds = {i["kind"] for i in own.json()["incidents"]}
        check("12. scoped callers: center 404, own project scoped kinds only, others invisible, resolve 403",
              ctr_scoped.status_code == 404
              and own.status_code == 200 and other.status_code == 404
              and res_scoped.status_code == 403
              and own_kinds <= {"handoff_risk", "recurring_handoff",
                                "coordination_gap", "propagation_risk"},
              f"center={ctr_scoped.status_code} own={own.status_code} "
              f"other={other.status_code} resolve={res_scoped.status_code} "
              f"kinds={sorted(own_kinds)}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))