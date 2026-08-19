"""Slice 4G.6 — model surface: the canonical business performance tables
exist in metadata with the exact-once unique constraints, the canonical
vocabularies are exported, and rows persist with their JSON evidence.

The table names and constraints are the contract: change-driven writes rely
on exact-once (organization_id, ..., source_event_id) uniqueness for
observations, snapshots, history and links, and key-only uniqueness for the
live single-row entities (metric, driver, target, forecast).
"""

from sqlalchemy import select

from app.db.database import Base
from app.models.business_performance import (
    COMPUTE_MODES,
    DRIVER_STRENGTHS,
    FORECAST_TYPES,
    HEALTH_STATES,
    LINK_KINDS,
    METRIC_DIRECTIONS,
    METRIC_KINDS,
    OBSERVATION_LABELS,
    SNAPSHOT_SCOPES,
    TARGET_STATUSES,
    BusinessDriver,
    BusinessForecast,
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceHistory,
    BusinessPerformanceLink,
    BusinessPerformanceSnapshot,
    BusinessTarget,
)
from tests.conftest import register_org


async def test_4g6_tables_registered_in_metadata():
    tables = {
        "business_metrics",
        "business_metric_observations",
        "business_drivers",
        "business_targets",
        "business_forecasts",
        "business_performance_snapshots",
        "business_performance_history",
        "business_performance_links",
    }
    assert tables <= set(Base.metadata.tables)


async def test_exact_once_unique_constraints():
    def constraints(table_name):
        return {
            tuple(c.columns.keys())
            for c in Base.metadata.tables[table_name].constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }

    assert ("organization_id", "metric_id", "observed_at", "source_event_id") in constraints(
        "business_metric_observations"
    )
    assert ("organization_id", "scope", "scope_entity_id", "period_label",
            "compute_mode", "source_event_id") in constraints(
        "business_performance_snapshots"
    )
    assert ("organization_id", "scope", "scope_entity_id", "period_label",
            "compute_mode", "source_event_id") in constraints(
        "business_performance_history"
    )
    assert ("organization_id", "entity_type", "entity_id", "target_type",
            "target_id", "kind", "source_event_id") in constraints(
        "business_performance_links"
    )
    # live single-row entities: key-only uniqueness (exact-once in the engine)
    assert ("organization_id", "key") in constraints("business_metrics")
    assert ("organization_id", "key") in constraints("business_drivers")
    assert ("organization_id", "metric_id", "period_label") in constraints("business_targets")
    assert ("organization_id", "metric_id", "horizon_label", "forecast_type") in constraints(
        "business_forecasts"
    )


async def test_canonical_vocabularies_exported():
    assert "revenue" in METRIC_KINDS
    assert "up_is_good" in METRIC_DIRECTIONS
    assert "down_is_good" in METRIC_DIRECTIONS
    assert "actual" in OBSERVATION_LABELS
    assert "strong" in DRIVER_STRENGTHS
    assert "slipped" in TARGET_STATUSES
    assert "missed" in TARGET_STATUSES
    assert "base" in FORECAST_TYPES
    assert "org_wide" in SNAPSHOT_SCOPES
    assert "business_unit" in SNAPSHOT_SCOPES
    assert "observed" in COMPUTE_MODES
    assert "projected" in COMPUTE_MODES
    assert "healthy" in HEALTH_STATES
    assert "linked_to" in LINK_KINDS


