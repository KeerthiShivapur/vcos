"""Slice 4H.6 - Step 2: temporal measurement helpers.

Under test (contract Steps 2 + L20/L21/L24/L27):

1.  valid actual -> actual: both sides recorded, explicit temporal basis,
    derived delta citing both source observations.
2.  missing baseline -> unknown (never zero).
3.  missing comparison -> unknown (never zero, never baseline).
4.  forecast observations are excluded from measurement truth.
5.  plan observations are excluded from measurement truth.
6.  estimated observations are excluded from measurement truth.
7.  derived delta carries basis = [baseline_id, comparison_id].
8.  no interpolation: a gap never fabricates an intermediate value.
9.  direction metadata stays canonical (up_is_good / down_is_good) and is
    never turned into a judgment.
10. determinism: same canonical rows => byte-identical result.
11. no writes: row counts and max(updated_at) unchanged.
12. no events emitted.
13. no LLM client on the helper path (source inspection).
14. anchor precedence: executed_at > approved_at > created_at; unknown
    decision -> None; unparseable anchor -> rejected, not invented.
15. linked-metric resolution: single link auto-selected, multiple links
    require an explicit metric, sibling org isolated.
"""

from datetime import datetime, timedelta, timezone

import inspect
import pytest
from sqlalchemy import func, select

from app.models.business_performance import (
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceLink,
)
from app.models.company_operating import CompanyDecision
from app.models.notification import Event as EventRow
from tests.conftest import register_org

_ANCHOR = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


async def _seed_decision(db_session_factory, org_id, decision_id, **kw):
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=decision_id,
            kind="hire", title="Perf decision", state="approved",
            approved_at=kw.pop("approved_at", _ANCHOR),
            executed_at=kw.pop("executed_at", None),
            source_event_id=f"evt:{decision_id}", **kw,
        ))
        await db.commit()


async def _seed_metric(db_session_factory, org_id, key="recurring_revenue",
                       direction="up_is_good"):
    async with db_session_factory() as db:
        metric = BusinessMetric(
            organization_id=org_id, key=key, label=key.title(),
            kind="revenue", direction=direction, unit="usd",
            scope="org_wide", last_value=0.0,
            source_event_id=f"evt:m-{key}",
        )
        db.add(metric)
        await db.commit()
        return metric.id


def _obs_at(days_offset):
    return _ANCHOR + timedelta(days=days_offset)


async def _seed_obs_at(db_session_factory, org_id, metric_id, value, when,
                       label="actual", seq=0):
    async with db_session_factory() as db:
        db.add(BusinessMetricObservation(
            organization_id=org_id, metric_id=metric_id, value=value,
            observed_at=when, label=label,
            source_event_id=f"evt:o-{metric_id}-{seq}-{label}-{when.isoformat()}",
        ))
        await db.commit()


async def _measure(db_session_factory, org_id, decision_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.decision_metric_measurement(
            db, organization_id=org_id, decision_id=decision_id, **kw,
        )
        await db.commit()
        return result


async def _window(db_session_factory, org_id, metric_id, anchor, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.metric_measurement_window(
            db, organization_id=org_id, metric_id=metric_id, anchor=anchor, **kw,
        )
        await db.commit()
        return result


async def _table_stats(db_session_factory, org_id):
    async with db_session_factory() as db:
        stats = {}
        for model in (CompanyDecision, BusinessMetric, BusinessMetricObservation,
                      BusinessPerformanceLink, EventRow):
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "organization_id"):
                stmt = stmt.where(model.organization_id == org_id)
            stats[model.__tablename__] = int(
                (await db.execute(stmt)).scalar_one() or 0)
        max_upd = await db.execute(
            select(func.max(CompanyDecision.updated_at))
            .where(CompanyDecision.organization_id == org_id)
        )
        stats["decision_max_updated"] = str(max_upd.scalar_one())
        return stats


# ----------------------------------------------------------------- 1-3, 7

async def test_actual_to_actual_recorded_with_derived_delta_and_basis(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s2_a@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-a")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 100.0,
                       _obs_at(-9), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 120.0,
                       _obs_at(10), seq=2)

    result = await _measure(db_session_factory, org_id, "dec:4h6s2-a",
                            metric_id=metric_id)
    assert result is not None and not result.get("rejected")
    m = result["measurement"]
    tb = m["temporal_basis"]
    assert set(tb) >= {"anchor", "baseline_as_of", "comparison_as_of", "window_days"}
    assert result["anchor_basis"] == "approved_at"
    assert m["baseline"]["truth_level"] == "recorded"
    assert m["baseline"]["value"] == 100.0
    assert m["comparison"]["truth_level"] == "recorded"
    assert m["comparison"]["value"] == 120.0
    d = m["delta"]
    assert d["truth_level"] == "derived"
    assert d["value"] == pytest.approx(20.0)
    assert d["percentage_delta"] == pytest.approx(20.0)
    assert set(d["basis"]) == {
        m["baseline"]["observation_id"], m["comparison"]["observation_id"],
    }


async def test_missing_baseline_is_unknown_not_zero(client, db_session_factory):
    org = await register_org(client, email="4h6s2_b@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-b")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 120.0,
                       _obs_at(5), seq=1)

    m = (await _measure(db_session_factory, org_id, "dec:4h6s2-b",
                        metric_id=metric_id))["measurement"]
    assert m["baseline"]["truth_level"] == "unknown"
    assert m["baseline"]["value"] is None
    assert m["baseline"]["reason"] == "no_actual_observation_at_or_before_anchor"
    assert m["delta"] is None


