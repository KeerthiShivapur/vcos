"""Slice 4H.6 - Step 3: truth & attribution classification.

Under test (contract Step 3, L20/L21/L22/L23/L28):

Numerical truth (exactly recorded | derived | unknown):
1.  two actual observations -> derived delta citing BOTH observation ids.
2.  missing comparison -> unknown with reason; baseline stays recorded.
3.  missing baseline -> unknown with reason.
4-6. forecast / plan / estimated observations are excluded from truth.
7.  no interpolation: gap values are never fabricated or filled.
8.  determinism: repeated classification is byte-identical.
9.  L20: recorded values surface verbatim, never recomputed.

Attribution (exactly SUPPORTED | ASSOCIATED | UNKNOWN):
10. canonical causal edge touching the decision -> SUPPORTED citing edge id.
11. evidence_indicates performance link -> SUPPORTED citing link id.
12. linked_to performance link -> ASSOCIATED only (association_link_only).
13. temporal context alone -> ASSOCIATED (temporal_context_only), never
    SUPPORTED; derived measurement + UNKNOWN-grade attribution coexist
    independently (the L21/L22 matrix).
14. no canonical basis at all -> UNKNOWN (no_canonical_attribution_basis).

Safety:
15. no writes, no events during classification.
16. no LLM on the classifier path (source inspection).
17. tenant isolation: sibling org sees nothing; unknown decision -> None.
18. people-scoring prohibition: no person-keyed scores anywhere.
19. metric ambiguity rejection passes through unchanged.
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
from app.models.company_operating import CompanyCausalEdge, CompanyDecision
from app.models.notification import Event as EventRow
from tests.conftest import register_org

_ANCHOR = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


def _obs_at(days):
    return _ANCHOR + timedelta(days=days)


async def _seed_decision(db_session_factory, org_id, decision_id):
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=decision_id,
            kind="hire", title="Step3 decision", state="approved",
            approved_at=_ANCHOR, source_event_id=f"evt:{decision_id}",
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


async def _seed_obs(db_session_factory, org_id, metric_id, value, when,
                    label="actual", seq=0):
    async with db_session_factory() as db:
        db.add(BusinessMetricObservation(
            organization_id=org_id, metric_id=metric_id, value=value,
            observed_at=when, label=label,
            source_event_id=f"evt:o-{seq}-{label}-{when.isoformat()}",
        ))
        await db.commit()


async def _classify(db_session_factory, org_id, decision_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.decision_metric_classification(
            db, organization_id=org_id, decision_id=decision_id, **kw,
        )
        await db.commit()
        return result


async def _table_stats(db_session_factory, org_id):
    async with db_session_factory() as db:
        stats = {}
        for model in (CompanyDecision, BusinessMetric, BusinessMetricObservation,
                      BusinessPerformanceLink, CompanyCausalEdge, EventRow):
            stmt = select(func.count()).select_from(model)
            if hasattr(model, "organization_id"):
                stmt = stmt.where(model.organization_id == org_id)
            stats[model.__tablename__] = int(
                (await db.execute(stmt)).scalar_one() or 0)
        return stats


# ------------------------------------------------------- numerical truth

async def test_derived_delta_cites_both_observations(client, db_session_factory):
    org = await register_org(client, email="4h6s3_dv@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-dv")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)

    res = await _classify(db_session_factory, org_id, "dec:s3-dv", metric_id=metric_id)
    m = res["measured"]
    assert m["truth"] == "derived"
    assert m["value"] == pytest.approx(6.0)
    assert m["basis"]["baseline_observation_id"] == m["baseline"]["observation_id"]
    assert m["basis"]["comparison_observation_id"] == m["comparison"]["observation_id"]
    assert None not in m["basis"].values()
    assert m["metric"]["unit"] == "pct"
    assert m["metric"]["direction"] == "up_is_good"


async def test_missing_comparison_unknown_baseline_stays_recorded(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s3_mc@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-mc")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 70.0, _obs_at(-5), seq=1)

    m = (await _classify(db_session_factory, org_id, "dec:s3-mc",
                         metric_id=metric_id))["measured"]
    assert m["truth"] == "unknown"
    assert m["reason"] == "comparison_observation_missing"
    assert m.get("value") is None
    assert m["baseline"]["truth_level"] == "recorded"
    assert m["baseline"]["value"] == 70.0


async def test_missing_baseline_unknown(client, db_session_factory):
    org = await register_org(client, email="4h6s3_mb@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-mb")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 90.0, _obs_at(3), seq=1)

    m = (await _classify(db_session_factory, org_id, "dec:s3-mb",
                         metric_id=metric_id))["measured"]
    assert m["truth"] == "unknown"
    assert m["reason"] == "baseline_observation_missing"
    assert m["comparison"]["truth_level"] == "recorded"


@pytest.mark.parametrize("label", ["forecast", "plan", "estimated"])
async def test_non_actual_labels_never_become_truth(
    client, db_session_factory, label,
):
    org = await register_org(client, email=f"4h6s3_{label}@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, f"dec:s3-{label}")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 150.0,
                    _obs_at(2), label=label, seq=1)

    res = await _classify(db_session_factory, org_id, f"dec:s3-{label}",
                          metric_id=metric_id)
    m = res["measured"]
    assert m["truth"] == "unknown"
    assert m["comparison"]["truth_level"] == "unknown"
    assert m["excluded_observations"].get(label) == 1


async def test_no_interpolation_or_fill(client, db_session_factory):
    org = await register_org(client, email="4h6s3_gap@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-gap")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 100.0, _obs_at(-20), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 140.0, _obs_at(20), seq=2)

    m = (await _classify(db_session_factory, org_id, "dec:s3-gap",
                         metric_id=metric_id))["measured"]
    blob = repr(m)
    assert str(120.0) not in blob and str(110.0) not in blob
    assert m["value"] == pytest.approx(40.0)


async def test_classification_deterministic(client, db_session_factory):
    org = await register_org(client, email="4h6s3_det@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-det")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 10.0, _obs_at(-4), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 12.0, _obs_at(4), seq=2)

    a = await _classify(db_session_factory, org_id, "dec:s3-det", metric_id=metric_id)
    b = await _classify(db_session_factory, org_id, "dec:s3-det", metric_id=metric_id)
    assert a == b


async def test_recorded_values_verbatim_l20(client, db_session_factory):
    org = await register_org(client, email="4h6s3_ver@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-ver")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 82.4, _obs_at(-2), seq=1)

    m = (await _classify(db_session_factory, org_id, "dec:s3-ver",
                         metric_id=metric_id))["measured"]
    assert m["baseline"]["value"] == 82.4  # exactly what was recorded


# ------------------------------------------------------------ attribution

async def test_causal_edge_supported(client, db_session_factory):
    org = await register_org(client, email="4h6s3_ce@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-ce")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 10.0, _obs_at(-4), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 14.0, _obs_at(4), seq=2)

    async with db_session_factory() as db:
        db.add(CompanyCausalEdge(
            organization_id=org_id, source_type="decision",
            source_id="dec:s3-ce", target_type="execution", target_id="act:1",
            kind="decision->task", confidence="high",
            source_event_id="evt:ce-1",
        ))
        await db.commit()

    res = await _classify(db_session_factory, org_id, "dec:s3-ce", metric_id=metric_id)
    att = res["attributed"]
    assert att["level"] == "SUPPORTED"
    assert any(b["type"] == "causal_edge" and b["kind"] == "decision->task"
               for b in att["basis"])
    assert att["reason"] is None


async def test_evidence_link_supported(client, db_session_factory):
    org = await register_org(client, email="4h6s3_el@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-el")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 1.0, _obs_at(-1), seq=1)

    async with db_session_factory() as db:
        db.add(BusinessPerformanceLink(
            organization_id=org_id, entity_type="business_metric",
            entity_id=metric_id, target_type="decision", target_id="dec:s3-el",
            kind="evidence_indicates", weight=0.9, reasoning="canonical",
            source_event_id="evt:l-supp",
        ))
        await db.commit()

    att = (await _classify(db_session_factory, org_id, "dec:s3-el",
                           metric_id=metric_id))["attributed"]
    assert att["level"] == "SUPPORTED"
    assert any(b["type"] == "business_performance_link" and b["id"]
               for b in att["basis"])


async def test_association_link_never_upgrades(client, db_session_factory):
    org = await register_org(client, email="4h6s3_al@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-al")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 5.0, _obs_at(-1), seq=1)

    async with db_session_factory() as db:
        db.add(BusinessPerformanceLink(
            organization_id=org_id, entity_type="business_metric",
            entity_id=metric_id, target_type="decision", target_id="dec:s3-al",
            kind="linked_to", weight=0.4, reasoning="weak tie",
            source_event_id="evt:l-assoc",
        ))
        await db.commit()

    att = (await _classify(db_session_factory, org_id, "dec:s3-al",
                           metric_id=metric_id))["attributed"]
    assert att["level"] == "ASSOCIATED"
    assert att["reason"] == "association_link_only"


async def test_temporal_context_alone_associated_not_supported(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s3_temp@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-temp")
    metric_id = await _seed_metric(db_session_factory, org_id)
    # real before/after pair => derived measurement, but ZERO canonical
    # attribution links => the L21/L22 matrix: derived x associated
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)

    res = await _classify(db_session_factory, org_id, "dec:s3-temp",
                          metric_key="customer_retention")
    assert res["measured"]["truth"] == "derived"
    att = res["attributed"]
    assert att["level"] == "ASSOCIATED"
    assert att["level"] != "SUPPORTED"
    assert att["reason"] == "temporal_context_only"


async def test_no_basis_unknown(client, db_session_factory):
    org = await register_org(client, email="4h6s3_none@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-none")
    metric_id = await _seed_metric(db_session_factory, org_id)
    # explicit metric, zero observations, zero links

    res = await _classify(db_session_factory, org_id, "dec:s3-none",
                          metric_id=metric_id)
    assert res["measured"]["truth"] == "unknown"
    att = res["attributed"]
    assert att["level"] == "UNKNOWN"
    assert att["reason"] == "no_canonical_attribution_basis"
    assert att["basis"] == []


# ---------------------------------------------------------------- safety

async def test_no_writes_no_events(client, db_session_factory):
    org = await register_org(client, email="4h6s3_ro@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-ro")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 3.0, _obs_at(-1), seq=1)

    before = await _table_stats(db_session_factory, org_id)
    await _classify(db_session_factory, org_id, "dec:s3-ro", metric_id=metric_id)
    after = await _table_stats(db_session_factory, org_id)
    assert before == after


async def test_no_llm_on_classifier_path():
    from app.intelligence import company_operating_engine as mod

    for name in ("classify_measurement_truth", "classify_attribution",
                 "decision_metric_classification"):
        src = inspect.getsource(getattr(mod.CompanyOperatingEngine, name)).lower()
        for banned in ("openai", "anthropic", "llm", "completion", "chat",
                       "httpx", "aiohttp", "requests", "prompt"):
            assert banned not in src, f"{name} references {banned}"


async def test_tenant_isolation(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s3_iso@test.co")
    org_id = org["organization"]["id"]
    other = await register_org(client, email="4h6s3_iso2@test.co")
    other_id = other["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-iso")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 7.0, _obs_at(-1), seq=1)
    async with db_session_factory() as db:
        db.add(CompanyCausalEdge(
            organization_id=org_id, source_type="decision",
            source_id="dec:s3-iso", target_type="outcome", target_id="out:1",
            kind="execution->outcome", confidence="medium",
            source_event_id="evt:iso",
        ))
        await db.commit()

    # sibling org: decision invisible
    assert await _classify(db_session_factory, other_id, "dec:s3-iso",
                           metric_id=metric_id) is None

    # sibling org querying ITS OWN identically-named decision namespace gets
    # no leakage of edges/links/observations from the first org: with
    # temporal context flagged, only the synthetic temporal basis appears;
    # without it, attribution is fully UNKNOWN.
    async with db_session_factory() as db:
        att = await company_operating_engine.classify_attribution(
            db, organization_id=other_id, decision_id="dec:s3-iso",
            has_temporal_context=True,
        )
    assert att["level"] == "ASSOCIATED"
    assert att["reason"] == "temporal_context_only"
    assert att["basis"] == [{"type": "temporal_context"}]  # zero leaked ids

    async with db_session_factory() as db:
        att = await company_operating_engine.classify_attribution(
            db, organization_id=other_id, decision_id="dec:s3-iso",
        )
    assert att["level"] == "UNKNOWN"
    assert att["reason"] == "no_canonical_attribution_basis"


async def test_no_people_scoring_in_output(client, db_session_factory):
    org = await register_org(client, email="4h6s3_people@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-people")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 9.0, _obs_at(-1), seq=1)

    res = await _classify(db_session_factory, org_id, "dec:s3-people",
                          metric_id=metric_id)
    blob = repr(res).lower()
    for banned in ("employee_score", "person_score", "manager_score",
                   "people_score", "effectiveness_score", "ranking",
                   '"winner"'):
        assert banned not in blob, f"forbidden concept leaked: {banned}"
    assert res["honesty"]["no_people_scoring"] is True
    assert res["honesty"]["no_confidence_number"] is True
    assert set(res["attributed"]) == {"level", "basis", "reason"}  # no score field


async def test_metric_ambiguity_rejection_passthrough(client, db_session_factory):
    org = await register_org(client, email="4h6s3_amb@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s3-amb")
    m1 = await _seed_metric(db_session_factory, org_id, key="k1")
    m2 = await _seed_metric(db_session_factory, org_id, key="k2")
    async with db_session_factory() as db:
        for mid, evt in ((m1, "a"), (m2, "b")):
            db.add(BusinessPerformanceLink(
                organization_id=org_id, entity_type="business_metric",
                entity_id=mid, target_type="decision", target_id="dec:s3-amb",
                kind="linked_to", weight=0.3, reasoning="x",
                source_event_id=f"evt:{evt}",
            ))
        await db.commit()

    res = await _classify(db_session_factory, org_id, "dec:s3-amb")
    assert res["rejected"] is True
    assert res["reason"] == "multiple_linked_metrics_require_explicit_metric"
