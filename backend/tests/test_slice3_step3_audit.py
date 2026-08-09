"""Vertical Slice 3 — Step 3 work-domain audit trail regression tests.

Every work-domain mutation must produce an audit entry queryable via
GET /audit, scoped to the organization, with resource_type/resource_id set.
"""

import pytest

from tests.conftest import register_org


async def _audit_actions(client, headers, *, action=None, resource_type=None):
    params = {}
    if action:
        params["action"] = action
    if resource_type:
        params["resource_type"] = resource_type
    r = await client.get("/api/v1/audit", params=params, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    return data["items"], data["total"]


async def _create_project(client, headers, name="Core Platform"):
    r = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_task(client, headers, title="Task"):
    r = await client.post("/api/v1/tasks", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- projects & tasks


@pytest.mark.asyncio
async def test_project_and_task_audit_trail(client):
    org = await register_org(client, email="s3a1@test.co")
    project = await _create_project(client, org["headers"], "Audited Project")

    items, _ = await _audit_actions(client, org["headers"], action="project.created", resource_type="project")
    assert any(i["resource_id"] == project["id"] and i["details"].get("name") == "Audited Project" for i in items)

    task = await _create_task(client, org["headers"], "Audited Task")
    items, _ = await _audit_actions(client, org["headers"], action="task.created", resource_type="task")
    assert any(i["resource_id"] == task["id"] for i in items)

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition", json={"status": "in_progress"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="task.transitioned", resource_type="task")
    assert any(i["resource_id"] == task["id"] and i["details"]["old_status"] == "backlog" for i in items)

    r = await client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "Renamed"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="task.updated", resource_type="task")
    assert any(i["resource_id"] == task["id"] for i in items)

    r = await client.delete(f"/api/v1/tasks/{task['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="task.deleted", resource_type="task")
    assert any(i["resource_id"] == task["id"] for i in items)


@pytest.mark.asyncio
async def test_dependency_audit_trail(client):
    org = await register_org(client, email="s3a2@test.co")
    a = await _create_task(client, org["headers"], "A")
    b = await _create_task(client, org["headers"], "B")

    r = await client.post(
        f"/api/v1/tasks/{b['id']}/dependencies",
        json={"depends_on_task_id": a["id"], "kind": "finish_to_start"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    dep = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="dependency.added", resource_type="task")
    assert any(
        i["resource_id"] == b["id"] and i["details"]["depends_on_task_id"] == a["id"] for i in items
    )

    r = await client.delete(
        f"/api/v1/tasks/{b['id']}/dependencies/{dep['id']}", headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="dependency.removed", resource_type="task")
    assert any(i["resource_id"] == b["id"] for i in items)


# --------------------------------------------------------------------------- planning structures


@pytest.mark.asyncio
async def test_roadmap_epic_milestone_sprint_audit_trail(client):
    org = await register_org(client, email="s3a3@test.co")
    project = await _create_project(client, org["headers"], "Planning Project")

    r = await client.post("/api/v1/roadmaps", json={"name": "Roadmap"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    roadmap = r.json()
    r = await client.post("/api/v1/epics", json={"name": "Epic", "project_id": project["id"], "roadmap_id": roadmap["id"]}, headers=org["headers"])
    assert r.status_code == 201, r.text
    epic = r.json()
    r = await client.post("/api/v1/milestones", json={"name": "Milestone", "project_id": project["id"]}, headers=org["headers"])
    assert r.status_code == 201, r.text
    milestone = r.json()
    r = await client.post("/api/v1/sprints", json={"name": "Sprint", "project_id": project["id"]}, headers=org["headers"])
    assert r.status_code == 201, r.text
    sprint = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="roadmap.created", resource_type="roadmap")
    assert any(i["resource_id"] == roadmap["id"] for i in items)
    items, _ = await _audit_actions(client, org["headers"], action="epic.created", resource_type="epic")
    assert any(i["resource_id"] == epic["id"] for i in items)
    items, _ = await _audit_actions(client, org["headers"], action="milestone.created", resource_type="milestone")
    assert any(i["resource_id"] == milestone["id"] for i in items)
    items, _ = await _audit_actions(client, org["headers"], action="sprint.created", resource_type="sprint")
    assert any(i["resource_id"] == sprint["id"] for i in items)

    r = await client.patch(f"/api/v1/epics/{epic['id']}", json={"name": "Epic v2"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="epic.updated", resource_type="epic")
    assert any(i["resource_id"] == epic["id"] for i in items)

    r = await client.post(f"/api/v1/milestones/{milestone['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="milestone.completed", resource_type="milestone")
    assert any(i["resource_id"] == milestone["id"] for i in items)

    r = await client.post(f"/api/v1/sprints/{sprint['id']}/start", headers=org["headers"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/sprints/{sprint['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="sprint.started", resource_type="sprint")
    assert any(i["resource_id"] == sprint["id"] for i in items)
    items, _ = await _audit_actions(client, org["headers"], action="sprint.completed", resource_type="sprint")
    assert any(i["resource_id"] == sprint["id"] for i in items)


# --------------------------------------------------------------------------- goals & meetings


@pytest.mark.asyncio
async def test_goal_and_key_result_audit_trail(client):
    org = await register_org(client, email="s3a4@test.co")

    r = await client.post("/api/v1/goals", json={"name": "Growth", "scope": "company"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    goal = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="goal.created", resource_type="goal")
    assert any(i["resource_id"] == goal["id"] for i in items)

    r = await client.post(
        f"/api/v1/goals/{goal['id']}/key-results",
        json={"title": "Revenue", "target": 100, "current": 10},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    kr = r.json()
    items, _ = await _audit_actions(client, org["headers"], action="key_result.created", resource_type="key_result")
    assert any(i["resource_id"] == kr["id"] for i in items)

    r = await client.patch(
        f"/api/v1/goals/{goal['id']}/key-results/{kr['id']}",
        json={"current": 80},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="key_result.updated", resource_type="key_result")
    assert any(i["resource_id"] == kr["id"] for i in items)

    r = await client.delete(f"/api/v1/goals/{goal['id']}/key-results/{kr['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="key_result.deleted", resource_type="key_result")
    assert any(i["resource_id"] == kr["id"] for i in items)

    r = await client.delete(f"/api/v1/goals/{goal['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="goal.deleted", resource_type="goal")
    assert any(i["resource_id"] == goal["id"] for i in items)


@pytest.mark.asyncio
async def test_meeting_audit_trail(client):
    org = await register_org(client, email="s3a5@test.co")

    r = await client.post("/api/v1/meetings", json={"title": "Standup"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    meeting = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="meeting.created", resource_type="meeting")
    assert any(i["resource_id"] == meeting["id"] for i in items)

    r = await client.patch(f"/api/v1/meetings/{meeting['id']}", json={"description": "Daily"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="meeting.updated", resource_type="meeting")
    assert any(i["resource_id"] == meeting["id"] for i in items)

    r = await client.post(f"/api/v1/meetings/{meeting['id']}/complete", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="meeting.completed", resource_type="meeting")
    assert any(i["resource_id"] == meeting["id"] for i in items)

    r = await client.delete(f"/api/v1/meetings/{meeting['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="meeting.deleted", resource_type="meeting")
    assert any(i["resource_id"] == meeting["id"] for i in items)


# --------------------------------------------------------------------------- approvals & risks


@pytest.mark.asyncio
async def test_approval_audit_trail(client):
    org = await register_org(client, email="s3a6@test.co")

    r = await client.post(
        "/api/v1/approvals", json={"title": "Budget", "approval_type": "project", "priority": "high"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    approval = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="approval.requested", resource_type="approval")
    assert any(i["resource_id"] == approval["id"] for i in items)

    r = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approved", "note": "Looks good"},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="approval.approved", resource_type="approval")
    assert any(i["resource_id"] == approval["id"] and i["details"].get("note") == "Looks good" for i in items)


@pytest.mark.asyncio
async def test_risk_audit_trail(client):
    org = await register_org(client, email="s3a7@test.co")

    r = await client.post(
        "/api/v1/risks", json={"title": "Slippage", "probability": 4, "impact": 4}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    risk = r.json()

    items, _ = await _audit_actions(client, org["headers"], action="risk.created", resource_type="risk")
    assert any(i["resource_id"] == risk["id"] for i in items)

    r = await client.post(f"/api/v1/risks/{risk['id']}/close", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="risk.closed", resource_type="risk")
    assert any(i["resource_id"] == risk["id"] for i in items)

    r = await client.delete(f"/api/v1/risks/{risk['id']}", headers=org["headers"])
    assert r.status_code == 200, r.text
    items, _ = await _audit_actions(client, org["headers"], action="risk.deleted", resource_type="risk")
    assert any(i["resource_id"] == risk["id"] for i in items)


# --------------------------------------------------------------------------- tenancy & catalog


@pytest.mark.asyncio
async def test_audit_trail_org_isolation(client):
    org_a = await register_org(client, email="s3a8a@test.co")
    org_b = await register_org(client, email="s3a8b@test.co")
    task = await _create_task(client, org_a["headers"], "Secret Task")

    items_b, _ = await _audit_actions(client, org_b["headers"], action="task.created", resource_type="task")
    assert not any(i["resource_id"] == task["id"] for i in items_b)

    items_a, _ = await _audit_actions(client, org_a["headers"], action="task.created", resource_type="task")
    assert any(i["resource_id"] == task["id"] for i in items_a)


@pytest.mark.asyncio
async def test_work_action_names_in_catalog(client):
    org = await register_org(client, email="s3a9@test.co")
    r = await client.get("/api/v1/audit/actions", headers=org["headers"])
    assert r.status_code == 200, r.text
    actions = set(r.json())
    for expected in (
        "project.created", "project.updated", "task.created", "task.transitioned",
        "dependency.added", "roadmap.created", "epic.created", "milestone.completed",
        "sprint.started", "goal.created", "key_result.updated", "meeting.completed",
        "approval.requested", "risk.closed",
    ):
        assert expected in actions, expected
