"""Slice 4E.2 — Universal Knowledge Ingestion.

Meaningful company activity speaks one internal language in the 4E.1
canonical model.  Real, durable events that were already flowing through the
org bus — messages, task transitions, meetings, memory records, pattern
confirmations — are funnelled through a single ingestion contract
(``canonical_engine.ingest_event``) with no new emission sites:

* live families: message/memory/pattern normalizers prove that chats and
  learned memories land as canonical sources with claims + evidence,
* temporal truth across activity: a task that moves to completed supersedes
  its own earlier status claims instead of deleting them,
* noise boundary: "Good morning everyone!" never becomes knowledge while
  "migration moved to Friday" is a candidate,
* exact-once + ordering safety: replays create no duplicate claims and a
  stale (out-of-order) event cannot roll history back,
* governance inherits: scope-anchored activity (tasks) is visible to scoped
  readers, unanchored chatter (org messages) is not; rival tenants see
  nothing,
* bounded reconcile now spans every family and recovers out-of-band content
  edits.
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.knowledge.canonical_service import SOURCE_FAMILIES, canonical_engine, _load_provenance
from app.models.communication import Message
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeSource,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _drain_events(db_session_factory, limit=300):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _source_rows(db_session_factory, organization_id, source_type, source_id=None):
    async with db_session_factory() as session:
        statement = select(KnowledgeSource).where(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.source_type == source_type,
        )
        if source_id:
            statement = statement.where(KnowledgeSource.source_id == source_id)
        statement = statement.order_by(KnowledgeSource.created_at.asc())
        return list((await session.execute(statement)).scalars().all())


async def _claim_rows(db_session_factory, organization_id, subject_type, subject_id):
    async with db_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.subject_type == subject_type,
                        KnowledgeClaim.subject_id == subject_id,
                    ).order_by(KnowledgeClaim.valid_from.asc())
                )
            ).scalars().all()
        )


async def _evidence_rows(db_session_factory, organization_id, claim_id):
    async with db_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.organization_id == organization_id,
                        KnowledgeEvidence.claim_id == claim_id,
                    )
                )
            ).scalars().all()
        )


async def _create_conversation(client, headers, title="ops-room"):
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    created = await client.post(
        "/api/v1/conversations",
        json={"type": "channel", "title": title, "member_ids": [me]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _send_message(client, headers, conversation_id, content):
    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )
    assert sent.status_code in (200, 201), sent.text
    return sent.json()


async def _create_task(client, headers, title, project_id=None):
    payload = {"title": title}
    if project_id:
        payload["project_id"] = project_id
    created = await client.post("/api/v1/tasks", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _transition_task(client, headers, task_id, status):
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"status": status}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _emit_pattern_event(db_session_factory, organization_id, *, pattern_id, pattern_type, key, status, count, confidence):
    from app.services.event_service import event_service

    async with db_session_factory() as session:
        await event_service.emit(
            session,
            name=f"pattern.{status}",
            organization_id=organization_id,
            payload={
                "pattern_id": pattern_id,
                "pattern_type": pattern_type,
                "key": key,
                "status": status,
                "count": count,
                "confidence": round(confidence, 3),
            },
        )
        await session.commit()


# ------------------------------------------- messages speak one internal language


async def test_meaningful_message_becomes_canonical_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e2_msg@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "release-room")
    message = await _send_message(
        client, headers, conv["id"],
        "The production migration has been moved to Friday.",
    )
    processed = await _drain_events(db_session_factory)
    assert processed >= 1, "messaging.message_sent was consumed"

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert len(sources) == 1, "exactly one canonical source per message"
    source = sources[0]
    assert source.source_status == "sent"
    assert source.authority_level == 1
    assert source.freshness_label == "very_high"
    assert source.content_hash

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.claim_type == "statement"
    assert claim.predicate == "stated"
    assert claim.status == "candidate", "raw chatter is knowledge-candidate, not asserted truth"
    assert "migration" in claim.object_text and "Friday" in claim.object_text
    assert claim.confidence is not None

    evidence = await _evidence_rows(db_session_factory, org["organization"]["id"], claim.id)
    assert len(evidence) == 1
    assert evidence[0].role == "primary"
    assert evidence[0].source_id == message["id"]


async def test_message_noise_never_becomes_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e2_noise@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "watercooler")
    for content in ("Good morning everyone!", "ok", "thx", "😀"):
        await _send_message(client, headers, conv["id"], content)
    await _drain_events(db_session_factory)

    sources, claims = [], []
    async with db_session_factory() as session:
        sources = list(
            (
                await session.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.organization_id == org["organization"]["id"],
                        KnowledgeSource.source_type == "message",
                    )
                )
            ).scalars().all()
        )
        claims = list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org["organization"]["id"],
                        KnowledgeClaim.subject_type == "message",
                    )
                )
            ).scalars().all()
        )
    assert len(sources) == 0, "noise never lands a canonical source"
    assert len(claims) == 0

    meaningful = await _send_message(
        client, headers, conv["id"], "The migration window is confirmed for 2am."
    )
    await _drain_events(db_session_factory)
    rows = await _source_rows(db_session_factory, org["organization"]["id"], "message", meaningful["id"])
    assert len(rows) == 1, "signal still flows through the same contract"


# ------------------------------------------------- ledgers: task, meeting, memory


async def test_task_lifecycle_lands_temporal_claim_chain(client, db_session_factory):
    org = await register_org(client, email="4e2_task@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration")
    task = await _create_task(client, headers, "Backfill the ledger", project["id"])
    await _transition_task(client, headers, task["id"], "in_progress")
    await _transition_task(client, headers, task["id"], "blocked")
    await _drain_events(db_session_factory)
    await _transition_task(client, headers, task["id"], "completed")
    await _drain_events(db_session_factory)

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    assert len(sources) == 1, "task activity is one canonical source, not one per event"
    source = sources[0]
    assert source.source_status == "completed"
    assert source.lifecycle == "updated"
    assert _load_provenance(source.provenance_json)["project_id"] == project["id"]
    assert _load_provenance(source.provenance_json)["author_id"] is not None, (
        "task governance scope is preserved"
    )
    assert source.authority_level == 2

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    assert len(claims) >= 3, "each meaningful status step keeps its own claim"
    latest = claims[-1]
    assert latest.predicate == "status"
    assert latest.status == "candidate", "task activity is knowledge-candidate until confirmed higher"
    assert "completed" in latest.object_text
    assert any(c.object_text.endswith("blocked") and c.status == "superseded" for c in claims), (
        "intermediate statuses are superseded, never deleted"
    )
    for older in claims[:-1]:
        assert older.valid_to is not None
        assert older.superseded_by is not None, "every superseded claim keeps its successor"
    reachable = {latest.id}
    for older in claims[:-1]:
        hop = older.superseded_by
        while hop not in reachable and hop is not None:
            link = next(c for c in claims if c.id == hop)
            hop = link.superseded_by
        assert hop is not None, f"chain from {older.id} orphans"
    assert claims[0].superseded_by is not None or len(claims) == 1
    assert any(c.object_text.endswith("blocked") for c in claims), "blocked step kept"


async def test_completed_meeting_becomes_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e2_meeting@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Onboarding")
    created = await client.post(
        "/api/v1/meetings",
        json={"title": "Onboarding kickoff", "project_id": project["id"], "meeting_type": "team"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    meeting = created.json()
    completed = await client.post(f"/api/v1/meetings/{meeting['id']}/complete", headers=headers)
    assert completed.status_code == 200, completed.text
    await _drain_events(db_session_factory)

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "meeting", meeting["id"])
    assert len(sources) == 1
    source = sources[0]
    assert source.source_status == "completed"
    assert _load_provenance(source.provenance_json)["project_id"] == project["id"]

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "meeting", meeting["id"])
    assert claims
    claim = claims[-1]
    assert claim.claim_type == "fact"
    assert claim.predicate == "occurred"
    assert "Onboarding kickoff" in claim.object_text


async def test_memory_record_flows_into_canonical_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e2_mem@test.co")
    headers = org["headers"]
    recorded = await client.post(
        "/api/v1/brain/memory",
        json={
            "memory_type": "lesson",
            "title": "Staging flakiness",
            "content": "E2E suite fails on staging every Monday morning.",
            "tags": ["staging", "e2e"],
            "importance": "medium",
        },
        headers=headers,
    )
    assert recorded.status_code in (200, 201), recorded.text
    memory = recorded.json()
    await _drain_events(db_session_factory)

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "memory", memory["id"])
    assert len(sources) == 1
    source = sources[0]
    assert source.source_status == "active"
    assert source.authority_level == 3, "recorded memory outranks chatter"

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "memory", memory["id"])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.claim_type == "memory"
    assert claim.predicate == "remembers"
    assert "Staging flakiness" in claim.object_text


async def test_confirmed_pattern_lands_high_authority_knowledge(client, db_session_factory):
    org = await register_org(client, email="4e2_pattern@test.co")
    headers = org["headers"]
    from app.models.intelligence import PatternDetection

    async with db_session_factory() as session:
        from datetime import datetime, timezone as tz

        now = datetime.now(tz.utc)
        pattern = PatternDetection(
            organization_id=org["organization"]["id"],
            pattern_type="repeated_delay",
            key="deploy:api",
            title="Repeated deployment delays",
            family="execution",
            status="confirmed",
            count=6,
            confidence=0.93,
            description="Six deployments slipped into the afternoon window.",
            first_seen=now,
            last_seen=now,
        )
        session.add(pattern)
        await session.commit()
        pattern_id = pattern.id
    await _emit_pattern_event(
        db_session_factory, org["organization"]["id"],
        pattern_id=pattern_id, pattern_type="repeated_delay", key="deploy:api",
        status="confirmed", count=6, confidence=0.93,
    )
    await _drain_events(db_session_factory)

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "pattern", pattern_id)
    assert len(sources) == 1
    source = sources[0]
    assert source.authority_level == 4, "confirmed patterns rise above raw memory"
    assert source.lifecycle == "validated"

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "pattern", pattern_id)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.claim_type == "pattern"
    assert claim.predicate == "signals"
    assert "deploy:api" in claim.object_text


# ------------------------------------- one contract: replay, ordering, recovery


async def test_exact_once_under_replay(client, db_session_factory):
    org = await register_org(client, email="4e2_idem@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "ops")
    message = await _send_message(client, headers, conv["id"], "Deploy is scheduled for midnight.")
    await _drain_events(db_session_factory)
    first = await _claim_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert len(first) == 1

    await _drain_events(db_session_factory)  # worker restart → same events re-pulled
    await _drain_events(db_session_factory)
    again = await _claim_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert len(again) == 1, "replays never duplicate canonical claims"
    assert again[0].id == first[0].id

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert sources[0].version == 1


async def test_stale_out_of_order_event_cannot_rewind_history(client, db_session_factory):
    org = await register_org(client, email="4e2_order@test.co")
    headers = org["headers"]
    task = await _create_task(client, headers, "Ship the release")
    await _transition_task(client, headers, task["id"], "completed")
    await _drain_events(db_session_factory)
    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    latest = claims[-1]
    assert "completed" in latest.object_text

    from app.models.notification import Event

    stale_time = latest.valid_from - timedelta(seconds=60)
    stale_payload = json.dumps(
        {"task_id": task["id"], "title": "Ship the release", "status": "in_progress"}
    )
    async with db_session_factory() as session:
        stale = Event(
            name="task.transitioned",
            organization_id=org["organization"]["id"],
            occurred_at=stale_time,
            payload_json=stale_payload,
        )
        result = await canonical_engine.ingest_event(
            db=session, event=stale, payload=json.loads(stale_payload)
        )
        await session.commit()
    assert result.get("status") == "skipped", result
    assert result.get("reason") == "stale_replay", "the ordering guard rejects it"

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    assert sources[0].source_status == "completed", "history is not rewound"
    claims_after = await _claim_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    assert len(claims_after) == len(claims), "no rollback claim was created"


async def test_reconcile_spans_every_family_and_recovers_edits(client, db_session_factory):
    org = await register_org(client, email="4e2_recon@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "ops")
    message = await _send_message(client, headers, conv["id"], "Deployment cutover is at 9pm.")
    task = await _create_task(client, headers, "Verify cutover")
    await _drain_events(db_session_factory)
    before = await _claim_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert before, "events already landed canonical claims"

    # simulate a lost canonical store: rows disappear, origin objects survive
    async with db_session_factory() as session:
        for model in (KnowledgeSource, KnowledgeClaim, KnowledgeEvidence):
            gone = list(
                (
                    await session.execute(
                        select(model).where(
                            model.organization_id == org["organization"]["id"]
                        )
                    )
                ).scalars().all()
            )
            for row in gone:
                await session.delete(row)
        await session.commit()

    async with db_session_factory() as session:
        result = await canonical_engine.reconcile(
            db=session, organization_id=org["organization"]["id"], limit=3
        )
        await session.commit()
    assert result["processed"] <= 3, "reconcile stays hard-capped"
    kinds_seen = {item["entity_type"] for item in result["items"]}
    assert kinds_seen == {"message", "task"}, "reconcile now spans live families"

    # out-of-band content edit (no event emitted) is recovered by reconcile
    async with db_session_factory() as session:
        row = (
            await session.execute(
                select(Message).where(
                    Message.id == message["id"],
                    Message.organization_id == org["organization"]["id"],
                )
            )
        ).scalar_one()
        row.content = "Deployment cutover is at 9pm and the window is 30 minutes."
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()

    async with db_session_factory() as session:
        result = await canonical_engine.reconcile(
            db=session, organization_id=org["organization"]["id"], limit=5
        )
        await session.commit()
    edited = [item for item in result["items"] if item["entity_id"] == message["id"]]
    assert edited, "drift was recovered"
    assert edited[0]["entity_type"] == "message"

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "message", message["id"])
    assert len(claims) == 2
    edited_claim = next(c for c in claims if "30 minutes" in c.object_text)
    prior_claim = next(c for c in claims if c.id != edited_claim.id)
    assert edited_claim.status == "candidate", "messages stay knowledge-candidates"
    assert prior_claim.status == "superseded"
    assert prior_claim.superseded_by == edited_claim.id


# ------------------------------------------------------- governance inheritance


async def test_tenant_isolation_for_live_families(client, db_session_factory):
    org_a = await register_org(client, email="4e2_iso_a@test.co")
    headers_a = org_a["headers"]
    conv = await _create_conversation(client, headers_a, "war-room")
    message = await _send_message(
        client, headers_a, conv["id"], "The board meeting has been rescheduled."
    )
    await _drain_events(db_session_factory)

    org_b = await register_org(client, email="4e2_iso_b@test.co")
    headers_b = org_b["headers"]
    await _drain_events(db_session_factory)

    registry = (await client.get("/api/v1/brain/knowledge", headers=headers_b)).json()
    assert registry["total"] == 0, "rival tenant never sees canonical chatter"
    hidden = await client.get(f"/api/v1/brain/knowledge/sources/message/{message['id']}", headers=headers_b)
    assert hidden.status_code == 404
    claims = (await client.get("/api/v1/brain/knowledge/claims", headers=headers_b)).json()
    assert claims["total"] == 0


async def test_scoped_reader_sees_anchored_not_unanchored_activity(client, db_session_factory):
    org = await register_org(client, email="4e2_gov@test.co")
    headers = org["headers"]
    visible_proj = await h.project(client, headers, "Governed Project")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.project(client, headers, "Hidden Project")

    await _create_task(client, headers, "Visible migration task", visible_proj["id"])
    await _create_task(client, headers, "Hidden strategy task", hidden_proj["id"])
    conv = await _create_conversation(client, headers, "general")
    await _send_message(client, headers, conv["id"], "The new pricing page ships today.")
    await _drain_events(db_session_factory)

    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4e2_gov_u@test.co")
    registry = (await client.get("/api/v1/brain/knowledge", headers=scoped)).json()
    titles = {s["title"] for s in registry["sources"]}
    assert registry["total"] == 1, "governance constrains retrieval itself"
    assert titles == {"Visible migration task"}, f"unexpected: {titles}"
    assert registry["scope"] == "project"

    visible_source = next(
        s for s in await _source_rows(db_session_factory, org["organization"]["id"], "task", None)
        if s.title == "Visible migration task"
    )
    seen = await client.get(
        f"/api/v1/brain/knowledge/sources/task/{visible_source.source_id}",
        headers=scoped,
    )
    assert seen.status_code == 200

    hidden_source = next(
        s for s in await _source_rows(db_session_factory, org["organization"]["id"], "task", None)
        if s.title == "Hidden strategy task"
    )
    blocked = await client.get(
        f"/api/v1/brain/knowledge/sources/task/{hidden_source.source_id}",
        headers=scoped,
    )
    assert blocked.status_code == 404, "hidden-project activity stays hidden"


async def test_universal_flow_is_fully_registered_in_source_families(client, db_session_factory):
    org = await register_org(client, email="4e2_fams@test.co")
    headers = org["headers"]
    registry = (await client.get("/api/v1/brain/knowledge", headers=headers)).json()
    assert set(registry["by_kind"]) <= set(SOURCE_FAMILIES), (
        "one registry vocabulary for every family"
    )
    assert len(SOURCE_FAMILIES) >= 11, (
        "the universal contract covers documents, live activity and learned truth"
    )
    rejected = await client.get("/api/v1/brain/knowledge/sources/planet/x", headers=headers)
    assert rejected.status_code == 404, "families outside the contract are impossible"