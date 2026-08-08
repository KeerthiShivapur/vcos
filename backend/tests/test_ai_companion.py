"""Phase 3 — AI Companion tests.

Covers: companion status, my-day grounding, entity summaries (project/task/
goal/meeting), org pulse, free-form fallback with no provider, and RBAC.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers, email=None):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_companion_status(client):
    org = await register_org(client, email="ai@work.test.co")
    response = await client.get("/api/v1/ai/companion/status", headers=org["headers"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available"] is True  # built-in local engine always available
    assert data["provider"] == "local"
    assert data["mode"] == "local"
    assert data["grounded"] is True
    assert "my_day" in data["capabilities"]


@pytest.mark.asyncio
async def test_companion_my_day(client):
    org = await register_org(client, email="day@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Day Project", "code": "DAY-1", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]

    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Write the report", "assignee_id": me, "status": "in_progress"},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Finish the proposal", "assignee_id": me},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Overdue old task", "assignee_id": me, "due_date": "2020-01-01"},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "What should I work on today?"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source"] == "rules"
    assert "Write the report" in data["answer"]
    assert "Finish the proposal" in data["answer"]
    assert "Overdue old task" in data["answer"]
    assert data["grounded"]["open_tasks"] == 3
    assert data["grounded"]["overdue_tasks"] == ["Overdue old task"]
    assert "my_day" in data["intents"]


@pytest.mark.asyncio
async def test_companion_project_summary(client):
    org = await register_org(client, email="sum@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Atlas Engine", "code": "ATL-1", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Build ingestion", "assignee_id": me},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Summarize this project", "context": {"project_id": project_id}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "Atlas Engine" in data["answer"]
    assert data["grounded"]["project_id"] == project_id
    assert "project" in data["intents"]


@pytest.mark.asyncio
async def test_companion_task_and_goal_summary(client):
    org = await register_org(client, email="tg@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    task = await client.post(
        "/api/v1/tasks",
        json={"title": "Fix the signup flow", "assignee_id": me},
        headers=headers,
    )
    task_id = task.json()["id"]

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Summarize this task", "context": {"task_id": task_id}},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Fix the signup flow" in response.json()["answer"]

    goal = await client.post(
        "/api/v1/goals",
        json={"name": "Double retention", "owner_id": me, "scope": "company",
              "key_results": [{"title": "Retention to 60%", "target_value": 60, "unit": "percent"}]},
        headers=headers,
    )
    goal_id = goal.json()["id"]

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Summarize this goal", "context": {"goal_id": goal_id}},
        headers=headers,
    )
    assert response.status_code == 200
    assert "Double retention" in response.json()["answer"]


@pytest.mark.asyncio
async def test_companion_meeting_summary(client):
    org = await register_org(client, email="mtg@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    meeting = await client.post(
        "/api/v1/meetings",
        json={"title": "Sprint Review", "meeting_type": "review", "organizer_id": me,
              "attendee_ids": [me]},
        headers=headers,
    )
    meeting_id = meeting.json()["id"]

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Summarize this meeting", "context": {"meeting_id": meeting_id}},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "Sprint Review" in data["answer"]
    assert data["grounded"]["attendees"] == 1


@pytest.mark.asyncio
async def test_companion_org_pulse(client):
    org = await register_org(client, email="pulse@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Pulse Project", "code": "PULSE-1", "owner_id": me},
        headers=headers,
    )
    task = await client.post(
        "/api/v1/tasks",
        json={"project_id": project.json()["id"], "title": "Ship v1", "assignee_id": me, "status": "completed"},
        headers=headers,
    )
    assert task.status_code == 201

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Give me the org pulse"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "org_pulse" in data["intents"]
    assert "Pulse Project" not in data["answer"]  # pulse is aggregate, not per-project
    assert data["grounded"]["tasks_completion_rate"] == 100.0


@pytest.mark.asyncio
async def test_companion_free_form_falls_back(client):
    org = await register_org(client, email="free@work.test.co")
    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "Invent a new feature for us"},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source"] == "rules"
    assert "What should I work on today?" in data["answer"]
    assert data["intents"] == []


@pytest.mark.asyncio
async def test_companion_requires_permission(client):
    org = await register_org(client, email="noperm@work.test.co")
    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "hello"},
    )
    assert response.status_code == 401
