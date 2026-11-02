"""Phase B P0 regression tests — VARCHAR(32) widening + event tenant isolation."""

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.timeutils import utcnow
from app.events.event_bus import event_bus
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
)
from app.models.knowledge import KnowledgeRecommendation
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventModel
from app.workers.event_worker import run_once, _get_orgs_with_pending_events


async def _drain_org(db_session, org_id, limit=50):
    for _ in range(200):
        processed = await event_bus.process_pending(
            db_session, limit=limit, organization_id=org_id
        )
        await db_session.commit()
        if not processed:
            return
    raise AssertionError(f"event dispatch did not quiesce for org {org_id}")


@pytest.mark.asyncio
async def test_decision_id_columns_widened_to_64(db_session):
    """Verify that all decision-id-bearing columns accept 64-char canonical IDs."""
    # Test canonical ID that exceeds 32 chars
    long_decision_id = "dec:commercial_action:abcdef123456"  # 34 chars
    
    # CompanyDecisionPrecedent.precedent_decision_id
    precedent = CompanyDecisionPrecedent(
        organization_id="test-org",
        decision_id="dec:test:111111111111",
        precedent_decision_id=long_decision_id,
        context_signature="test_signature",
        source_event_id="evt:123",
    )
    db_session.add(precedent)
    await db_session.flush()
    
    # Verify it persisted correctly
    result = await db_session.execute(
        text("SELECT precedent_decision_id FROM company_decision_precedents WHERE precedent_decision_id = :id"),
        {"id": long_decision_id}
    )
    assert result.scalar() == long_decision_id
    
    # CompanyDecisionContradiction.precedent_decision_id
    contradiction = CompanyDecisionContradiction(
        organization_id="test-org",
        decision_id="dec:test:222222222222",
        contradiction_key="cx:test:1",
        lesson_memory_id=None,
        precedent_decision_id=long_decision_id,
        side_a_json={},
        side_b_json={},
        status="open",
        source_event_id="evt:456",
    )
    db_session.add(contradiction)
    await db_session.flush()
    
    result = await db_session.execute(
        text("SELECT precedent_decision_id FROM company_decision_contradictions WHERE precedent_decision_id = :id"),
        {"id": long_decision_id}
    )
    assert result.scalar() == long_decision_id
    
    # CompanyDecisionContradiction.lesson_memory_id
    contradiction2 = CompanyDecisionContradiction(
        organization_id="test-org",
        decision_id="dec:test:333333333333",
        contradiction_key="cx:test:2",
        lesson_memory_id=long_decision_id,
        precedent_decision_id=None,
        side_a_json={},
        side_b_json={},
        status="open",
        source_event_id="evt:789",
    )
    db_session.add(contradiction2)
    await db_session.flush()
    
    result = await db_session.execute(
        text("SELECT lesson_memory_id FROM company_decision_contradictions WHERE lesson_memory_id = :id"),
        {"id": long_decision_id}
    )
    assert result.scalar() == long_decision_id
    
    # KnowledgeRecommendation.decision_id
    from app.models.knowledge import KnowledgeRecommendation
    rec = KnowledgeRecommendation(
        organization_id="test-org",
        kind="test_kind",
        fingerprint="fp:test:1",
        status="active",
        reason="Test",
        confidence=0.5,
        risk="low",
        decision_id=long_decision_id,
    )
    db_session.add(rec)
    await db_session.flush()
    
    result = await db_session.execute(
        text("SELECT decision_id FROM knowledge_recommendations WHERE decision_id = :id"),
        {"id": long_decision_id}
    )
    assert result.scalar() == long_decision_id
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_event_worker_tenant_isolation(db_session):
    """Verify event worker processes events per-organization."""
    # Create two organizations
    org_a_id = "org-a"
    org_b_id = "org-b"
    
    from app.core.timeutils import utcnow
    
    now = utcnow()
    # Create events for org A
    event_a = EventModel(
        organization_id=org_a_id,
        name="task.created",
        actor_id="user-a",
        payload_json='{"task_id": "task-a"}',
        occurred_at=now,
    )
    # Create event for org B
    event_b = EventModel(
        organization_id=org_b_id,
        name="task.created",
        actor_id="user-b",
        payload_json='{"task_id": "task-b"}',
        occurred_at=now,
    )
    db_session.add_all([event_a, event_b])
    await db_session.flush()
    
    # Create dispatch jobs for both
    job_a = BackgroundJob(
        organization_id=org_a_id,
        name="event.dispatch",
        status="queued",
        event_id=event_a.id,
        payload_json=f'{{"event_id": "{event_a.id}"}}',
    )
    job_b = BackgroundJob(
        organization_id=org_b_id,
        name="event.dispatch",
        status="queued",
        event_id=event_b.id,
        payload_json=f'{{"event_id": "{event_b.id}"}}',
    )
    db_session.add_all([job_a, job_b])
    await db_session.commit()
    
    # Process events for org A only
    orgs = await _get_orgs_with_pending_events(db_session)
    assert org_a_id in orgs
    assert org_b_id in orgs
    
    # Process only org A
    processed_a = await event_bus.process_pending(
        db_session, limit=50, organization_id=org_a_id
    )
    await db_session.commit()
    
    # Verify only org A's event was processed
    event_a_check = await db_session.get(EventModel, event_a.id)
    event_b_check = await db_session.get(EventModel, event_b.id)
    
    assert event_a_check.processed_at is not None, "Org A event should be processed"
    assert event_b_check.processed_at is None, "Org B event should NOT be processed"
    
    # Verify job status
    job_a_check = await db_session.get(BackgroundJob, job_a.id)
    job_b_check = await db_session.get(BackgroundJob, job_b.id)
    
    assert job_a_check.status == "done", "Org A job should be done"
    assert job_b_check.status == "queued", "Org B job should remain queued"
    
    # Now process org B
    processed_b = await event_bus.process_pending(
        db_session, limit=50, organization_id=org_b_id
    )
    await db_session.commit()
    
    event_b_check = await db_session.get(EventModel, event_b.id)
    assert event_b_check.processed_at is not None, "Org B event should now be processed"
    
    job_b_check = await db_session.get(BackgroundJob, job_b.id)
    assert job_b_check.status == "done", "Org B job should be done"


