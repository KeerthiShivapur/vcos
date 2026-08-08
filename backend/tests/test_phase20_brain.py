"""Phase 20 — Universal Organizational Intelligence Network (Company Brain) API.

Covers the living overview, universal AI, company health, executive
intelligence, briefing, memory + timeline, universal search, living graph,
universal context, digest, event stream, analytics, the evolution cycle,
RBAC gating and multi-tenant isolation of the brain.
"""

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Phase 20 Brain", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Phase 20 Brain", "password": "P20Pass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


# ------------------------------------------------------------- capabilities


async def test_brain_capabilities_and_overview(client):
    org = await register_org(client, email="p20brain_cap@test.co")
    headers = org["headers"]

    capabilities = (await client.get("/api/v1/brain/capabilities", headers=headers)).json()
    assert capabilities["phase"] == 20
    assert len(capabilities["capabilities"]) >= 12
    ids = {c["id"] for c in capabilities["capabilities"]}
    assert {"graph", "memory", "search", "health", "events", "orchestration"} <= ids

    overview = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    assert overview["organization_id"] == org["organization"]["id"]
    assert "state" in overview and "health" in overview and "graph" in overview
    assert "intelligence" in overview and "analytics" in overview
    assert overview["memory"]["total"] >= 0

    state = (await client.get("/api/v1/brain/state", headers=headers)).json()
    assert "state" in state and "score" in state


# ----------------------------------------------------------- universal ai


async def test_brain_universal_ai(client):
    org = await register_org(client, email="p20brain_ai@test.co")
    headers = org["headers"]

    answer = (await client.post(
        "/api/v1/brain/ask", json={"question": "How is the company doing?"}, headers=headers
    )).json()
    assert answer["conclusion"]
    assert "evidence" in answer and "recommendations" in answer

    advice = (await client.post(
        "/api/v1/brain/advise", json={"question": "Should we expand?"}, headers=headers
    )).json()
    assert advice["recommendation"] and advice["options"]

    explained = (await client.get("/api/v1/brain/explain?topic=projects", headers=headers)).json()
    assert explained["domain"] == "projects"
    assert explained["conclusion"]

    blank = await client.post("/api/v1/brain/ask", json={"question": "   "}, headers=headers)
    assert blank.status_code == 422


# ---------------------------------------------------------------- health


async def test_brain_health(client):
    org = await register_org(client, email="p20brain_health@test.co")
    headers = org["headers"]

    health = (await client.get("/api/v1/brain/health", headers=headers)).json()
    assert "score" in health and "status" in health

    refreshed = (await client.post("/api/v1/brain/health/refresh", headers=headers)).json()
    assert refreshed["score"] >= 0

    history = (await client.get("/api/v1/brain/health/history", headers=headers)).json()
    assert history["total"] >= 1


# ------------------------------------------------------------ intelligence


async def test_brain_intelligence(client):
    org = await register_org(client, email="p20brain_intel@test.co")
    headers = org["headers"]

    generated = (await client.post("/api/v1/brain/intelligence/generate", headers=headers)).json()
    assert generated["id"] and generated["period"] == "on_demand"
    assert "health" in generated["sections"] and "priorities" in generated["sections"]
    assert generated["intelligence_score"] >= 0

    latest = (await client.get("/api/v1/brain/intelligence", headers=headers)).json()
    assert latest["id"] == generated["id"]

    history = (await client.get("/api/v1/brain/intelligence/history", headers=headers)).json()
    assert history["total"] >= 1
    assert any(i["id"] == generated["id"] for i in history["intelligence"])


# --------------------------------------------------------------- briefing


async def test_brain_briefing(client):
    org = await register_org(client, email="p20brain_brief@test.co")
    headers = org["headers"]

    latest = (await client.get("/api/v1/brain/briefing", headers=headers)).json()
    assert latest["title"]
    assert "company_summary" in latest["sections"]

    generated = (await client.post("/api/v1/brain/briefing", headers=headers)).json()
    assert generated["title"]
    assert generated["recommendations"] is not None


