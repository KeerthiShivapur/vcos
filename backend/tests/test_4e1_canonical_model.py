"""Slice 4E.1 — Knowledge Foundation & Canonical Model.

Proves the universal ingestion contract end to end:

* event-driven canonical ingestion: existing durable events (create, publish,
  approve, decide) land exactly one canonical KnowledgeSource per object with
  lifecycle, authority and freshness — no scans, no new emission sites,
* temporal truth: an update supersedes the previous claim (valid_to +
  superseded_by) instead of deleting it, and re-processing unchanged content
  is a no-op (exact-once),
* authority model: approved policies are official (5) / authoritative,
  made decisions are authoritative (4), published documents are documented (3),
* governed retrieval: /brain/knowledge endpoints are tenant-scoped and filter
  to caller access before exposure — hidden sources return 404 and never
  appear in registries,
* bounded on-demand reconcile: hard-capped, never a full-org scan.
"""

from sqlalchemy import select

from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeSource,
    KnowledgeTopic,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _drain_events(db_session_factory, limit=200):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _create_published_document(client, headers, *, title, content, category=None, project_id=None, summary=None):
    payload = {"title": title, "content": content}
    if category:
        payload["category"] = category
    if project_id:
        payload["project_id"] = project_id
    if summary:
        payload["summary"] = summary
    created = await client.post("/api/v1/documents", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    doc = created.json()
    published = await client.post(f"/api/v1/documents/{doc['id']}/publish", headers=headers)
    assert published.status_code == 200, published.text
    return published.json()


async def _source_rows(db_session_factory, organization_id, source_type, source_id=None):
    async with db_session_factory() as session:
        statement = select(KnowledgeSource).where(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.source_type == source_type,
        )
        if source_id:
            statement = statement.where(KnowledgeSource.source_id == source_id)
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
                    )
                    .order_by(KnowledgeClaim.valid_from.asc())
                )
            ).scalars().all()
        )


# ------------------------------------------------- event-driven canonical model


async def test_events_create_canonical_source_with_claims_and_topics(client, db_session_factory):
    org = await register_org(client, email="4e1_ingest@test.co")
    headers = org["headers"]
    doc = await _create_published_document(
        client, headers,
        title="Refund policy v2", content="Refunds are processed within 14 days.",
        category="finance",
    )
    await _drain_events(db_session_factory)

    sources = await _source_rows(db_session_factory, org["organization"]["id"], "document", doc["id"])
    assert len(sources) == 1, "exactly one canonical source per object"
    source = sources[0]
    assert source.lifecycle == "validated"
    assert source.source_status == "published"
    assert source.authority_level == 3
    assert source.freshness_label == "very_high"
    assert source.content_hash

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "document", doc["id"])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.predicate == "states"
    assert claim.status == "supported"
    assert claim.source_id == doc["id"]

    async with db_session_factory() as session:
        evidence = list(
            (
                await session.execute(
                    select(KnowledgeEvidence).where(
                        KnowledgeEvidence.organization_id == org["organization"]["id"],
                        KnowledgeEvidence.claim_id == claim.id,
                    )
                )
            ).scalars().all()
        )
    assert len(evidence) == 1
    assert evidence[0].role == "primary"

    async with db_session_factory() as session:
        topic = (
            await session.execute(
                select(KnowledgeTopic).where(
                    KnowledgeTopic.organization_id == org["organization"]["id"],
                    KnowledgeTopic.name == "finance",
                )
            )
        ).scalar_one_or_none()
    assert topic is not None, "category seeds the canonical topic registry"
    assert topic.entity_id == doc["id"]


# ------------------------------------------------- temporal truth + exact-once


async def test_update_supersedes_claims_instead_of_deleting(client, db_session_factory):
    org = await register_org(client, email="4e1_temporal@test.co")
    headers = org["headers"]
    doc = await _create_published_document(client, headers, title="Pricing policy", content="Standard plan is 99.")
    await _drain_events(db_session_factory)

    updated = await client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"content": "Standard plan is 149.", "change_note": "Price change"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    await _drain_events(db_session_factory)

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "document", doc["id"])
    assert len(claims) == 2
    older, newer = claims[0], claims[1]
    assert newer.status == "supported"
    assert older.status == "superseded"
    assert older.valid_to is not None, "superseded claims keep valid_to"
    assert older.superseded_by == newer.id, "temporal chain: old -> new"

    source = (await _source_rows(db_session_factory, org["organization"]["id"], "document", doc["id"]))[0]
    assert source.lifecycle == "updated"
    assert source.version >= 2


async def test_reingest_is_exact_once_no_duplicate_claims(client, db_session_factory):
    org = await register_org(client, email="4e1_idem@test.co")
    headers = org["headers"]
    doc = await _create_published_document(client, headers, title="Onboarding handbook", content="Welcome aboard.")
    await _drain_events(db_session_factory)
    first = await _claim_rows(db_session_factory, org["organization"]["id"], "document", doc["id"])
    assert len(first) == 1

    # replay the same events: unchanged content must be a no-op
    await _drain_events(db_session_factory)
    await _drain_events(db_session_factory)
    again = await _claim_rows(db_session_factory, org["organization"]["id"], "document", doc["id"])
    assert len(again) == 1, "reprocessing unchanged content creates no new claims"
    assert again[0].id == first[0].id


# ------------------------------------------------------------------- authority


