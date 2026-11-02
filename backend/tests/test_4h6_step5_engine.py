"""Slice 4H.6 - Step 5: outcome cohort / longitudinal read.

Under test (contract Step 5, L20-L28):

1.  cohort composition: outcome-kind distribution over recorded decision
    rows; decisions without an outcome stay honestly uncounted.
2.  filters: kind/state narrow the cohort canonically.
3.  effectiveness aggregate: >=2 recorded values -> derived mean citing the
    contributing decision ids; exactly one -> recorded passthrough; none ->
    unknown with reason.
4.  measurement coverage + attribution aggregation reuse Steps 2-4 (a
    linked metric with a real pair yields derived counts and SUPPORTED).
5.  temporal coverage: earliest/latest anchors + anchor_bases histogram.
6.  unknown aggregate: reasons collected across the cohort's assessments.
7.  CompanyDecisionTrack UNTOUCHED: pre-seeded track rows are identical
    after cohort reads; output contains no track fields.
8.  bounds: cohort is capped at MAX_COHORT_DECISIONS with the bound exposed.
9.  determinism: repeated reads byte-identical.
10. tenant isolation: sibling org sees an empty cohort.
11. no writes, no events during cohort derivation.
12. no LLM on the cohort path (source inspection).
13. patterns-not-recommendations: honesty flags present; no recommendation
    or winner vocabulary anywhere in the payload.
"""

from datetime import datetime, timedelta, timezone

import inspect
import uuid
import pytest
from sqlalchemy import func, select

from app.models.business_performance import (
    BusinessMetric,
    BusinessMetricObservation,
    BusinessPerformanceLink,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionTrack,
)
from app.models.notification import Event as EventRow
from tests.conftest import register_org

_ANCHOR = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


def _obs_at(days):
    return _ANCHOR + timedelta(days=days)


async def _seed_decision(db_session_factory, org_id, decision_id, **kw):
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=decision_id,
            kind=kw.pop("kind", "hire"), title=f"Cohort {decision_id}",
            state=kw.pop("state", "approved"),
            approved_at=kw.pop("approved_at", _ANCHOR),
            source_event_id=f"evt:{decision_id}", **kw,
        ))
        await db.commit()


async def _seed_metric(db_session_factory, org_id, key="customer_retention"):
    async with db_session_factory() as db:
        metric = BusinessMetric(
            organization_id=org_id, key=key, label=key.title(),
            kind="retention", direction="up_is_good", unit="pct",
            scope="org_wide", last_value=0.0,
            source_event_id=f"evt:m-{key}",
        )
        db.add(metric)
        await db.commit()
        return metric.id


async def _seed_obs(db_session_factory, org_id, metric_id, value, when, seq=0):
    async with db_session_factory() as db:
        db.add(BusinessMetricObservation(
            organization_id=org_id, metric_id=metric_id, value=value,
            observed_at=when, label="actual",
            source_event_id=f"evt:o-{seq}-{when.isoformat()}",
        ))
        await db.commit()


async def _seed_link(db_session_factory, org_id, metric_id, decision_id,
                     kind="evidence_indicates", weight=0.8, evt="l"):
    async with db_session_factory() as db:
        db.add(BusinessPerformanceLink(
            organization_id=org_id, entity_type="business_metric",
            entity_id=metric_id, target_type="decision", target_id=decision_id,
            kind=kind, weight=weight, reasoning="canonical link",
            source_event_id=f"evt:{evt}",
        ))
        await db.commit()


async def _cohort(db_session_factory, org_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.decision_performance_cohort(
            db, organization_id=org_id, **kw,
        )
        await db.commit()
        return result


async def _table_stats(db_session_factory, org_id):
    async with db_session_factory() as db:
        stats = {}
        for model in (CompanyDecision, BusinessMetric, BusinessMetricObservation,
                      BusinessPerformanceLink, CompanyDecisionTrack, EventRow):
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "organization_id"):
                stmt = stmt.where(model.organization_id == org_id)
            stats[model.__tablename__] = int(
                (await db.execute(stmt)).scalar_one() or 0)
        return stats


