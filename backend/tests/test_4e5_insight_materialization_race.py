"""4E.5 concurrency regression — insight fingerprint materialization race.

GET /api/v1/brain/knowledge/brief (and every other materialize caller) can be
invoked concurrently by two workers deriving the same insight from the same
canonical substrate. The unique constraint
uq_knowledge_intel_insight_fingerprint (organization_id, kind, fingerprint)
remains the enforcement mechanism; the losing worker must resolve the
conflict to the winning record instead of surfacing an HTTP 500.

These tests run against real PostgreSQL (pg_db_session_factory /
TEST_DATABASE_URL). Concurrency is synchronized by observing the losing
session's PostgreSQL lock wait in pg_stat_activity — deterministic proof of
the race, not sleep-based timing.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.knowledge.action_engine import action_engine, _is_fingerprint_conflict
from app.knowledge.intelligence_engine import _fingerprint
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeIntelInsight,
    KnowledgeIntelInsightEvent,
    KnowledgeSource,
    KnowledgeTopic,
)
from app.models.organization import Organization

TOPIC_NAME = "Concurrency Probe"


async def _seed_org_with_topic(factory, *, tag):
    org_id = uuid.uuid4().hex
    source_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            Organization(id=org_id, name=f"Race {tag}", slug=f"race-{uuid.uuid4().hex[:18]}")
        )
        await session.flush()
        topic = KnowledgeTopic(
            organization_id=org_id, name=f"{TOPIC_NAME} {tag}", status="active"
        )
        session.add(topic)
        await session.flush()
        session.add(
            KnowledgeSource(
                organization_id=org_id,
                source_type="document",
                source_id=source_id,
                kind="internal",
                title=f"{TOPIC_NAME} {tag} quarterly note",
                content_hash=uuid.uuid4().hex * 2,
                lifecycle="active",
                source_status="active",
                authority_level=3,
                freshness_score=90,
                freshness_label="high",
                source_updated_at=now,
            )
        )
        claim = KnowledgeClaim(
            organization_id=org_id,
            subject_type="document",
            subject_id=source_id,
            predicate="status",
            object_text=f"{TOPIC_NAME} {tag} is on track.",
            claim_type="fact",
            status="supported",
            authority_level=3,
            confidence=0.8,
            source_type="document",
            source_id=source_id,
            topic_id=topic.id,
        )
        session.add(claim)
        await session.commit()
        return org_id, topic.id, source_id, claim.id


async def _cleanup(factory, *org_ids):
    async with factory() as session:
        for org_id in org_ids:
            await session.execute(
                text("DELETE FROM organizations WHERE id = :oid"), {"oid": org_id}
            )
        await session.commit()


async def _backend_pid(session):
    return (await session.execute(text("SELECT pg_backend_pid()"))).scalar()


async def _wait_for_lock_waits(observer, pids, expected, timeout=20.0):
    deadline = time.monotonic() + timeout
    waiting = 0
    while time.monotonic() < deadline:
        waiting = 0
        for pid in pids:
            state = (
                await observer.execute(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            ).scalar_one_or_none()
            if state == "Lock":
                waiting += 1
        if waiting >= expected:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"expected {expected} lock waits, observed {waiting} (pids={pids})"
    )


async def _insight_rows(factory, org_id):
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(KnowledgeIntelInsight).where(
                        KnowledgeIntelInsight.organization_id == org_id
                    )
                )
            ).scalars().all()
        )


def _assert_single_row_per_fingerprint(rows):
    keys = [(row.kind, row.fingerprint) for row in rows]
    assert len(keys) == len(set(keys)), "duplicate (kind, fingerprint) rows in one tenant"


async def test_sequential_replay_is_exact_once(pg_db_session_factory):
    org_id, topic_id, _source_id, claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="replay"
    )
    try:
        async with pg_db_session_factory() as session:
            first = await action_engine.materialize(session, organization_id=org_id)
            await session.commit()
            second = await action_engine.materialize(session, organization_id=org_id)
            await session.commit()

        assert first["created"] >= 1, "the seeded topic materializes insights"
        assert second["created"] == 0, "replay creates nothing new"
        assert second["updated"] >= 1, "replay refreshes the existing records"

        rows = await _insight_rows(pg_db_session_factory, org_id)
        _assert_single_row_per_fingerprint(rows)
        discovery = [row for row in rows if row.kind == "discovery"]
        assert discovery, "the fresh topic materializes a discovery insight"
        assert discovery[0].fingerprint == _fingerprint("discovery", topic_id)
        assert discovery[0].status == "active"
        assert claim_id in json.loads(discovery[0].source_claims_json or "[]")

        async with pg_db_session_factory() as session:
            events = list(
                (
                    await session.execute(
                        select(KnowledgeIntelInsightEvent).where(
                            KnowledgeIntelInsightEvent.organization_id == org_id,
                            KnowledgeIntelInsightEvent.action == "created",
                        )
                    )
                ).scalars().all()
            )
        assert len(events) == len(rows), "exactly one 'created' audit event per insight"
    finally:
        await _cleanup(pg_db_session_factory, org_id)


async def test_concurrent_materialize_converges_to_one_insight(pg_db_session_factory):
    org_id, topic_id, _source_id, claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="race"
    )
    try:
        async with pg_db_session_factory() as leader, pg_db_session_factory() as follower:
            follower_pid = await _backend_pid(follower)
            leader_result = await action_engine.materialize(leader, organization_id=org_id)
            assert leader_result["created"] >= 1

            follower_task = asyncio.create_task(
                action_engine.materialize(follower, organization_id=org_id)
            )
            await _wait_for_lock_waits(leader, [follower_pid], 1)
            await leader.commit()

            follower_result = await asyncio.wait_for(follower_task, timeout=60)
            await follower.commit()
            assert (await follower.execute(text("SELECT 1"))).scalar() == 1

        assert follower_result["created"] == 0, "the losing worker creates nothing"
        assert follower_result["updated"] >= 1, "the losing worker resolves to the winner"

        rows = await _insight_rows(pg_db_session_factory, org_id)
        _assert_single_row_per_fingerprint(rows)
        discovery = [row for row in rows if row.kind == "discovery"]
        assert discovery and discovery[0].fingerprint == _fingerprint("discovery", topic_id)
        assert discovery[0].status == "active"
        assert claim_id in json.loads(discovery[0].source_claims_json or "[]")
    finally:
        await _cleanup(pg_db_session_factory, org_id)


async def test_multiple_concurrent_materializers_converge(pg_db_session_factory):
    org_id, topic_id, _source_id, _claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="multi"
    )
    try:
        async with pg_db_session_factory() as leader, pg_db_session_factory() as f1, pg_db_session_factory() as f2:
            pid1 = await _backend_pid(f1)
            pid2 = await _backend_pid(f2)
            leader_result = await action_engine.materialize(leader, organization_id=org_id)
            assert leader_result["created"] >= 1

            task1 = asyncio.create_task(
                action_engine.materialize(f1, organization_id=org_id)
            )
            task2 = asyncio.create_task(
                action_engine.materialize(f2, organization_id=org_id)
            )
            await _wait_for_lock_waits(leader, [pid1, pid2], 2)
            await leader.commit()

            # Two losers converge on the same winning row; the first to finish
            # may hold the row lock while the other is blocked on it. Commit
            # each session as soon as its task completes so the blocked
            # materializer can converge — never await both before committing.
            pending = {task1: f1, task2: f2}
            summary: dict[asyncio.Task, dict] = {}
            while pending:
                finished, _ = await asyncio.wait(
                    list(pending), timeout=60, return_when=asyncio.FIRST_COMPLETED
                )
                if not finished:
                    raise AssertionError(
                        "concurrent materializers did not converge within 60s"
                    )
                for task in finished:
                    summary[task] = task.result()
                    await pending.pop(task).commit()

            first = summary[task1]
            second = summary[task2]

        assert first["created"] == 0 and second["created"] == 0
        assert first["updated"] >= 1 and second["updated"] >= 1
        rows = await _insight_rows(pg_db_session_factory, org_id)
        _assert_single_row_per_fingerprint(rows)
        assert any(row.fingerprint == _fingerprint("discovery", topic_id) for row in rows)
    finally:
        await _cleanup(pg_db_session_factory, org_id)


async def test_knowledge_brief_survives_fingerprint_race(pg_db_session_factory):
    org_id, _topic_id, _source_id, _claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="brief"
    )
    try:
        async with pg_db_session_factory() as leader, pg_db_session_factory() as follower:
            follower_pid = await _backend_pid(follower)
            await action_engine.materialize(leader, organization_id=org_id)

            brief_task = asyncio.create_task(
                action_engine.brief(
                    follower, organization_id=org_id, user=None, since_hours=24
                )
            )
            await _wait_for_lock_waits(leader, [follower_pid], 1)
            await leader.commit()

            result = await asyncio.wait_for(brief_task, timeout=60)
            await follower.commit()

        assert isinstance(result, dict)
        assert "counts" in result and "attention" in result
        rows = await _insight_rows(pg_db_session_factory, org_id)
        _assert_single_row_per_fingerprint(rows)
    finally:
        await _cleanup(pg_db_session_factory, org_id)


async def test_fingerprint_conflict_classifier_against_real_constraints(pg_db_session_factory):
    org_id, _topic_id, source_id, _claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="classifier"
    )
    try:
        async with pg_db_session_factory() as seed, pg_db_session_factory() as rival:
            seed.add(
                KnowledgeIntelInsight(
                    organization_id=org_id,
                    kind="discovery",
                    fingerprint="fp-classifier",
                    title="t",
                    summary="s",
                )
            )
            await seed.commit()
            rival.add(
                KnowledgeIntelInsight(
                    organization_id=org_id,
                    kind="discovery",
                    fingerprint="fp-classifier",
                    title="t",
                    summary="s",
                )
            )
            with pytest.raises(IntegrityError) as fingerprint_error:
                await rival.flush()
            await rival.rollback()
        assert _is_fingerprint_conflict(fingerprint_error.value)

        async with pg_db_session_factory() as session:
            session.add(
                KnowledgeSource(
                    organization_id=org_id,
                    source_type="document",
                    source_id=source_id,
                    kind="internal",
                    title="duplicate source id",
                    content_hash=uuid.uuid4().hex * 2,
                )
            )
            with pytest.raises(IntegrityError) as other_unique_error:
                await session.flush()
            await session.rollback()
        assert not _is_fingerprint_conflict(other_unique_error.value)

        async with pg_db_session_factory() as session:
            session.add(
                KnowledgeTopic(
                    organization_id=uuid.uuid4().hex,
                    name=f"ghost-{uuid.uuid4().hex[:10]}",
                    status="active",
                )
            )
            with pytest.raises(IntegrityError) as foreign_key_error:
                await session.flush()
            await session.rollback()
        assert not _is_fingerprint_conflict(foreign_key_error.value)
    finally:
        await _cleanup(pg_db_session_factory, org_id)


async def test_fingerprint_unique_per_tenant_not_global(pg_db_session_factory):
    org_a, _topic_a, _src_a, _claim_a = await _seed_org_with_topic(
        pg_db_session_factory, tag="tenant-a"
    )
    org_b, _topic_b, _src_b, _claim_b = await _seed_org_with_topic(
        pg_db_session_factory, tag="tenant-b"
    )
    try:
        async with pg_db_session_factory() as session:
            session.add(
                KnowledgeIntelInsight(
                    organization_id=org_a,
                    kind="discovery",
                    fingerprint="fp-shared",
                    title="t",
                    summary="s",
                )
            )
            session.add(
                KnowledgeIntelInsight(
                    organization_id=org_b,
                    kind="discovery",
                    fingerprint="fp-shared",
                    title="t",
                    summary="s",
                )
            )
            await session.commit()

        async with pg_db_session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(KnowledgeIntelInsight).where(
                            KnowledgeIntelInsight.fingerprint == "fp-shared"
                        )
                    )
                ).scalars().all()
            )
        assert {row.organization_id for row in rows} == {org_a, org_b}
        assert len(rows) == 2, "the same fingerprint is legal once per tenant"
    finally:
        await _cleanup(pg_db_session_factory, org_a, org_b)


async def test_genuine_integrity_error_is_not_swallowed(pg_db_session_factory, monkeypatch):
    import app.knowledge.action_engine as action_module

    monkeypatch.setattr(action_module, "_is_fingerprint_conflict", lambda exc: False)
    org_id, _topic_id, _source_id, _claim_id = await _seed_org_with_topic(
        pg_db_session_factory, tag="genuine"
    )
    try:
        async with pg_db_session_factory() as leader, pg_db_session_factory() as follower:
            follower_pid = await _backend_pid(follower)
            await action_engine.materialize(leader, organization_id=org_id)

            follower_task = asyncio.create_task(
                action_engine.materialize(follower, organization_id=org_id)
            )
            await _wait_for_lock_waits(leader, [follower_pid], 1)
            await leader.commit()

            with pytest.raises(IntegrityError):
                await asyncio.wait_for(follower_task, timeout=60)
            await follower.rollback()

        rows = await _insight_rows(pg_db_session_factory, org_id)
        _assert_single_row_per_fingerprint(rows)
        assert rows, "the winner's committed records remain"
    finally:
        await _cleanup(pg_db_session_factory, org_id)
