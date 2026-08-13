"""Slice 4E.3 — Universal Knowledge Understanding & Synthesis.

4E.2 funnels every meaningful piece of activity into one canonical model;
4E.3 connects those sources. Claims from different families that speak about
the same topic are synthesized into ONE topic-anchored understanding claim
with a full relationship graph:

* cross-source synthesis: message + task + memory about the same topic land
  in a single understanding claim with supporting claims, evidence rows and
  graph edges,
* contradiction detection: two claims with different values for the same
  facet conflict; the winner is resolved by authority, then valid_from; the
  loser stays as evidence with its resolution recorded,
* temporal reasoning: when the evidence changes the understanding evolves —
  the old understanding is superseded (never deleted) and the timeline shows
  both "what was true" and "what is true now",
* exact-once synthesis: replaying or re-triggering with unchanged evidence
  refreshes last_seen only — never a duplicate claim, never a spurious
  supersession,
* governance first: scoped readers only ever see the evidence inside their
  scope; a topic with no visible evidence is indistinguishable from a
  missing topic (404),
* evidence-backed answers: every answer carries the exact evidence chain,
* tenant isolation: rival tenants see nothing.
"""

import json
from urllib.parse import quote

from sqlalchemy import select

from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeRelation,
    KnowledgeSource,
    KnowledgeTopic,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _drain_events(db_session_factory, limit=300):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _synthesis_claims(db_session_factory, organization_id, topic_name):
    async with db_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(KnowledgeClaim)
                    .join(KnowledgeTopic, KnowledgeTopic.id == KnowledgeClaim.topic_id)
                    .where(
                        KnowledgeClaim.organization_id == organization_id,
                        KnowledgeClaim.claim_type == "synthesis",
                        KnowledgeTopic.name == topic_name,
                    )
                    .order_by(KnowledgeClaim.valid_from.asc())
                )
            ).scalars().all()
        )


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


async def _source_rows(db_session_factory, organization_id, source_type, source_id=None):
    async with db_session_factory() as session:
        statement = select(KnowledgeSource).where(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.source_type == source_type,
        )
        if source_id:
            statement = statement.where(KnowledgeSource.source_id == source_id)
        return list((await session.execute(statement)).scalars().all())


async def _relations(db_session_factory, organization_id, target_id):
    async with db_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(KnowledgeRelation).where(
                        KnowledgeRelation.organization_id == organization_id,
                        KnowledgeRelation.target_type == "topic",
                        KnowledgeRelation.target_id == target_id,
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


async def _record_memory(client, headers, title, content, tags):
    recorded = await client.post(
        "/api/v1/brain/memory",
        json={
            "memory_type": "lesson",
            "title": title,
            "content": content,
            "tags": tags,
            "importance": "medium",
        },
        headers=headers,
    )
    assert recorded.status_code in (200, 201), recorded.text
    return recorded.json()


def _topic_path(topic_name):
    return quote(topic_name, safe="")


# ------------------------------------------------ multiple sources, one state


async def test_cross_family_evidence_lands_one_understanding(client, db_session_factory):
    org = await register_org(client, email="4e3_cross@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    task = await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration window is confirmed for 2am.")
    await _record_memory(
        client, headers, "Migration go-live",
        "The migration go-live has been agreed for Monday.",
        ["migration", "go-live"],
    )
    await _drain_events(db_session_factory)

    # every family produced a canonical claim about the same topic
    task_claims = await _claim_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    assert task_claims, "task speaks canonical"
    sources = await _source_rows(db_session_factory, org["organization"]["id"], "memory")
    assert len(sources) == 1, "memory speaks canonical"

    claims = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    assert len(claims) >= 1
    understanding = claims[-1]
    assert understanding.status != "superseded", "the newest understanding is current"
    assert all(c.status == "superseded" for c in claims[:-1]), (
        "older versions are superseded, never deleted"
    )
    assert understanding.predicate == "synthesizes"
    assert understanding.object_text.startswith("Topic 'migration':")
    assert understanding.authority_level == 3, "max authority across evidence (memory outranks task)"
    assert understanding.status == "supported"
    assert understanding.confidence > 0.4, "deterministic confidence is populated"
    assert understanding.topic_id is not None
    assert understanding.valid_to is None, "the current understanding is open"
    assert understanding.last_seen is not None

    supporting = json.loads(understanding.supporting_claim_ids_json)
    assert len(supporting) == 3, "message + task + memory claims all support it"
    async with db_session_factory() as session:
        supporting_claims = list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org["organization"]["id"],
                        KnowledgeClaim.id.in_(supporting),
                    )
                )
            ).scalars().all()
        )
    assert {c.subject_type for c in supporting_claims} == {"message", "task", "memory"}, (
        "supporting claims are cross-family"
    )

    async with db_session_factory() as session:
        evidence_rows = list(
            (
                await session.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.claim_id == understanding.id
                    )
                )
            ).scalars().all()
        )
    assert len(evidence_rows) == 3
    assert {e.role for e in evidence_rows} == {"supporting"}

    edges = await _relations(db_session_factory, org["organization"]["id"], understanding.topic_id)
    assert len(edges) >= 3, "graph enrichment wires each family to the topic"
    assert {e.relation_type for e in edges} <= {"concerns", "relates_to"}

    # the API surfaces the same single state
    state = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/state",
            headers=headers,
        )
    ).json()
    assert state["current_state"]["id"] == understanding.id
    assert state["evidence"]["total"] == 3
    assert set(state["evidence"]["by_family"]) >= {"message", "task", "memory"}
    assert state["scope"] == "org"


