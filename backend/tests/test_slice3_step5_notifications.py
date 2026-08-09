"""Vertical Slice 3 — Step 5 work-domain notifications regression tests.

Work lifecycle moments must surface as in-app notifications to the people
they matter to: assignees of blocked tasks, project owners of milestone and
sprint moments, requesters of approval decisions, goal owners, risk owners.
Notifications ride the event bus (retry-safe, transactional with handlers).
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


async def _create_employee(client, headers, first_name, email):
    r = await client.post("/api/v1/employees", json={"first_name": first_name, "email": email}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_project(client, headers, name="Notify Project"):
    r = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_task_blocked_notifies_assignee(client, db_session_factory):
    org = await register_org(client, email="s5a1@test.co")
    assignee = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    a = (await client.post("/api/v1/tasks", json={"title": "Dep A"}, headers=org["headers"])).json()
    b = (await client.post(
        "/api/v1/tasks", json={"title": "Dep B", "assignee_id": assignee["id"]}, headers=org["headers"]
    )).json()
    r = await client.post(
        f"/api/v1/tasks/{b['id']}/dependencies",
        json={"depends_on_task_id": a["id"], "kind": "blocking"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text

    r = await client.post(f"/api/v1/tasks/{b['id']}/transition", json={"status": "blocked"}, headers=org["headers"])
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "task.blocked")
        assert notes, "assignee should be notified about the blocked task"
        assert notes[0].recipient_id == org["user"]["id"]
        assert notes[0].entity_id == b["id"]


@pytest.mark.asyncio
async def test_milestone_completed_notifies_project_owner(client, db_session_factory):
    org = await register_org(client, email="s5a2@test.co")
    owner_id = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()["id"]
    project = await _create_project(client, org["headers"])

    r = await client.post(
        "/api/v1/milestones", json={"name": "M1", "project_id": project["id"]}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    milestone = r.json()
    r = await client.post(f"/api/v1/milestones/{milestone['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "milestone.completed")
        assert notes, "project owner should hear about completed milestones"
        assert notes[0].recipient_id == org["user"]["id"]


@pytest.mark.asyncio
async def test_sprint_moments_notify_project_owner(client, db_session_factory):
    org = await register_org(client, email="s5a3@test.co")
    project = await _create_project(client, org["headers"])

    r = await client.post(
        "/api/v1/sprints", json={"name": "S1", "project_id": project["id"]}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    sprint = r.json()
    r = await client.post(f"/api/v1/sprints/{sprint['id']}/start", headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/sprints/{sprint['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        started = await _notifications(db, org["organization"]["id"], "sprint.started")
        completed = await _notifications(db, org["organization"]["id"], "sprint.completed")
        assert started and completed
        assert started[0].recipient_id == org["user"]["id"]
        assert completed[0].recipient_id == org["user"]["id"]


@pytest.mark.asyncio
async def test_approval_decision_notifies_requester(client, db_session_factory):
    org = await register_org(client, email="s5a4@test.co")
    approver = await _create_employee(client, org["headers"], "Approver", "approver@test.co")

    r = await client.post(
        "/api/v1/approvals",
        json={"title": "Budget signoff", "approval_type": "expense", "approver_id": approver["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    approval = r.json()
    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide", json={"decision": "approved"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "approval.decided")
        assert notes, "requester should hear the approval decision"
        assert notes[0].recipient_id == org["user"]["id"]
        assert notes[0].entity_id == approval["id"]


@pytest.mark.asyncio
async def test_goal_completed_notifies_owner(client, db_session_factory):
    org = await register_org(client, email="s5a5@test.co")
    owner_id = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()["id"]

    r = await client.post(
        "/api/v1/goals", json={"name": "OKR", "scope": "personal", "owner_id": owner_id}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    goal = r.json()
    r = await client.post(
        f"/api/v1/goals/{goal['id']}/key-results",
        json={"title": "KR", "target": 100, "current": 0},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    kr = r.json()
    r = await client.patch(
        f"/api/v1/goals/{goal['id']}/key-results/{kr['id']}", json={"current": 100}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "goal.completed")
        assert notes and notes[0].recipient_id == org["user"]["id"]


@pytest.mark.asyncio
async def test_risk_closed_notifies_owner(client, db_session_factory):
    org = await register_org(client, email="s5a6@test.co")
    owner = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    r = await client.post(
        "/api/v1/risks",
        json={"title": "Vendor risk", "probability": 3, "impact": 3, "owner_id": owner["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    risk = r.json()
    r = await client.post(f"/api/v1/risks/{risk['id']}/close", headers=org["headers"])
    assert r.status_code == 200, r.text

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "risk.closed")
        assert notes and notes[0].recipient_id == org["user"]["id"]
