"""Phase 19 — Company Memory, Organization Timeline & Universal Context.

Covers permanent organizational memory (record/list/recall/pin/delete), the
organization-wide timeline (record/list/summary/category filters), universal
context bundles (build/attach/flow across projects, tasks, meetings), RBAC
gating (read vs manage), multi-tenant isolation, the Phase 19 event catalog
and universal search integration.
"""

import pytest

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Phase 19 Worker", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Phase 19 Worker", "password": "P19Pass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=100", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


# ------------------------------------------------------------------- memory


async def test_memory_record_list_recall_pin_delete(client):
    org = await register_org(client, email="p19mem@test.co")
    headers = org["headers"]

    memory = (await client.post(
        "/api/v1/memory",
        json={
            "memory_type": "decision",
            "title": "Pivoted to usage-based pricing",
            "content": "The board approved a move to usage-based pricing.",
            "tags": ["pricing", "strategy"],
            "importance": "high",
        },
        headers=headers,
    )).json()
    assert memory["memory_type"] == "decision"
    assert memory["pinned"] is False
    assert memory["importance"] == "high"

    listed = (await client.get("/api/v1/memory", headers=headers)).json()
    assert listed["total"] >= 1
    assert any(m["id"] == memory["id"] for m in listed["memories"])

    recalled = (await client.get("/api/v1/memory/recall?topic=pricing", headers=headers)).json()
    assert recalled["total"] >= 1
    assert recalled["memories"][0]["id"] == memory["id"]

    pinned = (await client.patch(f"/api/v1/memory/{memory['id']}/pin", headers=headers)).json()
    assert pinned["pinned"] is True

    got = (await client.get(f"/api/v1/memory/{memory['id']}", headers=headers)).json()
    assert got["pinned"] is True

    deleted = (await client.delete(f"/api/v1/memory/{memory['id']}", headers=headers)).json()
    assert deleted["status"] == "deleted"

    missing = await client.get(f"/api/v1/memory/{memory['id']}", headers=headers)
    assert missing.status_code == 404


async def test_memory_validation_and_events(client):
    org = await register_org(client, email="p19memval@test.co")
    headers = org["headers"]

    bad = await client.post(
        "/api/v1/memory",
        json={"memory_type": "not-a-type", "title": "Bad"},
        headers=headers,
    )
    assert bad.status_code == 422

    await client.post(
        "/api/v1/memory",
        json={"memory_type": "lesson", "title": "Lesson learned", "content": "Always test."},
        headers=headers,
    )
    await client.get("/api/v1/memory/recall?topic=test", headers=headers)

    names = await _event_names(client, headers)
    assert "memory.recorded" in names
    assert "memory.recalled" in names


async def test_memory_rbac(client):
    org = await register_org(client, email="p19memrbac@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p19memrbac_e@test.co", role="employee")

    listed = await client.get("/api/v1/memory", headers=employee["headers"])
    assert listed.status_code == 200

    denied = await client.post(
        "/api/v1/memory",
        json={"memory_type": "policy", "title": "Remote work policy"},
        headers=employee["headers"],
    )
    assert denied.status_code == 403


# ----------------------------------------------------------------- timeline


async def test_timeline_record_list_summary(client):
    org = await register_org(client, email="p19tl@test.co")
    headers = org["headers"]

    entry = (await client.post(
        "/api/v1/timeline",
        json={
            "event_type": "project.created",
            "title": "Launched the Aurora platform project",
            "category": "projects",
            "detail": "Kickoff with a 6-month roadmap.",
        },
        headers=headers,
    )).json()
    assert entry["category"] == "projects"
    assert entry["event_type"] == "project.created"

    listed = (await client.get("/api/v1/timeline", headers=headers)).json()
    assert listed["total"] >= 1
    assert any(e["id"] == entry["id"] for e in listed["entries"])

    filtered = (await client.get("/api/v1/timeline?category=projects", headers=headers)).json()
    assert filtered["total"] >= 1

    summary = (await client.get("/api/v1/timeline/summary", headers=headers)).json()
    assert summary["total"] >= 1
    assert summary["categories"].get("projects", 0) >= 1
    assert summary["latest"][0]["id"] == entry["id"]

    got = (await client.get(f"/api/v1/timeline/{entry['id']}", headers=headers)).json()
    assert got["title"] == "Launched the Aurora platform project"


