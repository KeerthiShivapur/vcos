"""Slice 4G.5 acceptance — Customer & Market Execution Intelligence (live API).

Checks against the running stack (http://localhost:8999, APP_ENV=test). The
full journey: real customer signals from many customers on one enterprise need
-> the need aggregates into a theme WITH its evidence -> health recomputes
with the why -> resolution re-feeds health -> commitments (created, overdue,
delivered) and outcomes (baseline -> target -> actual) carry into health,
coverage, gaps, opportunities, trends, knowledge linkage and risk propagation
through a strategy goal chain -> the Universal Brain routes customer questions
-> scoped callers can't see org-wide customer intelligence -> re-drain leaves
every surface deterministic. The engine never mutates the org by itself.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time
from datetime import date, timedelta

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
CUST = f"{BRAIN}/execution/customer"
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
    timeout: float = 240,
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


async def customer(client: httpx.AsyncClient, headers: dict, name: str, **extra) -> str:
    body = {"company_name": name, "status": "customer", "segment": "enterprise",
            "tier": "gold", "industry": "Software", **extra}
    r = await client.post(f"{API}/customers", json=body, headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def signal(client: httpx.AsyncClient, headers: dict, customer_id: str, **kw) -> dict:
    body = {"customer_id": customer_id, "signal_type": "issue", "severity": "high",
            "summary": "SSO login is broken for our users", "source": "support", **kw}
    r = await client.post(f"{CUST}/signals", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def project(client: httpx.AsyncClient, headers: dict, name: str, code: str) -> dict:
    r = await client.post(
        f"{API}/projects",
        json={"name": name, "code": code, "status": "active"},
        headers=headers, timeout=60,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def goal(client: httpx.AsyncClient, headers: dict, title: str) -> str:
    r = await client.post(
        f"{STRATEGY}/goals",
        json={"title": title, "kind": "revenue", "priority": 1,
              "metric_kind": "revenue", "metric_unit": "pct",
              "target_value": 25, "current_value": 5, "timeline_label": "FY2026"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["goal_id"]


async def objective(client: httpx.AsyncClient, headers: dict, goal_id: str, title: str) -> str:
    r = await client.post(
        f"{STRATEGY}/objectives",
        json={"goal_id": goal_id, "title": title, "required_capabilities": ["sso"]},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["objective_id"]


async def initiative(client: httpx.AsyncClient, headers: dict, objective_id: str) -> str:
    r = await client.post(
        f"{STRATEGY}/initiatives",
        json={"objective_id": objective_id, "title": "SSO initiative",
              "required_capabilities": ["sso"]},
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


async def ask(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{KNOW}/query", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def invite_scoped_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Customer Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Customer Reader",
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
    org_wide = next(a for a in assignments if a["scope_id"] is None)
    await client.delete(f"{API}/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        f"{API}/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read",
              "reason": "4g.5 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Customer Co", f"cust4g5-{t}", f"c5{t}@cust.co", "Customer Founder")
        auth = org["headers"]

        # -------- 0. the flagship scenario: many customers, one enterprise need
        customers = {}
        names = ["Nova Labs", "Beta Corp", "Gamma Inc", "Delta Ltd", "Theta Corp",
                 "Omega Co", "Sigma SAS", "Zeta GmbH", "Alpha BV", "Kappa AB"]
        for i, name in enumerate(names):
            customers[name] = await customer(c, auth, name)
        await drain(c, auth)

        now = date.today()
        month_ago = (now - timedelta(days=35)).isoformat()
        # 8 SSO signals: 4 high-severity issues (Nova's enterprise security
        # problem, recurring) + 4 medium requests (enterprise market demand
        # for the same need)
        for name in range(4):
            await signal(c, auth, customers["Nova Labs"],
                         summary=f"SSO login is broken for our users (outage {name})",
                         severity="high")
        for name in list(names)[1:5]:
            await signal(c, auth, customers[name], signal_type="request",
                         severity="medium",
                         summary=f"Enterprise SSO support please ({name})")
        # a second, weaker need: 3 mobile requests from 3 customers (one recent)
        await signal(c, auth, customers["Sigma SAS"], signal_type="request", severity="info",
                     summary="iOS app support please", occurred_at=month_ago)
        await signal(c, auth, customers["Zeta GmbH"], signal_type="request", severity="info",
                     summary="Android app support please", occurred_at=month_ago)
        await signal(c, auth, customers["Kappa AB"], signal_type="request", severity="info",
                     summary="Mobile app for field teams please",
                     occurred_at=now.isoformat())
        await drain(c, auth)

        signals = (await c.get(f"{CUST}/signals", headers=auth)).json()
        themes = (await c.get(f"{CUST}/themes", headers=auth)).json()
        sso_theme = next(th for th in themes["themes"] if th["key"] == "sso")
        check("1. signals on one need aggregate into a theme with evidence",
              signals["total"] == 11
              and sso_theme["occurrences"] == 8
              and sso_theme["customers"] == 5
              and sso_theme["open"] == 8
              and sso_theme["high_severity"] == 4
              and len(sso_theme["evidence"]) >= 1
              and sso_theme["evidence"][0]["customer"],
              f"total={signals.get('total')} theme={ {k: sso_theme.get(k) for k in ('occurrences', 'customers', 'open', 'high_severity')} }")

        # -------- 1. health recomputes with the why
        healths = (await c.get(f"{CUST}/health", headers=auth)).json()
        by_name = {h["customer"]: h for h in healths["health"]}
        nova = by_name.get("Nova Labs")
        check("2. customer health carries the why, not a bare score",
              nova is not None
              and nova["score"] <= 88
              and any("critical" in r for r in nova["reasons"])
              and any("negative signal" in r for r in nova["reasons"]),
              f"nova={ {k: nova.get(k) if nova else None for k in ('state', 'score', 'reasons')} }")

        center = (await c.get(f"{CUST}/customers/{customers['Nova Labs']}", headers=auth)).json()
        check("3. the customer command center ties health to the signal timeline",
              center["customer"]["company_name"] == "Nova Labs"
              and center["health"]["state"]
              and len(center["signals"]) >= 1
              and center["signals"][0]["status"] == "open"
              and len(center["themes"]) == 1
              and center["themes"][0]["key"] == "sso",
              f"center signals={len(center.get('signals', []))} themes={len(center.get('themes', []))}")

        # -------- 2. resolution re-feeds health; double-resolve rejected
        sso_signals = (await c.get(f"{CUST}/signals",
                                   params={"need": "sso", "severity": "high"},
                                   headers=auth)).json()
        first = sso_signals["signals"][0]
        resolved = await c.post(
            f"{CUST}/signals/{first['signal_id']}/resolve",
            json={"resolution": "fixed the identity provider mapping"}, headers=auth,
        )
        assert resolved.status_code == 200, resolved.text
        await drain(c, auth)
        twice = await c.post(
            f"{CUST}/signals/{first['signal_id']}/resolve",
            json={"resolution": "again"}, headers=auth,
        )
        await drain(c, auth)
        themes = (await c.get(f"{CUST}/themes", headers=auth)).json()
        sso_theme = next(th for th in themes["themes"] if th["key"] == "sso")
        check("4. resolution closes the signal, drops theme open count, rejects replay",
              twice.status_code == 400
              and sso_theme["open"] == 7
              and sso_theme["occurrences"] == 8,
              f"twice={twice.status_code} open={sso_theme.get('open')}")

        # -------- 3. commitments: overdue weighs, delivery releases
        commit = await c.post(
            f"{CUST}/commitments",
            json={"customer_id": customers["Nova Labs"],
                  "summary": "Enterprise SSO launch",
                  "expected_at": (now - timedelta(days=3)).isoformat(),
                  "project_id": None, "capability": "sso",
                  "owner_label": "Platform Team"},
            headers=auth,
        )
        assert commit.status_code == 200, commit.text
        await drain(c, auth)
        center = (await c.get(f"{CUST}/customers/{customers['Nova Labs']}", headers=auth)).json()
        check("5. an overdue commitment weighs into health with a reason",
              center["commitments"]
              and center["commitments"][0]["status"] == "pending"
              and any("overdue" in r for r in center["health"]["reasons"]),
              f"reasons={center.get('health', {}).get('reasons')}")

        delivered = await c.post(
            f"{CUST}/commitments/{commit.json()['commitment_id']}/deliver",
            json={"delivered_at": now.isoformat(), "note": "released to all tenants"},
            headers=auth,
        )
        assert delivered.status_code == 200, delivered.text
        await drain(c, auth)
        center = (await c.get(f"{CUST}/customers/{customers['Nova Labs']}", headers=auth)).json()
        check("6. delivery is a governed write that releases the health reason",
              center["commitments"][0]["status"] == "delivered"
              and not any("overdue" in r for r in center["health"]["reasons"]),
              f"status={center.get('commitments', [{}])[0].get('status')} "
              f"reasons={center.get('health', {}).get('reasons')}")

        # -------- 4. outcomes: did the customer problem actually improve?
        outcome = await c.post(
            f"{CUST}/outcomes",
            json={"customer_id": customers["Nova Labs"], "metric_kind": "login_success",
                  "baseline": 70, "target": 95, "actual": 92, "unit": "pct",
                  "period_label": "Q3",
                  "note": "SSO fix moved login success toward target"},
            headers=auth,
        )
        assert outcome.status_code == 200, outcome.text
        await drain(c, auth)
        outcomes = (await c.get(f"{CUST}/outcomes", headers=auth)).json()
        center = (await c.get(f"{CUST}/customers/{customers['Nova Labs']}", headers=auth)).json()
        check("7. outcome evidence lands on the ledger and lifts health positives",
              outcomes["total"] == 1
              and outcomes["outcomes"][0]["improved"] is True
              and any("outcome" in p for p in center["health"]["positives"]),
              f"outcomes={outcomes.get('total')} positives={center.get('health', {}).get('positives')}")

        # -------- 5. coverage + gaps: what customers need vs what we address
        covered_proj = await project(c, auth, "SSO Rollout Project", f"sso{t % 9000}")
        g1 = await goal(c, auth, "Enterprise SSO security")
        obj = await objective(c, auth, g1, "Enterprise SSO hardening")
        init = await initiative(c, auth, obj)
        await link(c, auth, init, covered_proj["id"])
        await drain(c, auth)

        coverage = (await c.get(f"{CUST}/coverage", headers=auth))
        assert coverage.status_code == 200, coverage.text
        coverage = coverage.json()
        sso_cov = next(x for x in coverage["themes"] if x["key"] == "sso")
        mobile_cov = next(x for x in coverage["themes"] if x["key"] == "mobile")
        gaps = (await c.get(f"{CUST}/gaps", headers=auth)).json()
        check("8. coverage is traceable: sso addressed by its project, mobile not",
              coverage["advisory_only"] is True
              and sso_cov["coverage_pct"] == 100.0
              and sso_cov["addressing_projects"][0]["name"] == "SSO Rollout Project"
              and mobile_cov["coverage_pct"] == 0.0
              and any(g["key"] == "mobile" for g in gaps["gaps"])
              and gaps["gaps"][0]["impact"] in ("medium", "high")
              and not any(g["key"] == "sso" for g in gaps["gaps"]),
              f"sso={sso_cov} mobile={mobile_cov} gap_keys={[g.get('key') for g in gaps.get('gaps', [])]}")

        opportunities = (await c.get(f"{CUST}/opportunities", headers=auth)).json()
        sso_opp = next(o for o in opportunities["opportunities"] if o["key"] == "sso")
        mobile_opp = next(o for o in opportunities["opportunities"] if o["key"] == "mobile")
        check("9. opportunities are evidence-backed and never decide by themselves",
              opportunities["advisory_only"] is True
              and sso_opp["signals"] == 4
              and sso_opp["addressed"] is True
              and sso_opp["decision_linkage"]["requires_decision"] is False
              and mobile_opp["signals"] == 3
              and mobile_opp["decision_linkage"]["requires_decision"] is True
              and "no active initiative" in mobile_opp["decision_linkage"]["note"],
              f"opp={ {k: (sso_opp or {}).get(k) for k in ('signals', 'addressed', 'decision_linkage')} } "
              f"mobile={ {k: (mobile_opp or {}).get(k) for k in ('signals', 'decision_linkage')} }")

        # -------- 6. trends + knowledge linkage
        trends = (await c.get(f"{CUST}/trends", headers=auth)).json()
        sso_trend = next(x for x in trends["themes"] if x["key"] == "sso")
        knowledge = (await c.get(f"{CUST}/knowledge", headers=auth)).json()
        check("10. trends are temporal buckets; knowledge linkage is honest",
              sso_trend["monthly"] and len(sso_trend["monthly"]) <= 6
              and sum(m["count"] for m in sso_trend["monthly"]) == 8
              and knowledge["advisory_only"] is True
              and knowledge["themes"][0]["knowledge_covered"] is False
              and knowledge["knowledge_coverage_pct"] == 0.0,
              f"buckets={len(sso_trend.get('monthly', []))} sum="
              f"{sum(m.get('count', 0) for m in sso_trend.get('monthly', []))}")

        # -------- 7. risk propagation: project delay -> commitment -> goal
        at_risk_commit = await c.post(
            f"{CUST}/commitments",
            json={"customer_id": customers["Nova Labs"],
                  "summary": "Enterprise SSO GA",
                  "expected_at": (now - timedelta(days=1)).isoformat(),
                  "project_id": covered_proj["id"], "capability": "sso",
                  "owner_label": "Platform Team"},
            headers=auth,
        )
        assert at_risk_commit.status_code == 200, at_risk_commit.text
        await drain(c, auth)
        risk = (await c.get(f"{CUST}/risk", headers=auth)).json()
        nova_risk = next((r for r in risk["at_risk_customers"]
                          if r["customer_id"] == customers["Nova Labs"]), None)
        commit_rows = [x for x in risk["commitments_at_risk"]
                       if x["commitment_id"] == at_risk_commit.json()["commitment_id"]]
        check("11. risk propagates from the customer and commitment to the goal",
              risk["advisory_only"] is True
              and nova_risk is not None
              and nova_risk["state"] == "at_risk"
              and len(commit_rows) == 1
              and commit_rows[0]["customer"] == "Nova Labs"
              and commit_rows[0]["project"] == "SSO Rollout Project"
              and any(g["goal"] == "Enterprise SSO security" for g in commit_rows[0]["goals"])
              and risk["propagation_note"],
              f"at_risk={nova_risk is not None} commits={len(commit_rows)} "
              f"goals={commit_rows[0]['goals'] if commit_rows else []}")

        # -------- 8. the Universal Brain routes customer questions
        q1 = await ask(c, auth, "what are our customers asking for")
        q2 = await ask(c, auth, "which customer problems are getting worse")
        q3 = await ask(c, auth, "which customers are at risk")
        q4 = await ask(c, auth, "what have we promised our customers")
        q5 = await ask(c, auth, "what are our biggest customer gaps")
        q6 = await ask(c, auth, "are our strategic priorities aligned with customer demand")
        q7 = await ask(c, auth, "what should we improve for our customers")
        check("12. customer questions route to the customer_intelligence intent",
              q1["intent"] == "customer_intelligence" and any(
                  th["key"] == "sso" for th in q1["themes"])
              and q1["advisory_only"] is True
              and q3["intent"] == "customer_intelligence" and q3["at_risk_customers"]
              and q4["intent"] == "customer_intelligence" and q4["total"] >= 2
              and q5["intent"] == "customer_intelligence" and q5["gaps"],
              f"intents={q1.get('intent')},{q2.get('intent')},{q3.get('intent')},"
              f"{q4.get('intent')},{q5.get('intent')},{q6.get('intent')},{q7.get('intent')}")

        # -------- 9. governance: scoped callers never reach org-wide customer intelligence
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "Nova scope", "scope_type": "project",
                                    "entity_id": covered_proj["id"]},
                              headers=auth)).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"c5s{t}@cust.co")
        reads = {
            "health": (await c.get(f"{CUST}/health", headers=scoped)).status_code,
            "signals": (await c.get(f"{CUST}/signals", headers=scoped)).status_code,
            "risk": (await c.get(f"{CUST}/risk", headers=scoped)).status_code,
        }
        writes = {
            "signal": (await c.post(f"{CUST}/signals",
                                    json={"customer_id": customers["Nova Labs"],
                                          "signal_type": "issue", "severity": "high",
                                          "summary": "x", "source": "support"},
                                    headers=scoped)).status_code,
        }
        check("13. scoped callers: customer reads 404, writes blocked",
              set(reads.values()) == {404} and writes["signal"] in (403, 404),
              f"reads={reads} writes={writes}")

        # -------- 10. deterministic on the same evidence; reads never mutate
        await drain(c, auth, rounds=12)
        baseline = await c.get(f"{CUST}/risk", headers=auth)
        swept = await drain(c, auth, rounds=12)
        risk2 = (await c.get(f"{CUST}/risk", headers=auth)).json()
        stable = {k: v for k, v in risk2.items() if k != "generated_at"}
        first = {k: v for k, v in baseline.json().items() if k != "generated_at"}
        check("14. replay is exact-once and the surfaces stay deterministic",
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
