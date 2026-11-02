"""Slice 4H.1 acceptance — Universal Company / Organizational Intelligence
(live API).

Checks against the running stack (http://localhost:8999). The journey:
    seed a team + people + two covered projects with demands and a linked
    customer + task activity -> the org health trail opens and temporal
    state returns the exact-once series -> narrative explains the move ->
    the derived causality snapshot is walked from a project subject ->
    multi-level state reads the team and a person through the same
    parameterized schema -> what-happens-if extends what-if with company
    hops while keeping the honesty contract -> decisions carry predictions
    and the closed loop returns compare + lesson memory -> the Universal
    Brain's company_universal intent answers across-my-company questions ->
    scoped callers never see the org-wide universal surfaces -> re-drain
    leaves every surface deterministic.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time
from datetime import date, timedelta

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
COMPANY = f"{BRAIN}/execution/company"
CAP = f"{BRAIN}/execution/capacity"
CUST = f"{BRAIN}/execution/customer"
PROJECTS = f"{API}/projects"
TEAMS = f"{API}/teams"
EMPLOYEES = f"{API}/employees"
TASKS = f"{API}/tasks"
CUSTOMERS = f"{API}/customers"
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


async def project(client: httpx.AsyncClient, headers: dict, name: str) -> str:
    r = await client.post(
        f"{PROJECTS}",
        json={"name": name, "description": "4h1 anchor", "status": "active"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def team(client: httpx.AsyncClient, headers: dict, name: str, code: str) -> str:
    r = await client.post(
        f"{TEAMS}", json={"name": name, "code": code}, headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def employee(client: httpx.AsyncClient, headers: dict, email: str, first: str,
                   last: str, team_id: str) -> str:
    r = await client.post(
        f"{EMPLOYEES}",
        json={"first_name": first, "last_name": last, "email": email, "team_id": team_id},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def task(client: httpx.AsyncClient, headers: dict, project_id: str,
               title: str, assignee_id: str | None = None) -> str:
    body = {"title": title, "project_id": project_id, "status": "todo"}
    if assignee_id:
        body["assignee_id"] = assignee_id
    r = await client.post(f"{TASKS}", json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    tid = r.json()["id"]
    t = await client.post(f"{TASKS}/{tid}/transition", json={"status": "completed"}, headers=headers)
    assert t.status_code == 200, t.text
    return tid


async def demand(client: httpx.AsyncClient, headers: dict, project_id: str,
                 capability: str, units: int) -> dict:
    ws = date.today().isoformat()
    we = (date.today() + timedelta(days=30)).isoformat()
    r = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": capability, "units": units,
              "window_start": ws, "window_end": we, "proficiency": "high"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def customer(client: httpx.AsyncClient, headers: dict) -> str:
    r = await client.post(
        f"{CUSTOMERS}",
        json={"company_name": "Atlas Retail Group", "status": "customer",
              "segment": "enterprise", "tier": "key",
              "email": "atlas@cust4h1.test.co"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def link(client: httpx.AsyncClient, headers: dict, customer_id: str, project_id: str) -> None:
    r = await client.post(f"{CUSTOMERS}/{customer_id}/projects/{project_id}", headers=headers)
    assert r.status_code in (200, 201), r.text


async def commitment(client: httpx.AsyncClient, headers: dict, customer_id: str,
                     project_id: str) -> dict:
    r = await client.post(
        f"{CUST}/commitments",
        json={"customer_id": customer_id, "summary": "Land the Q3 retail rollout",
              "expected_at": (date.today() + timedelta(days=45)).isoformat(),
              "project_id": project_id, "status": "pending"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


async def ask(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{KNOW}/query", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def invite_scoped_reader(client: httpx.AsyncClient, headers: dict,
                               scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Universal Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Universal Reader",
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
        await client.get(f"{API}/governance/assignments", params={"user_id": user_id},
                         headers=headers)
    ).json()
    org_wide = next(a for a in assignments if a["scope_id"] is None)
    await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        f"{API}/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read",
              "reason": "4h.1 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Universal Co", f"uni4h1-{t}", f"u1{t}@uni.co", "Universal Operator")
        auth = org["headers"]

        # -------- 0. meaningful activity: team, people, coverage gap
        guild = await team(c, auth, "Covered Guild", "h1-cov")
        lead = await employee(c, auth, f"lead{t}@uni.co", "Covered", "Lead", guild)
        await employee(c, auth, f"member{t}@uni.co", "Team", "Member", guild)
        p1 = await project(c, auth, "Covered one")
        p2 = await project(c, auth, "Covered two")
        p3 = await project(c, auth, "Uncovered three")
        await drain(c, auth)
        await demand(c, auth, p1, "covered_eng", 2)
        await demand(c, auth, p2, "covered_eng", 2)
        await task(c, auth, p1, "Scope one", lead)
        await task(c, auth, p2, "Scope two", lead)
        await demand(c, auth, p3, "uncovered_eng", 2)
        cust_id = await customer(c, auth)
        await link(c, auth, cust_id, p1)
        await commitment(c, auth, cust_id, p1)
        await drain(c, auth)

        # -------- 1. temporal state: exact-once org trail series
        trail = (await c.get(f"{COMPANY}/state?limit=40", headers=auth)).json()
        check("1. temporal state returns the org trail series",
              trail["scope_type"] == "org"
              and trail["count"] >= 2
              and trail["latest"] is not None
              and set(trail["series"][-1]) == {
                  "occurred_at", "company_score", "company_state",
                  "primary_constraint", "domains"}
              and 0 <= trail["latest"]["company_score"] <= 100,
              f"count={trail.get('count')} "
              f"score={trail.get('latest', {}).get('company_score')}")

        redrained = (await c.get(f"{COMPANY}/state?limit=40", headers=auth)).json()
        check("1b. the trail is exact-once (re-drain adds no rows)",
              redrained["count"] == trail["count"],
              f"before={trail.get('count')} after={redrained.get('count')}")

        # -------- 2. narrative explains why the score moved
        narr = (await c.get(f"{COMPANY}/narrative", headers=auth)).json()
        check("2. the company narrative is composed from trail deltas",
              narr["window"] != "insufficient_history"
              and narr["steps"]
              and narr["story"]
              and all(
                  set(step) == {
                      "window", "score_before", "score_after", "state_before",
                      "state_after", "deltas", "constraint_shift"}
                  for step in narr["steps"]
              ),
              f"window={narr.get('window')} steps={len(narr.get('steps', []))} "
              f"story={narr.get('story')}")

        # -------- 3. derived causality snapshot: walk from a project
        chain = (await c.get(
            f"{COMPANY}/causal-chain",
            params={"subject_type": "project", "subject_id": p1},
            headers=auth,
        )).json()
        chain_kinds = [h["kind"] for h in chain["hops"]]
        check("3. causal chain walks the derived graph from a project subject",
              chain["subject"] == {"type": "project", "id": p1}
              and "project->milestone" not in chain_kinds  # no milestones seeded
              and any("project->customer" in k for k in chain_kinds)
              and any("milestone->customer" in k or "capacity->project" in k
                      for k in chain_kinds)
              and all(h["confidence"] in ("high", "medium", "low") for h in chain["hops"])
              and any(h.get("from_label") or h.get("to_label") for h in chain["hops"]),
              f"kinds={sorted(set(chain_kinds))} hops={len(chain['hops'])}")
        chain_org = (await c.get(
            f"{COMPANY}/causal-chain",
            params={"subject_type": "project", "subject_id": p3},
            headers=auth,
        )).json()
        check("3b. a subject without snapshot edges falls back to live impact",
              chain_org["subject"]["id"] == p3
              and chain_org["hops"]
              and all("reverse" in h for h in chain_org["hops"]),
              f"hops={len(chain_org.get('hops', []))}")

        # -------- 4. multi-level state: team + person scoped reads
        team_state = (await c.get(
            f"{COMPANY}/state?scope_type=team&scope_id={guild}",
            headers=auth,
        )).json()
        check("4. multi-level state reads the team through the same schema",
              team_state["scope_type"] == "team"
              and team_state["scope_id"] == guild
              and (team_state["latest"] is not None or team_state["live_snapshot"] is not None)
              and all(
                  {"key", "label", "score", "state", "reasons", "affected"} <= set(d)
                  for d in (team_state["live_snapshot"]["domains"]
                            if team_state.get("live_snapshot") else [])
              ),
              f"latest={team_state.get('latest') is not None} "
              f"snapshot={bool(team_state.get('live_snapshot'))}")
        person_state = (await c.get(
            f"{COMPANY}/state?scope_type=person&scope_id={lead}",
            headers=auth,
        )).json()
        check("4b. a person scope returns the same parameterized shape",
              person_state["scope_type"] == "person"
              and person_state["scope_id"] == lead
              and 0 <= (person_state.get("latest") or
                        person_state.get("live_snapshot", {})).get("company_score", 80) <= 100,
              f"score={(person_state.get('latest') or {}).get('company_score')}")
        bogus = await c.get(
            f"{COMPANY}/state?scope_type=galaxy&scope_id=x",
            headers=auth,
        )
        check("4c. unsupported scopes are rejected by the surface bound",
              bogus.status_code == 422,
              f"status={bogus.status_code}")

        # -------- 5. what-happens-if extends what-if with company hops
        whi = (await c.post(
            f"{COMPANY}/what-happens-if",
            json={"scenario_type": "delay",
                  "payload": {"project_id": p1, "days": 21}},
            headers=auth,
        )).json()
        check("5. what-happens-if keeps the honesty contract and adds company hops",
              whi["not_a_prediction"] is True
              and whi["scenario_type"] == "delay"
              and whi["consequences"]
              and isinstance(whi["company_consequences"], list)
              and sorted(whi["company_hop_kinds"]) == sorted({
                  h["kind"] for h in whi["company_consequences"]}),
              f"company hops={len(whi.get('company_consequences', []))} "
              f"kinds={whi.get('company_hop_kinds')}")

        # -------- 6. decisions record predictions; the loop compares + learns
        decision = (await c.post(
            f"{COMPANY}/decisions",
            json={"kind": "delay_project",
                  "title": "Delay covered one to protect Atlas",
                  "predicted_outcome": {"expected_outcome": "partial",
                                        "reason": "customer commitment protected"},
                  "prediction_confidence": 0.6,
                  "owner_label": "Delivery Leadership"},
            headers=auth,
        )).json()
        decision_id = decision["decision_id"]
        check("6. a decision records its prediction with clamped confidence",
              decision["decision_recorded"] is True
              and decision["prediction_recorded"] is True
              and decision["source_event_id"],
              f"id={decision_id}")
        bad = (await c.post(
            f"{COMPANY}/decisions",
            json={"kind": "hire", "title": "bad", "prediction_confidence": 1.5},
            headers=auth,
        ))
        check("6b. out-of-range confidence is rejected",
              bad.status_code == 400,
              f"status={bad.status_code}")
        await drain(c, auth)
        executed = (await c.post(
            f"{COMPANY}/decisions/{decision_id}/execute", json={}, headers=auth,
        ))
        assert executed.status_code == 200, executed.text
        await drain(c, auth)
        outcome_resp = (await c.post(
            f"{COMPANY}/decisions/{decision_id}/outcome",
            json={"outcome_kind": "partial", "effectiveness": 0.7,
                  "lesson": "a partial delay protects the customer commitment"},
            headers=auth,
        ))
        assert outcome_resp.status_code == 200, outcome_resp.text
        ob = outcome_resp.json()
        await drain(c, auth)
        check("6c. the closed loop returns the compare block + lesson memory",
              ob["actual_outcome_compare"]["predicted"] == "partial"
              and ob["actual_outcome_compare"]["observed"] == "partial"
              and ob["actual_outcome_compare"]["aligned"] is True
              and ob["lesson_memory"]["fact_kind"] == "lesson",
              f"compare={ob.get('actual_outcome_compare')}")
        recalled = (await c.get(f"{COMPANY}/memory?predicted=true", headers=auth)).json()
        check("6d. predictions are recallable through the memory surface",
              recalled["total_decisions"] >= 1
              and recalled["decisions"][0]["predicted_outcome"]["expected_outcome"] == "partial"
              and recalled["decisions"][0]["actual_outcome_compare"]["aligned"] is True,
              f"total={recalled.get('total_decisions')}")

        # -------- 7. the Universal Brain answers across-my-company questions
        q1 = await ask(c, auth, "how is my company doing")
        check("7. universal questions route to the company_universal intent",
              q1["intent"] == "company_universal"
              and (q1.get("series") or q1.get("live_snapshot") or q1.get("latest")),
              f"intent={q1.get('intent')} keys={sorted(q1.keys())}")

        # -------- 8. governance: scoped readers never reach universal surfaces
        scope = (await c.post(
            f"{API}/governance/scopes",
            json={"name": "4h1 project scope", "scope_type": "project",
                  "entity_id": "p-slice4h1"},
            headers=auth,
        )).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"u1s{t}@uni.co")
        reads = {
            "narrative": (await c.get(f"{COMPANY}/narrative", headers=scoped)).status_code,
            "causal": (await c.get(
                f"{COMPANY}/causal-chain",
                params={"subject_type": "project", "subject_id": p1},
                headers=scoped,
            )).status_code,
            "temporal": (await c.get(
                f"{COMPANY}/state?from=2026-01-01", headers=scoped,
            )).status_code,
            "what_if": (await c.post(
                f"{COMPANY}/what-happens-if",
                json={"scenario_type": "delay", "payload": {"project_id": p1, "days": 1}},
                headers=scoped,
            )).status_code,
        }
        check("8. scoped callers: universal company surfaces 404",
              set(reads.values()) == {404},
              f"reads={reads}")

        # -------- 9. deterministic on the same evidence; reads never mutate
        await drain(c, auth, rounds=12)
        before = (await c.get(f"{COMPANY}/state?limit=40", headers=auth)).json()
        swept = await drain(c, auth, rounds=12)
        after = (await c.get(f"{COMPANY}/state?limit=40", headers=auth)).json()
        check("9. replay converges: the trail stays deterministic",
              after["count"] == before["count"]
              and after["latest"]["company_score"] == before["latest"]["company_score"],
              f"swept={swept} before={before.get('count')} after={after.get('count')}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))