# ----------------------------------------------- contradiction detection + law


async def test_contradiction_new_wins_and_loser_stays_as_evidence(client, db_session_factory):
    org = await register_org(client, email="4e3_contra@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "budget")
    old = await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _drain_events(db_session_factory)
    new = await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")
    await _drain_events(db_session_factory)

    old_claims = await _claim_rows(db_session_factory, org["organization"]["id"], "message", old["id"])
    new_claims = await _claim_rows(db_session_factory, org["organization"]["id"], "message", new["id"])
    claims = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    assert len(claims) == 2, "the contradiction produced an evolution"
    current, prior = claims[-1], claims[0]
    assert prior.status == "superseded" and prior.valid_to is not None
    assert prior.superseded_by == current.id
    assert current.object_text.startswith("Topic 'migration': contested.")

    contradicting = json.loads(current.contradicting_claim_ids_json)
    assert len(contradicting) == 1, "the losing budget value is recorded"
    entry = contradicting[0]
    assert entry["claim_id"] == old_claims[0].id
    assert entry["facet"] == "currency"
    assert entry["winner_claim_id"] == new_claims[0].id
    assert entry["resolution"] == "newer valid_from", "equal authority breaks on valid_from"
    supporting = json.loads(current.supporting_claim_ids_json)
    assert new_claims[0].id in supporting and old_claims[0].id not in supporting

    async with db_session_factory() as session:
        evidence_rows = list(
            (
                await session.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.claim_id == current.id
                    )
                )
            ).scalars().all()
        )
    roles = {e.source_id: e.role for e in evidence_rows}
    assert roles[old["id"]] == "contradicted", "the loser remains as contradicting evidence"
    assert roles[new["id"]] == "supporting"

    contradictions = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/contradictions",
            headers=headers,
        )
    ).json()
    assert contradictions["total"] == 1
    assert contradictions["contradictions"][0]["resolution"] == "newer valid_from"


async def test_contradiction_higher_authority_wins_over_recency(client, db_session_factory):
    org = await register_org(client, email="4e3_auth@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")
    task = await _create_task(client, headers, "Migration budget 8 lakh")
    await _drain_events(db_session_factory)

    task_claims = await _claim_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
    claims = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    current = claims[-1]
    contradicting = json.loads(current.contradicting_claim_ids_json)
    assert len(contradicting) == 2, "both chat values lost to the team record"
    assert all(
        c["resolution"] == "authority 2 > 1" for c in contradicting
    ), "authority resolves, not recency"
    assert current.authority_level == 2
    assert current.object_text.startswith("Topic 'migration': contested.")
    assert "Budget: 8 lakh" in current.object_text, "the winning facet is stated"


# ----------------------------------------------------- temporal reasoning