async def test_rows_persist_with_json_evidence(client, db_session_factory):
    org = await register_org(client, email="4g6_mod4@test.co")
    org_id = org["organization"]["id"]

    async with db_session_factory() as db:
        metric = BusinessMetric(
            organization_id=org_id, key="recurring_revenue",
            label="Recurring Revenue", kind="revenue",
            direction="up_is_good", unit="usd",
            scope="org_wide", last_value=100000.0,
            source_event_id="evt-model-0",
        )
        db.add(metric)
        await db.flush()

        observation = BusinessMetricObservation(
            organization_id=org_id, metric_id=metric.id,
            value=100000.0, observed_at=__import__("datetime")
            .datetime(2026, 7, 31, tzinfo=__import__("datetime").timezone.utc),
            unit="usd", label="actual", source="financial",
            provenance="business.outcome.recorded:evt-model-1",
            source_event_id="evt-model-1",
        )
        db.add(observation)
        await db.flush()

        driver = BusinessDriver(
            organization_id=org_id, key="enterprise_velocity",
            title="Enterprise deal velocity", driver_type="customer",
            strength="strong", direction="toward",
            metric_keys_json=["recurring_revenue"],
            monetized_impact=400000.0, source_event_id="evt-model-2",
        )
        db.add(driver)
        await db.flush()

        target = BusinessTarget(
            organization_id=org_id, metric_id=metric.id,
            metric_label="Recurring Revenue", target_value=120000.0,
            end_at=__import__("datetime").date(2026, 12, 31),
            period_label="FY2026", status="on_track", belief="likely",
            owner_label="CFO",
            initiative_labels_json=["Expand enterprise footprint"],
            source_event_id="evt-model-3",
        )
        db.add(target)
        await db.flush()

        forecast = BusinessForecast(
            organization_id=org_id, metric_id=metric.id,
            metric_label="Recurring Revenue", forecast_type="base",
            horizon_label="2026-Q4", basis="last 6 months growth",
            midpoint_value=115000.0, confidence=0.6,
            risk_factors_json=["enterprise deal slippage"],
            source_event_id="evt-model-4",
        )
        db.add(forecast)
        await db.flush()

        snapshot = BusinessPerformanceSnapshot(
            organization_id=org_id, scope="org_wide",
            compute_mode="observed", period_label="2026-07",
            health_score=78, health_state="healthy",
            health_dimensions_json=[{"key": "growth", "score": 78}],
            metric_trajectories_json=[{"metric_key": "recurring_revenue"}],
            driver_links_json=[{"driver_key": "enterprise_velocity"}],
            gains_losses_json=[{"label": "revenue", "delta": 5000.0}],
            links_json=[{"target_type": "strategy"}],
            summary_narrative="Revenue is growing.",
            event_name="business.outcome.recorded",
            source_event_id="evt-model-5",
        )
        db.add(snapshot)

        history = BusinessPerformanceHistory(
            organization_id=org_id, scope="org_wide",
            compute_mode="observed", period_label="2026-07",
            health_score=78, health_state="healthy",
            payload_json={"summary_narrative": "Revenue is growing."},
            event_name="business.outcome.recorded",
            source_event_id="evt-model-5",
            occurred_at=__import__("datetime")
            .datetime(2026, 7, 31, tzinfo=__import__("datetime").timezone.utc),
        )
        db.add(history)

        link = BusinessPerformanceLink(
                organization_id=org_id, entity_type="driver",
                entity_id=driver.id, target_type="knowledge",
                target_id="topic-1", kind="linked_to", weight=0.9,
                reasoning="Topic covers the driver.",
                source_event_id="evt-model-2",
            )
        db.add(link)
        await db.commit()

        saved = (
            await db.execute(
                select(BusinessMetric).where(
                    BusinessMetric.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert saved.label == "Recurring Revenue"
        assert saved.last_value == 100000.0

        obs_saved = (
            await db.execute(
                select(BusinessMetricObservation).where(
                    BusinessMetricObservation.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert obs_saved.source_event_id == "evt-model-1"
        assert obs_saved.provenance.startswith("business.outcome.recorded:")

        driver_saved = (
            await db.execute(
                select(BusinessDriver).where(
                    BusinessDriver.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert driver_saved.metric_keys_json == ["recurring_revenue"]

        target_saved = (
            await db.execute(
                select(BusinessTarget).where(
                    BusinessTarget.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert target_saved.status == "on_track"
        assert target_saved.initiative_labels_json == ["Expand enterprise footprint"]

        forecast_saved = (
            await db.execute(
                select(BusinessForecast).where(
                    BusinessForecast.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert forecast_saved.midpoint_value == 115000.0
        assert forecast_saved.risk_factors_json == ["enterprise deal slippage"]

        snapshot_saved = (
            await db.execute(
                select(BusinessPerformanceSnapshot).where(
                    BusinessPerformanceSnapshot.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert snapshot_saved.health_state == "healthy"
        assert snapshot_saved.health_dimensions_json[0]["key"] == "growth"

        link_saved = (
            await db.execute(
                select(BusinessPerformanceLink).where(
                    BusinessPerformanceLink.organization_id == org_id,
                )
            )
        ).scalars().one()
        assert link_saved.kind == "linked_to"
        assert link_saved.weight == 0.9