async def _full_cohort_fixture(client, db_session_factory, suffix):
    org = await register_org(
        client, email=f"4h6s5_{suffix}_{uuid.uuid4().hex[:6]}@test.co",
    )
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, f"dec:s5-{suffix}-a",
                         outcome_kind="successful", effectiveness=0.8)
    await _seed_decision(db_session_factory, org_id, f"dec:s5-{suffix}-b",
                         kind="pricing", outcome_kind="partial",
                         effectiveness=0.6)
    await _seed_decision(db_session_factory, org_id, f"dec:s5-{suffix}-c")
    return org_id


async def test_outcome_distribution_and_honest_gaps(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "dist")

    res = await _cohort(db_session_factory, org_id)
    assert res["cohort"]["decision_count"] == 3
    ro = res["recorded_outcomes"]
    assert ro["by_kind"]["successful"] == 1
    assert ro["by_kind"]["partial"] == 1
    assert ro["by_kind"]["unsuccessful"] == 0
    assert ro["with_outcome_record"] == 2
    assert ro["without_outcome_record"] == 1
    assert res["honesty"]["patterns_not_recommendations"] is True


async def test_filters_narrow_cohort(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "filt")

    res = await _cohort(db_session_factory, org_id, kind="pricing")
    assert res["cohort"]["decision_count"] == 1
    assert res["decisions"][0]["decision_id"].endswith("-b")
    res = await _cohort(db_session_factory, org_id, state="proposed")
    assert res["cohort"]["decision_count"] == 0


async def test_effectiveness_aggregate_truth_levels(client, db_session_factory):
    org = await register_org(client, email="4h6s5_eff@test.co")
    org_id = org["organization"]["id"]

    # zero values -> unknown
    await _seed_decision(db_session_factory, org_id, "dec:s5-eff-0")
    agg = (await _cohort(db_session_factory, org_id))["effectiveness_aggregate"]
    assert agg["truth_level"] == "unknown"
    assert agg["reason"] == "no_recorded_effectiveness_values"

    # one value -> recorded passthrough
    async with db_session_factory() as db:
        row = (await db.execute(select(CompanyDecision).where(
            CompanyDecision.organization_id == org_id))).scalar_one()
        row.effectiveness = 0.55
        await db.commit()
    agg = (await _cohort(db_session_factory, org_id))["effectiveness_aggregate"]
    assert agg["truth_level"] == "recorded"
    assert agg["value"] == 0.55

    # two values -> derived mean citing both decision ids
    await _seed_decision(db_session_factory, org_id, "dec:s5-eff-1",
                         outcome_kind="partial", effectiveness=0.65)
    agg = (await _cohort(db_session_factory, org_id))["effectiveness_aggregate"]
    assert agg["truth_level"] == "derived"
    assert agg["value"] == pytest.approx(0.6)
    assert sorted(agg["basis"]) == ["dec:s5-eff-0", "dec:s5-eff-1"]


async def test_measurement_and_attribution_aggregation(client, db_session_factory):
    org = await register_org(client, email="4h6s5_meas@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s5-m-a",
                         outcome_kind="successful", effectiveness=0.9)
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s5-m-a")

    res = await _cohort(db_session_factory, org_id)
    cov = res["measurement_coverage"]
    assert cov["decisions_with_linked_metrics"] == 1
    assert cov["derived_measurement_items"] == 1
    assert res["attribution_summary"]["SUPPORTED"] == 1


async def test_temporal_coverage(client, db_session_factory):
    org = await register_org(client, email="4h6s5_time@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s5-t-1",
                         approved_at=_obs_at(-30))
    await _seed_decision(db_session_factory, org_id, "dec:s5-t-2",
                         approved_at=_obs_at(30))

    tc = (await _cohort(db_session_factory, org_id))["temporal_coverage"]
    assert tc["earliest_anchor"] < tc["latest_anchor"]
    assert tc["anchor_bases"] == {"approved_at": 2}


async def test_unknown_reasons_aggregated(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "unk")

    reasons = (await _cohort(db_session_factory, org_id))["unknown_aggregate"]
    assert reasons["total_items"] >= 3  # two unlinked + one unmeasured outcome gap
    assert "no_linked_canonical_metrics" in reasons["reasons"]
    assert "no_outcome_recorded" in reasons["reasons"]