async def test_understanding_evolves_and_history_is_kept(client, db_session_factory):
    org = await register_org(client, email="4e3_evolve@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "Migration moved to Friday.")
    await _drain_events(db_session_factory)
    await _send_message(client, headers, conv["id"], "Migration moved to next Monday.")
    await _drain_events(db_session_factory)

    claims = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    assert len(claims) == 2, "v1 -> v2 evolution"
    v1, v2 = claims[0], claims[-1]
    assert "Friday" in v1.object_text and "Monday" in v2.object_text
    assert v1.status == "superseded" and v1.superseded_by == v2.id
    assert v1.valid_to is not None and v2.valid_to is None

    timeline = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/timeline",
            headers=headers,
        )
    ).json()
    kinds = {e["kind"] for e in timeline["events"]}
    assert "synthesis" in kinds, "the timeline shows how understanding developed"
    versions = [e for e in timeline["events"] if e["kind"] == "synthesis"]
    assert len(versions) == 2
    assert versions[0]["status"] == "superseded" and versions[0]["valid_to"] is not None
    assert versions[-1]["status"] != "superseded"

    state = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/state",
            headers=headers,
        )
    ).json()
    assert "Monday" in state["current_state"]["object_text"], "what is true now"
    assert state["evolution"]["versions"] == 1, "one prior understanding kept"
    detail = (
        await client.get(
            f"/api/v1/brain/knowledge/claims/{v1.id}", headers=headers
        )
    ).json()
    assert detail["claim"]["status"] == "superseded"
    assert detail["superseded_by"]["id"] == v2.id, "temporal truth links forward"


async def test_exact_once_synthesis_and_manual_trigger(client, db_session_factory):
    org = await register_org(client, email="4e3_idem@test.co")
    headers = org["headers"]
    conv = await _create_conversation(client, headers, "ops")
    await _send_message(client, headers, conv["id"], "The migration is scheduled for 2am.")
    await _drain_events(db_session_factory)
    first = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    assert len(first) == 1

    await _drain_events(db_session_factory)
    await _drain_events(db_session_factory)
    again = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    assert len(again) == 1, "replays never duplicate the understanding"
    assert again[0].id == first[0].id

    triggered = await client.post(
        f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/synthesize",
        headers=headers,
    )
    assert triggered.status_code == 200, triggered.text
    result = triggered.json()
    assert result["synthesized"] is False, "unchanged evidence is a no-op"
    assert result["claim_id"] == first[0].id


# ------------------------------------------------------------------ governance


async def test_scoped_reader_only_sees_evidence_inside_scope(client, db_session_factory):
    org = await register_org(client, email="4e3_gov@test.co")
    headers = org["headers"]
    visible_proj = await h.project(client, headers, "Governed Migration")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.project(client, headers, "Shadow Migration")
    visible_task = await _create_task(client, headers, "Migration alpha", visible_proj["id"])
    hidden_task = await _create_task(client, headers, "Stealth migration beta", hidden_proj["id"])
    conv = await _create_conversation(client, headers, "general")
    await _send_message(client, headers, conv["id"], "The migration cutover is tonight.")
    await _drain_events(db_session_factory)

    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4e3_gov_u@test.co")

    state = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/state",
            headers=scoped,
        )
    ).json()
    assert state["scope"] == "project"
    visible_ids = {c["subject_id"] for c in state["evidence"]["claims"]}
    assert visible_ids == {visible_task["id"]}, f"unexpected: {visible_ids}"
    assert state["evidence"]["total"] == 1, "governance constrains retrieval itself"
    assert not any(c["subject_type"] == "message" for c in state["evidence"]["claims"]), (
        "unanchored chatter stays hidden from scoped readers"
    )
    assert state["current_state"] is not None, "visible evidence keeps the understanding"

    hidden_state = await client.get(
        f"/api/v1/brain/knowledge/topics/{_topic_path('stealth')}/state",
        headers=scoped,
    )
    assert hidden_state.status_code == 404, "a topic with no visible evidence is hidden"
    org_state = await client.get(
        f"/api/v1/brain/knowledge/topics/{_topic_path('stealth')}/state",
        headers=headers,
    )
    assert org_state.status_code == 200, "the org-wide reader still sees it"

    org_detail = await client.get(
        f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/state",
        headers=headers,
    )
    assert org_detail.status_code == 200
    assert org_detail.json()["evidence"]["total"] == 3, "org-wide reader sees everything"


