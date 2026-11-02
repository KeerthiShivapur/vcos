"""Slice 4H.6 - Step 6: comparative read (COMPARE != RANK).

Under test (contract Step 6, L20-L28):

1.  composition: side-by-side comparison reuses Step 4 assessments
    verbatim (embedded assessments equal direct assessment calls) and
    Step 5 longitudinal context per involved kind - zero duplicated logic.
2.  columns: compact neutral facts per decision, input order preserved,
    duplicates deduped.
3.  recorded facts verbatim: outcome kind / effectiveness passthrough;
    unknown stays unknown, never zero-filled.
4.  derived measurements + SUPPORTED attribution flow through from the
    Steps 2-3 primitives via the embedded assessments.
5.  temporal basis exposed per compared decision (anchor + named basis).
6.  bounds: at most MAX_COMPARE_DECISIONS unique decisions; over-bound is
    REJECTED, never silently truncated; fewer than two resolvable is
    rejected honestly.
7.  not_found: missing and foreign-org decision ids are reported, tenant
    isolation holds (moat feature).
8.  contrasts: neutral with/without partitions of factual evidence - no
    judgement vocabulary anywhere in the comparison sections.
9.  COMPARE != RANK: no winner/rank/score/probability/recommendation/
    forecast/learning/person-evaluation keys exist in the payload.
10. CompanyDecisionTrack untouched after comparisons; no track fields in
    the payload.
11. no writes, no events during comparison derivation.
12. determinism: repeated reads identical.
13. no LLM on the comparison path (source inspection).
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
            kind=kw.pop("kind", "hire"), title=f"Compare {decision_id}",
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


async def _compare(db_session_factory, org_id, decision_ids):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.decision_performance_comparison(
            db, organization_id=org_id, decision_ids=list(decision_ids),
        )
        await db.commit()
        return result


async def _direct_assessment(db_session_factory, org_id, decision_id):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        return await company_operating_engine.decision_performance_assessment(
            db, organization_id=org_id, decision_id=decision_id,
        )


async def _direct_cohort(db_session_factory, org_id, **kw):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        return await company_operating_engine.decision_performance_cohort(
            db, organization_id=org_id, **kw,
        )


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


def _all_keys(payload):
    keys = set()
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for k, v in node.items():
                keys.add(str(k))
                stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)
    return keys


async def _pair_fixture(client, db_session_factory, suffix):
    org = await register_org(
        client, email=f"4h6s6_{suffix}_{uuid.uuid4().hex[:6]}@test.co",
    )
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, f"dec:s6-{suffix}-a",
                         outcome_kind="successful", effectiveness=0.8)
    await _seed_decision(db_session_factory, org_id, f"dec:s6-{suffix}-b",
                         kind="pricing", outcome_kind="unsuccessful")
    return org_id, f"dec:s6-{suffix}-a", f"dec:s6-{suffix}-b"


async def test_side_by_side_composes_step4_assessments(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "comp")

    res = await _compare(db_session_factory, org_id, [a, b])
    assert not res.get("rejected")
    cmp_ = res["comparison"]
    assert cmp_["decision_ids"] == [a, b]  # input order preserved
    assert cmp_["compared"] == 2
    assert cmp_["compare_not_rank"] is True
    assert cmp_["derived_on_read"] is True
    # composition proof: embedded assessments are byte-identical to direct
    # Step 4 calls - no duplicated or re-implemented logic.
    for did in (a, b):
        direct = await _direct_assessment(db_session_factory, org_id, did)
        assert res["assessments"][did] == direct
    assert [c["decision_id"] for c in res["columns"]] == [a, b]


async def test_columns_carry_recorded_facts_verbatim(client, db_session_factory):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "verb")
    await _seed_decision(db_session_factory, org_id, "dec:s6-verb-c")

    cols = {
        c["decision_id"]: c
        for c in (await _compare(
            db_session_factory, org_id, [a, b, "dec:s6-verb-c"],
        ))["columns"]
    }
    assert cols[a]["outcome"]["outcome_kind"] == "successful"
    assert cols[a]["outcome"]["truth"] == "recorded"
    assert cols[a]["recorded_effectiveness"] == pytest.approx(0.8)
    # outcome recorded but effectiveness never set -> passthrough None
    assert cols[b]["outcome"]["outcome_kind"] == "unsuccessful"
    assert cols[b]["outcome"]["truth"] == "recorded"
    assert cols[b]["recorded_effectiveness"] is None  # absent, not zero
    # no outcome record at all -> unknown truth
    assert cols["dec:s6-verb-c"]["outcome"]["outcome_kind"] is None
    assert cols["dec:s6-verb-c"]["outcome"]["truth"] == "unknown"
    assert cols["dec:s6-verb-c"]["unknowns"]["count"] >= 1


async def test_derived_measurement_and_supported_attribution_flow_through(
    client, db_session_factory,
):
    org = await register_org(client, email="4h6s6_meas@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s6-m-a",
                         outcome_kind="successful", effectiveness=0.9)
    await _seed_decision(db_session_factory, org_id, "dec:s6-m-b")
    metric_id = await _seed_metric(db_session_factory, org_id)
    await _seed_obs(db_session_factory, org_id, metric_id, 80.0, _obs_at(-9), seq=1)
    await _seed_obs(db_session_factory, org_id, metric_id, 86.0, _obs_at(6), seq=2)
    await _seed_link(db_session_factory, org_id, metric_id, "dec:s6-m-a")

    res = await _compare(db_session_factory, org_id,
                         ["dec:s6-m-a", "dec:s6-m-b"])
    col_a = res["columns"][0]
    assert col_a["measured"]["linked_metrics"] == 1
    assert col_a["measured"]["derived_measurements"] == 1
    assert col_a["attribution_summary"]["SUPPORTED"] == 1
    col_b = res["columns"][1]
    assert col_b["measured"]["linked_metrics"] == 0
    assert col_b["attribution_summary"] == {
        "SUPPORTED": 0, "ASSOCIATED": 0, "UNKNOWN": 0,
    }
    # unmeasured decision reports the canonical gap, not an invented level
    assert "no_linked_canonical_metrics" in col_b["unknowns"]["reasons"]
    # delta provenance survives inside the embedded assessment
    item = res["assessments"]["dec:s6-m-a"]["measured"]["items"][0]
    assert item["measurement"]["truth"] == "derived"
    assert sorted(
        item["measurement"]["basis"].keys()
    ) == ["baseline_observation_id", "comparison_observation_id"]


async def test_temporal_basis_exposed_per_decision(client, db_session_factory):
    org = await register_org(client, email="4h6s6_time@test.co")
    org_id = org["organization"]["id"]
    await _seed_decision(db_session_factory, org_id, "dec:s6-t-1",
                         approved_at=_obs_at(-30))
    await _seed_decision(db_session_factory, org_id, "dec:s6-t-2",
                         approved_at=_obs_at(30))

    cols = {
        c["decision_id"]: c
        for c in (await _compare(db_session_factory, org_id,
                                 ["dec:s6-t-1", "dec:s6-t-2"]))["columns"]
    }
    assert cols["dec:s6-t-1"]["anchor_basis"] == "approved_at"
    assert cols["dec:s6-t-1"]["anchor"] < cols["dec:s6-t-2"]["anchor"]


async def test_bound_of_five_accepted(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s6_bnd@test.co")
    org_id = org["organization"]["id"]
    n = company_operating_engine.MAX_COMPARE_DECISIONS
    ids = []
    for i in range(n):
        did = f"dec:s6-bnd-{i}"
        ids.append(did)
        await _seed_decision(db_session_factory, org_id, did)

    res = await _compare(db_session_factory, org_id, ids)
    assert res["comparison"]["compared"] == n == 5
    assert len(res["columns"]) == n


async def test_reject_over_bound_never_truncates(client, db_session_factory):
    from app.intelligence.company_operating_engine import company_operating_engine

    org = await register_org(client, email="4h6s6_ovb@test.co")
    org_id = org["organization"]["id"]
    n = company_operating_engine.MAX_COMPARE_DECISIONS
    ids = []
    for i in range(n + 1):
        did = f"dec:s6-ovb-{i}"
        ids.append(did)
        await _seed_decision(db_session_factory, org_id, did)

    res = await _compare(db_session_factory, org_id, ids)
    assert res["rejected"] is True
    assert res["reason"] == "too_many_decisions"
    assert res["received"] == n + 1
    assert res["max_decisions"] == n


async def test_reject_single_unique_and_dedupe_duplicates(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "dup")

    one = await _compare(db_session_factory, org_id, [a])
    assert one["rejected"] is True
    assert one["reason"] == "at_least_two_unique_decisions_required"

    res = await _compare(db_session_factory, org_id, [a, a, b])
    assert not res.get("rejected")
    assert res["comparison"]["requested"] == 2  # deduped
    assert res["comparison"]["decision_ids"] == [a, b]


async def test_missing_ids_reported_valid_pair_still_compared(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "miss")

    res = await _compare(db_session_factory, org_id,
                         [a, "dec:does-not-exist", b])
    assert res["comparison"]["not_found"] == ["dec:does-not-exist"]
    assert res["comparison"]["compared"] == 2


async def test_fewer_than_two_resolvable_rejected_honestly(
    client, db_session_factory,
):
    org_id, a, _ = await _pair_fixture(client, db_session_factory, "few")

    res = await _compare(db_session_factory, org_id,
                         [a, "dec:ghost-1", "dec:ghost-2"])
    assert res["rejected"] is True
    assert res["reason"] == "fewer_than_two_resolvable_decisions"
    assert res["not_found"] == ["dec:ghost-1", "dec:ghost-2"]


async def test_tenant_isolation_foreign_ids_never_resolve(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "iso")
    other = await register_org(client, email="4h6s6_iso2@test.co")
    other_id = other["organization"]["id"]
    await _seed_decision(db_session_factory, other_id, "dec:s6-own-x",
                         kind="pricing")
    await _seed_decision(db_session_factory, other_id, "dec:s6-own-y",
                         kind="pricing")

    # org B asks to compare its own two decisions plus org A's decision id:
    # the foreign id must land in not_found, never silently resolve.
    res = await _compare(db_session_factory, other_id,
                         ["dec:s6-own-x", a, "dec:s6-own-y"])
    assert not res.get("rejected")
    assert res["comparison"]["not_found"] == [a]
    assert res["comparison"]["decision_ids"] == ["dec:s6-own-x", "dec:s6-own-y"]
    assert all(c["decision_id"] != a for c in res["columns"])


async def test_longitudinal_context_matches_step5_cohort(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "long")
    await _seed_decision(db_session_factory, org_id, "dec:s6-long-c",
                         kind="pricing", outcome_kind="partial")

    res = await _compare(db_session_factory, org_id, [a, b])
    ctx = res["longitudinal_context"]
    assert set(ctx.keys()) == {"hire", "pricing"}  # kinds actually compared
    for k in ("hire", "pricing"):
        direct = await _direct_cohort(db_session_factory, org_id, kind=k)
        assert ctx[k]["decision_count"] == direct["cohort"]["decision_count"]
        assert ctx[k]["recorded_outcomes_by_kind"] == \
            direct["recorded_outcomes"]["by_kind"]
        assert ctx[k]["effectiveness_aggregate"] == \
            direct["effectiveness_aggregate"]
        assert ctx[k]["attribution_summary"] == direct["attribution_summary"]


async def test_contrasts_are_neutral_partitions(client, db_session_factory):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "cont")
    await _seed_decision(db_session_factory, org_id, "dec:s6-cont-c")

    ids = [a, b, "dec:s6-cont-c"]
    res = await _compare(db_session_factory, org_id, ids)
    c = res["contrasts"]
    # a and b carry outcome records; c does not
    assert sorted(c["outcome_record_present"]["with"]) == [a, b]
    assert c["outcome_record_present"]["without"] == ["dec:s6-cont-c"]
    # partitions always cover exactly the compared set
    for name, part in c.items():
        assert sorted(part["with"] + part["without"]) == sorted(ids)


async def test_compare_not_rank_no_forbidden_fields(client, db_session_factory):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "cmp")

    res = await _compare(db_session_factory, org_id, [a, b])
    h = res["honesty"]
    for flag in ("no_ranking_or_winner", "no_scores", "no_probability",
                 "no_recommendations", "no_forecasting", "no_learning",
                 "no_people_scoring", "compare_not_rank",
                 "chronology_is_not_causality", "read_only"):
        assert h[flag] is True

    forbidden_stems = ("winner", "rank", "score", "probab", "recommend",
                       "forecast", "best", "superior", "inferior")
    bad_keys = [
        k for k in _all_keys(res)
        if any(s in k.lower() for s in forbidden_stems)
        and not k.lower().startswith("no_")
        and k.lower() != "compare_not_rank"
    ]
    assert bad_keys == [], f"forbidden comparison keys leaked: {bad_keys}"

    blob = repr(res["columns"]) + repr(res["contrasts"])
    blob_l = blob.lower()
    for banned in ("better", "worse", "winner", "should", "superior",
                   "recommended"):
        assert banned not in blob_l, f"judgement vocabulary leaked: {banned}"


async def test_track_infrastructure_untouched_after_comparison(
    client, db_session_factory,
):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "trk")

    async with db_session_factory() as db:
        db.add(CompanyDecisionTrack(
            organization_id=org_id, cohort_key="kind:hire",
            decisions_measured=1, predictions_recorded=2, aligned=1,
            partial=1, misaligned=0, avg_effectiveness=0.8,
            source_event_id="evt:s6-trk-1",
            snapshot_ts=_ANCHOR,
        ))
        await db.commit()

    async with db_session_factory() as db:
        before_rows = list((await db.execute(
            select(CompanyDecisionTrack).where(
                CompanyDecisionTrack.organization_id == org_id)
        )).scalars().all())
        before_repr = [(t.id, t.cohort_key, t.decisions_measured, t.aligned,
                        t.snapshot_ts) for t in before_rows]

    before_stats = await _table_stats(db_session_factory, org_id)
    res = await _compare(db_session_factory, org_id, [a, b])

    after_stats = await _table_stats(db_session_factory, org_id)
    async with db_session_factory() as db:
        after_rows = list((await db.execute(
            select(CompanyDecisionTrack).where(
                CompanyDecisionTrack.organization_id == org_id)
        )).scalars().all())
        after_repr = [(t.id, t.cohort_key, t.decisions_measured, t.aligned,
                       t.snapshot_ts) for t in after_rows]

    assert before_repr == after_repr
    assert before_stats == after_stats
    assert not any("track" in k.lower() for k in _all_keys(res))


async def test_no_writes_no_events(client, db_session_factory):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "ro")
    before = await _table_stats(db_session_factory, org_id)
    await _compare(db_session_factory, org_id, [a, b])
    after = await _table_stats(db_session_factory, org_id)
    assert before == after


async def test_deterministic_identical_reads(client, db_session_factory):
    org_id, a, b = await _pair_fixture(client, db_session_factory, "det")
    x = await _compare(db_session_factory, org_id, [a, b])
    y = await _compare(db_session_factory, org_id, [a, b])
    assert x == y


async def test_no_llm_on_comparison_path():
    from app.intelligence import company_operating_engine as mod

    src = inspect.getsource(
        getattr(mod.CompanyOperatingEngine, "decision_performance_comparison"),
    ).lower()
    for banned in ("openai", "anthropic", "llm", "completion", "chat",
                   "httpx", "aiohttp", "requests", "prompt"):
        assert banned not in src, f"comparison references {banned}"
