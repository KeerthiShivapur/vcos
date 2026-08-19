"""Slice 4G.6 — surfaces: the business API walkthrough (metrics, outcomes,
targets, forecasts, drivers, performance, behind-target, recommendations)
and the Universal Brain routing of business-performance questions.

Everything is the canonical business-performance ledger: advisory,
evidence-backed and deterministic — never a dashboard.
"""

from datetime import date, timedelta

from tests.conftest import register_org

BRAIN = "/api/v1/brain"
BUS = f"{BRAIN}/execution/business"


async def _drain(db_session_factory, limit=200, rounds=6):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _metric(client, headers, key="recurring_revenue", label="Recurring Revenue",
                  kind="revenue", direction="up_is_good", unit="usd"):
    resp = await client.post(
        f"{BUS}/metrics",
        json={"key": key, "label": label, "kind": kind, "direction": direction,
              "unit": unit, "period_granularity": "monthly", "scope": "org_wide"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _outcome(client, headers, metric_key, value, observed_at,
                   source="financial"):
    resp = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": metric_key, "value": value,
              "observed_at": observed_at, "source": source},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _ask(client, headers, question):
    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": question}, headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_surfaces_walkthrough(client, db_session_factory):
    org = await register_org(client, email="4g6_sur1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _metric(client, headers)
    await _outcome(client, headers, "recurring_revenue", 100000.0,
                   "2026-07-31T00:00:00+00:00")
    await _drain(db_session_factory)
    target_resp = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "recurring_revenue", "target_value": 200000.0,
              "end_at": "2026-12-31", "period_label": "FY2026",
              "belief": "likely", "owner_label": "CFO",
              "initiative_labels": ["Expand enterprise footprint"]},
        headers=headers,
    )
    assert target_resp.status_code == 200, target_resp.text
    await client.post(
        f"{BUS}/forecasts",
        json={"metric_key": "recurring_revenue", "horizon_label": "2026-Q4",
              "forecast_type": "base", "basis": "last 6 months growth",
              "midpoint": 140000.0, "low": 120000.0, "high": 160000.0,
              "confidence": 0.6},
        headers=headers,
    )
    driver_resp = await client.post(
        f"{BUS}/drivers",
        json={"key": "enterprise_velocity", "title": "Enterprise deal velocity",
              "driver_type": "customer", "strength": "strong",
              "direction": "toward", "impact_shape": "aggregation",
              "metric_keys": ["recurring_revenue"], "monetized_impact": 400000.0},
        headers=headers,
    )
    assert driver_resp.status_code == 200, driver_resp.text
    await _drain(db_session_factory)

    metrics = (await client.get(f"{BUS}/metrics", headers=headers)).json()
    assert metrics["advisory_only"] is True
    assert metrics["total"] == 1
    item = metrics["metrics"][0]
    assert item["key"] == "recurring_revenue"
    assert item["current"] == 100000.0
    assert item["direction"] == "up_is_good"

    detail = (
        await client.get(f"{BUS}/metrics/recurring_revenue", headers=headers)
    ).json()
    assert detail["metric"]["key"] == "recurring_revenue"
    assert detail["observations"][0]["value"] == 100000.0
    assert detail["targets"][0]["status"] in ("on_track", "at_risk", "slipped")

    targets = (await client.get(f"{BUS}/targets", headers=headers)).json()
    assert targets["advisory_only"] is True
    assert targets["total"] == 1
    target_row = targets["targets"][0]
    assert target_row["metric_key"] == "recurring_revenue"
    assert target_row["period_label"] == "FY2026"
    assert target_row["gap"] == 100000.0
    target_id = target_row["target_id"]

    target_detail = (
        await client.get(f"{BUS}/targets/{target_id}", headers=headers)
    ).json()
    assert target_detail["target"]["status"] == target_row["status"]
    assert target_detail["target"]["gap"] == 100000.0

    forecasts = (await client.get(f"{BUS}/forecasts", headers=headers)).json()
    assert forecasts["advisory_only"] is True
    assert forecasts["total"] == 1
    assert forecasts["forecasts"][0]["midpoint"] == 140000.0
    assert forecasts["forecasts"][0]["forecast_type"] == "base"

    drivers = (await client.get(f"{BUS}/drivers", headers=headers)).json()
    assert drivers["total"] == 1
    assert drivers["drivers"][0]["driver_key"] == "enterprise_velocity"
    assert drivers["drivers"][0]["kind_label"] in (
        "linked to", "strongly associated with", "evidence indicates",
    )

    performance = (await client.get(f"{BUS}/performance", headers=headers)).json()
    assert performance["scope"] == "org_wide"
    assert performance["health"]["score"] <= 100
    assert performance["metrics"]["total"] == 1
    assert performance["summary"]
    assert len(performance["history"]) >= 1

    behind = (
        await client.get(f"{BUS}/behind-target", headers=headers)
    ).json()
    assert behind["advisory_only"] is True
    assert behind["metric"]["key"] == "recurring_revenue"
    assert behind["target"]["gap"] == 100000.0
    assert any(d["title"] == "Enterprise deal velocity" for d in behind["drivers"])
    assert any(w["kind"] == "close_gap" for w in behind["what_to_do"])
    assert behind["summary"]

    recommendations = (
        await client.get(f"{BUS}/recommendations", headers=headers)
    ).json()
    assert recommendations["advisory_only"] is True
    assert recommendations["total"] >= 1
    assert all("why" in r or "reason" in r for r in recommendations["recommendations"])