async def test_missing_comparison_is_unknown_not_zero(client, db_session_factory):
    org = await register_org(client, email="4h6s2_c@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-c")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 100.0,
                       _obs_at(-5), seq=1)

    m = (await _measure(db_session_factory, org_id, "dec:4h6s2-c",
                        metric_id=metric_id))["measurement"]
    assert m["comparison"]["truth_level"] == "unknown"
    assert m["comparison"]["value"] is None
    assert m["comparison"]["reason"] == (
        "no_actual_observation_after_anchor_within_window")
    assert m["delta"] is None


# ------------------------------------------------------------- 4-6, 8

@pytest.mark.parametrize("label", ["forecast", "plan", "estimated"])
async def test_non_actual_labels_excluded_but_counted(
    client, db_session_factory, label,
):
    org = await register_org(client, email=f"4h6s2_{label}@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, f"dec:4h6s2-{label}")
    metric_id = await _seed_metric(db_session_factory, org_id)
    # only a non-actual observation after the anchor: must NOT become the
    # comparison even though it is the only candidate in the window
    await _seed_obs_at(db_session_factory, org_id, metric_id, 150.0,
                       _obs_at(3), label=label, seq=1)

    m = (await _measure(db_session_factory, org_id, f"dec:4h6s2-{label}",
                        metric_id=metric_id))["measurement"]
    assert m["comparison"]["truth_level"] == "unknown"
    assert m["excluded_observations"].get(label) == 1
    assert m["honesty"]["forecast_excluded"] is True


async def test_no_interpolation_across_gap(client, db_session_factory):
    org = await register_org(client, email="4h6s2_gap@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-gap")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 100.0,
                       _obs_at(-30), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 140.0,
                       _obs_at(30), seq=2)

    m = (await _measure(db_session_factory, org_id, "dec:4h6s2-gap",
                        metric_id=metric_id))["measurement"]
    values = {m["baseline"]["value"], m["comparison"]["value"]}
    assert values == {100.0, 140.0}
    assert 120.0 not in values  # nothing synthesized between the gap
    assert m["delta"]["value"] == pytest.approx(40.0)


# ------------------------------------------------------------------ 9

@pytest.mark.parametrize("direction", ["up_is_good", "down_is_good"])
async def test_direction_preserved_never_judged(
    client, db_session_factory, direction,
):
    org = await register_org(client, email=f"4h6s2_dir_{direction}@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, f"dec:4h6s2-{direction}")
    metric_id = await _seed_metric(db_session_factory, org_id, direction=direction)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 50.0,
                       _obs_at(-2), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 40.0,
                       _obs_at(2), seq=2)

    m = (await _measure(db_session_factory, org_id, f"dec:4h6s2-{direction}",
                        metric_id=metric_id))["measurement"]
    assert m["metric"]["direction"] == direction
    assert m["delta"]["direction"] == direction
    assert m["delta"]["delta_sign"] == "negative"
    blob = repr(m)
    assert "good" not in blob.replace("up_is_good", "").replace("down_is_good", "")
    assert "improved" not in blob and "favorable" not in blob


# ----------------------------------------------------------------- 10-13

async def test_determinism_byte_identical(client, db_session_factory):
    org = await register_org(client, email="4h6s2_det@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-det")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 100.0,
                       _obs_at(-9), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 118.0,
                       _obs_at(9), seq=2)

    a = await _measure(db_session_factory, org_id, "dec:4h6s2-det",
                       metric_id=metric_id)
    b = await _measure(db_session_factory, org_id, "dec:4h6s2-det",
                       metric_id=metric_id)
    assert a == b  # no generated_at, no randomness


async def test_no_writes_no_events(client, db_session_factory):
    org = await register_org(client, email="4h6s2_ro@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-ro")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 100.0,
                       _obs_at(-9), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 125.0,
                       _obs_at(4), seq=2)

    before = await _table_stats(db_session_factory, org_id)
    await _measure(db_session_factory, org_id, "dec:4h6s2-ro", metric_id=metric_id)
    await _window(db_session_factory, org_id, metric_id, _ANCHOR)
    after = await _table_stats(db_session_factory, org_id)
    assert before == after


