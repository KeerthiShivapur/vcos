"""Phase 4 — Documents: CRUD, lifecycle, versions, collaboration, relations, tenancy."""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _create_document(client, headers, **overrides):
    payload = {
        "title": "Onboarding Handbook",
        "description": "How we onboard new team members",
        "content": "Day one starts with a welcome call. Then accounts are provisioned, "
        "mentors are assigned, and the 30-60-90 plan is reviewed weekly.",
        "category": "hr",
        "tags": ["onboarding", "people"],
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/documents", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_document_crud_lifecycle(client):
    org = await register_org(client, email="doc@phase4.test.co")
    headers = org["headers"]
    doc = await _create_document(client, headers)
    doc_id = doc["id"]
    assert doc["kind"] == "document"
    assert doc["tags"] == ["onboarding", "people"]
    assert doc["author_id"] is not None

    updated = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"content": "Updated content for version two.", "change_note": "Rewrote section 1"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["status"] == "draft"

    published = await client.post(f"/api/v1/documents/{doc_id}/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["published_at"] is not None

    got = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["view_count"] >= 1

    versions = await client.get(f"/api/v1/knowledge/document/{doc_id}/versions", headers=headers)
    assert versions.status_code == 200, versions.text
    assert len(versions.json()) >= 2
    assert versions.json()[0]["version"] == 2

    deleted = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    missing = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_document_review_workflow_creates_approval(client):
    org = await register_org(client, email="docflow@phase4.test.co")
    headers = org["headers"]
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "owner@phase4.test.co", "full_name": "Doc Owner", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Doc Owner", "password": "Owner123!"},
    )
    assert registered.status_code == 201, registered.text
    owner_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    owner_id = (await client.get("/api/v1/employees/me", headers=owner_headers)).json()["id"]

    doc = await _create_document(client, headers, owner_id=owner_id)
    doc_id = doc["id"]

    submitted = await client.post(f"/api/v1/documents/{doc_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "in_review"

    approvals = await client.get("/api/v1/approvals", headers=headers)
    assert approvals.status_code == 200, approvals.text
    types = [a["approval_type"] for a in approvals.json()]
    assert "document" in types

    approved = await client.post(f"/api/v1/documents/{doc_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "published"


@pytest.mark.asyncio
async def test_document_collaboration_and_relations(client):
    org = await register_org(client, email="doccollab@phase4.test.co")
    headers = org["headers"]
    doc = await _create_document(client, headers)
    doc_id = doc["id"]

    comment = await client.post(
        f"/api/v1/knowledge/document/{doc_id}/comments",
        json={"content": "Great start — let's add the remote-work section."},
        headers=headers,
    )
    assert comment.status_code == 201, comment.text
    assert comment.json()["author_name"] is not None
    comment_id = comment.json()["id"]

    comments = await client.get(f"/api/v1/knowledge/document/{doc_id}/comments", headers=headers)
    assert len(comments.json()) == 1

    updated = await client.patch(
        f"/api/v1/knowledge/document/{doc_id}/comments/{comment_id}",
        json={"content": "Updated comment"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    watch = await client.post(f"/api/v1/knowledge/document/{doc_id}/watch", headers=headers)
    assert watch.status_code == 200
    assert watch.json()["watching"] is True
    watchers = await client.get(f"/api/v1/knowledge/document/{doc_id}/watchers", headers=headers)
    assert len(watchers.json()) == 1

    fav = await client.post(f"/api/v1/knowledge/document/{doc_id}/favorite", headers=headers)
    assert fav.status_code == 200
    assert fav.json()["favorited"] is True
    favorites = await client.get("/api/v1/knowledge/favorites", headers=headers)
    assert len(favorites.json()) == 1

    presence = await client.post(f"/api/v1/knowledge/document/{doc_id}/presence", headers=headers)
    assert presence.status_code == 200
    present = await client.get(f"/api/v1/knowledge/document/{doc_id}/presence", headers=headers)
    assert len(present.json()) == 1

    project = await client.post(
        "/api/v1/projects", json={"name": "KB Project", "code": "KB-1", "owner_id": doc["author_id"]},
        headers=headers,
    )
    project_id = project.json()["id"]
    relation = await client.post(
        f"/api/v1/knowledge/document/{doc_id}/relations",
        json={"target_type": "project", "target_id": project_id, "relation_type": "belongs_to"},
        headers=headers,
    )
    assert relation.status_code == 201, relation.text
    relations = await client.get(f"/api/v1/knowledge/document/{doc_id}/relations", headers=headers)
    assert len(relations.json()) == 1
    assert relations.json()[0]["target_title"] == "KB Project"

    recent = await client.get("/api/v1/knowledge/recent", headers=headers)
    assert recent.status_code == 200
    assert any(r["id"] == doc_id for r in recent.json())


@pytest.mark.asyncio
async def test_document_tenancy_isolation(client):
    org_a = await register_org(client, email="tenanta@phase4.test.co")
    org_b = await register_org(client, email="tenantb@phase4.test.co")
    doc = await _create_document(client, org_a["headers"])
    doc_id = doc["id"]

    got = await client.get(f"/api/v1/documents/{doc_id}", headers=org_b["headers"])
    assert got.status_code == 404