# ----------------------------------------------------- evidence-backed answers


async def test_evidence_backed_answer_cites_exact_evidence_chain(client, db_session_factory):
    org = await register_org(client, email="4e3_answer@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration is delayed by 2 days.")
    await _drain_events(db_session_factory)

    answer = (
        await client.get(
            f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/evidence",
            params={"question": "what is the status of the migration?"},
            headers=headers,
        )
    ).json()
    assert answer["question"].startswith("what is the status")
    assert "migration" in answer["answer"].lower()
    assert answer["confidence"] is not None and answer["risk"] is not None
    assert answer["evidence"], "citations are mandatory"
    for citation in answer["evidence"]:
        assert citation["claim_id"] and citation["type"] in ("task", "message", "memory")
        assert citation["excerpt"], "every citation quotes its source"
        assert citation["authority_level"] >= 1
        assert citation["valid_from"], "citations carry their temporal anchor"

    claim_ids = [c["claim_id"] for c in answer["evidence"]]
    async with db_session_factory() as session:
        resolved = list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org["organization"]["id"],
                        KnowledgeClaim.id.in_(claim_ids),
                    )
                )
            ).scalars().all()
        )
    assert len(resolved) == len(claim_ids), "every cited claim exists"


# ------------------------------------------------------------ tenant isolation


async def test_topic_knowledge_never_crosses_tenants(client, db_session_factory):
    org_a = await register_org(client, email="4e3_iso_a@test.co")
    headers_a = org_a["headers"]
    conv = await _create_conversation(client, headers_a, "release")
    await _send_message(client, headers_a, conv["id"], "The migration is happening Friday.")
    await _drain_events(db_session_factory)

    org_b = await register_org(client, email="4e3_iso_b@test.co")
    headers_b = org_b["headers"]
    await _drain_events(db_session_factory)

    claims_a = await _synthesis_claims(db_session_factory, org_a["organization"]["id"], "migration")
    assert len(claims_a) == 1

    state = await client.get(
        f"/api/v1/brain/knowledge/topics/{_topic_path('migration')}/state",
        headers=headers_b,
    )
    assert state.status_code == 404, "rival tenant never sees the topic state"
    claim = await client.get(
        f"/api/v1/brain/knowledge/claims/{claims_a[0].id}", headers=headers_b
    )
    assert claim.status_code == 404

    registry_b = (await client.get("/api/v1/brain/knowledge", headers=headers_b)).json()
    assert registry_b["total"] == 0


# ---------------------------------------------------------------- provenance


async def test_synthesis_claim_carries_full_provenance(client, db_session_factory):
    org = await register_org(client, email="4e3_prov@test.co")
    headers = org["headers"]
    project = await h.project(client, headers, "Migration Program")
    task = await _create_task(client, headers, "Migration runbook", project["id"])
    conv = await _create_conversation(client, headers, "release")
    await _send_message(client, headers, conv["id"], "The migration window is confirmed for 2am.")
    await _drain_events(db_session_factory)

    claims = await _synthesis_claims(db_session_factory, org["organization"]["id"], "migration")
    understanding = claims[-1]
    assert len(claims) == 2, "task then message -> v1, v2"
    detail = (
        await client.get(
            f"/api/v1/brain/knowledge/claims/{understanding.id}", headers=headers
        )
    ).json()
    assert detail["topic"]["id"] == understanding.topic_id
    assert detail["authority"]["label"] == "team_record", "task (2) outranks message (1)"
    assert len(detail["supporting_claims"]) == 2
    assert detail["related_entities"], "related entities are attached"
    entity_keys = {(e["type"], e["id"]) for e in detail["related_entities"]}
    assert (task["id"] in {k[1] for k in entity_keys}), "the task entity is related"
    sources = detail["evidence"]
    assert len(sources) == 2
    assert all(s["title"] for s in sources), "every evidence row cites its source title"
    task_source = next(
        s for s in await _source_rows(db_session_factory, org["organization"]["id"], "task", task["id"])
        if s.source_id == task["id"]
    )
    assert any(s["source_id"] == task_source.source_id for s in sources)