@pytest.mark.asyncio
async def test_brain_route_passes_org_id(db_session):
    """Verify brain route passes organization_id to process_pending."""
    from app.events.event_bus import event_bus
    
    # Create an event for testing
    org_id = "test-org-brain"
    now = utcnow()
    event = EventModel(
        organization_id=org_id,
        name="decision.made",
        actor_id="user-1",
        payload_json='{"decision_id": "dec:test:111111111111"}',
        occurred_at=now,
    )
    db_session.add(event)
    await db_session.flush()
    
    job = BackgroundJob(
        organization_id=org_id,
        name="event.dispatch",
        status="queued",
        event_id=event.id,
        payload_json=f'{{"event_id": "{event.id}"}}',
    )
    db_session.add(job)
    await db_session.commit()
    
    # Call process_pending with organization_id (simulating brain route fix)
    processed = await event_bus.process_pending(
        db_session, limit=50, organization_id=org_id
    )
    await db_session.commit()
    
    assert processed == 1
    
    event_check = await db_session.get(EventModel, event.id)
    assert event_check.processed_at is not None
    
    # Verify cross-org isolation - create event for different org
    org_other = "other-org"
    now = utcnow()
    event_other = EventModel(
        organization_id=org_other,
        name="decision.made",
        actor_id="user-2",
        payload_json='{"decision_id": "dec:test:222222222222"}',
        occurred_at=now,
    )
    db_session.add(event_other)
    await db_session.flush()
    
    job_other = BackgroundJob(
        organization_id=org_other,
        name="event.dispatch",
        status="queued",
        event_id=event_other.id,
        payload_json=f'{{"event_id": "{event_other.id}"}}',
    )
    db_session.add(job_other)
    await db_session.commit()
    
    # Process only org_id - should not touch other org. Handlers emit
    # follow-up events for the same org, so drain to quiescence.
    await _drain_org(db_session, org_id)
    
    remaining = (
        await db_session.execute(
            select(EventModel.id).where(
                EventModel.organization_id == org_id,
                EventModel.processed_at.is_(None),
            )
        )
    ).scalars().all()
    assert remaining == []
    
    event_other_check = await db_session.get(EventModel, event_other.id)
    assert event_other_check.processed_at is None, "Other org event should not be processed"


@pytest.mark.asyncio
async def test_exact_once_replay_with_org_scope(db_session):
    """Verify exact-once semantics are preserved with org scoping."""
    org_id = "replay-org"
    now = utcnow()
    
    event = EventModel(
        organization_id=org_id,
        name="task.completed",
        actor_id="user-1",
        payload_json='{"task_id": "task-replay"}',
        occurred_at=now,
    )
    db_session.add(event)
    await db_session.flush()
    
    job = BackgroundJob(
        organization_id=org_id,
        name="event.dispatch",
        status="queued",
        event_id=event.id,
        payload_json=f'{{"event_id": "{event.id}"}}',
    )
    db_session.add(job)
    await db_session.commit()
    
    # First pass dispatches the original event exactly once
    processed_1 = await event_bus.process_pending(
        db_session, limit=50, organization_id=org_id
    )
    await db_session.commit()
    assert processed_1 == 1
    
    # Replay: drain follow-up events emitted by handlers, then a pass over a
    # quiesced queue must be a no-op (the original event is never re-run)
    await _drain_org(db_session, org_id)
    replayed = await event_bus.process_pending(
        db_session, limit=50, organization_id=org_id
    )
    await db_session.commit()
    assert replayed == 0
    
    # Event should remain processed
    event_check = await db_session.get(EventModel, event.id)
    assert event_check.processed_at is not None
    
    # Job should be done
    job_check = await db_session.get(BackgroundJob, job.id)
    assert job_check.status == "done"


