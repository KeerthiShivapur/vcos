"""Slice 4G.4 acceptance — Universal Resource & Capacity Allocation Intelligence (live API).

Checks against the running stack (http://localhost:8999). The full journey:
real people completing real work create a scarce organizational capability ->
three strategic initiatives (two goals) declare EXPLICIT demands on the same
capability inside one window -> a live conflict -> center/gaps/contention/
traceability/overloads/detail/alternatives/what-if surfaces -> the Universal
Brain routes allocation questions to the capacity intent without stealing
4F.6/4G.3 questions -> governed writes (demands/removals/allocations/outcomes)
update the ledger with reasons -> the same evidence is deterministic and reads
never enqueue events. The engine never moves people or capacity by itself.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
CAP = f"{BRAIN}/execution/capacity"
STRATEGY = f"{BRAIN}/execution/strategy"
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


async def hire(client: httpx.AsyncClient, headers: dict, email: str, first: str, last: str) -> dict:
    r = await client.post(
        f"{API}/employees",
        json={"first_name": first, "last_name": last, "email": email},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def complete_task(client: httpx.AsyncClient, headers: dict, assignee_id: str, title: str) -> None:
    created = await client.post(
        f"{API}/tasks", json={"title": title, "assignee_id": assignee_id, "status": "todo"},
        headers=headers, timeout=60,
    )
    assert created.status_code == 201, created.text
    done = await client.post(
        f"{API}/tasks/{created.json()['id']}/transition",
        json={"status": "completed"}, headers=headers, timeout=60,
    )
    assert done.status_code == 200, done.text


async def project(client: httpx.AsyncClient, headers: dict, name: str, code: str) -> dict:
    r = await client.post(
        f"{API}/projects",
        json={"name": name, "code": code, "status": "active"},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def goal(client: httpx.AsyncClient, headers: dict, title: str, priority: int = 3) -> str:
    r = await client.post(
        f"{STRATEGY}/goals",
        json={"title": title, "kind": "revenue", "priority": priority,
              "metric_kind": "revenue", "metric_unit": "pct",
              "target_value": 25, "current_value": 5,
              "timeline_label": "FY2026"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["goal_id"]


async def objective(client: httpx.AsyncClient, headers: dict, goal_id: str) -> str:
    r = await client.post(
        f"{STRATEGY}/objectives",
        json={"goal_id": goal_id, "title": "Obj"}, headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["objective_id"]


async def initiative(client: httpx.AsyncClient, headers: dict, objective_id: str) -> str:
    r = await client.post(
        f"{STRATEGY}/initiatives",
        json={"objective_id": objective_id, "title": "Init", "required_capabilities": []},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["initiative_id"]


async def link(client: httpx.AsyncClient, headers: dict, initiative_id: str, project_id: str) -> None:
    r = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert r.status_code in (200, 201), r.text


async def demand(client: httpx.AsyncClient, headers: dict, project_id: str, capability: str,
                 units: int, ws: str, we: str, **extra) -> dict:
    body = {"project_id": project_id, "capability": capability, "units": units,
            "window_start": ws, "window_end": we, "proficiency": "high", **extra}
    r = await client.post(f"{CAP}/demands", json=body, headers=headers)
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
        json={"email": email, "full_name": "Scoped Capacity Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Capacity Reader",
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4g.4 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Allocation Co", f"alloc4g4-{t}", f"g4{t}@alloc.co", "Capacity Founder")
        auth = org["headers"]
        ada = await hire(c, auth, f"g4a{t}@alloc.co", "Ada", "Alvarez")
        grace = await hire(c, auth, f"g4b{t}@alloc.co", "Grace", "Mercer")
        await drain(c, auth)

        # -------- 0. real completed work creates ONE scarce capability
        for i in range(6):
            await complete_task(c, auth, ada["id"], f"Kubernetes cluster operations and observability {t}-a{i}")
        for i in range(6):
            await complete_task(c, auth, grace["id"], f"Kubernetes cluster operations and observability {t}-b{i}")
        await drain(c, auth)
        view = await poll(c, auth, "GET", f"{BRAIN}/capabilities/overview",
                          lambda d: any(
                              k["expert_count"] >= 2 and k["capacity_available"] >= 2
                              for k in d["capabilities"]
                          ), timeout=300,
                          tick=lambda: drain(c, auth))
        cap = next(k for k in view["capabilities"]
                   if k["expert_count"] >= 2 and k["capacity_available"] >= 2)
        check("1. real completed work yields a scarce capability with 2 free experts",
              cap["capacity_potential"] == 2 and cap["capacity_committed"] == 0
              and cap["capacity_available"] == 2,
              f"pot={cap.get('capacity_potential')} committed={cap.get('capacity_committed')} "
              f"avail={cap.get('capacity_available')}")
        cap_name = cap["name"]

        # -------- 1. the flagship conflict: three initiatives, one capability
        compliance = await project(c, auth, "Compliance Sprint", f"cpl{t % 9000}")
        pen_blitz = await project(c, auth, "Penetration Blitz", f"pen{t % 9000}")
        zero_trust = await project(c, auth, "Zero Trust", f"ztr{t % 9000}")
        g1 = await goal(c, auth, "GDPR Certification", priority=1)
        g2 = await goal(c, auth, "Security Leadership", priority=2)
        for name, goal_id, units in (
            ("Compliance Sprint", g1, 2),
            ("Penetration Blitz", g2, 2),
            ("Zero Trust", g2, 2),
        ):
            obj = await objective(c, auth, goal_id)
            init = await initiative(c, auth, obj)
            pid = {"Compliance Sprint": compliance["id"],
                   "Penetration Blitz": pen_blitz["id"],
                   "Zero Trust": zero_trust["id"]}[name]
            await link(c, auth, init, pid)
        await drain(c, auth)
        from datetime import date, timedelta
        ws = date.today().isoformat()
        we = (date.today() + timedelta(days=30)).isoformat()
        d1 = await demand(c, auth, compliance["id"], cap_name, 2, ws, we)
        d2 = await demand(c, auth, pen_blitz["id"], cap_name, 2, ws, we)
        d3 = await demand(c, auth, zero_trust["id"], cap_name, 2, ws, we)
        await drain(c, auth)

        center = (await c.get(f"{CAP}/center", headers=auth)).json()
        check("2. the center names the top constraint: demand 6 vs supply 2",
              center["advisory_only"] is True
              and center["top_constraint"]["capability"] == cap_name
              and center["top_constraint"]["gap"] == 4
              and center["top_constraint"]["affected_goals"] == 2
              and center["capability_gaps"] == 1
              and center["critical_bottlenecks"]
              and center["recommendations"][0]["capability"] == cap_name,
              f"top={center.get('top_constraint')} gaps={center.get('capability_gaps')}")

        gaps = (await c.get(f"{CAP}/gaps", headers=auth)).json()
        check("3. gaps quantify the shortage in utilization terms",
              gaps["advisory_only"] is True
              and gaps["current_gaps"][0]["capability"] == cap_name
              and gaps["current_gaps"][0]["utilization"] == 300.0
              and gaps["projection_notice"],
              f"gap={gaps.get('current_gaps', [{}])[0]}")

        contention = (await c.get(f"{CAP}/contention", headers=auth)).json()
        group = contention["groups"][0] if contention["groups"] else {}
        check("4. contention groups the three claimants with their goal stakes",
              contention["advisory_only"] is True
              and contention["contention_count"] == 1
              and group.get("capability") == cap_name
              and len(group.get("claimants", [])) == 3
              and group["claimants"][0]["project_id"] == compliance["id"]
              and group["claimants"][0]["goal_priority"] == 1
              and {s["goal_id"] for s in group.get("strategic_stakes", [])} == {g1, g2},
              f"count={contention.get('contention_count')} group={group}")

        trace = (await c.get(f"{CAP}/traceability", headers=auth)).json()
        by_cap = {x["capability"]: x for x in trace["capabilities"]}
        check("5. traceability ties every demanded unit to a goal",
              trace["advisory_only"] is True
              and by_cap[cap_name]["demand_total"] == 6
              and {g["goal_id"] for g in by_cap[cap_name]["goals"]} == {g1, g2}
              and by_cap[cap_name]["unaligned_units"] == 0,
              f"cap={by_cap.get(cap_name)}")

        overloads = (await c.get(f"{CAP}/overloads", headers=auth)).json()
        check("6. the overloaded-capability advisory surfaces the winner",
              overloads["advisory_only"] is True
              and overloads["capability_overloads"][0]["capability"] == cap_name,
              f"overloads={overloads.get('capability_overloads')}")

        detail = (await c.get(f"{CAP}/capabilities/{cap_name}", headers=auth)).json()
        check("7. capability detail keeps the demand trail on record",
              detail["capability"] == cap_name
              and detail["demand"]["total"] == 6
              and detail["demand"]["project_count"] == 3
              and detail["supply"]["available"] == 2
              and detail["gap"] == 4
              and detail["history"],
              f"demand={detail.get('demand')} supply={detail.get('supply')} gap={detail.get('gap')}")

        alternatives = (await c.get(
            f"{CAP}/alternatives", params={"project_id": pen_blitz["id"]}, headers=auth)).json()
        check("8. alternatives are advisory, bounded, with an explicit decision link",
              alternatives["advisory_only"] is True
              and {o["key"] for o in alternatives["options"]} == {
                  "sequence", "reassign", "external_capability"}
              and alternatives["decision_linkage"]["requires_decision"] is True
              and alternatives["recommendation"],
              f"keys={ {o.get('key') for o in alternatives.get('options', [])} }")

        what_if = (await c.get(
            f"{CAP}/what-if",
            params={"from_project_id": compliance["id"],
                    "to_project_id": pen_blitz["id"],
                    "capability": cap_name, "units": 1},
            headers=auth)).json()
        check("9. what-if re-allocates in-bound and never claims prediction",
              what_if["not_a_prediction"] is True
              and what_if["change"]["units"] == 1
              and what_if["demand_after"][compliance["id"]] == 1
              and what_if["demand_after"][pen_blitz["id"]] == 3
              and what_if["assumptions"]
              and "never moves people" in what_if["bounds"],
              f"after={what_if.get('demand_after')} bounds={what_if.get('bounds')}")

        # -------- 2. the Universal Brain routes allocation questions
        q1 = await ask(c, auth, "which capability is our biggest bottleneck")
        q2 = await ask(c, auth, "which projects contend for the same scarce capability")
        q3 = await ask(c, auth, "where should we allocate capacity")
        q4 = await ask(c, auth, "where are we wasting capacity")
        q5 = await ask(c, auth, "what capability do we need to hire or develop")
        check("10. all five allocation questions route to the capacity intent",
              q1["intent"] == "capacity" and q1["top_constraint"]["capability"] == cap_name
              and q2["intent"] == "capacity" and q2["contention_count"] == 1
              and q3["intent"] == "capacity" and q3["gaps"]["current_gaps"]
              and q4["intent"] == "capacity" and q4["capability_overloads"][0]["capability"] == cap_name
              and q5["intent"] == "capacity" and q5["gaps"]["current_gaps"],
              f"intents={q1.get('intent')},{q2.get('intent')},{q3.get('intent')},"
              f"{q4.get('intent')},{q5.get('intent')}")
        q6 = await ask(c, auth, "are we capacity constrained anywhere")
        check("10b. the 4F.6 question keeps its own intent",
              q6["intent"] not in ("capacity", "") and q6["intent"] != "capacity",
              f"intent={q6.get('intent')}")

        # -------- 3. governed writes: change, remove, allocate, outcome
        updated = await demand(c, auth, zero_trust["id"], cap_name, 4, ws, we,
                               reason="assessment scope doubled")
        assert updated["created"] is False
        await drain(c, auth)
        center = (await c.get(f"{CAP}/center", headers=auth)).json()
        check("11. a governed demand update raises the constraint (8 vs 2)",
              center["top_constraint"]["gap"] == 6,
              f"gap={center.get('top_constraint', {}).get('gap')}")

        removed = await c.post(f"{CAP}/demands/{d3['demand_id']}/remove",
                               json={"reason": "de-scoped after review"}, headers=auth)
        assert removed.status_code == 200, removed.text
        await drain(c, auth)
        center = (await c.get(f"{CAP}/center", headers=auth)).json()
        check("12. removing the demand shrinks the constraint back (4 vs 2)",
              center["top_constraint"]["gap"] == 2,
              f"gap={center.get('top_constraint', {}).get('gap')}")

        allocation = await c.post(
            f"{CAP}/allocations",
            json={"project_id": compliance["id"], "capability": cap_name, "units": 2,
                  "window_start": ws, "window_end": we,
                  "note": "two external Kubernetes contractors"},
            headers=auth,
        )
        assert allocation.status_code == 200, allocation.text
        outcome = await c.post(
            f"{CAP}/allocations/{allocation.json()['allocation_id']}/outcome",
            json={"outcome": "partial", "note": "one onboarded, one delayed"},
            headers=auth,
        )
        assert outcome.status_code == 200, outcome.text
        await drain(c, auth)
        trace = (await c.get(f"{CAP}/traceability", headers=auth)).json()
        by_cap = {x["capability"]: x for x in trace["capabilities"]}
        check("13. the allocation decision is a governed write that leaves demand intact",
              by_cap[cap_name]["demand_total"] == 4,
              f"trace={by_cap.get(cap_name)}")

        # -------- 4. governance: scoped callers never reach org-wide capacity
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Compliance scope", "scope_type": "project",
                                    "entity_id": compliance["id"]},
                              headers=auth)).json()
        scoped = await invite_project_reader(c, auth, scope["id"], f"g4s{t}@alloc.co")
        scoped_center = await c.get(f"{CAP}/center", headers=scoped)
        scoped_write = await c.post(
            f"{CAP}/demands",
            json={"project_id": compliance["id"], "capability": cap_name, "units": 1,
                  "window_start": ws, "window_end": we},
            headers=scoped)
        scoped_q = await ask(c, scoped, "which capability is our biggest bottleneck")
        check("14. scoped callers: capacity reads 404, writes 403, answers are scoped",
              scoped_center.status_code == 404
              and scoped_write.status_code == 403
              and scoped_q.get("scope") == "project",
              f"read={scoped_center.status_code} write={scoped_write.status_code} "
              f"scope={scoped_q.get('scope')}")

        # -------- 5. deterministic on the same evidence; reads never mutate
        await drain(c, auth, rounds=12)
        baseline = await c.get(f"{CAP}/center", headers=auth)
        assert baseline.status_code == 200, baseline.text
        swept = await drain(c, auth, rounds=12)
        center2 = (await c.get(f"{CAP}/center", headers=auth)).json()
        stable = {k: v for k, v in center2.items() if k != "generated_at"}
        first = {k: v for k, v in baseline.json().items() if k != "generated_at"}
        check("15. replay is exact-once and the surfaces stay deterministic",
              stable == first,
              f"swept={swept} deltas={sorted(set(stable) - set(first))}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
