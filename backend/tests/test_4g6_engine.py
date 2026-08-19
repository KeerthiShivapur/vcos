"""Slice 4G.6 — Commercial & Business Performance Intelligence engine.

Under test:

* metric.created / metric.updated: one live canonical metric per key,
  observations land exact-once and update the last-value cache,
* outcome.recorded: an actual observation on a metric (lazy metric
  creation when the metric does not exist yet),
* target.created / target.updated: deterministic status transitions
  (pending -> on_track / at_risk / slipped -> delivered / missed) with a
  review trail, direction-aware (up_is_good / down_is_good),
* forecast.created / updated: live forecast per (metric, horizon, type),
* driver.detected: live driver with deterministic link language
  (strength -> linked_to / strongly_associated_with / evidence_indicates),
* exact-once replays: the same source_event_id converges to the same rows,
* change-driven scope isolation: events refresh ONLY the affected metric's
  scope snapshot (org_wide vs business_unit),
* the flagship behind_target chain: target -> drivers -> customers ->
  knowledge -> strategy -> projects -> capacity -> decisions -> what to do,
* non-business events are ignored.
"""

from types import SimpleNamespace

from sqlalchemy import select

from app.intelligence.business_performance_engine import (
    DRIVER_STRENGTH_KIND,
    LINK_LABELS,
    business_performance_engine,
)
from app.models.business_performance import (
    BusinessDriver,
    BusinessForecast,
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceHistory,
    BusinessPerformanceSnapshot,
    BusinessTarget,
)
from app.models.execution_strategy import CompanyGoal
from app.models.knowledge import KnowledgeTopic
from tests.conftest import register_org


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


async def _publish(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _metric_events(db_session_factory, org_id, actor_id, key="recurring_revenue"):
    await _publish(db_session_factory, org_id, actor_id, "business.metric.created", {
        "organization_id": org_id,
        "key": key,
        "label": "Recurring Revenue",
        "kind": "revenue",
        "direction": "up_is_good",
        "unit": "usd",
        "period_granularity": "monthly",
        "scope": "org_wide",
    })
    await _publish(db_session_factory, org_id, actor_id, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": key,
        "value": 100000.0,
        "observed_at": "2026-07-31T00:00:00+00:00",
        "source": "financial",
    })


