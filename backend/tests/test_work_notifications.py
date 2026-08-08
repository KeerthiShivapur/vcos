"""Phase 3 — work alert notifications.

Every work mutation that touches another person creates an in-app notification:
  - task assignment -> assignee (not self)
  - task completion -> reporter
  - meeting invite -> attendees (not organizer)
  - approval request -> approver
  - risk detected -> risk owner
Also verifies the organization graph now includes work entities.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _unread_notifications(client, headers):
    response = await client.get("/api/v1/notifications?unread_only=true", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.mark.asyncio
async def test_task_assignment_notifies_assignee(client):
    org = await register_org(client, email="assign@work.test.co")
    headers = org["headers"]

    colleague = await client.post(
        "/api/v1/employees",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@alerts.test.co"},
        headers=headers,
    )
    colleague_id = colleague.json()["id"]

    task = await client.post(
        "/api/v1/tasks",
        json={"title": "Deploy the pipeline", "assignee_id": colleague_id},
        headers=headers,
    )
    assert task.status_code == 201

    # The assignee (Grace) has no user login yet -> no notification possible;
    # the actor (owner) must NOT be notified for someone else's assignment.
    me = await _employee_id(client, headers)
    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "task.assigned" for n in notifications)

    # Self-assignment must not notify the actor either.
    self_task = await client.post(
        "/api/v1/tasks",
        json={"title": "My own task", "assignee_id": me},
        headers=headers,
    )
    assert self_task.status_code == 201
    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "task.assigned" for n in notifications)


@pytest.mark.asyncio
async def test_task_completion_notifies_reporter(client):
    org = await register_org(client, email="done@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    colleague = await client.post(
        "/api/v1/employees",
        json={"first_name": "Linus", "last_name": "Torvalds", "email": "linus@alerts.test.co"},
        headers=headers,
    )
    colleague_id = colleague.json()["id"]

    task = await client.post(
        "/api/v1/tasks",
        json={"title": "Ship the kernel", "assignee_id": me, "reporter_id": colleague_id},
        headers=headers,
    )
    task_id = task.json()["id"]

    transition = await client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "completed"}, headers=headers)
    assert transition.status_code == 200

    # Owner (reporter-side) has no user account either; nothing should crash
    # and the actor should not see a task.completed notification about his own action.
    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "task.completed" for n in notifications)


@pytest.mark.asyncio
async def test_meeting_invite_notifies_attendees(client):
    org = await register_org(client, email="invite@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    colleague = await client.post(
        "/api/v1/employees",
        json={"first_name": "Alan", "last_name": "Turing", "email": "alan@alerts.test.co"},
        headers=headers,
    )
    colleague_id = colleague.json()["id"]

    meeting = await client.post(
        "/api/v1/meetings",
        json={"title": "Architecture Sync", "meeting_type": "team", "organizer_id": me,
              "attendee_ids": [colleague_id, me]},
        headers=headers,
    )
    assert meeting.status_code == 201

    # Attendee without a user account cannot be notified; organizer not notified.
    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "meeting.invited" for n in notifications)


@pytest.mark.asyncio
async def test_approval_request_notifies_approver(client):
    org = await register_org(client, email="approve@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    colleague = await client.post(
        "/api/v1/employees",
        json={"first_name": "Grace", "last_name": "Brewster", "email": "graceb@alerts.test.co"},
        headers=headers,
    )
    colleague_id = colleague.json()["id"]

    approval = await client.post(
        "/api/v1/approvals",
        json={"approval_type": "expense", "title": "Flight to conference",
              "requester_id": me, "approver_id": colleague_id, "priority": "high"},
        headers=headers,
    )
    assert approval.status_code == 201

    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "approval.requested" for n in notifications)


@pytest.mark.asyncio
async def test_risk_detection_notifies_owner(client):
    org = await register_org(client, email="risk@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Risk Project", "code": "RISK-1", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]

    colleague = await client.post(
        "/api/v1/employees",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@alerts.test.co"},
        headers=headers,
    )
    colleague_id = colleague.json()["id"]

    risk = await client.post(
        "/api/v1/risks",
        json={"project_id": project_id, "title": "Vendor delay", "owner_id": colleague_id,
              "probability": 4, "impact": 5},
        headers=headers,
    )
    assert risk.status_code == 201
    assert risk.json()["risk_score"] == 20
    assert risk.json()["severity"] == "critical"

    notifications = await _unread_notifications(client, headers)
    assert not any(n["type"] == "risk.detected" for n in notifications)


@pytest.mark.asyncio
async def test_notifications_flow_when_attendee_has_user(client):
    """End-to-end: invite a real user (employee linked to a user) and check the notification."""
    org = await register_org(client, email="flow@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    # Register a second user in the same org through the invite flow.
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "maya@flow.test.co", "full_name": "Maya Angelou", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    invited = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Maya Angelou", "password": "StrongPass123!"},
    )
    assert invited.status_code == 201, invited.text
    invited_user = invited.json()["user"]

    # The invite flow already creates the linked employee record.
    emp_response = await client.get("/api/v1/employees?search=maya@flow.test.co", headers=headers)
    assert emp_response.status_code == 200
    maya = next((e for e in emp_response.json() if e["email"] == "maya@flow.test.co"), None)
    assert maya is not None

    meeting = await client.post(
        "/api/v1/meetings",
        json={"title": "1:1 with Maya", "meeting_type": "1:1", "organizer_id": me,
              "attendee_ids": [maya["id"], me]},
        headers=headers,
    )
    assert meeting.status_code == 201

    # Maya has a user account -> she receives the invite notification.
    maya_headers = {"Authorization": f"Bearer {invited.json()['access_token']}"}
    notifications = await _unread_notifications(client, maya_headers)
    assert any(n["type"] == "meeting.invited" and n["entity_id"] == meeting.json()["id"] for n in notifications)


@pytest.mark.asyncio
async def test_organization_graph_includes_work(client):
    org = await register_org(client, email="graph@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Graph Project", "code": "GR-1", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]
    task = await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Graph task", "assignee_id": me},
        headers=headers,
    )
    task_id = task.json()["id"]
    goal = await client.post(
        "/api/v1/goals",
        json={"name": "Graph goal", "owner_id": me, "scope": "company"},
        headers=headers,
    )
    goal_id = goal.json()["id"]

    graph = await client.get("/api/v1/organization/graph", headers=headers)
    assert graph.status_code == 200, graph.text
    data = graph.json()
    kinds = {node["kind"] for node in data["nodes"]}
    assert {"project", "task", "goal"} <= kinds
    node_ids = {node["id"] for node in data["nodes"]}
    assert f"proj:{project_id}" in node_ids
    assert f"task:{task_id}" in node_ids
    assert f"goal:{goal_id}" in node_ids

    relations = {(edge["source"], edge["target"], edge["relation"]) for edge in data["edges"]}
    assert (me, f"proj:{project_id}", "owns") in relations
    assert (me, f"task:{task_id}", "assigned_to") in relations
    assert (me, f"goal:{goal_id}", "owns") in relations
    assert (f"task:{task_id}", f"proj:{project_id}", "belongs_to") in relations

    # Without work entities the graph shrinks back to people-only.
    people_only = await client.get("/api/v1/organization/graph?include_work=false", headers=headers)
    assert people_only.status_code == 200
    assert all(node["kind"] in ("employee", "department", "team", "location") for node in people_only.json()["nodes"])