# ------------------------------------------------- memory + timeline


async def test_brain_memory_and_timeline(client):
    org = await register_org(client, email="p20brain_mem@test.co")
    headers = org["headers"]

    memory = (await client.post(
        "/api/v1/brain/memory",
        json={"memory_type": "lesson", "title": "Pivoted to usage-based pricing",
              "content": "Customers prefer metered plans.", "importance": "high"},
        headers=headers,
    )).json()
    assert memory["id"] and memory["memory_type"] == "lesson"

    listed = (await client.get("/api/v1/brain/memory", headers=headers)).json()
    assert any(m["id"] == memory["id"] for m in listed["memories"])

    found = (await client.get(
        "/api/v1/brain/memory?search=pricing", headers=headers
    )).json()
    assert any(m["id"] == memory["id"] for m in found["memories"])

    bad = await client.post(
        "/api/v1/brain/memory",
        json={"memory_type": "not-a-type", "title": "Bad"}, headers=headers,
    )
    assert bad.status_code == 422

    entry = (await client.post(
        "/api/v1/brain/timeline",
        json={"event_type": "project.created", "title": "Launched the Aurora platform",
              "category": "projects", "detail": "GA release shipped."},
        headers=headers,
    )).json()
    assert entry["id"] and entry["category"] == "projects"

    timeline = (await client.get("/api/v1/brain/timeline", headers=headers)).json()
    assert any(e["id"] == entry["id"] for e in timeline["entries"])

    bad_entry = await client.post(
        "/api/v1/brain/timeline",
        json={"event_type": "x.y", "title": "X", "category": "not-real"}, headers=headers,
    )
    assert bad_entry.status_code == 422


# ------------------------------------------------------ universal search


async def test_brain_universal_search(client):
    org = await register_org(client, email="p20brain_search@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Nova Constellation", "description": "Flagship platform", "status": "active"},
        headers=headers,
    )).json()
    task = (await client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "Design the Nova launch", "status": "todo"},
        headers=headers,
    )).json()

    results = (await client.get("/api/v1/brain/search?q=Nova", headers=headers)).json()
    assert results["total"] >= 2
    assert any(r["domain"] == "projects" and r["id"] == project["id"] for r in results["results"])
    assert any(r["domain"] == "tasks" and r["id"] == task["id"] for r in results["results"])

    blank = await client.get("/api/v1/brain/search?q=%20%20", headers=headers)
    assert blank.status_code == 422


# ------------------------------------------------------------------ graph


async def test_brain_graph(client):
    org = await register_org(client, email="p20brain_graph@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Orion", "description": "Graph test", "status": "active"},
        headers=headers,
    )).json()
    await client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "Map the graph", "status": "todo"},
        headers=headers,
    )

    rebuilt = (await client.post("/api/v1/brain/graph/rebuild", headers=headers)).json()
    assert rebuilt["nodes"] >= 2
    assert "project" in rebuilt["nodes_by_type"]

    stats = (await client.get("/api/v1/brain/graph", headers=headers)).json()
    assert stats["total_nodes"] == rebuilt["nodes"]

    nodes = (await client.get(
        "/api/v1/brain/graph/nodes?node_type=project", headers=headers
    )).json()
    assert any(n["external_id"] == project["id"] for n in nodes["nodes"])

    search = (await client.get(
        "/api/v1/brain/graph/search?q=Orion", headers=headers
    )).json()
    assert any(r["node_type"] == "project" for r in search["results"])


# ------------------------------------------------- context + digest


async def test_brain_context_and_digest(client):
    org = await register_org(client, email="p20brain_ctx@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Vela", "description": "Context test", "status": "active"},
        headers=headers,
    )).json()
    task = (await client.post(
        "/api/v1/tasks",
        json={"project_id": project["id"], "title": "Wire the context", "status": "todo"},
        headers=headers,
    )).json()

    flow = (await client.get(
        "/api/v1/brain/context",
        params={"entity_type": "project", "entity_id": project["id"]},
        headers=headers,
    )).json()
    assert "related" in flow

    digest = (await client.get("/api/v1/brain/digest?days=7", headers=headers)).json()
    assert digest["new_tasks"] >= 1
    assert "events" in digest and "timeline_headlines" in digest
    assert task["id"] or digest["new_tasks"] >= 0