async def test_track_infrastructure_untouched(client, db_session_factory):
    org = await register_org(client, email="4h6s5_trk@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s5-trk",
                         outcome_kind="successful", effectiveness=0.7)

    async with db_session_factory() as db:
        db.add(CompanyDecisionTrack(
            organization_id=org_id, cohort_key="kind:hire",
            decisions_measured=1, predictions_recorded=2, aligned=1,
            partial=1, misaligned=0, avg_effectiveness=0.7,
            source_event_id="evt:trk-1",
            snapshot_ts=_ANCHOR,
        ))
        await db.commit()

    before = await _table_stats(db_session_factory, org_id)
    async with db_session_factory() as db:
        before_rows = list((await db.execute(
            select(CompanyDecisionTrack).where(
                CompanyDecisionTrack.organization_id == org_id)
        )).scalars().all())
        before_repr = [(t.id, t.cohort_key, t.decisions_measured, t.aligned,
                        t.snapshot_ts) for t in before_rows]

    res = await _cohort(db_session_factory, org_id)

    after = await _table_stats(db_session_factory, org_id)
    async with db_session_factory() as db:
        after_rows = list((await db.execute(
            select(CompanyDecisionTrack).where(
                CompanyDecisionTrack.organization_id == org_id)
        )).scalars().all())
        after_repr = [(t.id, t.cohort_key, t.decisions_measured, t.aligned,
                       t.snapshot_ts) for t in after_rows]
    assert before == after
    assert before_repr == after_repr
    assert "track_infrastructure_untouched" in repr(res["honesty"])
    assert not any(k.startswith("track") for k in res)


async def test_bounds_enforced(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s5_bound@test.co")
    org_id = org["organization"]["id"]
    for i in range(company_operating_engine.MAX_COHORT_DECISIONS + 5):
        await _seed_decision(db_session_factory, org_id, f"dec:s5-bd-{i}")

    res = await _cohort(db_session_factory, org_id)
    assert res["cohort"]["decision_count"] == \
        company_operating_engine.MAX_COHORT_DECISIONS
    assert res["cohort"]["bounded"] is True


async def test_determinism_byte_identical(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "det")
    a = await _cohort(db_session_factory, org_id)
    b = await _cohort(db_session_factory, org_id)
    assert a == b


async def test_tenant_isolation_empty_cohort(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "iso")
    other = await register_org(client, email="4h6s5_iso2@test.co")
    other_id = other["organization"]["id"]

    res = await _cohort(db_session_factory, other_id)
    assert res["cohort"]["decision_count"] == 0
    assert res["decisions"] == []


async def test_no_writes_no_events(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "ro")
    before = await _table_stats(db_session_factory, org_id)
    await _cohort(db_session_factory, org_id)
    after = await _table_stats(db_session_factory, org_id)
    assert before == after


async def test_no_llm_on_cohort_path():
    from app.intelligence import company_operating_engine as mod

    src = inspect.getsource(
        getattr(mod.CompanyOperatingEngine, "decision_performance_cohort"),
    ).lower()
    for banned in ("openai", "anthropic", "llm", "completion", "chat",
                   "httpx", "aiohttp", "requests", "prompt"):
        assert banned not in src, f"cohort references {banned}"


async def test_patterns_not_recommendations(client, db_session_factory):
    org_id = await _full_cohort_fixture(client, db_session_factory, "pat")
    res = await _cohort(db_session_factory, org_id)
    h = res["honesty"]
    for flag in ("no_learning", "no_forecasting", "no_ranking_or_winner",
                 "no_scores", "no_people_scoring", "compare_not_rank",
                 "read_only"):
        assert h[flag] is True
    blob = repr(res).lower().replace("patterns_not_recommendations", "")
    for banned in ("recommend", '"winner"', '"rank"', "should make",
                   "next action", "lesson_learned_recommendation"):
        assert banned not in blob, f"forbidden vocabulary leaked: {banned}"
