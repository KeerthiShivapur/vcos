"""Slice 4G.7 acceptance — Universal Company Operating Intelligence
(live API).

Checks against the running stack (http://localhost:8999, APP_ENV=test). The
full journey: seed meaningful activity across the canonical 4G systems
(strategy goal, a project-kind, a scarce-capability demand, a business target
behind its evidence) -> the universal company state composes all eight
domains -> the health trail records one exact-once assessment per event with
a deterministic primary constraint -> root-cause chains walk a problem down
to capacity and people -> impact propagates from a project to customers ->
the recommendation queue is advisory, bounded and unique -> governed
what-if scenarios (delay / hire / unknown) are declared, never executed ->
"What changed?" reports real deltas over the trail -> the governed memory
loop closes decision -> execution -> outcome -> lesson -> the Universal
Brain routes company questions -> scoped callers can't see the org-wide
company view -> re-drain leaves every surface deterministic.

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
BUS = f"{BRAIN}/execution/business"
CAP = f"{BRAIN}/execution/capacity"
CUST = f"{BRAIN}/execution/customer"
STRATEGY = f"{BRAIN}/execution/strategy"
PROJECTS = f"{API}/projects"
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


async def goal(client: httpx.AsyncClient, headers: dict, title: str) -> str:
    r = await client.post(
        f"{STRATEGY}/goals",
        json={"title": title, "kind": "revenue", "priority": 1,
              "metric_kind": "recurring_revenue", "metric_unit": "usd",
              "target_value": 500000, "current_value": 100000, "timeline_label": "FY2026"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["goal_id"]


async def project(client: httpx.AsyncClient, headers: dict, name: str) -> str:
    r = await client.post(
        f"{PROJECTS}",
        json={"name": name, "description": "4g7 anchor", "status": "active"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


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


async def metric(client: httpx.AsyncClient, headers: dict, key: str) -> dict:
    r = await client.post(
        f"{BUS}/metrics",
        json={"key": key, "kind": "revenue", "direction": "up_is_good",
              "unit": "usd", "period_granularity": "monthly", "scope": "org_wide"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def outcome(client: httpx.AsyncClient, headers: dict, metric_key: str,
                  value: float, days_ago: int) -> dict:
    r = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": metric_key, "value": value,
              "observed_at": (date.today() - timedelta(days=days_ago)).isoformat()
              + "T00:00:00+00:00",
              "source": "financial"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def target(client: httpx.AsyncClient, headers: dict, metric_key: str,
                 value: float) -> dict:
    r = await client.post(
        f"{BUS}/targets",
        json={"metric_key": metric_key, "target_value": value,
              "end_date": (date.today() + timedelta(days=200)).isoformat(),
              "owner_label": "CFO"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def customer(client: httpx.AsyncClient, headers: dict) -> str:
    r = await client.post(
        f"{API}/customers",
        json={"company_name": "Northstar Enterprises", "status": "customer",
              "segment": "enterprise", "tier": "key",
              "email": "northstar@cust.test.co"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def commitment(client: httpx.AsyncClient, headers: dict, customer_id: str,
                     project_id: str) -> dict:
    r = await client.post(
        f"{CUST}/commitments",
        json={"customer_id": customer_id, "summary": "Ship the Q3 enterprise release",
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
        json={"email": email, "full_name": "Scoped Company Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Company Reader",
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
              "reason": "4g.7 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Operating Co", f"oper4g7-{t}", f"o7{t}@oper.co", "Company Operator")
        auth = org["headers"]

        # -------- 0. meaningful activity across the canonical 4G systems
        await goal(c, auth, "Grow recurring revenue")
        g_project = await project(c, auth, "Flagship Platform")
        await demand(c, auth, g_project, "platform_eng", 4)
        await metric(c, auth, "recurring_revenue")
        await drain(c, auth)
        await outcome(c, auth, "recurring_revenue", 40000.0, 120)
        await outcome(c, auth, "recurring_revenue", 60000.0, 60)
        await drain(c, auth)
        await target(c, auth, "recurring_revenue", 200000.0)
        cust_id = await customer(c, auth)
        await commitment(c, auth, cust_id, g_project)
        await drain(c, auth)

        # -------- 1. universal company state: all eight domains
        state = (await c.get(f"{COMPANY}/state", headers=auth)).json()
        check("1. the company state composes all eight domains and stays bounded",
              state["advisory_only"] is True
              and set(state["dimensions"].keys()) == {
                  "strategy", "execution", "coordination", "capacity",
                  "people", "customers", "financial", "knowledge"}
              and 0 < len(state["attention"]) <= 5
              and state["dimensions"]["capacity"]["top_constraint"]["capability"] == "platform_eng",
              f"dims={sorted(state.get('dimensions', {}).keys())} "
              f"attention={len(state.get('attention', []))}")

        # -------- 2. health trail: exact-once assessments, primary constraint
        health = (await c.get(f"{COMPANY}/health", headers=auth)).json()
        check("2. company health is deterministic with a constraint and a trail",
              health["advisory_only"] is True
              and len(health["domains"]) == 8
              and health["primary_constraint"]["domain"] in ("capacity", "strategy")
              and health["primary_constraint"]["interventions"]
              and len(health["history"]) >= 1
              and health["history"][0]["company_score"] == health["company_score"],
              f"score={health.get('company_score')} "
              f"history={len(health.get('history', []))} "
              f"constraint={health.get('primary_constraint', {}).get('label')}")

        # -------- 3. root-cause chains walk to capacity then people
        rc = (await c.get(f"{COMPANY}/root-cause", params={"problem": "platform_eng"},
                          headers=auth)).json()
        rc_layers = [s["layer"] for s in rc["chain"]]
        check("3. root-cause chains end at people/capability and carry the gap",
              rc["matched_on"] == "capability"
              and rc["chain"]
              and rc_layers[-1] in ("people_capability", "capacity_constraint")
              and rc["advisory_only"] is True
              and bool(rc["resolution_hint"]),
              f"matched_on={rc.get('matched_on')} layers={rc_layers}")

        # -------- 4. impact propagates from project to customers
        imp = (await c.get(f"{COMPANY}/impact",
                           params={"subject_type": "project", "subject_id": g_project},
                           headers=auth)).json()
        imp_steps = [s["step"] for s in imp.get("chain", [])]
        check("4. impact propagation follows the composed chain to customers",
              imp["subject_type"] == "project"
              and imp_steps
              and imp_steps[0] == "execution"
              and "customers" in imp_steps
              and imp["consequence_summary"],
              f"steps={imp_steps}")
        imp_cust = (await c.get(f"{COMPANY}/impact",
                                params={"subject_type": "customer", "subject_id": cust_id},
                                headers=auth)).json()
        check("4b. a customer subject walks back through execution",
              imp_cust["subject_type"] == "customer"
              and [s["step"] for s in imp_cust["chain"]][0] == "customers",
              f"steps={[s['step'] for s in imp_cust.get('chain', [])]}")

        # -------- 5. advisory, bounded, unique recommendation queue
        recs = (await c.get(f"{COMPANY}/recommendations", headers=auth)).json()
        keys = [r["key"] for r in recs["recommendations"]]
        check("5. the company recommendation queue is advisory, unique, bounded",
              recs["advisory_only"] is True
              and 0 < len(recs["recommendations"]) <= 20
              and len(keys) == len(set(keys))
              and all(r["title"] and r["why"] and r["confidence"] and r["owner_label"]
                      and r["expected_improvement"] and r["evidence_ref"] and r["source"]
                      for r in recs["recommendations"])
              and any(r["source"] == "capacity" for r in recs["recommendations"]),
              f"count={len(recs.get('recommendations', []))} "
              f"sources={sorted({r['source'] for r in recs.get('recommendations', [])})}")

        # -------- 6. governed what-if: declared, never executed
        wi = await c.post(f"{COMPANY}/what-if",
                          json={"scenario_type": "delay",
                                "payload": {"project_id": g_project, "days": 21}},
                          headers=auth)
        assert wi.status_code == 200, wi.text
        wi_body = wi.json()
        check("6. what-if delay propagates consequences with the honesty labels",
              wi_body["not_a_prediction"] is True
              and wi_body["scenario_type"] == "delay"
              and wi_body["consequences"]
              and any("delayed 21 days" in x["label"] for x in wi_body["consequences"])
              and any(t in wi_body["note"] for t in (
                  "not a prediction", "humans decide", "does not reschedule")),
              f"consequences={len(wi_body.get('consequences', []))} note={wi_body.get('note')}")
        hire = await c.post(f"{COMPANY}/what-if",
                            json={"scenario_type": "hire",
                                  "payload": {"capability": "platform_eng",
                                              "people": 2, "ramp_days": 30}},
                            headers=auth)
        assert hire.status_code == 200, hire.text
        hire_body = hire.json()
        check("6b. hire what-if returns the ramp language",
              hire_body["scenario_type"] == "hire"
              and hire_body["scenario"]["people"] == 2
              and any("hire 2 people" in x["label"] for x in hire_body["consequences"]),
              f"labels={[x.get('label') for x in hire_body.get('consequences', [])]}")
        unknown = (await c.post(f"{COMPANY}/what-if",
                                json={"scenario_type": "moon", "payload": {}},
                                headers=auth)).json()
        check("6c. unknown scenarios are declared, not guessed",
              "reallocate | delay | hire" in unknown["note"],
              f"note={unknown.get('note')}")

        # -------- 7. what changed: real deltas over the exact-once trail
        await demand(c, auth, g_project, "platform_eng", 2)
        await outcome(c, auth, "recurring_revenue", 120000.0, 60)
        await drain(c, auth)
        changes = (await c.get(f"{COMPANY}/changes", headers=auth)).json()
        check("7. what-changed reports real deltas once the trail opens",
              changes["window"] != "insufficient_history"
              and changes["company_score_before"] != changes["company_score_after"]
              and changes["changes"]
              and any(x.get("domain") == "financial" for x in changes["changes"]),
              f"before={changes.get('company_score_before')} "
              f"after={changes.get('company_score_after')} "
              f"changes={[x.get('kind') for x in changes.get('changes', [])]}")

        # -------- 8. governed memory loop: decision -> execute -> outcome
        decision = (await c.post(
            f"{COMPANY}/decisions",
            json={"kind": "hire", "title": "Hire two platform engineers",
                  "recommendation_key": "capacity:01",
                  "rationale": "platform_eng is the company bottleneck",
                  "impact_label": "gap 4 units",
                  "expected_improvement": "clear the platform constraint",
                  "confidence": 0.8, "owner_label": "Technical Leadership"},
            headers=auth,
        )).json()
        decision_id = decision["decision_id"]
        await drain(c, auth)
        executed = (await c.post(f"{COMPANY}/decisions/{decision_id}/execute",
                                 json={}, headers=auth))
        assert executed.status_code == 200, executed.text
        await drain(c, auth)
        outcome_resp = (await c.post(
            f"{COMPANY}/decisions/{decision_id}/outcome",
            json={"outcome_kind": "successful", "effectiveness": 0.9,
                  "evidence": ["two engineers onboarded; constraint cleared"],
                  "lesson": "hiring the capability bottleneck pays off first"},
            headers=auth,
        ))
        assert outcome_resp.status_code == 200, outcome_resp.text
        await drain(c, auth)
        memory = (await c.get(f"{COMPANY}/memory", headers=auth)).json()
        check("8. the governed memory loop closes with a recorded lesson",
              memory["total_decisions"] == 1
              and memory["decisions"][0]["decision_id"] == decision_id
              and memory["decisions"][0]["state"] == "outcome_recorded"
              and any("pays off" in str(l) for l in memory["learnings"]),
              f"state={memory.get('decisions', [{}])[0].get('state')} "
              f"learnings={len(memory.get('learnings', []))}")

        # -------- 9. the Universal Brain routes company questions
        q1 = await ask(c, auth, "how is the entire company doing")
        q2 = await ask(c, auth, "what should the company do")
        q3 = await ask(c, auth, "what is the biggest company constraint")
        check("9. company questions route to the company operating intent",
              q1["intent"] == "company_operating"
              and set(q1["dimensions"].keys()) == {
                  "strategy", "execution", "coordination", "capacity",
                  "people", "customers", "financial", "knowledge"}
              and q2["intent"] == "company_operating"
              and q2["total"] >= 1
              and q3["intent"] == "company_operating"
              and q3["primary_constraint"]
              and q3["primary_constraint"]["domain"] in (
                  "capacity", "strategy", "financial"),
              f"intents={q1.get('intent')},{q2.get('intent')},{q3.get('intent')} "
              f"constraint={(q3.get('primary_constraint') or {}).get('domain')}")

        # -------- 10. governance: scoped callers never reach the org-wide view
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "4g7 project scope", "scope_type": "project",
                                    "entity_id": "p-slice4g7"},
                              headers=auth)).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"o7s{t}@oper.co")
        reads = {
            "state": (await c.get(f"{COMPANY}/state", headers=scoped)).status_code,
            "health": (await c.get(f"{COMPANY}/health", headers=scoped)).status_code,
            "recommendations": (await c.get(f"{COMPANY}/recommendations", headers=scoped)).status_code,
            "changes": (await c.get(f"{COMPANY}/changes", headers=scoped)).status_code,
            "memory": (await c.get(f"{COMPANY}/memory", headers=scoped)).status_code,
        }
        write = (await c.post(f"{COMPANY}/decisions",
                              json={"kind": "hire", "title": "x"},
                              headers=scoped)).status_code
        check("10. scoped callers: company reads 404, governed writes denied",
              set(reads.values()) == {404} and write in (403, 404),
              f"reads={reads} write={write}")

        # -------- 11. deterministic on the same evidence; reads never mutate
        await drain(c, auth, rounds=12)
        before_health = (await c.get(f"{COMPANY}/health", headers=auth)).json()
        before_memory = (await c.get(f"{COMPANY}/memory", headers=auth)).json()
        swept = await drain(c, auth, rounds=12)
        after_health = (await c.get(f"{COMPANY}/health", headers=auth)).json()
        after_memory = (await c.get(f"{COMPANY}/memory", headers=auth)).json()
        stable_h = {k: v for k, v in after_health.items() if k != "generated_at"}
        first_h = {k: v for k, v in before_health.items() if k != "generated_at"}
        check("11. replay is exact-once and the company surfaces stay deterministic",
              stable_h == first_h
              and after_memory["total_decisions"] == before_memory["total_decisions"],
              f"swept={swept}")

        print(f"\n=== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ===")
        if FAILED:
            print("FAILED:")
            for f in FAILED:
                print(f"  - {f}")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))