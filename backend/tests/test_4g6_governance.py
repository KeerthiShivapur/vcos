"""Slice 4G.6 — governance: the event catalog, route validation, RBAC scope
gating, event-bus wiring and multi-tenant isolation.

Every write is governed (auth + scope), every business.* event is
documented, and a scoped reader never sees the org-wide business view.
"""

from sqlalchemy import select

from app.models.business_performance import BusinessMetric, BusinessTarget
from app.models.notification import Event
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
BUS = f"{BRAIN}/execution/business"

G4_6_EVENTS = {
    "business.metric.created",
    "business.metric.updated",
    "business.outcome.recorded",
    "business.target.created",
    "business.target.updated",
    "business.forecast.created",
    "business.forecast.updated",
    "business.driver.detected",
    "business.performance.changed",
}


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


async def test_catalog_documents_all_4g6_events():
    from app.events.event_models import EVENT_CATALOG

    assert G4_6_EVENTS <= set(EVENT_CATALOG)


async def test_business_routes_validate_enum_fields(client, db_session_factory):
    org = await register_org(client, email="4g6_gov2@test.co")
    headers = org["headers"]

    bad_kind = await client.post(
        f"{BUS}/metrics",
        json={"key": "k1", "kind": "voodoo", "direction": "up_is_good"},
        headers=headers,
    )
    assert bad_kind.status_code == 400
    assert "kind" in bad_kind.json()["detail"]

    bad_direction = await client.post(
        f"{BUS}/metrics",
        json={"key": "k1", "kind": "revenue", "direction": "sideways"},
        headers=headers,
    )
    assert bad_direction.status_code == 400
    assert "direction" in bad_direction.json()["detail"]

    await _drain(db_session_factory)
    await client.post(
        f"{BUS}/metrics",
        json={"key": "recurring_revenue", "kind": "revenue",
              "direction": "up_is_good"},
        headers=headers,
    )
    await _drain(db_session_factory)

    bad_source = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": "recurring_revenue", "value": 10, "source": "rumor"},
        headers=headers,
    )
    assert bad_source.status_code == 400
    assert "source" in bad_source.json()["detail"]

    no_value = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": "recurring_revenue", "source": "financial"},
        headers=headers,
    )
    assert no_value.status_code == 400

    unknown_metric = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "does-not-exist", "target_value": 100,
              "end_at": "2026-12-31", "period_label": "FY2026"},
        headers=headers,
    )
    assert unknown_metric.status_code == 404

    no_metric = await client.post(
        f"{BUS}/targets",
        json={"target_value": 100, "end_at": "2026-12-31", "period_label": "FY2026"},
        headers=headers,
    )
    assert no_metric.status_code == 400

    bad_confidence = await client.post(
        f"{BUS}/forecasts",
        json={"metric_key": "recurring_revenue", "horizon_label": "Q4",
              "forecast_type": "base", "confidence": 7},
        headers=headers,
    )
    assert bad_confidence.status_code == 400

    bad_strength = await client.post(
        f"{BUS}/drivers",
        json={"key": "d1", "title": "d", "driver_type": "customer",
              "strength": "absolute", "direction": "toward",
              "impact_shape": "aggregation"},
        headers=headers,
    )
    assert bad_strength.status_code == 400
    assert "strength" in bad_strength.json()["detail"]

    bad_shape = await client.post(
        f"{BUS}/drivers",
        json={"key": "d1", "title": "d", "driver_type": "customer",
              "strength": "strong", "direction": "toward",
              "impact_shape": "cube"},
        headers=headers,
    )
    assert bad_shape.status_code == 400


async def test_writes_require_authentication(client):
    response = await client.post(
        f"{BUS}/metrics",
        json={"key": "x", "kind": "revenue", "direction": "up_is_good"},
    )
    assert response.status_code in (401, 403)


async def test_scoped_reader_sees_no_business_view(client, db_session_factory):
    org = await register_org(client, email="4g6_gov4@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await client.post(
        f"{BUS}/metrics",
        json={"key": "recurring_revenue", "kind": "revenue",
              "direction": "up_is_good"},
        headers=headers,
    )
    await _drain(db_session_factory)

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4g6 scope", "scope_type": "organization", "entity_id": org_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped_headers = await invite_scoped_reader(
        client, headers, scope.json()["id"], "reader4g6@test.co"
    )

    metrics = await client.get(f"{BUS}/metrics", headers=scoped_headers)
    assert metrics.status_code == 404
    performance = await client.get(f"{BUS}/performance", headers=scoped_headers)
    assert performance.status_code == 404
    behind = await client.get(f"{BUS}/behind-target", headers=scoped_headers)
    assert behind.status_code == 404
    recommendations = await client.get(
        f"{BUS}/recommendations", headers=scoped_headers
    )
    assert recommendations.status_code == 404

    write = await client.post(
        f"{BUS}/metrics",
        json={"key": "x", "kind": "revenue", "direction": "up_is_good"},
        headers=scoped_headers,
    )
    assert write.status_code in (403, 404)


async def test_event_bus_wires_events_to_engine(client, db_session_factory):
    org = await register_org(client, email="4g6_gov7@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    created = await client.post(
        f"{BUS}/metrics",
        json={"key": "recurring_revenue", "kind": "revenue",
              "direction": "up_is_good"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        events = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name == "business.metric.created",
                    )
                )
            ).scalars().all()
        )
        assert len(events) == 1
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert metric.source_event_id == events[0].id
        assert metric.key == "recurring_revenue"

    outcome = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": "recurring_revenue", "value": 100000.0,
              "observed_at": "2026-07-31T00:00:00+00:00", "source": "financial"},
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    await _drain(db_session_factory)

    updated = await client.post(
        f"{BUS}/targets",
        json={"metric_key": "recurring_revenue", "target_value": 120000.0,
              "end_at": "2026-12-31", "period_label": "FY2026"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        target_events = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name == "business.target.created",
                    )
                )
            ).scalars().all()
        )
        assert len(target_events) == 1
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.source_event_id == target_events[0].id
        assert target.status == "on_track"


async def test_multi_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="4g6_gov8a@test.co")
    org_b = await register_org(client, email="4g6_gov8b@test.co")

    await client.post(
        f"{BUS}/metrics",
        json={"key": "tenant_a_revenue", "kind": "revenue",
              "direction": "up_is_good"},
        headers=org_a["headers"],
    )
    await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": "tenant_a_revenue", "value": 100000.0,
              "observed_at": "2026-07-31T00:00:00+00:00", "source": "financial"},
        headers=org_a["headers"],
    )
    await _drain(db_session_factory)

    metrics_b = (
        await client.get(f"{BUS}/metrics", headers=org_b["headers"])
    ).json()
    assert metrics_b["total"] == 0
    assert metrics_b["metrics"] == []

    performance_a = (
        await client.get(f"{BUS}/performance", headers=org_a["headers"])
    ).json()
    assert performance_a["metrics"]["total"] == 1
    assert performance_a["metrics"]["trajectories"][0]["metric_key"] == "tenant_a_revenue"

    performance_b = (
        await client.get(f"{BUS}/performance", headers=org_b["headers"])
    )
    assert performance_b.status_code == 404