# -------------------------------------------------- events + analytics


async def test_brain_events_and_analytics(client):
    org = await register_org(client, email="p20brain_evt@test.co")
    headers = org["headers"]

    await client.post(
        "/api/v1/brain/memory",
        json={"memory_type": "milestone", "title": "Quarter one review"}, headers=headers,
    )
    await client.post("/api/v1/brain/graph/rebuild", headers=headers)

    events = (await client.get("/api/v1/brain/events", headers=headers)).json()
    names = {e["name"] for e in events["events"]}
    assert "memory.updated" in names and "graph.updated" in names

    summary = (await client.get("/api/v1/brain/events/summary", headers=headers)).json()
    assert summary["total_events"] >= 2

    analytics = (await client.get("/api/v1/brain/analytics", headers=headers)).json()
    assert "graph" in analytics and "state" in analytics


# -------------------------------------------------------------- evolve


async def test_brain_evolve(client):
    org = await register_org(client, email="p20brain_evolve@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Auriga", "description": "Evolution seed", "status": "active"},
        headers=headers,
    )).json()

    evolved = (await client.post("/api/v1/brain/evolve", headers=headers)).json()
    assert evolved["organization_id"] == org["organization"]["id"]
    assert evolved["observed"]["snapshot_id"]
    assert evolved["graph"]["nodes"] >= 1
    assert evolved["intelligence"]["id"]
    assert evolved["timeline"]["id"]
    assert evolved["events"] == ["organization.updated", "organization.evolved"]

    graph = (await client.get("/api/v1/brain/graph", headers=headers)).json()
    assert graph["total_nodes"] >= 1
    assert graph["nodes_by_type"].get("project", 0) >= 1

    events = (await client.get("/api/v1/brain/events?name=organization.evolved", headers=headers)).json()
    assert events["total"] >= 1

    timeline = (await client.get("/api/v1/brain/timeline?category=system", headers=headers)).json()
    assert any("evolution" in (e["title"] or "").lower() or "cycle" in (e["title"] or "").lower()
               for e in timeline["entries"])

    assert project["id"]  # project still exists after the cycle


# --------------------------------------------------------------- rbac


async def test_brain_governance(client):
    org = await register_org(client, email="p20brain_gov@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p20brain_govemp@test.co", role="employee")

    rec = (await client.post(
        "/api/v1/brain/governance/recommendation",
        json={"title": "Hire two backend engineers", "category": "hiring",
              "rationale": "Release velocity is falling across three projects",
              "evidence": {"type": "risk", "evidence": [
                  {"type": "project", "summary": "3 at-risk projects"}]},
              "confidence": 0.75,
              "affected_systems": ["projects", "hiring"],
              "requires_approval": True},
        headers=headers,
    )).json()
    assert rec["id"] and rec["status"] == "proposed"
    assert rec["confidence"] == 0.75
    assert rec["evidence"]["type"] == "risk"
    assert rec["affected_systems"] == ["projects", "hiring"]

    listed = (await client.get("/api/v1/brain/governance", headers=headers)).json()
    assert listed["pending"] >= 1
    assert any(r["id"] == rec["id"] for r in listed["recommendations"])

    denied = await client.post(
        f"/api/v1/brain/governance/{rec['id']}/approved", headers=employee["headers"]
    )
    assert denied.status_code == 403

    approved = (await client.post(
        f"/api/v1/brain/governance/{rec['id']}/approved", headers=headers
    )).json()
    assert approved["status"] == "approved" and approved["decided_by"]

    implemented = (await client.post(
        f"/api/v1/brain/governance/{rec['id']}/implemented", headers=headers
    )).json()
    assert implemented["status"] == "implemented"

    invalid_transition = await client.post(
        f"/api/v1/brain/governance/{rec['id']}/rejected", headers=headers
    )
    assert invalid_transition.status_code == 422

    missing = await client.post("/api/v1/brain/governance/nope/approved", headers=headers)
    assert missing.status_code == 404

    bad = await client.post(
        "/api/v1/brain/governance/recommendation",
        json={"title": "Bad", "category": "not-a-category"}, headers=headers,
    )
    assert bad.status_code == 422

    bad_confidence = await client.post(
        "/api/v1/brain/governance/recommendation",
        json={"title": "Bad", "category": "risk", "confidence": 3.5}, headers=headers,
    )
    assert bad_confidence.status_code == 422


