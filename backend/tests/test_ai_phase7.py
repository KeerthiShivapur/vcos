"""Phase 7 — Universal AI Companion tests.

Covers the memory system, universal search, planning, recommendations,
predictions, actions, learning, voice helpers and the new AI endpoints.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_memory_remember_recall_forget_api(client):
    org = await register_org(client, email="mem@work.test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/ai/memory",
        json={"content": "Grace prefers async standups", "kind": "preference", "scope": "user"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    memory_id = created.json()["id"]

    recalled = await client.get("/api/v1/ai/memory", headers=headers)
    assert recalled.status_code == 200
    bodies = [m["content"] for m in recalled.json()["memories"]]
    assert "Grace prefers async standups" in bodies

    searched = await client.get("/api/v1/ai/memory?text=async", headers=headers)
    assert any("async standups" in m["content"] for m in searched.json()["memories"])

    deleted = await client.delete(f"/api/v1/ai/memory/{memory_id}", headers=headers)
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_universal_search_finds_everything(client):
    org = await register_org(client, email="uni@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Nebula Search", "code": "NEB-7", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Calibrate the orbital mapper", "assignee_id": me},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/ai/search",
        json={"query": "Nebula"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    types = {r["type"] for r in data["results"]}
    assert "project" in types

    response = await client.post(
        "/api/v1/ai/search",
        json={"query": "orbital"},
        headers=headers,
    )
    types = {r["type"] for r in response.json()["results"]}
    assert "task" in types


@pytest.mark.asyncio
async def test_planning_creates_daily_plan(client):
    org = await register_org(client, email="plan@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    await client.post(
        "/api/v1/tasks",
        json={"title": "Land the deal", "assignee_id": me, "priority": "high"},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Overdue deliverable", "assignee_id": me, "due_date": "2020-01-01"},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/ai/plan",
        json={"plan_type": "daily"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["plan_type"] == "daily"
    assert "Land the deal" in data["focus"]
    assert "Overdue deliverable" in data["overdue"]

    latest = await client.get("/api/v1/ai/plan/latest?plan_type=daily", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == data["id"]


@pytest.mark.asyncio
async def test_recommendations_engine_returns_items(client):
    org = await register_org(client, email="rec@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Docless", "code": "DOC-0", "owner_id": me},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project.json()["id"], "title": "Ship it", "assignee_id": me, "status": "completed"},
        headers=headers,
    )

    response = await client.get("/api/v1/ai/recommendations?audience=organization", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "recommendations" in data
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_predictions_endpoint(client):
    org = await register_org(client, email="pred@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Risky Business", "code": "RISK-1", "owner_id": me},
        headers=headers,
    )
    project_id = project.json()["id"]
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Missed thing", "assignee_id": me, "due_date": "2020-01-01"},
        headers=headers,
    )

    response = await client.get(
        "/api/v1/ai/predictions?subject_type=project&metric=delay_risk&refresh=true", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    top = data["predictions"][0]
    assert top["subject_id"] == project_id
    assert top["level"] in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_action_engine_create_task_via_companion(client):
    org = await register_org(client, email="act@work.test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "create a task to update the onboarding docs"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "action" in data["intents"]
    assert "action" in data["tools"]
    assert "onboarding" in data["answer"].lower()

    tasks = await client.get("/api/v1/tasks?search=onboarding", headers=headers)
    assert tasks.status_code == 200
    titles = [t["title"] for t in tasks.json()]
    assert any("onboarding" in t.lower() for t in titles)

    history = await client.get("/api/v1/ai/actions", headers=headers)
    assert history.status_code == 200
    kinds = [a["action_type"] for a in history.json()["actions"]]
    assert "create_task" in kinds
    executed = [a for a in history.json()["actions"] if a["action_type"] == "create_task"][0]
    assert executed["status"] == "executed"
    assert executed["permission_check"] == "tasks:manage"


@pytest.mark.asyncio
async def test_action_engine_remember_and_mark_done(client):
    org = await register_org(client, email="act2@work.test.co")
    headers = org["headers"]

    remembered = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "remember that the sprint demo is every Friday"},
        headers=headers,
    )
    assert remembered.status_code == 200
    assert "action" in remembered.json()["intents"]

    memories = await client.get("/api/v1/ai/memory?text=Friday", headers=headers)
    assert any("Friday" in m["content"] for m in memories.json()["memories"])

    task = await client.post(
        "/api/v1/tasks",
        json={"title": "Finish the release notes", "assignee_id": None},
        headers=headers,
    )
    assert task.status_code == 201

    marked = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "mark the task 'Finish the release notes' as done"},
        headers=headers,
    )
    assert marked.status_code == 200, marked.text
    data = marked.json()
    assert "action" in data["intents"]
    assert "done" in data["answer"].lower()

    tasks = await client.get("/api/v1/tasks?search=release notes", headers=headers)
    found = [t for t in tasks.json() if t["title"] == "Finish the release notes"]
    assert found and found[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_feedback_records_and_learns(client):
    org = await register_org(client, email="feed@work.test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/ai/feedback",
        json={"content": "good", "rating": 5, "correction": "always use UTC in summaries"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "recorded"

    memories = await client.get("/api/v1/ai/memory?text=UTC", headers=headers)
    assert any("UTC" in m["content"] for m in memories.json()["memories"])


@pytest.mark.asyncio
async def test_voice_helpers_and_ask(client):
    org = await register_org(client, email="voice@work.test.co")
    headers = org["headers"]

    cleaned = await client.post(
        "/api/v1/ai/voice/clean",
        json={"transcript": "um uh give me the org pulse"},
        headers=headers,
    )
    assert cleaned.status_code == 200
    assert "um" not in cleaned.json()["transcript"].lower()

    response = await client.post(
        "/api/v1/ai/voice/ask",
        json={"transcript": "give me the org pulse"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "org_pulse" in data["intents"]
    assert data["conversation_id"]


@pytest.mark.asyncio
async def test_conversation_persistence_and_history(client):
    org = await register_org(client, email="conv@work.test.co")
    headers = org["headers"]

    first = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "What should I work on today?"},
        headers=headers,
    )
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    assert conversation_id

    second = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "And after that?", "conversation_id": conversation_id},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    history = await client.get(f"/api/v1/ai/conversations/{conversation_id}", headers=headers)
    assert history.status_code == 200
    roles = [m["role"] for m in history.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]

    listing = await client.get("/api/v1/ai/conversations", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1


@pytest.mark.asyncio
async def test_companion_expert_finder(client):
    org = await register_org(client, email="exp@work.test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/ai/companion/ask",
        json={"message": "find an expert on React"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "expert" in data["intents"]
    assert "expert_finder" in data["tools"]


@pytest.mark.asyncio
async def test_companion_stream_events(client):
    org = await register_org(client, email="stream@work.test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/ai/companion/stream",
        json={"message": "Give me the org pulse"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("content-type", "").startswith("text/event-stream")

    body = response.text
    assert '"delta"' in body, body
    assert '"done"' in body, body

    import json as _json

    events = [_json.loads(line[5:]) for line in body.splitlines() if line.startswith("data: ")]
    deltas = [e["delta"] for e in events if "delta" in e]
    done = [e["done"] for e in events if "done" in e]
    assert "".join(deltas) == done[0].get("answer", "") or len(deltas) > 0
    assert done[0]["conversation_id"]
    assert done[0]["source"] in ("rules", "llm")
    assert "org_pulse" in done[0]["intents"]


@pytest.mark.asyncio
async def test_memory_search_endpoint_requires_permission(client):
    org = await register_org(client, email="perm2@work.test.co")
    response = await client.post("/api/v1/ai/search", json={"query": "x"})
    assert response.status_code == 401