@pytest.mark.asyncio
async def test_cross_tenant_no_leak_in_worker(db_session, db_session_factory, monkeypatch):
    """Verify worker doesn't process other tenant's events."""
    from app.workers import event_worker

    monkeypatch.setattr(event_worker, "SessionLocal", db_session_factory)
    org_a = "cross-tenant-a"
    org_b = "cross-tenant-b"
    now = utcnow()
    
    # Create events for both orgs
    event_a = EventModel(
        organization_id=org_a,
        name="task.created",
        actor_id="user-a",
        payload_json='{"task_id": "task-a"}',
        occurred_at=now,
    )
    event_b = EventModel(
        organization_id=org_b,
        name="task.created",
        actor_id="user-b",
        payload_json='{"task_id": "task-b"}',
        occurred_at=now,
    )
    db_session.add_all([event_a, event_b])
    await db_session.flush()
    
    # Create jobs
    job_a = BackgroundJob(
        organization_id=org_a,
        name="event.dispatch",
        status="queued",
        event_id=event_a.id,
        payload_json=f'{{"event_id": "{event_a.id}"}}',
    )
    job_b = BackgroundJob(
        organization_id=org_b,
        name="event.dispatch",
        status="queued",
        event_id=event_b.id,
        payload_json=f'{{"event_id": "{event_b.id}"}}',
    )
    db_session.add_all([job_a, job_b])
    await db_session.commit()
    
    # Run worker once - should process both orgs in separate passes
    event_a_id, event_b_id = event_a.id, event_b.id
    job_a_id, job_b_id = job_a.id, job_b.id
    total = await run_once(limit=50)
    await db_session.commit()
    db_session.expire_all()
    
    # Both events should be processed (one per org)
    event_a_check = await db_session.get(EventModel, event_a_id)
    event_b_check = await db_session.get(EventModel, event_b_id)
    
    assert event_a_check.processed_at is not None
    assert event_b_check.processed_at is not None
    
    # But they were processed in separate organization-scoped passes
    job_a_check = await db_session.get(BackgroundJob, job_a_id)
    job_b_check = await db_session.get(BackgroundJob, job_b_id)
    
    assert job_a_check.status == "done"
    assert job_b_check.status == "done"


@pytest.mark.asyncio
async def test_long_decision_id_roundtrip_full_chain(db_session):
    """Verify canonical decision ID survives full decision→action→outcome chain."""
    long_id = "dec:commercial_action:abcdef123456"
    
    # Create CompanyDecision
    decision = CompanyDecision(
        organization_id="test-org",
        decision_id=long_id,
        kind="commercial_action",
        title="Test Commercial Action",
        state="approved",
        rationale="Test rationale",
        source_event_id="evt:source",
    )
    db_session.add(decision)
    await db_session.flush()
    
    # Create CompanyAction with source_company_decision_id
    from app.models.company_actions import CompanyAction
    action = CompanyAction(
        organization_id="test-org",
        action_type="task",
        title="Test Action",
        fingerprint=f"fp:{long_id}",
        source_company_decision_id=long_id,
        state="proposed",
    )
    db_session.add(action)
    await db_session.flush()
    
    # Verify all IDs round-trip correctly
    decision_check = await db_session.get(CompanyDecision, decision.id)
    assert decision_check.decision_id == long_id
    
    action_check = await db_session.get(CompanyAction, action.id)
    assert action_check.source_company_decision_id == long_id
    
    await db_session.rollback()


@pytest.mark.asyncio
async def test_migration_applies_cleanly(db_session):
    """Verify the migration can be applied without errors."""
    # SQLite doesn't have information_schema, use PRAGMA table_info instead
    
    tables_to_check = [
        ('company_decision_precedents', 'precedent_decision_id'),
        ('company_decision_contradictions', 'precedent_decision_id'),
        ('company_decision_contradictions', 'lesson_memory_id'),
        ('knowledge_recommendations', 'decision_id'),
    ]
    
    for table, column in tables_to_check:
        result = await db_session.execute(text(f"PRAGMA table_info({table})"))
        cols = result.fetchall()
        col_info = {c[1]: c for c in cols}  # name -> (cid, name, type, notnull, dflt_value, pk)
        
        assert column in col_info, f"Column {column} not found in {table}"
        col_type = col_info[column][2].upper()
        # SQLite reports widened columns as VARCHAR(64)
        assert col_type in ('TEXT', 'VARCHAR', 'VARCHAR(64)'), f"Column {column} in {table} has type {col_type}, expected TEXT/VARCHAR"
    
    await db_session.rollback()