async def test_timeline_category_fallback_and_validation(client):
    org = await register_org(client, email="p19tlcv@test.co")
    headers = org["headers"]

    entry = (await client.post(
        "/api/v1/timeline",
        json={"event_type": "invoice.received", "title": "Invoice #1042 received"},
        headers=headers,
    )).json()
    assert entry["category"] == "finance"

    bad = await client.post(
        "/api/v1/timeline",
        json={"event_type": "something.new", "title": "X", "category": "not-real"},
        headers=headers,
    )
    assert bad.status_code == 422

    names = await _event_names(client, headers)
    assert "timeline.recorded" in names


# ----------------------------------------------------------------- context


async def test_context_build_attach_flow_for_project(client):
    org = await register_org(client, email="p19ctx@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Nova", "description": "Context test project", "status": "active"},
        headers=headers,
    )).json()
    task = (await client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "Design the context API", "status": "todo"},
        headers=headers,
    )).json()

    context = (await client.get(f"/api/v1/context/project/{project['id']}", headers=headers)).json()
    assert context["entity_type"] == "project"
    assert context["entity_id"] == project["id"]
    assert len(context["related"].get("tasks", [])) >= 1
    assert context["related"]["tasks"][0]["id"] == task["id"]
    assert context["summary"]
    assert context["flow"]

    attached = (await client.post(
        "/api/v1/context/attach",
        json={"entity_type": "project", "entity_id": project["id"], "related": {"goals": ["g-1"]}},
        headers=headers,
    )).json()
    assert attached["related"]["goals"] == ["g-1"]

    flow = (await client.get(f"/api/v1/context/project/{project['id']}", headers=headers)).json()
    assert flow["entity_id"] == project["id"]
    assert isinstance(flow["flow"], list)

    names = await _event_names(client, headers)
    assert "context.updated" in names


async def test_context_unknown_entity_is_defensive(client):
    org = await register_org(client, email="p19ctxdef@test.co")
    headers = org["headers"]

    context = (await client.get("/api/v1/context/project/nonexistent-id", headers=headers)).json()
    assert context["entity_type"] == "project"
    assert all(len(v) == 0 for v in context["related"].values())

    flow = (await client.get("/api/v1/context/task/does-not-exist", headers=headers)).json()
    assert flow["flow"] == []


async def test_context_rebuild(client):
    org = await register_org(client, email="p19ctxreb@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Rebuild", "status": "active"},
        headers=headers,
    )).json()
    task = (await client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "Design the API", "status": "todo"},
        headers=headers,
    )).json()

    rebuilt = (await client.post(
        f"/api/v1/context/project/{project['id']}/build",
        headers=headers,
    )).json()
    assert rebuilt["entity_type"] == "project"
    assert len(rebuilt["related"].get("tasks", [])) >= 1
    assert rebuilt["related"]["tasks"][0]["id"] == task["id"]


# ------------------------------------------------------------- isolation + search


async def test_phase19_tenant_isolation(client):
    org_a = await register_org(client, email="p19iso_a@test.co")
    org_b = await register_org(client, email="p19iso_b@test.co")

    mem_a = (await client.post(
        "/api/v1/memory",
        json={"memory_type": "institutional", "title": "Secret A strategy"},
        headers=org_a["headers"],
    )).json()
    await client.post(
        "/api/v1/timeline",
        json={"event_type": "milestone.completed", "title": "Secret A milestone"},
        headers=org_a["headers"],
    )

    listed_b = (await client.get("/api/v1/memory", headers=org_b["headers"]))
    assert listed_b.status_code == 200
    assert not any(m["id"] == mem_a["id"] for m in listed_b.json()["memories"])

    cross = await client.get(f"/api/v1/memory/{mem_a['id']}", headers=org_b["headers"])
    assert cross.status_code == 404


async def test_memory_and_timeline_in_universal_search(client):
    org = await register_org(client, email="p19search@test.co")
    headers = org["headers"]

    await client.post(
        "/api/v1/memory",
        json={"memory_type": "lesson", "title": "Churn analysis lesson", "content": "Retention starts at onboarding."},
        headers=headers,
    )
    await client.post(
        "/api/v1/timeline",
        json={"event_type": "opportunity.won", "title": "Won the Zephyr deal", "category": "customers"},
        headers=headers,
    )

    results = (await client.get("/api/v1/search?q=churn", headers=headers)).json()
    assert any(r["type"] == "memory" for r in results.get("results", results))

    results = (await client.get("/api/v1/search?q=zephyr", headers=headers)).json()
    assert any(r["type"] == "timeline" for r in results.get("results", results))