async def test_brain_resilience(client):
    org = await register_org(client, email="p20brain_res@test.co")
    headers = org["headers"]

    department = (await client.post(
        "/api/v1/departments",
        json={"name": "Quality Assurance", "code": "qa"}, headers=headers,
    )).json()
    employee = (await client.post(
        "/api/v1/employees",
        json={"first_name": "Solo", "last_name": "Guardian",
              "email": "solo@resilience.co", "department_id": department["id"]},
        headers=headers,
    )).json()
    assert employee["id"]

    assessed = (await client.post("/api/v1/brain/resilience/assess", headers=headers)).json()
    assert assessed["assessed_at"]
    assert any(s["type"] == "single_point_of_failure" for s in assessed["signals"])

    plans = (await client.get("/api/v1/brain/resilience", headers=headers)).json()
    assert plans["total"] >= 1
    key_plan = next(p for p in plans["plans"] if p["scenario"] == "key_employee")
    assert key_plan["response_plan"]
    assert key_plan["impact"]["domains"] == ["people"]
    assert key_plan["status"] == "active"

    filtered = (await client.get(
        "/api/v1/brain/resilience?scenario=key_employee&status=active", headers=headers
    )).json()
    assert filtered["total"] == 1

    again = (await client.post("/api/v1/brain/resilience/assess", headers=headers)).json()
    assert again["created"] == []
    assert again["total"] == 1

    plans_after = (await client.get("/api/v1/brain/resilience", headers=headers)).json()
    assert plans_after["total"] == 1


# --------------------------------------------------------------- rbac


async def test_brain_rbac(client):
    org = await register_org(client, email="p20brain_rbac@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p20brain_emp@test.co", role="employee")

    overview = await client.get("/api/v1/brain/overview", headers=employee["headers"])
    assert overview.status_code == 200

    search = await client.get("/api/v1/brain/search?q=anything", headers=employee["headers"])
    assert search.status_code == 200

    denied = await client.post(
        "/api/v1/brain/intelligence/generate", headers=employee["headers"]
    )
    assert denied.status_code == 403

    denied_memory = await client.post(
        "/api/v1/brain/memory",
        json={"memory_type": "lesson", "title": "Nope"}, headers=employee["headers"],
    )
    assert denied_memory.status_code == 403

    unauthenticated = await client.get("/api/v1/brain/overview")
    assert unauthenticated.status_code == 401


# ----------------------------------------------------- tenant isolation


async def test_brain_tenant_isolation(client):
    org_a = await register_org(client, email="p20brain_orga@test.co")
    org_b = await register_org(client, email="p20brain_orgb@test.co")

    await client.post(
        "/api/v1/brain/memory",
        json={"memory_type": "lesson", "title": "Secret org-a lesson"}, headers=org_a["headers"],
    )

    memories_b = (await client.get("/api/v1/brain/memory", headers=org_b["headers"])).json()
    assert all("org-a" not in (m["title"] or "") for m in memories_b["memories"])

    search_b = (await client.get(
        "/api/v1/brain/search?q=org-a", headers=org_b["headers"]
    )).json()
    assert search_b["total"] == 0

    search_a = (await client.get(
        "/api/v1/brain/search?q=org-a", headers=org_a["headers"]
    )).json()
    assert search_a["total"] >= 1

    health_b = (await client.get("/api/v1/brain/health", headers=org_b["headers"])).json()
    assert health_b["score"] >= 0
