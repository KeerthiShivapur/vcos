"""Vertical Slice 3 — Step 12 approvals & risks integration tests.

Approvals must be requestable against work entities (tasks), notify the
approver at creation, notify the requester on decision, and hold a single
decidable/cancellable lifecycle. Risks must recompute score on probability
or impact changes and notify their owner through the event bus. The
approval-request notification must link to the approvals surface.
"""

import pytest
from sqlalchemy import select

from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _notifications(db, organization_id, type=None):
    from app.models.notification import Notification

    stmt = select(Notification).where(Notification.organization_id == organization_id)
    if type:
        stmt = stmt.where(Notification.type == type)
    return (await db.execute(stmt)).scalars().all()


async def _audit_actions(client, headers, *, action=None, resource_type=None):
    params = {}
    if action:
        params["action"] = action
    if resource_type:
        params["resource_type"] = resource_type
    r = await client.get("/api/v1/audit", params=params, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    return data if isinstance(data, list) else data.get("items", data.get("entries", []))


async def _create_employee(client, headers, first_name, email):
    r = await client.post("/api/v1/employees", json={"first_name": first_name, "email": email}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _invite_with_user(client, headers, email, full_name="Dana Dana"):
    invite = await client.post(
        "/api/v1/users/invite", json={"email": email, "full_name": full_name, "role": "employee"}, headers=headers
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": full_name, "password": "DanaPass123!"},
    )
    assert registered.status_code in (200, 201), registered.text
    r = await client.get("/api/v1/employees/me", headers={
        "Authorization": f"Bearer {registered.json()['access_token']}"
    })
    assert r.status_code == 200, r.text
    return r.json(), registered.json()["user"]["id"]


async def _create_project_and_task(client, headers, name="Approval Project"):
    r = await client.post("/api/v1/projects", json={"name": name, "status": "active"}, headers=headers)
    assert r.status_code == 201, r.text
    project = r.json()
    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Ship release notes", "project_id": project["id"]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return project, r.json()


@pytest.mark.asyncio
async def test_task_linked_approval_full_cycle(client, db_session_factory):
    org = await register_org(client, email="s12a1@test.co")
    approver, approver_user_id = await _invite_with_user(client, org["headers"], "dana12@test.co")
    project, task = await _create_project_and_task(client, org["headers"])

    r = await client.post(
        "/api/v1/approvals",
        json={
            "approval_type": "task",
            "title": f"Approve: {task['title']}",
            "description": "Gate for publishing the notes",
            "approver_id": approver["id"],
            "priority": "high",
            "entity_type": "task",
            "entity_id": task["id"],
        },
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    approval = r.json()
    assert approval["status"] == "pending"
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    assert approval["requester_id"] == me["id"]
    assert approval["entity_type"] == "task" and approval["entity_id"] == task["id"]

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "approval.requested")
        assert notes, "approver should be notified on request"
        assert notes[0].recipient_id == approver_user_id
        assert notes[0].entity_id == approval["id"]
        assert notes[0].link == "/approvals", "notification must link to the approvals surface"
    audits = await _audit_actions(client, org["headers"], action="approval.requested")
    assert any(a["resource_id"] == approval["id"] for a in audits)

    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "note": "LGTM"},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["decided_at"] is not None
    assert r.json()["decision_note"] == "LGTM"

    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide", json={"decision": "approved"}, headers=org["headers"]
    )
    assert r.status_code == 400, "double decision must be rejected"

    r = await client.get("/api/v1/approvals", headers=org["headers"])
    assert r.status_code == 200, r.text
    items = r.json()
    assert any(a["id"] == approval["id"] and a["status"] == "approved" for a in items)
    linked = [a for a in items if a["entity_type"] == "task"]
    assert linked and linked[0]["entity_id"] == task["id"], "list must carry the entity link"

    r = await client.get(f"/api/v1/approvals/{approval['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["approver_name"]

    r = await client.get("/api/v1/approvals/stats", headers=org["headers"])
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total"] >= 1 and stats["approved"] >= 1
    assert stats["approval_rate"] >= 0.5


@pytest.mark.asyncio
async def test_approval_cancel_lifecycle(client, db_session_factory):
    org = await register_org(client, email="s12a2@test.co")
    approver = await _create_employee(client, org["headers"], "Carl", "carl12@test.co")

    r = await client.post(
        "/api/v1/approvals",
        json={"title": "Purchase order", "approval_type": "purchase", "approver_id": approver["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    approval = r.json()

    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/cancel", headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide", json={"decision": "approved"}, headers=org["headers"]
    )
    assert r.status_code == 400, "cancelled approvals must not be decidable"

    r = await client.get("/api/v1/approvals?status=pending", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert not any(a["id"] == approval["id"] for a in r.json()), "cancelled must leave pending filter"


@pytest.mark.asyncio
async def test_risk_register_score_and_notifications(client, db_session_factory):
    org = await register_org(client, email="s12a3@test.co")
    owner = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    project, _ = await _create_project_and_task(client, org["headers"], name="Risk Project")

    r = await client.post(
        "/api/v1/risks",
        json={
            "project_id": project["id"],
            "title": "Key vendor may miss deadline",
            "probability": 4,
            "impact": 3,
            "owner_id": owner["id"],
            "mitigation": "Weekly sync with vendor",
            "due_at": "2026-12-31T00:00:00Z",
        },
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    risk = r.json()
    assert risk["risk_score"] == 12, "score must be probability x impact"
    assert risk["severity"] == "high"

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "risk.detected")
        assert notes and notes[0].recipient_id == org["user"]["id"]
        assert notes[0].entity_id == risk["id"]

    r = await client.patch(f"/api/v1/risks/{risk['id']}", json={"impact": 5}, headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["risk_score"] == 20 and r.json()["severity"] == "critical"

    r = await client.get("/api/v1/risks?severity=high", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert not any(x["id"] == risk["id"] for x in r.json()), "critical risk must not match high filter"

    r = await client.post(f"/api/v1/risks/{risk['id']}/close", headers=org["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "risk.closed")
        assert notes and notes[0].entity_id == risk["id"]

    r = await client.delete(f"/api/v1/risks/{risk['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/risks/{risk['id']}", headers=org["headers"])
    assert r.status_code == 404, r.text

    audits = await _audit_actions(client, org["headers"], action="risk.deleted")
    assert any(a["resource_id"] == risk["id"] for a in audits), "risk deletion must be audited"


@pytest.mark.asyncio
async def test_approval_list_filters_and_decision_note(client, db_session_factory):
    org = await register_org(client, email="s12a4@test.co")
    approver = await _create_employee(client, org["headers"], "Eve", "eve12@test.co")

    for title, atype in (("Docs signoff", "document"), ("Travel claim", "expense")):
        r = await client.post(
            "/api/v1/approvals",
            json={"title": title, "approval_type": atype, "approver_id": approver["id"]},
            headers=org["headers"],
        )
        assert r.status_code == 201, r.text

    r = await client.get("/api/v1/approvals?approval_type=expense", headers=org["headers"])
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1 and items[0]["title"] == "Travel claim"
    assert items[0]["approver_name"] == "Eve"
    assert items[0]["requester_name"]

    r = await client.post(
        f"/api/v1/approvals/{items[0]['id']}/decide",
        json={"decision": "rejected", "note": "Missing receipt"},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "Missing receipt"
