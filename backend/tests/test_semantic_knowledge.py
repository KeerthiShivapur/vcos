"""Slice 4D.2 — semantic company knowledge intelligence.

Proves the four pillars end to end:

* provider abstraction (deterministic provider is default and reproducible),
* deterministic chunking + persisted ``KnowledgeVector`` lineage
  (idempotent re-index, stale-chunk deletion, delete removes rows),
* change-driven indexing through the durable event bus (create/publish/delete),
* hybrid retrieval under governance: relevance ranking with explicit score
  fields, tenant isolation, and project-anchored scoping for scoped callers —
  plus the canonical /brain/knowledge/search endpoint contract and knowledge
  evidence citation from the company brain.
"""

from sqlalchemy import select

from app.knowledge.chunking import chunk_text, content_hash
from app.models.knowledge import KnowledgeVector
from tests.conftest import register_org


async def _create_published_document(client, headers, *, title, content, project_id=None):
    response = await client.post(
        "/api/v1/documents",
        json={"title": title, "content": content, "project_id": project_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    document = response.json()
    published = await client.post(
        f"/api/v1/documents/{document['id']}/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    return published.json()


async def _index_all(db, *, organization_id, kind="document", entity_id):
    from app.knowledge import semantic_indexer

    written = await semantic_indexer.reindex_entity(
        db, organization_id=organization_id, kind=kind, entity_id=entity_id
    )
    await db.commit()
    return written


async def _vector_rows(db, *, organization_id, kind="document", entity_id=None):
    statement = select(KnowledgeVector).where(
        KnowledgeVector.organization_id == organization_id,
        KnowledgeVector.source_type == kind,
    )
    if entity_id:
        statement = statement.where(KnowledgeVector.source_id == entity_id)
    return list((await db.execute(statement)).scalars().all())


async def _drain_events(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _search(client, headers, question, kinds=None):
    response = await client.post(
        "/api/v1/brain/knowledge/search",
        json={"question": question, "kinds": kinds or ["document"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- 1. provider


async def test_embedding_provider_deterministic_default():
    from app.knowledge.embeddings import get_embedding_provider, reset_embedding_provider_for_tests

    reset_embedding_provider_for_tests()
    provider = get_embedding_provider()
    assert provider.name == "deterministic"
    assert provider.dim == 256

    first = (await provider.embed_many(["refund policy for enterprise accounts"]))[0]
    second = (await provider.embed_many(["refund policy for enterprise accounts"]))[0]
    assert first == second  # fully reproducible
    unrelated = (await provider.embed_many(["quarterly revenue grew by 12 percent"]))[0]
    related = (await provider.embed_many(["refund policy for enterprise accounts and approval workflow"]))[0]
    assert provider.cosine(first, related) > provider.cosine(first, unrelated)
    assert 0.0 <= provider.cosine(first, [0.0] * 256) <= 1.0
    reset_embedding_provider_for_tests()


# ---------------------------------------------------------------- 2. chunking


async def test_chunking_deterministic_and_capped():
    long_text = (
        "This paragraph explains the refund approval workflow in detail. "
        "It must be split into several bounded chunks so embedding stays local.\n\n"
        "A second paragraph covers escalation paths and approval authorities.\n"
        "Additional sentences keep the content long enough to force splitting."
    ) * 30
    first = chunk_text(long_text)
    second = chunk_text(long_text)
    assert first == second  # deterministic
    assert len(first) > 1
    assert all(len(chunk) <= 1200 for chunk in first)
    assert chunk_text("Short title") == ["Short title"]
    assert content_hash("a") == content_hash("a")
    assert content_hash("a") != content_hash("b")


# ----------------------------------------------------------- 3. indexer lineage


async def test_reindex_entity_creates_vectors_with_lineage(client, db_session_factory):
    org = await register_org(client, email="s4d2_lineage@test.co")
    document = await _create_published_document(
        client, org["headers"],
        title="Onboarding Runbook",
        content="Step one: request equipment. Step two: grant system access. "
                "Step three: schedule the first week with the buddy. " * 25,
    )
    async with db_session_factory() as db:
        written = await _index_all(
            db, organization_id=org["organization"]["id"], entity_id=document["id"]
        )
        assert written >= 1
        rows = await _vector_rows(
            db, organization_id=org["organization"]["id"], entity_id=document["id"]
        )
    assert rows
    assert rows[0].provider == "deterministic"
    assert rows[0].dim == 256
    assert rows[0].chunk_index == 0
    assert rows[0].content_hash
    assert rows[0].indexed_at is not None
    assert rows[0].source_updated_at is not None
    assert rows[0].embedding
    assert '"title":"Onboarding Runbook"' in rows[0].metadata_json
    chunk_indexes = sorted(row.chunk_index for row in rows)
    assert chunk_indexes == list(range(len(rows)))


async def test_reindex_idempotent_no_duplicates(client, db_session_factory):
    org = await register_org(client, email="s4d2_idempotent@test.co")
    document = await _create_published_document(
        client, org["headers"],
        title="Idempotency Spec",
        content="Re-running the same reindex must be a no-op and never duplicate "
                "rows even under the unique constraint. " * 20,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        first = await _index_all(db, organization_id=org_id, entity_id=document["id"])
        second = await _index_all(db, organization_id=org_id, entity_id=document["id"])
        assert second == 0  # nothing changed, no writes
        rows = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert first >= 1
    assert len(rows) == first
    hashes = [row.content_hash for row in rows]
    assert len(set(hashes)) == len(hashes)


async def test_reindex_deletes_stale_chunks(client, db_session_factory):
    org = await register_org(client, email="s4d2_stale@test.co")
    long_content = ("Long section alpha about procurement thresholds. " * 40
                    + "\n\nLong section beta about vendor risk scoring. " * 40
                    + "\n\nLong section gamma about contract renewals. " * 40)
    document = await _create_published_document(
        client, org["headers"], title="Procurement Playbook", content=long_content
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=document["id"])
        before = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert len(before) >= 2

    shortened = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"content": "Only the first section remains now."},
        headers=org["headers"],
    )
    assert shortened.status_code == 200, shortened.text
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=document["id"])
        after = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert len(after) < len(before)
    assert all(row.chunk_index < len(after) for row in after)
    stale_text = [row.chunk_text for row in before[len(after):]]
    for row in after:
        assert not any(text in row.chunk_text for text in stale_text)


async def test_delete_entity_removes_vectors(client, db_session_factory):
    org = await register_org(client, email="s4d2_delete@test.co")
    document = await _create_published_document(
        client, org["headers"],
        title="Obsolete Note",
        content="This content must never resurface once removed. " * 20,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=document["id"])
        assert await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    deleted = await client.delete(f"/api/v1/documents/{document['id']}", headers=org["headers"])
    assert deleted.status_code == 200, deleted.text
    await _drain_events(db_session_factory)
    async with db_session_factory() as db:
        remaining = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert remaining == []


# ------------------------------------------------------- 7. change-driven bus


async def test_event_pipeline_indexes_and_unindexes(client, db_session_factory):
    org = await register_org(client, email="s4d2_events@test.co")
    org_id = org["organization"]["id"]
    document = await _create_published_document(
        client, org["headers"],
        title="Event-Driven Knowledge",
        content="Writes flow through the durable event bus into the vector index. " * 15,
    )
    processed = await _drain_events(db_session_factory)
    assert processed >= 1
    async with db_session_factory() as db:
        rows = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert rows and rows[0].provider == "deterministic"

    removed = await client.delete(f"/api/v1/documents/{document['id']}", headers=org["headers"])
    assert removed.status_code == 200, removed.text
    await _drain_events(db_session_factory)
    async with db_session_factory() as db:
        remaining = await _vector_rows(db, organization_id=org_id, entity_id=document["id"])
    assert remaining == []


# ------------------------------------------------------------ 8. retrieval


async def test_semantic_search_relevance_and_lineage(client, db_session_factory):
    org = await register_org(client, email="s4d2_retrieval@test.co")
    headers = org["headers"]
    match = await _create_published_document(
        client, headers,
        title="Refund Policy",
        content="Refunds are approved by finance after the customer request is "
                "verified against the contract terms. Escalations go to the "
                "approval workflow. " * 15,
    )
    other = await _create_published_document(
        client, headers,
        title="Cloud Architecture Blueprint",
        content="The platform runs on Kubernetes with event-driven microservices "
                "and a multi-region disaster recovery design. " * 15,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=match["id"])
        await _index_all(db, organization_id=org_id, entity_id=other["id"])

    body = await _search(client, headers, "how does the refund approval workflow work")
    assert body["results"]
    assert body["provider"] == "deterministic"
    top = body["results"][0]
    assert top["source_id"] == match["id"]
    assert top["source_type"] == "document"
    assert top["title"] == "Refund Policy"
    assert top["url"].startswith("/documents/")
    assert top["semantic_score"] >= 0.0
    assert top["lexical_score"] >= 0.0
    assert top["retrieval_score"] >= top["semantic_score"]
    assert top["updated_at"] and top["indexed_at"]
    assert "embedding" not in top
    assert top["scope"] == "org"


async def test_semantic_search_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="s4d2_tenant_a@test.co")
    org_b = await register_org(client, email="s4d2_tenant_b@test.co")
    secret = await _create_published_document(
        client, org_a["headers"],
        title="Secret Launch Plan",
        content="The confidential product launch happens next quarter. " * 20,
    )
    org_a_id = org_a["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_a_id, entity_id=secret["id"])

    body = await _search(client, org_b["headers"], "secret launch plan next quarter")
    assert body["results"] == []
    assert all(result["source_id"] != secret["id"] for result in body["results"])


async def test_semantic_search_scoped_caller_project_anchor(client, db_session_factory):
    org = await register_org(client, email="s4d2_scoped@test.co")
    headers = org["headers"]
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Scoped Knowledge Project", "description": "anchor", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Scoped Knowledge", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")

    invited = await client.post(
        "/api/v1/users/invite",
        json={"email": "s4d2_scoped_u@test.co", "full_name": "Scoped Reader", "role": "employee"},
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invited.json()["token"], "full_name": "Scoped Reader", "password": "S4DPass123!"},
    )
    assert joined.status_code == 201, joined.text
    scoped_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": joined.json()["user"]["id"], "role_id": manager_role["id"],
              "scope_id": scope["id"]},
        headers=headers,
    )
    assignments = (
        await client.get(
            "/api/v1/governance/assignments",
            params={"user_id": joined.json()["user"]["id"]},
            headers=headers,
        )
    ).json()
    org_wide = next(a for a in assignments if a["scope_id"] is None)
    removed = await client.delete(
        f"/api/v1/governance/assignments/{org_wide['id']}", headers=headers
    )
    assert removed.status_code == 200, removed.text

    # The brain search surface stays org-wide authority; the founder delegates
    # the brain:read permission to the scoped manager (existing 4C delegation
    # machinery) so the scoped caller may search — while retrieval scoping is
    # still governed by their scoped assignment alone (project-anchored only).
    delegated = await client.post(
        "/api/v1/governance/delegations",
        json={
            "granted_to_user": joined.json()["user"]["id"],
            "permission_code": "brain:read",
            "reason": "slice 4d.2 scoped knowledge search",
        },
        headers=headers,
    )
    assert delegated.status_code == 201, delegated.text

    anchored = await _create_published_document(
        client, headers,
        title="Scoped Finance Doc",
        content="Expense policy details visible inside the scoped project. " * 15,
        project_id=project["id"],
    )
    org_wide_doc = await _create_published_document(
        client, headers,
        title="Org Wide Secret",
        content="Executive compensation details shared only organization wide. " * 15,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=anchored["id"])
        await _index_all(db, organization_id=org_id, entity_id=org_wide_doc["id"])

    body = await _search(client, scoped_headers, "expense policy details")
    visible_ids = [result["source_id"] for result in body["results"]]
    assert anchored["id"] in visible_ids
    assert org_wide_doc["id"] not in visible_ids
    assert body["results"][0]["scope"] == "project"


# -------------------------------------------------------------- 11-12. endpoints


async def test_brain_knowledge_search_endpoint_contract(client, db_session_factory):
    org = await register_org(client, email="s4d2_endpoint@test.co")
    document = await _create_published_document(
        client, org["headers"],
        title="Endpoint Contract Doc",
        content="The endpoint returns evidence lineage with explicit scores. " * 15,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=document["id"])

    body = await _search(client, org["headers"], "endpoint evidence lineage scores")
    assert {"query", "results", "total", "limit", "provider", "truncated"} <= set(body)
    assert body["results"] and body["results"][0]["source_id"] == document["id"]

    empty = await client.post(
        "/api/v1/brain/knowledge/search",
        json={"question": "   "},
        headers=org["headers"],
    )
    assert empty.status_code == 422

    anonymous = await client.post(
        "/api/v1/brain/knowledge/search",
        json={"question": "anything"},
    )
    assert anonymous.status_code in (401, 403)


async def test_brain_answer_cites_knowledge_evidence(client, db_session_factory):
    org = await register_org(client, email="s4d2_answer@test.co")
    document = await _create_published_document(
        client, org["headers"],
        title="Refund Policy",
        content="Refund requests are approved by the finance workflow and must be "
                "filed within thirty days of the invoice. " * 15,
    )
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        await _index_all(db, organization_id=org_id, entity_id=document["id"])

    answer = await client.post(
        "/api/v1/brain/answer",
        json={"question": "What does the refund policy say about approvals?"},
        headers=org["headers"],
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    document_claims = [
        claim for claim in body.get("claims", [])
        if any(evidence.get("type") == "document" for evidence in claim.get("evidence", []))
    ]
    assert document_claims
    evidence = document_claims[0]["evidence"][0]
    assert evidence["id"] == document["id"]
    assert evidence["url"].startswith("/documents/")
