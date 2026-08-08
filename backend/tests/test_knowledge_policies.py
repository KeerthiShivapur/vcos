"""Phase 4 — Policies, SOPs and Templates."""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_policy_approval_workflow(client):
    org = await register_org(client, email="pol@phase4.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    created = await client.post(
        "/api/v1/policies",
        json={
            "title": "Remote Work Policy",
            "category": "remote_work",
            "content": "Team members may work remotely up to four days a week with manager approval.",
            "owner_id": me,
            "review_date": "2020-01-01",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    assert created.json()["category"] == "remote_work"

    submitted = await client.post(f"/api/v1/policies/{policy_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "in_review"

    approved = await client.post(f"/api/v1/policies/{policy_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["review_overdue"] is True

    overdue = await client.get("/api/v1/policies/overdue", headers=headers)
    assert overdue.status_code == 200, overdue.text
    assert any(p["id"] == policy_id for p in overdue.json())

    rejected_doc = await client.post(
        "/api/v1/policies",
        json={"title": "Expense Policy", "content": "Submit receipts within 30 days."},
        headers=headers,
    )
    rejected_id = rejected_doc.json()["id"]
    await client.post(f"/api/v1/policies/{rejected_id}/submit", headers=headers)
    rejected = await client.post(
        f"/api/v1/policies/{rejected_id}/reject", json={"note": "Need finance input"}, headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "draft"
    assert rejected.json()["approval_note"] == "Need finance input"


@pytest.mark.asyncio
async def test_sop_with_steps(client):
    org = await register_org(client, email="sop@phase4.test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/sops",
        json={
            "title": "New Hire Laptop Setup",
            "content": "Steps to provision a laptop.",
            "steps": [
                {"title": "Order laptop", "instruction": "Use IT budget code", "is_checklist": True, "sort_order": 0},
                {"title": "Configure SSO", "instruction": "Enroll in identity provider", "is_checklist": True, "sort_order": 1},
                {"title": "Deliver", "sort_order": 2},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sop_id = created.json()["id"]
    assert len(created.json()["steps"]) == 3
    assert created.json()["steps"][0]["is_checklist"] is True

    updated = await client.patch(
        f"/api/v1/sops/{sop_id}",
        json={"steps": [{"title": "Order laptop", "is_checklist": True}]},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["steps"]) == 1

    published = await client.post(f"/api/v1/sops/{sop_id}/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    got = await client.get(f"/api/v1/sops/{sop_id}", headers=headers)
    assert got.status_code == 200
    assert len(got.json()["steps"]) == 1


@pytest.mark.asyncio
async def test_template_usage_tracking(client):
    org = await register_org(client, email="tpl@phase4.test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/templates",
        json={
            "title": "Meeting Notes Template",
            "kind": "meeting_notes",
            "content": "# Agenda\n- Topic 1\n- Topic 2",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["kind_name"] == "meeting_notes"

    published = await client.post(f"/api/v1/templates/{template_id}/publish", headers=headers)
    assert published.status_code == 200, published.text

    for _ in range(3):
        used = await client.post(f"/api/v1/templates/{template_id}/use", headers=headers)
        assert used.status_code == 200, used.text
    assert used.json()["usage_count"] == 3

    most_used = await client.get("/api/v1/templates/most-used", headers=headers)
    assert most_used.status_code == 200, most_used.text
    assert most_used.json()[0]["id"] == template_id


@pytest.mark.asyncio
async def test_knowledge_rbac(client):
    org = await register_org(client, email="kbrbac@phase4.test.co")
    headers = org["headers"]
    create = await client.post(
        "/api/v1/documents", json={"title": "RBAC doc", "content": "x"}, headers=headers,
    )
    assert create.status_code == 201, create.text

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "reader@phase4.test.co", "full_name": "Reader User", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["token"]
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "full_name": "Reader User", "password": "Reader123!"},
    )
    assert registered.status_code == 201, registered.text
    reader_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    read = await client.get("/api/v1/documents", headers=reader_headers)
    assert read.status_code == 200
    write = await client.post(
        "/api/v1/documents", json={"title": "nope", "content": "x"}, headers=reader_headers,
    )
    assert write.status_code == 403
