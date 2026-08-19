"""Slice 4G.6 acceptance — Commercial & Business Performance Intelligence
(live API).

Checks against the running stack (http://localhost:8999, APP_ENV=test). The
full journey: define a canonical revenue metric -> record outcomes (rising,
then declining) -> commit a target whose deterministic status trails the
evidence (at_risk -> slipped -> on_track with a review trail) -> commit a
bounded forecast -> detect a driver with the deterministic link language ->
the performance snapshot carries multidimensional health, trajectories and a
summary narrative -> the flagship behind-target chain walks target -> gap ->
drivers -> customers -> strategy -> projects -> capacity -> decisions ->
what to do -> the Universal Brain routes business questions -> a business-unit
metric stays isolated from the org-wide view -> scoped callers can't see the
org-wide business view -> re-drain leaves every surface deterministic.

Exit code 0 when all pass.
"""

import asyncio
import sys
import time
from datetime import date, timedelta

import httpx

API = "http://localhost:8999/api/v1"
BRAIN = f"{API}/brain"
BUS = f"{BRAIN}/execution/business"
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


async def metric(client: httpx.AsyncClient, headers: dict, key: str, **kw) -> dict:
    body = {"key": key, "label": kw.pop("label", key.replace("_", " ").title()),
            "kind": "revenue", "direction": "up_is_good",
            "unit": "usd", "period_granularity": "monthly", "scope": "org_wide", **kw}
    r = await client.post(f"{BUS}/metrics", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def outcome(client: httpx.AsyncClient, headers: dict, metric_key: str, value: float,
                  days_ago: int, **kw) -> dict:
    body = {"metric_key": metric_key, "value": value,
            "observed_at": (date.today() - timedelta(days=days_ago)).isoformat() + "T00:00:00+00:00",
            "source": "financial", **kw}
    r = await client.post(f"{BUS}/outcomes", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def target(client: httpx.AsyncClient, headers: dict, metric_key: str, value: float, **kw) -> dict:
    r = await client.post(
        f"{BUS}/targets",
        json={"metric_key": metric_key, "target_value": value,
              "end_at": (date.today() + timedelta(days=200)).isoformat(),
              "period_label": "FY2026", "belief": "likely", **kw},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def goal(client: httpx.AsyncClient, headers: dict, title: str, metric_kind: str) -> str:
    r = await client.post(
        f"{STRATEGY}/goals",
        json={"title": title, "kind": "revenue", "priority": 1,
              "metric_kind": metric_kind, "metric_unit": "usd",
              "target_value": 200000, "current_value": 100000, "timeline_label": "FY2026"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["goal_id"]


async def ask(client: httpx.AsyncClient, headers: dict, question: str) -> dict:
    r = await client.post(f"{KNOW}/query", json={"question": question}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def invite_scoped_reader(client: httpx.AsyncClient, headers: dict, scope_id: str, email: str) -> dict:
    roles = (await client.get(f"{API}/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invite = await client.post(
        f"{API}/users/invite",
        json={"email": email, "full_name": "Scoped Business Reader", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        f"{API}/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "Scoped Business Reader",
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
              "reason": "4g.6 scoped reader"},
        headers=headers,
    )
    return scoped_headers


async def main() -> int:
    async with httpx.AsyncClient(timeout=120) as c:
        t = int(time.time())
        org = await register(c, "Metric Co", f"metric4g6-{t}", f"m6{t}@metric.co", "Business Founder")
        auth = org["headers"]

        # -------- 0. define the canonical metric and record rising outcomes
        await metric(c, auth, "recurring_revenue",
                     label="Recurring Revenue (ARR)")
        await outcome(c, auth, "recurring_revenue", 60000.0, 180)
        await outcome(c, auth, "recurring_revenue", 100000.0, 90)
        await drain(c, auth)

        ledger = (await c.get(f"{BUS}/metrics", headers=auth)).json()
        arr = ledger["metrics"][0]
        check("1. the metric ledger carries the current value and trend",
              ledger["advisory_only"] is True
              and ledger["total"] == 1
              and arr["key"] == "recurring_revenue"
              and arr["current"] == 100000.0
              and arr["previous"] == 60000.0
              and arr["trend"] == "improving"
              and arr["unit"] == "usd",
              f"arr={ {k: arr.get(k) for k in ('current', 'previous', 'trend')} }")

        # -------- 1. target status trails the evidence with a review trail
        await target(c, auth, "recurring_revenue", 200000.0,
                     owner_label="CFO", initiative_labels=["Expand enterprise footprint"])
        await drain(c, auth)
        targets = (await c.get(f"{BUS}/targets", headers=auth)).json()
        row = targets["targets"][0]
        # 100000 / 200000 = 0.5 -> at_risk at the boundary, gap 100000
        check("2. the committed target gets a deterministic status and gap",
              targets["advisory_only"] is True
              and targets["total"] == 1
              and row["period_label"] == "FY2026"
              and row["status"] == "at_risk"
              and row["gap"] == 100000.0
              and row["current"] == 100000.0,
              f"status={row.get('status')} gap={row.get('gap')}")

        # decline -> slipped
        await outcome(c, auth, "recurring_revenue", 45000.0, 60)
        await drain(c, auth)
        targets = (await c.get(f"{BUS}/targets", headers=auth)).json()
        slipped = targets["targets"][0]["status"]
        # recovery -> on_track (0.8)
        await outcome(c, auth, "recurring_revenue", 160000.0, 30)
        await drain(c, auth)
        targets = (await c.get(f"{BUS}/targets", headers=auth)).json()
        row = targets["targets"][0]
        target_detail = (await c.get(f"{BUS}/targets/{row['target_id']}", headers=auth)).json()
        check("3. status transitions are deterministic with a review trail",
              slipped == "slipped"
              and row["status"] == "on_track"
              and row["gap"] == 40000.0
              and len(target_detail["target"]["reviews"]) >= 2,
              f"slipped={slipped} status={row.get('status')} "
              f"reviews={len(target_detail.get('target', {}).get('reviews', []))}")

        # -------- 2. forecast + driver with deterministic link language
        forecast = await c.post(
            f"{BUS}/forecasts",
            json={"metric_key": "recurring_revenue", "horizon_label": "2026-Q4",
                  "forecast_type": "base", "basis": "last 6 months growth",
                  "midpoint": 180000.0, "low": 150000.0, "high": 210000.0,
                  "confidence": 0.6, "risk_factors": ["enterprise deal slippage"]},
            headers=auth,
        )
        assert forecast.status_code == 200, forecast.text
        driver = await c.post(
            f"{BUS}/drivers",
            json={"key": "enterprise_velocity", "title": "Enterprise deal velocity",
                  "driver_type": "customer", "strength": "strong",
                  "direction": "toward", "impact_shape": "aggregation",
                  "metric_keys": ["recurring_revenue"], "monetized_impact": 400000.0},
            headers=auth,
        )
        assert driver.status_code == 200, driver.text
        await drain(c, auth)

        forecasts = (await c.get(f"{BUS}/forecasts", headers=auth)).json()
        drivers = (await c.get(f"{BUS}/drivers", headers=auth)).json()
        drow = drivers["drivers"][0]
        check("4. forecasts are labeled projected; drivers carry the link language",
              forecasts["advisory_only"] is True
              and forecasts["total"] == 1
              and forecasts["forecasts"][0]["midpoint"] == 180000.0
              and forecasts["forecasts"][0]["forecast_type"] == "base"
              and drivers["total"] == 1
              and drow["driver_key"] == "enterprise_velocity"
              and drow["metric_keys"] == ["recurring_revenue"]
              and drow["kind"] == "linked_to"
              and drow["kind_label"] == "linked to",
              f"forecast_mid={forecasts.get('forecasts', [{}])[0].get('midpoint')} "
              f"kind={drow.get('kind_label')}")

        # -------- 3. performance snapshot: multidimensional health + narrative
        performance = (await c.get(f"{BUS}/performance", headers=auth)).json()
        check("5. performance is multidimensional, explainable and bounded",
              performance["scope"] == "org_wide"
              and performance["advisory_only"] is True
              and 0 <= performance["health"]["score"] <= 100
              and performance["health"]["state"] in ("healthy", "concerned", "at_risk")
              and 1 <= len(performance["health"]["dimensions"]) <= 8
              and all("reasons" in d and "positives" in d and "top_metrics" in d
                      for d in performance["health"]["dimensions"])
              and any(d["key"] == "financial" for d in performance["health"]["dimensions"])
              and performance["metrics"]["total"] == 1
              and performance["metrics"]["trajectories"][0]["trend"] in (
                  "improving", "worsening", "stable")
              and performance["summary"]
              and len(performance["history"]) >= 1,
              f"score={performance.get('health', {}).get('score')} "
              f"dims={[d.get('key') for d in performance.get('health', {}).get('dimensions', [])]}")

        # -------- 4. the flagship behind-target chain
        g1 = await goal(c, auth, "Grow recurring revenue", "recurring_revenue")
        assert g1
        await drain(c, auth)
        behind = (await c.get(f"{BUS}/behind-target", headers=auth)).json()
        check("6. the flagship chain walks from target to drivers to strategy to actions",
              behind["advisory_only"] is True
              and behind["metric"]["key"] == "recurring_revenue"
              and behind["target"]["target_value"] == 200000.0
              and behind["target"]["gap"] == 40000.0
              and any(d["driver_key"] == "enterprise_velocity" for d in behind["drivers"])
              and any(g["goal"] == "Grow recurring revenue" for g in behind["strategy"])
              and any(w["kind"] == "close_gap" for w in behind["what_to_do"])
              and behind["what_to_do"][0]["gap"] == 40000.0
              and behind["summary"],
              f"drivers={len(behind.get('drivers', []))} "
              f"strategy={[g.get('goal') for g in behind.get('strategy', [])]} "
              f"actions={[w.get('kind') for w in behind.get('what_to_do', [])]}")

        recs = (await c.get(f"{BUS}/recommendations", headers=auth)).json()
        check("7. recommendations are advisory, bounded and evidence-carrying",
              recs["advisory_only"] is True
              and len(recs["recommendations"]) <= 5
              and all(any(k in r for k in ("why", "reason", "evidence")) for r in recs["recommendations"]),
              f"count={len(recs.get('recommendations', []))}")

        # -------- 5. the Universal Brain routes business questions
        q1 = await ask(c, auth, "why are we behind target on revenue")
        q2 = await ask(c, auth, "how is the business performing")
        q3 = await ask(c, auth, "what is the revenue forecast")
        q4 = await ask(c, auth, "what is driving revenue growth")
        check("8. business questions route to the business_performance intent",
              q1["intent"] == "business_performance"
              and q1["target"]["gap"] == 40000.0
              and q2["intent"] == "business_performance"
              and q2["health"]["score"] <= 100
              and q3["intent"] == "business_performance"
              and q3["forecasts"][0]["midpoint"] == 180000.0
              and q4["intent"] == "business_performance"
              and q4["total"] >= 1,
              f"intents={q1.get('intent')},{q2.get('intent')},{q3.get('intent')},{q4.get('intent')}")

        # -------- 6. lazy metric creation + scope isolation
        r0 = await c.post(
            f"{BUS}/outcomes",
            json={"metric_key": "churn_rate", "metric_label": "Customer Churn",
                  "value": 4.2,
                  "observed_at": (date.today() - timedelta(days=30)).isoformat() + "T00:00:00+00:00",
                  "source": "measurement", "unit": "pct"},
            headers=auth,
        )
        assert r0.status_code == 200, r0.text
        await metric(c, auth, "bu_revenue", label="BU Revenue",
                     scope="business_unit", scope_entity_id="bu-1")
        await outcome(c, auth, "bu_revenue", 5000.0, 30)
        await drain(c, auth)

        ledger = (await c.get(f"{BUS}/metrics", headers=auth)).json()
        churn = next(m for m in ledger["metrics"] if m["key"] == "churn_rate")
        perf_org = (await c.get(f"{BUS}/performance", headers=auth)).json()
        perf_bu = (await c.get(f"{BUS}/performance", headers=auth,
                               params={"scope": "business_unit", "scope_entity_id": "bu-1"})).json()
        check("9. an outcome-only metric materializes; scopes stay isolated",
              churn["current"] == 4.2
              and churn["unit"] == "pct"
              and perf_org["metrics"]["total"] == 2
              and all(t["metric_key"] != "bu_revenue"
                      for t in perf_org["metrics"]["trajectories"])
              and perf_bu["scope_entity_id"] == "bu-1"
              and perf_bu["metrics"]["total"] == 1
              and perf_bu["metrics"]["trajectories"][0]["metric_key"] == "bu_revenue",
              f"org_total={perf_org.get('metrics', {}).get('total')} "
              f"bu_total={perf_bu.get('metrics', {}).get('total')}")

        # -------- 7. governance: scoped callers never reach the org-wide view
        scope = (await c.post(f"{API}/governance/scopes",
                              json={"name": "4g6 project scope", "scope_type": "project",
                                    "entity_id": "p-slice4g6"},
                              headers=auth)).json()
        scoped = await invite_scoped_reader(c, auth, scope["id"], f"m6s{t}@metric.co")
        reads = {
            "metrics": (await c.get(f"{BUS}/metrics", headers=scoped)).status_code,
            "performance": (await c.get(f"{BUS}/performance", headers=scoped)).status_code,
            "behind": (await c.get(f"{BUS}/behind-target", headers=scoped)).status_code,
            "recommendations": (await c.get(f"{BUS}/recommendations", headers=scoped)).status_code,
        }
        writes = {
            "metric": (await c.post(f"{BUS}/metrics",
                                    json={"key": "x", "kind": "revenue",
                                          "direction": "up_is_good"},
                                    headers=scoped)).status_code,
        }
        check("10. scoped callers: business reads 404, writes blocked",
              set(reads.values()) == {404} and writes["metric"] in (403, 404),
              f"reads={reads} writes={writes}")

        # -------- 8. deterministic on the same evidence; reads never mutate
        await drain(c, auth, rounds=12)
        baseline = await c.get(f"{BUS}/performance", headers=auth)
        swept = await drain(c, auth, rounds=12)
        perf2 = (await c.get(f"{BUS}/performance", headers=auth)).json()
        stable = {k: v for k, v in perf2.items() if k != "generated_at"}
        first = {k: v for k, v in baseline.json().items() if k != "generated_at"}
        check("11. replay is exact-once and the surfaces stay deterministic",
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