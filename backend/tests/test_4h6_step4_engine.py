"""Slice 4H.6 - Step 4: unified decision-performance assessment.

Under test (contract Step 4, L20-L28):

1.  composition: all nine ratified sections present, unknown decision -> None.
2.  decision section: identity + lifecycle + anchor_basis; recorded
    expectation surfaced verbatim.
3.  observed: outcome record flips recorded/unknown with the canonical
    row; action outcomes come from the 4H.5 chain.
4.  measured: linked metric classified derived with observation-id basis;
    attribution rides alongside per metric.
5.  no linked metrics -> honest empty measured + unknown entry
    (no_linked_canonical_metrics).
6.  unknown aggregation: measurement-side and attribution-side unknowns are
    first-class items with reasons.
7.  assessed: evidence COUNTS only - never a score or verdict.
8.  execution chain consumed verbatim (minus volatile generated_at), not
    duplicated: section equals a fresh chain call modulo that timestamp.
9.  determinism: two full assessments over identical rows are byte-identical.
10. L20: recorded effectiveness surfaces verbatim, never recomputed.
11. safety envelope: honesty flags present; no score/rank/winner fields;
    temporal-sequence-is-not-causality asserted in output.
12. no writes, no events during assessment.
13. tenant isolation: sibling org -> None.
14. no LLM on the assessment path (source inspection).
15. actual_outcome_compare (recorded reconciliation payload) surfaces
    verbatim when present.
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


async def _seed_decision(db_session_factory, org_id, decision_id, **kw):
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=decision_id,
            kind="hire", title="Step4 decision", state="approved",
            approved_at=_ANCHOR, source_event_id=f"evt:{decision_id}",
            expected_improvement=kw.pop("expected_improvement", ""),
            **kw,
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


async def _assess(db_session_factory, org_id, decision_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.decision_performance_assessment(
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


async def test_nine_sections_and_unknown_decision(client, db_session_factory):
    org = await register_org(client, email="4h6s4_sec@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-sec")

    res = await _assess(db_session_factory, org_id, "dec:s4-sec")
    assert set(res) == {
        "decision", "observed", "measured", "attributed", "assessed",
        "unknown", "temporal_basis", "execution_chain", "honesty",
    }
    assert res["execution_chain"]["decision"]["decision_id"] == "dec:s4-sec"

    from app.intelligence.company_operating_engine import company_operating_engine
    async with db_session_factory() as db:
        assert await company_operating_engine.decision_performance_assessment(
            db, organization_id=org_id, decision_id="dec:missing",
        ) is None


async def test_decision_section_identity_and_expectation(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s4_dec@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-dec",
                         expected_improvement="+10% retention")

    d = (await _assess(db_session_factory, org_id, "dec:s4-dec"))["decision"]
    assert d["anchor_basis"] == "approved_at"
    assert d["state"] == "approved"
    assert d["expected_improvement"] == "+10% retention"


async def test_observed_outcome_record_truth_flip(client, db_session_factory):
    org = await register_org(client, email="4h6s4_obs@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-obs")

    obs = (await _assess(db_session_factory, org_id, "dec:s4-obs"))["observed"]
    assert obs["outcome_record"]["truth"] == "unknown"
    assert obs["outcome_record"]["reason"] == "no_outcome_recorded"
    assert obs["outcome_record"]["outcome_kind"] is None

    async with db_session_factory() as db:
        row = (await db.execute(select(CompanyDecision).where(
            CompanyDecision.organization_id == org_id,
            CompanyDecision.decision_id == "dec:s4-obs",
        ))).scalar_one()
        row.outcome_kind = "successful"
        row.effectiveness = 0.7
        await db.commit()

    obs = (await _assess(db_session_factory, org_id, "dec:s4-obs"))["observed"]
    assert obs["outcome_record"]["truth"] == "recorded"
    assert obs["outcome_record"]["outcome_kind"] == "successful"
    assert obs["outcome_record"]["effectiveness"] == 0.7


async def test_measured_derived_with_attribution(client, db_session_factory):
    org = await register_org(client, email="4h6s4_meas@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-meas")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s4-meas")

    res = await _assess(db_session_factory, org_id, "dec:s4-meas")
    item = res["measured"]["items"][0]
    assert item["measurement"]["truth"] == "derived"
    assert item["measurement"]["value"] == pytest.approx(6.0)
    assert item["measurement"]["basis"]["baseline_observation_id"]
    assert item["attribution"]["level"] == "SUPPORTED"  # evidence_indicates link
    assert res["attributed"]["per_metric"][0]["metric_key"] == "customer_retention"
    assert res["attributed"]["summary"]["SUPPORTED"] == 1


async def test_no_linked_metrics_honest_empty(client, db_session_factory):
    org = await register_org(client, email="4h6s4_empty@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-empty")

    res = await _assess(db_session_factory, org_id, "dec:s4-empty")
    assert res["measured"]["metric_count"] == 0
    reasons = [u["reason"] for u in res["unknown"]["items"]]
    assert "no_linked_canonical_metrics" in reasons
    assert res["assessed"]["linked_metrics_count"] == 0


async def test_unknown_aggregation(client, db_session_factory):
    org = await register_org(client, email="4h6s4_unk@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-unk")
    metric_id = await _seed_metric(db_session_factory, org_id)
    # one pre-anchor observation only: comparison missing; linked so it IS
    # measured by the unified assessment
    await _seed_obs(db_session_factory, org_id, metric_id, 70.0, _obs_at(-5), seq=1)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s4-unk",
                     kind="evidence_indicates", weight=0.8, evt="l1")
    # second linked metric with ZERO observations: measurement unknown;
    # attribution stays ASSOCIATED via its canonical link
    metric2_id = await _seed_metric(db_session_factory, org_id, key="net_margin")
    await _seed_link(db_session_factory, org_id, metric2_id, "dec:s4-unk",
                     kind="linked_to", weight=0.3, evt="l2")

    res = await _assess(db_session_factory, org_id, "dec:s4-unk")
    # three honest unknowns: two measurement gaps + unrecorded outcome.
    # NOTE: per-metric attribution inside a unified assessment can never be
    # UNKNOWN - a metric is only measured here BECAUSE a canonical link
    # exists, which is already >= ASSOCIATED evidence.
    assert res["unknown"]["count"] == 3
    sections = {u["section"] for u in res["unknown"]["items"]}
    assert sections == {"measured", "observed"}
    meas_reasons = [u["reason"] for u in res["unknown"]["items"]
                    if u["section"] == "measured"]
    assert sorted(meas_reasons) == [
        "comparison_observation_missing", "no_actual_observation_pair",
    ]
    per_metric = {p["metric_key"]: p for p in res["attributed"]["per_metric"]}
    assert per_metric["customer_retention"]["level"] == "SUPPORTED"
    assert per_metric["net_margin"]["level"] == "ASSOCIATED"
    assert per_metric["net_margin"]["reason"] == "association_link_only"


async def test_assessed_counts_not_scores(client, db_session_factory):
    org = await register_org(client, email="4h6s4_cnt@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-cnt",
                         effectiveness=0.7)
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s4-cnt")

    a = (await _assess(db_session_factory, org_id, "dec:s4-cnt"))["assessed"]
    assert a["recorded_effectiveness"] == 0.7  # verbatim, L20
    assert a["derived_measurements_count"] == 1
    assert a["linked_metrics_count"] == 1
    assert a["attribution_summary"] == {"SUPPORTED": 1, "ASSOCIATED": 0, "UNKNOWN": 0}
    blob = repr(a).lower()
    for banned in ("score", "grade", "verdict:", "/100"):
        assert banned not in blob.replace("not a quality score", ""), banned


async def test_chain_consumed_verbatim_not_duplicated(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s4_chain@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-chain")

    res = await _assess(db_session_factory, org_id, "dec:s4-chain")
    async with db_session_factory() as db:
        fresh = await company_operating_engine.execution_chain(
            db, organization_id=org_id, decision_id="dec:s4-chain",
        )
    fresh.pop("generated_at")
    assert res["execution_chain"] == fresh
    assert "generated_at" not in res["execution_chain"]


async def test_determinism_byte_identical(client, db_session_factory):
    org = await register_org(client, email="4h6s4_det@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-det")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s4-det")

    a = await _assess(db_session_factory, org_id, "dec:s4-det")
    b = await _assess(db_session_factory, org_id, "dec:s4-det")
    assert a == b


async def test_safety_envelope_and_no_score_fields(client, db_session_factory):
    org = await register_org(client, email="4h6s4_safe@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-safe")

    res = await _assess(db_session_factory, org_id, "dec:s4-safe")
    h = res["honesty"]
    for flag in ("no_scores", "no_ranking_or_winner", "no_forecasting",
                 "no_recommendations", "no_learning", "no_people_scoring",
                 "temporal_sequence_is_not_causality", "read_only"):
        assert h[flag] is True
    blob = repr(res).lower()
    for banned in ("decision_score", '"winner"', '"rank"', "success_probability",
                   "quality_score", "employee_score"):
        assert banned not in blob, f"forbidden field leaked: {banned}"


async def test_no_writes_no_events(client, db_session_factory):
    org = await register_org(client, email="4h6s4_ro@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-ro")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 3.0, _obs_at(-1), seq=1)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s4-ro")

    before = await _table_stats(db_session_factory, org_id)
    await _assess(db_session_factory, org_id, "dec:s4-ro")
    after = await _table_stats(db_session_factory, org_id)
    assert before == after


async def test_tenant_isolation(client, db_session_factory):
    org = await register_org(client, email="4h6s4_iso@test.co")
    org_id = org["organization"]["id"]
    other = await register_org(client, email="4h6s4_iso2@test.co")
    other_id = other["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-iso")
    assert await _assess(db_session_factory, other_id, "dec:s4-iso") is None


async def test_no_llm_on_assessment_path():
    from app.intelligence import company_operating_engine as mod

    src = inspect.getsource(
        getattr(mod.CompanyOperatingEngine, "decision_performance_assessment"),
    ).lower()
    for banned in ("openai", "anthropic", "llm", "completion", "chat",
                   "httpx", "aiohttp", "requests", "prompt"):
        assert banned not in src, f"assessment references {banned}"


async def test_actual_outcome_compare_surfaces_verbatim(
    client, db_session_factory,
):
    compare_payload = {
        "predicted": "faster onboarding",
        "observed": "onboarding time down 20%",
        "effectiveness_observed": 0.72,
        "aligned": True,
    }
    org = await register_org(client, email="4h6s4_cmp@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s4-cmp",
                         outcome_kind="partial", effectiveness=0.72,
                         actual_outcome_compare=compare_payload)

    obs = (await _assess(db_session_factory, org_id, "dec:s4-cmp"))["observed"]
    assert obs["outcome_record"]["actual_outcome_compare"] == compare_payload
    assert obs["outcome_record"]["truth"] == "recorded"