async def _counts(db_session_factory, org_id):
    async with db_session_factory() as db:
        return {
            "metrics": len(list(
                (await db.execute(
                    select(BusinessMetric).where(
                        BusinessMetric.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "observations": len(list(
                (await db.execute(
                    select(BusinessMetricObservation).where(
                        BusinessMetricObservation.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "targets": len(list(
                (await db.execute(
                    select(BusinessTarget).where(
                        BusinessTarget.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "drivers": len(list(
                (await db.execute(
                    select(BusinessDriver).where(
                        BusinessDriver.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "forecasts": len(list(
                (await db.execute(
                    select(BusinessForecast).where(
                        BusinessForecast.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "snapshots": len(list(
                (await db.execute(
                    select(BusinessPerformanceSnapshot).where(
                        BusinessPerformanceSnapshot.organization_id == org_id,
                    )
                )).scalars().all()
            )),
            "history": len(list(
                (await db.execute(
                    select(BusinessPerformanceHistory).where(
                        BusinessPerformanceHistory.organization_id == org_id,
                    )
                )).scalars().all()
            )),
        }


async def test_metric_lifecycle_and_snapshot(client, db_session_factory):
    org = await register_org(client, email="4g6_eng1@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)

    counts = await _counts(db_session_factory, org_id)
    assert counts["metrics"] == 1
    assert counts["observations"] == 1
    assert counts["snapshots"] == 2  # created + outcome
    assert counts["history"] == 2

    async with db_session_factory() as db:
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org_id,
                    BusinessMetric.key == "recurring_revenue",
                )
            )
        ).scalars().one()
        assert metric.kind == "revenue"
        assert metric.direction == "up_is_good"
        assert metric.last_value == 100000.0
        assert metric.scope == "org_wide"

        obs = (
            await db.execute(
                select(BusinessMetricObservation).where(
                    BusinessMetricObservation.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert obs.value == 100000.0
        assert obs.label == "actual"
        assert obs.source == "financial"
        assert obs.provenance.startswith("business.outcome.recorded:")

    # update: label change + a second observation via the payload value
    await _publish(db_session_factory, org_id, actor, "business.metric.updated", {
        "organization_id": org_id,
        "key": "recurring_revenue",
        "label": "Recurring Revenue (ARR)",
        "value": 105000.0,
        "observed_at": "2026-08-15T00:00:00+00:00",
    })
    counts = await _counts(db_session_factory, org_id)
    assert counts["metrics"] == 1
    assert counts["observations"] == 2

    async with db_session_factory() as db:
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert metric.label == "Recurring Revenue (ARR)"
        assert metric.last_value == 105000.0
        assert metric.last_observed_at is not None

        result = await business_performance_engine.metrics(
            db, organization_id=org_id,
        )
        item = result["metrics"][0]
        assert item["current"] == 105000.0
        assert item["previous"] == 100000.0
        assert item["trend"] == "improving"


async def test_exact_once_replay_converges(client, db_session_factory):
    org = await register_org(client, email="4g6_eng2@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)

    async with db_session_factory() as db:
        obs = (
            await db.execute(
                select(BusinessMetricObservation).where(
                    BusinessMetricObservation.organization_id == org_id,
                )
            )
        ).scalars().one()
        event_id = obs.source_event_id
        await business_performance_engine.record_event(
            db, organization_id=org_id,
            event=SimpleNamespace(name="business.outcome.recorded", id=event_id),
            payload={
                "organization_id": org_id,
                "metric_key": "recurring_revenue",
                "value": 100000.0,
                "observed_at": "2026-07-31T00:00:00+00:00",
                "source": "financial",
            },
        )
        await db.commit()

    counts = await _counts(db_session_factory, org_id)
    assert counts["metrics"] == 1
    assert counts["observations"] == 1
    assert counts["snapshots"] == 2
    assert event_id


async def test_target_status_lifecycle(client, db_session_factory):
    org = await register_org(client, email="4g6_eng3@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)
    await _publish(db_session_factory, org_id, actor, "business.target.created", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "target_value": 120000.0,
        "end_at": "2026-12-31",
        "period_label": "FY2026",
        "belief": "likely",
        "owner_label": "CFO",
        "initiative_labels": ["Expand enterprise footprint"],
    })

    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        # 100000 vs 120000 -> progress 0.833 -> on_track
        assert target.status == "on_track"
        assert target.period_label == "FY2026"

    # decline -> still on_track at 0.73 but moves at 0.6
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "value": 88000.0,
        "observed_at": "2026-08-31T00:00:00+00:00",
        "source": "financial",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.status in ("on_track", "at_risk")
        assert target.reviews_json  # a review note exists for the transition

    # fall further -> slipped
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "value": 50000.0,
        "observed_at": "2026-09-30T00:00:00+00:00",
        "source": "financial",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.status == "slipped"

    # exceed the target -> delivered (terminal)
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "value": 125000.0,
        "observed_at": "2026-10-31T00:00:00+00:00",
        "source": "financial",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.status == "delivered"


async def test_target_missed_after_deadline(client, db_session_factory):
    org = await register_org(client, email="4g6_eng4@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)
    await _publish(db_session_factory, org_id, actor, "business.target.created", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "target_value": 200000.0,
        "end_at": "2026-01-31",
        "period_label": "Q1-2026",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.status == "missed"


async def test_target_direction_down_is_good(client, db_session_factory):
    org = await register_org(client, email="4g6_eng5@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _publish(db_session_factory, org_id, actor, "business.metric.created", {
        "organization_id": org_id,
        "key": "customer_churn",
        "label": "Customer Churn",
        "kind": "churn",
        "direction": "down_is_good",
        "unit": "pct",
        "period_granularity": "monthly",
    })
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "customer_churn",
        "value": 8.0,
        "observed_at": "2026-07-31T00:00:00+00:00",
        "source": "measurement",
    })
    await _publish(db_session_factory, org_id, actor, "business.target.created", {
        "organization_id": org_id,
        "metric_key": "customer_churn",
        "target_value": 5.0,
        "end_at": "2026-12-31",
        "period_label": "FY2026",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        # churn 8 vs target 5 (down_is_good): progress 5/8 = 0.625 -> at_risk
        assert target.status == "at_risk"

    # improvement below the target -> delivered
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "customer_churn",
        "value": 3.5,
        "observed_at": "2026-08-31T00:00:00+00:00",
        "source": "measurement",
    })
    async with db_session_factory() as db:
        target = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target.status == "delivered"


async def test_forecast_and_driver_lifecycle(client, db_session_factory):
    org = await register_org(client, email="4g6_eng6@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)
    await _publish(db_session_factory, org_id, actor, "business.forecast.created", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "horizon_label": "2026-Q4",
        "forecast_type": "base",
        "basis": "last 6 months growth",
        "midpoint": 115000.0,
        "low": 100000.0,
        "high": 130000.0,
        "confidence": 0.6,
        "risk_factors": ["enterprise deal slippage"],
    })
    await _publish(db_session_factory, org_id, actor, "business.driver.detected", {
        "organization_id": org_id,
        "key": "enterprise_velocity",
        "title": "Enterprise deal velocity",
        "driver_type": "customer",
        "strength": "strong",
        "direction": "toward",
        "impact_shape": "aggregation",
        "metric_keys": ["recurring_revenue"],
        "monetized_impact": 400000.0,
    })

    counts = await _counts(db_session_factory, org_id)
    assert counts["forecasts"] == 1
    assert counts["drivers"] == 1

    async with db_session_factory() as db:
        forecast = (
            await db.execute(
                select(BusinessForecast).where(
                    BusinessForecast.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert forecast.horizon_label == "2026-Q4"
        assert forecast.midpoint_value == 115000.0
        assert forecast.confidence == 0.6
        assert forecast.risk_factors_json == ["enterprise deal slippage"]

        driver = (
            await db.execute(
                select(BusinessDriver).where(
                    BusinessDriver.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert driver.metric_keys_json == ["recurring_revenue"]
        kind = DRIVER_STRENGTH_KIND[driver.strength]
        assert kind == "linked_to"
        assert LINK_LABELS[kind] == "linked to"

    # update the forecast (same horizon+type -> one live row)
    await _publish(db_session_factory, org_id, actor, "business.forecast.updated", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "horizon_label": "2026-Q4",
        "forecast_type": "base",
        "midpoint": 108000.0,
    })
    counts = await _counts(db_session_factory, org_id)
    assert counts["forecasts"] == 1
    async with db_session_factory() as db:
        forecast = (
            await db.execute(
                select(BusinessForecast).where(
                    BusinessForecast.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert forecast.midpoint_value == 108000.0


async def test_outcome_lazily_creates_metric(client, db_session_factory):
    org = await register_org(client, email="4g6_eng7@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "net_revenue_retention",
        "metric_label": "Net Revenue Retention",
        "value": 1.08,
        "observed_at": "2026-07-31T00:00:00+00:00",
        "source": "customer",
        "unit": "ratio",
    })
    async with db_session_factory() as db:
        metric = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert metric.key == "net_revenue_retention"
        assert metric.last_value == 1.08
        assert metric.kind == "other"  # no kind declared -> canonical default


async def test_non_business_events_ignored(client, db_session_factory):
    org = await register_org(client, email="4g6_eng8@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _publish(db_session_factory, org_id, actor, "project.created", {
        "organization_id": org_id,
        "project_id": "p1",
    })
    counts = await _counts(db_session_factory, org_id)
    assert counts["metrics"] == 0
    assert counts["snapshots"] == 0
    assert counts["history"] == 0


async def test_scope_isolation_org_wide_vs_business_unit(client, db_session_factory):
    org = await register_org(client, email="4g6_eng9@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor, key="org_revenue")
    await _publish(db_session_factory, org_id, actor, "business.metric.created", {
        "organization_id": org_id,
        "key": "bu_revenue",
        "label": "BU Revenue",
        "kind": "revenue",
        "direction": "up_is_good",
        "unit": "usd",
        "scope": "business_unit",
        "scope_entity_id": "bu-1",
    })
    await _publish(db_session_factory, org_id, actor, "business.outcome.recorded", {
        "organization_id": org_id,
        "metric_key": "bu_revenue",
        "value": 5000.0,
        "observed_at": "2026-07-31T00:00:00+00:00",
        "source": "financial",
    })

    async with db_session_factory() as db:
        org_wide = await business_performance_engine.performance(
            db, organization_id=org_id, scope="org_wide",
        )
        assert org_wide is not None
        assert org_wide["metrics"]["total"] == 1  # only org_revenue

        bu = await business_performance_engine.performance(
            db, organization_id=org_id, scope="business_unit",
            scope_entity_id="bu-1",
        )
        assert bu is not None
        assert bu["metrics"]["total"] == 1  # only bu_revenue
        assert bu["scope_entity_id"] == "bu-1"
        trajectory = bu["metrics"]["trajectories"][0]
        assert trajectory["metric_key"] == "bu_revenue"


async def test_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="4g6_eng10a@test.co")
    org_b = await register_org(client, email="4g6_eng10b@test.co")
    org_a_id = org_a["organization"]["id"]
    org_b_id = org_b["organization"]["id"]

    await _metric_events(db_session_factory, org_a_id, org_a["user"]["id"])
    await _metric_events(db_session_factory, org_b_id, org_b["user"]["id"],
                         key="other_revenue")

    async with db_session_factory() as db:
        result_a = await business_performance_engine.metrics(
            db, organization_id=org_a_id,
        )
        result_b = await business_performance_engine.metrics(
            db, organization_id=org_b_id,
        )
        assert result_a["total"] == 1
        assert result_a["metrics"][0]["key"] == "recurring_revenue"
        assert result_b["total"] == 1
        assert result_b["metrics"][0]["key"] == "other_revenue"


async def test_explicit_performance_changed(client, db_session_factory):
    org = await register_org(client, email="4g6_eng11@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _publish(db_session_factory, org_id, actor, "business.performance.changed", {
        "organization_id": org_id,
        "scope": "org_wide",
    })
    async with db_session_factory() as db:
        perf = await business_performance_engine.performance(
            db, organization_id=org_id,
        )
        assert perf is not None
        assert perf["scope"] == "org_wide"
        assert perf["metrics"]["total"] == 0
        assert perf["summary"]  # narrative exists even with no metrics


async def test_behind_target_flagship_chain(client, db_session_factory):
    org = await register_org(client, email="4g6_eng12@test.co")
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]

    await _metric_events(db_session_factory, org_id, actor)
    await _publish(db_session_factory, org_id, actor, "business.target.created", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "target_value": 200000.0,
        "end_at": "2026-12-31",
        "period_label": "FY2026",
        "owner_label": "CFO",
        "initiative_labels": ["Expand enterprise footprint"],
    })
    await _publish(db_session_factory, org_id, actor, "business.driver.detected", {
        "organization_id": org_id,
        "key": "enterprise_velocity",
        "title": "Enterprise deal velocity",
        "driver_type": "customer",
        "strength": "strong",
        "direction": "toward",
        "metric_keys": ["recurring_revenue"],
        "monetized_impact": 400000.0,
    })
    await _publish(db_session_factory, org_id, actor, "business.forecast.created", {
        "organization_id": org_id,
        "metric_key": "recurring_revenue",
        "horizon_label": "2026-Q4",
        "forecast_type": "base",
        "basis": "last 6 months growth",
        "midpoint": 140000.0,
        "low": 120000.0,
        "high": 160000.0,
        "confidence": 0.6,
    })

    # strategy linkage: an active goal carrying this metric as its outcome
    async with db_session_factory() as db:
        db.add(CompanyGoal(
            organization_id=org_id,
            title="Grow recurring revenue",
            kind="growth",
            status="active",
            priority=1,
            metric_kind="recurring_revenue",
            metric_unit="usd",
            target_value=200000.0,
            current_value=100000.0,
        ))
        db.add(KnowledgeTopic(
            organization_id=org_id,
            name="enterprise deal velocity",
            category="sales",
        ))
        await db.commit()

    async with db_session_factory() as db:
        bt = await business_performance_engine.behind_target(
            db, organization_id=org_id,
        )
        assert bt is not None
        assert bt["target"]["status"] == "at_risk"  # 100000/200000 = 0.5 boundary
        assert bt["target"]["gap"] == 100000.0
        assert any(d["title"] == "Enterprise deal velocity" for d in bt["drivers"])
        assert bt["forecasts"][0]["midpoint"] == 140000.0
        assert any(c["goal"] == "Grow recurring revenue" for c in bt["strategy"])
        assert any(k["driver_key"] == "enterprise_velocity" for k in bt["knowledge"])
        assert any(w["kind"] == "close_gap" for w in bt["what_to_do"])
        assert bt["what_to_do"][0]["gap"] == 100000.0
        assert "evidence-backed" in " ".join(bt["summary"])
        assert bt["advisory_only"] is True