async def test_brain_routes_business_questions(client, db_session_factory):
    org = await register_org(client, email="4g6_sur2@test.co")
    headers = org["headers"]

    await _metric(client, headers)
    await _outcome(client, headers, "recurring_revenue", 100000.0,
                   "2026-07-31T00:00:00+00:00")
    await _drain(db_session_factory)
    target_resp = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "recurring_revenue", "target_value": 200000.0,
              "end_at": (date.today() + timedelta(days=200)).isoformat(),
              "period_label": "FY2026", "belief": "likely"},
        headers=headers,
    )
    assert target_resp.status_code == 200, target_resp.text
    forecast_resp = await client.post(
        f"{BUS}/forecasts",
        json={"metric_key": "recurring_revenue", "horizon_label": "2026-Q4",
              "forecast_type": "base", "midpoint": 140000.0},
        headers=headers,
    )
    assert forecast_resp.status_code == 200, forecast_resp.text
    await _drain(db_session_factory)

    behind = await _ask(client, headers, "why are we behind target on revenue?")
    assert behind["intent"] == "business_performance"
    assert behind["scope"] == "org"
    assert behind["advisory_only"] is True
    assert behind["metric"]["key"] == "recurring_revenue"
    assert behind["target"]["gap"] == 100000.0

    performing = await _ask(client, headers, "how is the business performing?")
    assert performing["intent"] == "business_performance"
    assert performing["scope"] == "org"
    assert performing["health"]["state"] in ("healthy", "concerned", "at_risk")

    forecast = await _ask(client, headers, "what is the revenue forecast?")
    assert forecast["intent"] == "business_performance"
    assert forecast["total"] == 1
    assert forecast["forecasts"][0]["midpoint"] == 140000.0

    drivers = await _ask(client, headers, "what is driving revenue growth?")
    assert drivers["intent"] == "business_performance"


async def test_record_and_update_flows(client, db_session_factory):
    org = await register_org(client, email="4g6_sur3@test.co")
    headers = org["headers"]

    created = await _metric(client, headers, key="net_revenue_retention",
                            label="NRR", kind="retention",
                            direction="up_is_good", unit="ratio")
    assert created["created"] is True
    await _drain(db_session_factory)

    updated = await client.post(
        f"{BUS}/metrics",
        json={"key": "net_revenue_retention", "kind": "retention",
              "direction": "up_is_good", "label": "Net Revenue Retention (NRR)"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["created"] is False
    await _drain(db_session_factory)

    await _outcome(client, headers, "net_revenue_retention", 1.08,
                   "2026-07-31T00:00:00+00:00", source="customer")
    await _drain(db_session_factory)

    metrics = (await client.get(f"{BUS}/metrics", headers=headers)).json()
    assert metrics["total"] == 1
    assert metrics["metrics"][0]["label"] == "Net Revenue Retention (NRR)"
    assert metrics["metrics"][0]["current"] == 1.08

    # target update (created -> updated) keeps one live row and refreshes
    made = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "net_revenue_retention", "target_value": 1.10,
              "end_at": "2026-12-31", "period_label": "FY2026"},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    assert made.json()["created"] is True
    await _drain(db_session_factory)
    revised = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "net_revenue_retention", "target_value": 1.12,
              "end_at": "2026-12-31", "period_label": "FY2026"},
        headers=headers,
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["created"] is False
    await _drain(db_session_factory)

    targets = (await client.get(f"{BUS}/targets", headers=headers)).json()
    assert targets["total"] == 1
    assert targets["targets"][0]["target_value"] == 1.12


async def test_outcome_lazily_creates_metric_from_api(client, db_session_factory):
    org = await register_org(client, email="4g6_sur4@test.co")
    headers = org["headers"]

    await _outcome(client, headers, "churn_rate", 4.2,
                   "2026-07-31T00:00:00+00:00", source="measurement")
    await _drain(db_session_factory)

    metrics = (await client.get(f"{BUS}/metrics", headers=headers)).json()
    assert metrics["total"] == 1
    assert metrics["metrics"][0]["key"] == "churn_rate"
    assert metrics["metrics"][0]["current"] == 4.2


async def test_performance_scope_isolation_via_api(client, db_session_factory):
    org = await register_org(client, email="4g6_sur5@test.co")
    headers = org["headers"]

    await _metric(client, headers, key="org_revenue")
    await _outcome(client, headers, "org_revenue", 100000.0,
                   "2026-07-31T00:00:00+00:00")
    await client.post(
        f"{BUS}/metrics",
        json={"key": "bu_revenue", "label": "BU Revenue", "kind": "revenue",
              "direction": "up_is_good", "unit": "usd",
              "scope": "business_unit", "scope_entity_id": "bu-1"},
        headers=headers,
    )
    await _outcome(client, headers, "bu_revenue", 5000.0,
                   "2026-07-31T00:00:00+00:00")
    await _drain(db_session_factory)

    org_wide = (
        await client.get(f"{BUS}/performance", headers=headers)
    ).json()
    assert org_wide["metrics"]["total"] == 1
    assert org_wide["metrics"]["trajectories"][0]["metric_key"] == "org_revenue"

    bu = (
        await client.get(
            f"{BUS}/performance", headers=headers,
            params={"scope": "business_unit", "scope_entity_id": "bu-1"},
        )
    ).json()
    assert bu["scope_entity_id"] == "bu-1"
    assert bu["metrics"]["total"] == 1
    assert bu["metrics"]["trajectories"][0]["metric_key"] == "bu_revenue"