async def test_approved_policy_is_official_and_authoritative(client, db_session_factory):
    org = await register_org(client, email="4e1_policy@test.co")
    headers = org["headers"]
    created = await client.post(
        "/api/v1/policies",
        json={"title": "Expense approval threshold", "content": "All expenses above 500 need approval.", "category": "finance"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    approved = await client.post(f"/api/v1/policies/{policy['id']}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    await _drain_events(db_session_factory)

    source = (await _source_rows(db_session_factory, org["organization"]["id"], "policy", policy["id"]))[0]
    assert source.lifecycle == "validated"
    assert source.authority_level == 5

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "policy", policy["id"])
    assert claims
    claim = claims[-1]
    assert claim.status == "authoritative"
    assert claim.predicate == "effective"
    assert "Expense approval threshold" in claim.object_text


async def test_made_decision_records_chosen_option(client, db_session_factory):
    org = await register_org(client, email="4e1_decision@test.co")
    headers = org["headers"]
    created = await client.post(
        "/api/v1/decisions",
        json={
            "title": "Choose analytics store",
            "context": "Primary datastore for analytics.",
            "content": "Evaluating options.",
            "options": [{"title": "Postgres"}, {"title": "ClickHouse"}],
            "participants": [],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    decision = created.json()
    options = (await client.get(f"/api/v1/decisions/{decision['id']}/options", headers=headers)).json()
    chosen = await client.post(
        f"/api/v1/decisions/{decision['id']}/choose",
        json={"option_id": options[1]["id"], "reason": "Columnar for analytics"},
        headers=headers,
    )
    assert chosen.status_code == 200, chosen.text
    await _drain_events(db_session_factory)

    claims = await _claim_rows(db_session_factory, org["organization"]["id"], "decision", decision["id"])
    assert claims, "decision.made must land a canonical claim"
    claim = claims[-1]
    assert claim.claim_type == "decision"
    assert claim.status in ("authoritative", "supported")
    assert "ClickHouse" in claim.object_text, "the chosen option is part of the canonical claim"
    assert claim.predicate == "decision"


# -------------------------------------------------- governance + tenant isolation


async def test_tenant_isolation_registry_and_detail(client, db_session_factory):
    org_a = await register_org(client, email="4e1_iso_a@test.co")
    headers_a = org_a["headers"]
    doc = await _create_published_document(client, headers_a, title="Secret roadmap", content="Launch October.")
    await _drain_events(db_session_factory)

    org_b = await register_org(client, email="4e1_iso_b@test.co")
    headers_b = org_b["headers"]
    await _drain_events(db_session_factory)

    registry = (await client.get("/api/v1/brain/knowledge", headers=headers_b)).json()
    assert registry["total"] == 0, "rival org never sees this org's canonical sources"
    hidden = await client.get(f"/api/v1/brain/knowledge/sources/document/{doc['id']}", headers=headers_b)
    assert hidden.status_code == 404
    claims = (await client.get("/api/v1/brain/knowledge/claims", headers=headers_b)).json()
    assert claims["total"] == 0


async def test_scoped_reader_only_sees_accessible_sources(client, db_session_factory):
    org = await register_org(client, email="4e1_gov@test.co")
    headers = org["headers"]
    visible_proj = await h.project(client, headers, "Canonical Visible")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    await _create_published_document(
        client, headers, title="Visible doc", content="Inside the visible project.",
        project_id=visible_proj["id"],
    )
    await _create_published_document(client, headers, title="Hidden doc", content="Outside any scoped project.")
    await _drain_events(db_session_factory)
    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4e1_gov_u@test.co")

    registry = (await client.get("/api/v1/brain/knowledge", headers=scoped)).json()
    assert registry["total"] == 1, "governance constrains retrieval itself"
    assert registry["sources"][0]["title"] == "Visible doc"
    assert registry["scope"] == "project"

    hidden = await client.get(
        f"/api/v1/brain/knowledge/sources/document/{registry['sources'][0]['source_id']}",
        headers=scoped,
    )
    assert hidden.status_code == 200


async def test_canonical_endpoints_require_permission(client, db_session_factory):
    resp = await client.get("/api/v1/brain/knowledge")
    assert resp.status_code in (401, 403), resp.text


# ------------------------------------------------- bounded on-demand reconcile


async def test_reconcile_is_bounded_and_idempotent(client, db_session_factory):
    org = await register_org(client, email="4e1_recon@test.co")
    headers = org["headers"]
    for i in range(4):
        await _create_published_document(
            client, headers, title=f"Reconcile doc {i}", content=f"Content number {i}."
        )
    await _drain_events(db_session_factory)

    from app.knowledge.canonical_service import canonical_engine

    async with db_session_factory() as session:
        result = await canonical_engine.reconcile(db=session, organization_id=org["organization"]["id"], limit=2)
        await session.commit()
    assert result["processed"] <= 2, "reconcile is hard-capped"
    assert len(result["items"]) == result["processed"]

    async with db_session_factory() as session:
        result = await canonical_engine.reconcile(db=session, organization_id=org["organization"]["id"], limit=2)
        await session.commit()
    assert result["processed"] <= 2
    async with db_session_factory() as session:
        all_claims = list(
            (
                await session.execute(
                    select(KnowledgeClaim).where(
                        KnowledgeClaim.organization_id == org["organization"]["id"]
                    )
                )
            ).scalars().all()
        )
    assert len(all_claims) == 4, "reconcile never duplicates canonical claims"