async def test_no_llm_on_helper_path():
    from app.intelligence import company_operating_engine as mod

    for name in ("decision_temporal_anchor", "decision_linked_metrics",
                 "metric_measurement_window", "decision_metric_measurement"):
        src = inspect.getsource(getattr(mod.CompanyOperatingEngine, name))
        low = src.lower()
        for banned in ("openai", "anthropic", "llm", "completion", "chat",
                       "httpx", "aiohttp", "requests"):
            assert banned not in low, f"{name} references {banned}"


# ------------------------------------------------------------------ 14-15

async def test_anchor_precedence_and_unknown_decision(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s2_anchor@test.co")
    org_id = org["organization"]["id"]

    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id="dec:4h6s2-exec",
            kind="hire", title="Exec wins", state="approved",
            approved_at=_obs_at(-10), executed_at=_obs_at(-5),
            source_event_id="evt:exec",
        ))
        db.add(CompanyDecision(
            organization_id=org_id, decision_id="dec:4h6s2-appr",
            kind="hire", title="Approved only", state="approved",
            approved_at=_obs_at(-7), source_event_id="evt:appr",
        ))
        await db.commit()

    async with db_session_factory() as db:
        res = await company_operating_engine.decision_temporal_anchor(
            db, organization_id=org_id, decision_id="dec:4h6s2-exec")
        assert res["anchor_basis"] == "executed_at"
        res = await company_operating_engine.decision_temporal_anchor(
            db, organization_id=org_id, decision_id="dec:4h6s2-appr")
        assert res["anchor_basis"] == "approved_at"
        res = await company_operating_engine.decision_temporal_anchor(
            db, organization_id=org_id, decision_id="dec:missing")
        assert res is None


async def test_unparseable_anchor_rejected_not_invented(client, db_session_factory):
    org = await register_org(client, email="4h6s2_bad@test.co")
    org_id = org["organization"]["id"]
    metric_id = await _seed_metric(db_session_factory, org_id)
    res = await _window(db_session_factory, org_id, metric_id, "not-a-timestamp")
    assert res == {"rejected": True, "reason": "anchor_not_parseable"}


async def test_linked_metrics_resolution_and_isolation(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s2_link@test.co")
    org_id = org["organization"]["id"]
    other = await register_org(client, email="4h6s2_link2@test.co")
    other_id = other["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-link")
    metric_id = await _seed_metric(db_session_factory, org_id)
    metric2_id = await _seed_metric(db_session_factory, org_id, key="churn")

    async with db_session_factory() as db:
        db.add(BusinessPerformanceLink(
            organization_id=org_id, entity_type="business_metric",
            entity_id=metric_id, target_type="decision",
            target_id="dec:4h6s2-link", kind="evidence_indicates",
            weight=0.8, reasoning="canonical link", source_event_id="evt:l1",
        ))
        await db.commit()

    # single linked metric auto-selected
    res = await _measure(db_session_factory, org_id, "dec:4h6s2-link")
    assert not res.get("rejected") and res["measurement"] is not None

    # second link -> ambiguity must be rejected, never silently resolved
    async with db_session_factory() as db:
        db.add(BusinessPerformanceLink(
            organization_id=org_id, entity_type="business_metric",
            entity_id=metric2_id, target_type="decision",
            target_id="dec:4h6s2-link", kind="linked_to",
            weight=0.3, reasoning="second", source_event_id="evt:l2",
        ))
        await db.commit()
    res = await _measure(db_session_factory, org_id, "dec:4h6s2-link")
    assert res["rejected"] is True
    assert res["reason"] == "multiple_linked_metrics_require_explicit_metric"
    assert len(res["linked_metrics"]) == 2

    # explicit key resolves deterministically
    res = await _measure(db_session_factory, org_id, "dec:4h6s2-link",
                         metric_key="churn")
    assert res["measurement"]["metric"]["key"] == "churn"

    # tenant isolation: sibling org sees neither decision nor links
    async with db_session_factory() as db:
        assert await company_operating_engine.decision_temporal_anchor(
            db, organization_id=other_id, decision_id="dec:4h6s2-link",
        ) is None
        assert await company_operating_engine.decision_linked_metrics(
            db, organization_id=other_id, decision_id="dec:4h6s2-link",
        ) == []


async def test_percentage_delta_unknown_when_baseline_zero(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s2_zero@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:4h6s2-zero")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 0.0,
                       _obs_at(-1), seq=1)
    await _seed_obs_at(db_session_factory, org_id, metric_id, 25.0,
                       _obs_at(1), seq=2)

    m = (await _measure(db_session_factory, org_id, "dec:4h6s2-zero",
                        metric_id=metric_id))["measurement"]
    assert m["delta"]["percentage_delta"] is None
    assert m["delta"]["percentage_unknown_reason"] == "baseline_value_zero"
    assert m["delta"]["value"] == pytest.approx(25.0)
