"""Slice 4A — Decision -> Execution loop.

Every decision carries structured follow-up actions (owner, project, goal, due
date). An action converts into a real task (Decision -> Reason -> Action ->
Task -> Owner), completion of every produced task automatically implements the
decision, and the whole loop is tenanted, audited, searchable and graph-linked.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _invite(client, headers, email, full_name="Bob Worker", role="employee"):
    invite = await client.post(
        "/api/v1/users/invite", json={"email": email, "role": role, "full_name": full_name}, headers=headers
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "email": email, "full_name": full_name, "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    return registered.json()


async def _decision(client, headers, *, project_id=None, goal_id=None, owner_id=None, **overrides):
    payload = {
        "title": "Launch the enterprise portal",
        "context": "Reduce onboarding time for enterprise customers.",
        "summary": "Adopt a dedicated customer portal.",
        "status": "made",
        "project_id": project_id,
        "goal_id": goal_id,
        "follow_up_actions": [
            {"text": "Build the onboarding flow", "owner_id": owner_id, "project_id": project_id, "goal_id": goal_id},
            {"text": "Contact five pilot customers", "owner_id": owner_id},
        ],
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/decisions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_structured_follow_up_actions_validated(client):
    org = await register_org(client, email="actions@4a.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = (await client.post("/api/v1/projects", json={"name": "Portal", "code": "P4A"}, headers=headers)).json()
    goal = (
        await client.post(
            "/api/v1/goals",
            json={"name": "Improve activation", "scope": "project", "project_id": project["id"], "status": "planned"},
            headers=headers,
        )
    ).json()

    decision = await _decision(
        client, headers, project_id=project["id"], goal_id=goal["id"], owner_id=me,
        follow_up_actions=[
            {"text": "Build the onboarding flow", "owner_id": me, "project_id": project["id"], "goal_id": goal["id"], "due_date": "2026-09-01"},
            "Legacy plain-text action",
        ],
    )
    assert len(decision["follow_up_actions"]) == 2
    assert decision["follow_up_actions"][0]["text"] == "Build the onboarding flow"
    assert decision["follow_up_actions"][0]["due_date"] == "2026-09-01"
    assert decision["follow_up_actions"][0]["status"] == "pending"
    assert decision["follow_up_actions"][1]["text"] == "Legacy plain-text action"
    assert decision["goal_name"] == "Improve activation"

    # Foreign references must be rejected, not silently accepted.
    foreign = await register_org(client, email="foreign@4a.test.co")
    foreign_me = await _employee_id(client, foreign["headers"])
    rejected = await client.post(
        "/api/v1/decisions",
        json={
            "title": "Sneaky decision",
            "follow_up_actions": [{"text": "Do it", "owner_id": foreign_me}],
        },
        headers=headers,
    )
    assert rejected.status_code == 400, rejected.text


@pytest.mark.asyncio
async def test_execute_action_converts_to_linked_task(client):
    org = await register_org(client, email="exec@4a.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    bob = await _invite(client, headers, email="bob.exec@4a.test.co")
    bob_emp = (await client.get("/api/v1/employees", headers=headers)).json()
    bob_id = next(e["id"] for e in bob_emp if e["email"] == "bob.exec@4a.test.co")
    bob_auth = {"Authorization": f"Bearer {bob['access_token']}"}

    project = (await client.post("/api/v1/projects", json={"name": "Portal", "code": "P4A2"}, headers=headers)).json()
    goal = (
        await client.post(
            "/api/v1/goals",
            json={"name": "Activation", "scope": "project", "project_id": project["id"], "status": "planned"},
            headers=headers,
        )
    ).json()

    decision = await _decision(
        client, headers, project_id=project["id"], goal_id=goal["id"], owner_id=bob_id, decision_maker_id=me,
    )
    decision_id = decision["id"]

    executed = await client.post(f"/api/v1/decisions/{decision_id}/actions/0/execute", headers=headers)
    assert executed.status_code == 200, executed.text
    task = executed.json()["task"]
    assert task["decision_id"] == decision_id
    assert task["goal_id"] == goal["id"]
    assert task["project_id"] == project["id"]
    assert task["assignee_id"] == bob_id
    assert task["decision"]["title"] == "Launch the enterprise portal"
    assert "Reduce onboarding time" in (task["description"] or "")
    assert "decision" in (task["tags"] or [])

    # The owner is notified with the decision cited in the title.
    notifications = (await client.get("/api/v1/notifications", headers=bob_auth)).json()["items"]
    assert any(
        n["type"] == "task.assigned" and "from decision 'Launch the enterprise portal'" in n["title"]
        for n in notifications
    )

    # The action is now linked; duplicate execution is rejected.
    decision_after = (await client.get(f"/api/v1/decisions/{decision_id}", headers=headers)).json()
    action = decision_after["follow_up_actions"][0]
    assert action["task_id"] == task["id"]
    assert action["status"] == "in_progress"

    duplicate = await client.post(f"/api/v1/decisions/{decision_id}/actions/0/execute", headers=headers)
    assert duplicate.status_code == 400, duplicate.text


@pytest.mark.asyncio
async def test_decision_tasks_endpoint_and_produces_edge(client):
    org = await register_org(client, email="list@4a.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = (await client.post("/api/v1/projects", json={"name": "Portal", "code": "P4A3"}, headers=headers)).json()
    decision = await _decision(client, headers, project_id=project["id"], owner_id=me)

    first = await client.post(f"/api/v1/decisions/{decision['id']}/actions/0/execute", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/decisions/{decision['id']}/actions/1/execute", headers=headers)
    assert second.status_code == 200

    tasks = (await client.get(f"/api/v1/decisions/{decision['id']}/tasks", headers=headers)).json()
    assert len(tasks) == 2
    assert {t["title"] for t in tasks} == {"Build the onboarding flow", "Contact five pilot customers"}

    # Knowledge graph carries the decision -> task edge.
    relations = (await client.get(f"/api/v1/knowledge/decision/{decision['id']}/relations", headers=headers)).json()
    produced = [r for r in relations if r.get("relation_type") == "produces"]
    assert len(produced) == 2
    assert all(r["target_type"] == "task" for r in produced)


@pytest.mark.asyncio
async def test_completing_all_tasks_implements_decision(client):
    org = await register_org(client, email="loop@4a.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    bob = await _invite(client, headers, email="bob.loop@4a.test.co")
    bob_emp = (await client.get("/api/v1/employees", headers=headers)).json()
    bob_id = next(e["id"] for e in bob_emp if e["email"] == "bob.loop@4a.test.co")

    decision = await _decision(
        client, headers, owner_id=bob_id,
        decision_maker_id=me,
        participants=[{"employee_id": me, "role": "maker"}],
    )
    decision_id = decision["id"]

    executed = await client.post(f"/api/v1/decisions/{decision_id}/actions/0/execute", headers=headers)
    task_id = executed.json()["task"]["id"]

    # Partial completion must NOT implement the decision yet.
    await client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "in_progress"}, headers=headers)
    still_made = (await client.get(f"/api/v1/decisions/{decision_id}", headers=headers)).json()
    assert still_made["status"] == "made"

    done = await client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "completed"}, headers=headers)
    assert done.status_code == 200, done.text

    decision_after = (await client.get(f"/api/v1/decisions/{decision_id}", headers=headers)).json()
    assert decision_after["status"] == "implemented"
    executed_action = next(a for a in decision_after["follow_up_actions"] if a["task_id"])
    assert executed_action["status"] == "completed"
    unexecuted = next(a for a in decision_after["follow_up_actions"] if not a["task_id"])
    assert unexecuted["status"] == "pending"

    # The loop is audited and notified.
    events = await client.get("/api/v1/events?name=decision.implemented", headers=headers)
    assert events.status_code == 200
    assert events.json()["total"] >= 1

    audit = await client.get(
        "/api/v1/audit", params={"action": "decision.implemented", "resource_type": "decision"}, headers=headers,
    )
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1
    assert audit.json()["items"][0]["action"] == "decision.implemented"

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()["items"]
    assert any(n["type"] == "decision.implemented" for n in notifications)


@pytest.mark.asyncio
async def test_cross_tenant_decision_links_rejected(client):
    org_a = await register_org(client, email="a@4a.test.co")
    org_b = await register_org(client, email="b@4a.test.co")
    headers_a, headers_b = org_a["headers"], org_b["headers"]
    me_a = await _employee_id(client, headers_a)
    me_b = await _employee_id(client, headers_b)

    decision_a = await _decision(client, headers_a, owner_id=me_a)
    decision_b = await _decision(client, headers_b, owner_id=me_b)

    # A task in org B cannot cite a decision from org A.
    rejected = await client.post(
        "/api/v1/tasks",
        json={"title": "Sneaky task", "decision_id": decision_a["id"], "assignee_id": me_b},
        headers=headers_b,
    )
    assert rejected.status_code == 400, rejected.text

    # Updating the decision with a foreign owner reference is rejected.
    foreign = await client.patch(
        f"/api/v1/decisions/{decision_b['id']}",
        json={"follow_up_actions": [{"text": "Hijacked", "owner_id": me_a}]},
        headers=headers_b,
    )
    assert foreign.status_code == 400, foreign.text

    # Cross-org reads of the decision's tasks return nothing.
    leaked = await client.get(f"/api/v1/decisions/{decision_a['id']}/tasks", headers=headers_b)
    assert leaked.status_code == 404


@pytest.mark.asyncio
async def test_follow_up_text_is_searchable(client):
    org = await register_org(client, email="search@4a.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    decision = await _decision(client, headers, owner_id=me)
    query = "onboarding"
    results = (await client.get("/api/v1/knowledge/search", params={"q": query, "kind": "decision"}, headers=headers)).json()
    assert any(r["id"] == decision["id"] for r in results["results"]), results
