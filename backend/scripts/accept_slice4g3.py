"""Slice 4G.3 acceptance — Strategic Portfolio & Goal Execution Intelligence (live API).

Checks against the running stack (http://localhost:8999). The full journey:
real people/projects/tasks/dependencies through the real API -> durable events ->
execution health -> a live goal/objective/initiative chain -> coverage with
capability + capacity factors -> temporal priority history -> alignment tiers and
strategic gaps -> bounded delay impact down the chain -> bounded what-if priority
re-ranking -> advisory alternatives with a recommendation -> outcome learning
with an over-optimism verdict -> portfolio surfaces with focus and confidence ->
universal query routing -> org-wide surfaces protected by Governance scopes ->
and exact-once behavior under replay. The engine never mutates projects or goals.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
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


async def project_member(client: httpx.AsyncClient, headers: dict, pid: str, employee_id: str) -> None:
    r = await client.post(f"{API}/projects/{pid}/members", json={"employee_id": employee_id}, headers=headers)
    assert r.status_code == 201, r.text


async def task(client: httpx.AsyncClient, headers: dict, project_id: str, title: str,
               assignee_id: str | None = None) -> dict:
    body: dict = {"title": title, "project_id": project_id, "status": "todo"}
    if assignee_id:
        body["assignee_id"] = assignee_id
    r = await client.post(f"{API}/tasks", json=body, headers=headers, timeout=60)
    assert r.status_code == 201, r.text
    return r.json()


async def depend(client: httpx.AsyncClient, headers: dict, task_id: str, on: str, kind: str = "blocking") -> None:
    r = await client.post(
        f"{API}/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": on, "kind": kind},
        headers=headers,
    )
    assert r.status_code == 201, r.text


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


async def objective(client: httpx.AsyncClient, headers: dict, goal_id: str,
                    title: str = "Conversion", caps: list[str] | None = None) -> str:
    r = await client.post(
        f"{STRATEGY}/objectives",
        json={"goal_id": goal_id, "title": title,
              "required_capabilities": caps or []},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["objective_id"]


async def initiative(client: httpx.AsyncClient, headers: dict, objective_id: str,
                     title: str = "Platform 3.0", expected: dict | None = None,
                     commitments: list[dict] | None = None) -> str:
    r = await client.post(
        f"{STRATEGY}/initiatives",
        json={"objective_id": objective_id, "title": title,
              "required_capabilities": [],
              "expected_outcome": expected,
              "customer_commitments": commitments or []},
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


async def detail(client: httpx.AsyncClient, headers: dict, goal_id: str) -> dict:
    r = await client.get(f"{STRATEGY}/goals/{goal_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def portfolio(client: httpx.AsyncClient, headers: dict) -> dict:
    r = await client.get(f"{STRATEGY}/portfolio", headers=headers)
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
        json={"email": email, "full_name": "Scoped Strategy Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Strategy Reader",
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "4g.3 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Strategic Co", f"strat4g3-{t}", f"g3{t}@strat.co", "Strategy Founder")
        auth = org["headers"]
        ada = await hire(c, auth, f"g3a{t}@strat.co", "Ada", "Lovelace")
        grace = await hire(c, auth, f"g3b{t}@strat.co", "Grace", "Hopper")
        linus = await hire(c, auth, f"g3c{t}@strat.co", "Linus", "Torvalds")
        await dispatch(c, auth)

        # -------- 0. a clean active project with real tasks -> execution health 80
        apollo = await project(c, auth, "Apollo Launch", f"apl{t % 9000}")
        zeus = await project(c, auth, "Zeus Adapter", f"zeu{t % 9000}")
        await start_project(c, auth, apollo["id"])
        await start_project(c, auth, zeus["id"])
        await project_member(c, auth, apollo["id"], ada["id"])
        await project_member(c, auth, apollo["id"], grace["id"])
        core = await task(c, auth, apollo["id"], "core engine")
        zeus_task = await task(c, auth, zeus["id"], "zeus adapter")
        await depend(c, auth, zeus_task["id"], core["id"])
        await drain(c, auth)

        # -------- 1. strategy chain from real events, coverage with factors
        g1 = await goal(c, auth, "Enterprise Revenue +25%", priority=3)
        obj1 = await objective(c, auth, g1)
        init1 = await initiative(
            c, auth, obj1,
            expected={"metric_kind": "retention", "target_value": 8, "unit": "pct"},
            commitments=[{"customer": "ACME", "summary": "Enterprise launch by Q3"}],
        )
        await link(c, auth, init1, apollo["id"])
        await drain(c, auth)
        pf = await portfolio(c, auth)
        check("1. a live chain lands a 90 coverage (execution 0.4 + capability 0.3 + capacity 0.2)",
              pf["advisory_only"] is True
              and pf["mean_goal_coverage"] == 90
              and pf["health_summary"]["total"] == 1 and pf["health_summary"]["healthy"] == 1
              and pf["focus"][0]["goal_id"] == g1 and pf["focus"][0]["why"]
              and pf["alignment"]["direct"] == 1 and pf["alignment"]["none"] == 1
              and pf["alignment"]["total_active_projects"] == 2
              and pf["confidence"]["outcome_samples"] == 0,
              f"cov={pf.get('mean_goal_coverage')} health={pf.get('health_summary')} "
              f"focus={[f.get('goal_id') for f in pf.get('focus', [])]} "
              f"align={pf.get('alignment')}")

        pf2 = await portfolio(c, auth)
        stable = {k: v for k, v in pf2.items() if k != "generated_at"}
        first = {k: v for k, v in pf.items() if k != "generated_at"}
        check("1b. the portfolio is deterministic on the same evidence",
              stable == first, f"deltas={sorted(set(stable) - set(first))}")

        d = await detail(c, auth, g1)
        check("2. goal detail explains the score with factors, history and people",
              d["coverage"] == 90 and d["factors"]["execution"] == 0.8
              and d["factors"]["capability"] == 1.0 and d["factors"]["capacity"] == 1.0
              and d["primary_reason"] and d["health"] == "healthy"
              and any(h["field"] == "created" for h in d["history"])
              and d["projects"][0]["health_score"] == 80 and d["people"],
              f"cov={d.get('coverage')} factors={d.get('factors')} "
              f"hist={[h.get('field') for h in d.get('history', [])]} "
              f"health={d.get('projects', [{}])[0].get('health_score')}")

        # -------- 3. alignment tiers and strategic gaps
        g2 = await goal(c, auth, "International Expansion", priority=3)
        obj2 = await objective(c, auth, g2, caps=["localization"])
        init2 = await initiative(c, auth, obj2)
        await drain(c, auth)
        gaps = (await c.get(f"{STRATEGY}/gaps", headers=auth)).json()
        zeus_rows = [g for g in gaps["unaligned_projects"] if g["project_id"] == zeus["id"]]
        check("4. a live project without a link is an unaligned gap with a reason",
              len(zeus_rows) == 1 and zeus_rows[0]["alignment"] == "none"
              and "no explicit relationship" in zeus_rows[0]["reason"]
              and g2 in [u["goal_id"] for u in gaps["under_covered_goals"]],
              f"unaligned={[(g.get('project_id'), g.get('alignment')) for g in gaps.get('unaligned_projects', [])]} "
              f"under={[u.get('goal_id') for u in gaps.get('under_covered_goals', [])]}")

        # -------- 3b. a second goal at risk from real blockers, a third healthy
        g2p = await project(c, auth, "Expansion Ops", f"exp{t % 9000}")
        await start_project(c, auth, g2p["id"])
        await project_member(c, auth, g2p["id"], linus["id"])
        prev = await task(c, auth, g2p["id"], "base task")
        for i in range(5):
            b = await task(c, auth, g2p["id"], f"blocked {i + 1}")
            await depend(c, auth, b["id"], prev["id"])
            prev = b
        await link(c, auth, init2, g2p["id"])
        g3 = await goal(c, auth, "Regional Push", priority=2)
        obj3 = await objective(c, auth, g3)
        init3 = await initiative(c, auth, obj3)
        g3p = await project(c, auth, "Regional Work", f"reg{t % 9000}")
        await start_project(c, auth, g3p["id"])
        await project_member(c, auth, g3p["id"], grace["id"])
        await link(c, auth, init3, g3p["id"])
        await drain(c, auth)

        pf = await portfolio(c, auth)
        ranks = {f["goal_id"]: i for i, f in enumerate(pf["focus"])}
        check("4b. focus leads with the at-risk P1, then healthy P2, then healthy P3",
              ranks[g2] < ranks[g3] < ranks[g1]
              and any("priority" in w for w in pf["focus"][ranks[g2]]["why"])
              and any("coverage" in w for w in pf["focus"][ranks[g2]]["why"]),
              f"ranks={ranks}")

        # -------- 4. bounded what-if: priority re-ranking
        wi = (await c.get(
            f"{STRATEGY}/what-if", params={"goal_id": g1, "priority": 1},
            headers=auth)).json()
        check("5. what-if is bounded, never a prediction, and shows the re-rank",
              wi["not_a_prediction"] is True
              and wi["change"]["type"] == "priority"
              and wi["change"]["goal_id"] == g1
              and wi["rank_after"] < wi["rank_before"]
              and wi["assumptions"],
              f"rank {wi.get('rank_before')} -> {wi.get('rank_after')} "
              f"change={wi.get('change')}")

        # -------- 4b. temporal priority memory, exact-once history
        changed = await c.post(
            f"{STRATEGY}/goals/{g1}/priority",
            json={"priority": 1, "reason": "board escalation"},
            headers=auth,
        )
        assert changed.status_code == 200, changed.text
        await drain(c, auth)
        d = await detail(c, auth, g1)
        fields = [(h["field"], h.get("old_value"), h.get("new_value"), h.get("reason"))
                  for h in d["history"]]
        check("5b. a real priority change is temporal history with the reason kept",
              changed.json()["changed"] is True
              and ("priority", "3", "1", "board escalation") in fields
              and len([f for f, *_ in fields if f == "created"]) >= 1,
              f"hist={fields}")
        pf = await portfolio(c, auth)
        ranks = {f["goal_id"]: i for i, f in enumerate(pf["focus"])}
        check("5c. the same evidence re-ranks focus after the real priority change",
              ranks[g1] == 1,
              f"ranks={ranks}")

        # -------- 5. bounded delay impact down the chain
        imp = (await c.get(
            f"{STRATEGY}/impact", params={"project_id": apollo["id"], "delay_days": 14},
            headers=auth)).json()
        chain = {s["goal_id"]: s for s in imp["strategic_chain"]}
        check("6. a 14-day delay lowers goal coverage and carries commitments downstream",
              any(p["project_id"] == zeus["id"] for p in imp["downstream_projects"])
              and imp["downstream_count"] >= 1
              and imp["portfolio_projects_affected"] >= 2
              and g1 in chain
              and chain[g1]["coverage_simulated"] < chain[g1]["coverage_now"]
              and chain[g1]["customer_commitments"][0]["customer"] == "ACME"
              and imp["bounds"] and imp["risk"] in ("high", "medium"),
              f"sim={chain[g1].get('coverage_simulated')} "
              f"now={chain[g1].get('coverage_now')} risk={imp.get('risk')} "
              f"downstream={[p.get('project_id') for p in imp.get('downstream_projects', [])]}")

        # -------- 6. advisory alternatives with a recommendation
        alt = (await c.get(
            f"{STRATEGY}/alternatives", params={"project_id": apollo["id"]},
            headers=auth)).json()
        keys = {o["key"] for o in alt["options"]}
        check("7. alternatives are advisory, bounded to three options, with a recommendation",
              alt["advisory_only"] is True and len(alt["options"]) == 3
              and keys == {"keep_scope", "reduce_scope", "add_external_capability"}
              and alt["recommendation"]
              and "open_decisions" in alt["decision_linkage"],
              f"keys={keys} rec={bool(alt.get('recommendation'))}")

        # -------- 7. outcome learning: a closed assumption with a verdict
        rec = await c.post(
            f"{STRATEGY}/initiatives/{init1}/outcome",
            json={"metric_kind": "retention", "unit": "pct",
                  "expected_value": 8, "actual_value": 2},
            headers=auth,
        )
        assert rec.status_code == 200, rec.text
        await drain(c, auth)
        d = await detail(c, auth, g1)
        check("8. the closed assumption lands in goal detail with an over-optimism verdict",
              d["learning"] and d["learning"][0]["verdict"] == "over-optimistic"
              and d["learning"][0]["metric_kind"] == "retention"
              and d["outcomes"][0]["expected_value"] == 8,
              f"verdict={d.get('learning', [{}])[0].get('verdict')} "
              f"outcomes={[(o.get('expected_value'), o.get('actual_value')) for o in d.get('outcomes', [])]}")

        # -------- 8. universal query routing
        q1 = await ask(c, auth, "are we achieving our goals?")
        q2 = await ask(c, auth, "what should leadership focus on?")
        q3 = await ask(c, auth, "which projects are not aligned to current priorities?")
        check("9. the universal query routes strategy questions coherently",
              q1["intent"] == "strategy_execution"
              and q1["health_summary"]["total"] == 3
              and q2["intent"] == "strategy_execution"
              and q2["focus"][0]["goal_id"] == g2
              and q3["intent"] == "strategy_execution"
              and q3["gaps"]["unaligned_count"] >= 1,
              f"i1={q1.get('intent')} i2={q2.get('intent')} i3={q3.get('intent')}")

        # -------- 9. governance: strategy surfaces are org-wide only
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Apollo scope", "scope_type": "project",
                                    "entity_id": apollo["id"]},
                              headers=auth)).json()
        scoped = await invite_project_reader(c, auth, scope["id"], f"g3s{t}@strat.co")
        pf_scoped = await c.get(f"{STRATEGY}/portfolio", headers=scoped)
        d_scoped = await c.get(f"{STRATEGY}/goals/{g1}", headers=scoped)
        write_scoped = await c.post(
            f"{STRATEGY}/goals",
            json={"title": "Sneaky Goal", "kind": "revenue", "priority": 3},
            headers=scoped)
        check("10. scoped callers: portfolio and goal detail 404, strategy writes 403",
              pf_scoped.status_code == 404
              and d_scoped.status_code == 404
              and write_scoped.status_code == 403,
              f"pf={pf_scoped.status_code} detail={d_scoped.status_code} "
              f"write={write_scoped.status_code}")

        # -------- 10. replay is exact-once; the engine never mutates
        baseline = await portfolio(c, auth)
        again = await drain(c, auth)
        pf3 = await portfolio(c, auth)
        stable = {k: v for k, v in pf3.items() if k != "generated_at"}
        first = {k: v for k, v in baseline.items() if k != "generated_at"}
        d = await detail(c, auth, g1)
        apollo_row = (await c.get(f"{API}/projects/{apollo['id']}", headers=auth)).json()
        check("11. replay converges exactly-once and the engine stays advisory-only",
              stable == first
              and apollo_row["status"] == "active"
              and d["goal"]["priority"] == 1
              and len([h for h in d["history"] if h["field"] == "priority"]) == 1,
              f"processed={again} status={apollo_row.get('status')} "
              f"prio={d.get('goal', {}).get('priority')}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
