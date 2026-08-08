"""Phase 19 — Autonomous Enterprise & Intelligence Network API.

Covers organizational state/observation, autonomous plans, executive
briefings, decision cases, predictive intelligence and the intelligence
network (reasoning, strategic advice, collective learning, innovation,
organization graph) plus RBAC gating.
"""

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Phase 19 Autonomy", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Phase 19 Autonomy", "password": "P19Pass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


# ------------------------------------------------------------------- state


async def test_autonomy_state_and_observe(client):
    org = await register_org(client, email="p19auto_state@test.co")
    headers = org["headers"]

    state = (await client.get("/api/v1/autonomy/state", headers=headers)).json()
    assert "state" in state
    assert "score" in state

    observed = (await client.post("/api/v1/autonomy/observe", headers=headers)).json()
    assert observed["snapshot_id"]
    assert observed["score"] >= 0

    metrics = (await client.get("/api/v1/autonomy/metrics", headers=headers)).json()
    assert "metrics" in metrics

    insights = (await client.get("/api/v1/autonomy/insights", headers=headers)).json()
    assert "insights" in insights


# ------------------------------------------------------------------- plans


async def test_autonomy_plans_flow(client):
    org = await register_org(client, email="p19auto_plan@test.co")
    headers = org["headers"]

    generated = (await client.post(
        "/api/v1/autonomy/plans/generate", json={"kinds": ["daily"]}, headers=headers
    )).json()
    assert generated["total"] >= 1
    plan = generated["plans"][0]

    listed = (await client.get("/api/v1/autonomy/plans?kind=daily", headers=headers)).json()
    assert any(p["id"] == plan["id"] for p in listed["plans"])

    approved = (await client.patch(
        f"/api/v1/autonomy/plans/{plan['id']}", json={"status": "approved"}, headers=headers
    )).json()
    assert approved["status"] == "approved"
    assert approved["approved_by"]

    invalid = await client.patch(
        f"/api/v1/autonomy/plans/{plan['id']}", json={"status": "nonsense"}, headers=headers
    )
    assert invalid.status_code == 422


# ----------------------------------------------------------------- briefing


async def test_executive_briefing(client):
    org = await register_org(client, email="p19auto_brief@test.co")
    headers = org["headers"]

    briefing = (await client.post("/api/v1/autonomy/briefing/generate", headers=headers)).json()
    assert briefing["title"]
    assert "company_summary" in briefing["sections"]
    assert briefing["recommendations"]

    latest = (await client.get("/api/v1/autonomy/briefing", headers=headers)).json()
    assert latest["id"] == briefing["id"]


# ----------------------------------------------------------------- decisions


async def test_decision_case_lifecycle(client):
    org = await register_org(client, email="p19auto_dec@test.co")
    headers = org["headers"]

    case = (await client.post(
        "/api/v1/autonomy/decisions",
        json={
            "title": "Hire a second designer",
            "category": "hiring",
            "context": "Design capacity is the bottleneck.",
            "alternatives": [{"title": "Hire", "pros": ["Speed"], "cons": ["Cost"]}],
        },
        headers=headers,
    )).json()
    assert case["status"] == "pending_approval"
    assert len(case["alternatives"]) == 1

    got = (await client.get(f"/api/v1/autonomy/decisions/{case['id']}", headers=headers)).json()
    assert got["id"] == case["id"]

    decided = (await client.post(
        f"/api/v1/autonomy/decisions/{case['id']}/decide",
        json={"decision": "approved", "outcome": "Offer extended", "lessons": ["Move fast on hiring"]},
        headers=headers,
    )).json()
    assert decided["status"] == "approved"
    assert decided["outcome"] == "Offer extended"
    assert decided["lessons"] == ["Move fast on hiring"]


# -------------------------------------------------------------- predictions


async def test_prediction_lifecycle(client):
    org = await register_org(client, email="p19auto_pred@test.co")
    headers = org["headers"]

    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Prediction Seed", "status": "active"},
        headers=headers,
    )).json()
    overdue = (await client.post(
        "/api/v1/tasks",
        json={
            "project_id": project["id"],
            "title": "Ship the release",
            "status": "in_progress",
            "due_date": "2026-07-01",
        },
        headers=headers,
    )).json()
    assert overdue["id"]

    generated = (await client.post("/api/v1/predictions/generate", headers=headers)).json()
    assert generated["total"] >= 1
    prediction = generated["predictions"][0]
    assert prediction["kind"]

    listed = (await client.get("/api/v1/predictions?status=open", headers=headers)).json()
    assert any(p["id"] == prediction["id"] for p in listed["predictions"])

    models = (await client.get("/api/v1/predictions/models", headers=headers)).json()
    assert "models" in models

    validated = (await client.post(
        f"/api/v1/predictions/{prediction['id']}/validate", json={"came_true": True}, headers=headers
    )).json()
    assert validated["status"] == "validated"

    history = (await client.get("/api/v1/predictions/history", headers=headers)).json()
    assert history["total"] >= 1

    missing = await client.get("/api/v1/predictions/nonexistent-id", headers=headers)
    assert missing.status_code == 404


# ------------------------------------------------------------ network


async def test_network_reasoning_and_advice(client):
    org = await register_org(client, email="p19net_reason@test.co")
    headers = org["headers"]

    answer = (await client.post(
        "/api/v1/intelligence/network/reason",
        json={"question": "Why is my organization slow?"},
        headers=headers,
    )).json()
    assert answer["question"]
    assert "conclusion" in answer
    assert "root_causes" in answer

    advice = (await client.post(
        "/api/v1/intelligence/network/advise",
        json={"question": "Should we expand into Germany?"},
        headers=headers,
    )).json()
    assert advice["topic"] == "expansion"
    assert advice["recommendation"]
    assert advice["human_approval_required"] is True

    bad = await client.post(
        "/api/v1/intelligence/network/reason", json={"question": "   "}, headers=headers
    )
    assert bad.status_code == 422


async def test_network_graph_and_innovation(client):
    org = await register_org(client, email="p19net_graph@test.co")
    headers = org["headers"]

    rebuilt = (await client.post("/api/v1/intelligence/network/graph/rebuild", headers=headers)).json()
    assert rebuilt["nodes"] >= 1

    stats = (await client.get("/api/v1/intelligence/network/graph", headers=headers)).json()
    assert stats["total_nodes"] >= 1
    assert "nodes_by_type" in stats

    nodes = (await client.get("/api/v1/intelligence/network/graph/nodes", headers=headers)).json()
    assert nodes["total"] >= 1

    scan = (await client.post("/api/v1/intelligence/network/innovation/scan", headers=headers)).json()
    assert "tracked_topics" in scan

    innovations = (await client.get("/api/v1/intelligence/network/innovation", headers=headers)).json()
    assert "innovations" in innovations

    overview = (await client.get("/api/v1/intelligence/network/overview", headers=headers)).json()
    assert "graph" in overview
    assert overview["graph"]["total_nodes"] >= 1


async def test_network_decisions_and_collective(client):
    org = await register_org(client, email="p19net_dec@test.co")
    headers = org["headers"]

    case = (await client.post(
        "/api/v1/intelligence/network/decisions",
        json={"title": "Choose a cloud provider", "category": "infrastructure"},
        headers=headers,
    )).json()
    assert case["id"]
    assert "organization_graph" in case["analysis"]

    got = (await client.get(f"/api/v1/intelligence/network/decisions/{case['id']}", headers=headers)).json()
    assert got["id"] == case["id"]

    decided = (await client.post(
        f"/api/v1/intelligence/network/decisions/{case['id']}/decide",
        json={"decision": "approved", "outcome": "Signed with provider"},
        headers=headers,
    )).json()
    assert decided["status"] == "approved"

    learned = (await client.post("/api/v1/intelligence/network/learn", headers=headers)).json()
    assert "insights" in learned


# ------------------------------------------------------------------- rbac


async def test_autonomy_rbac(client):
    org = await register_org(client, email="p19auto_rbac@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p19auto_rbac_e@test.co", role="employee")

    state = await client.get("/api/v1/autonomy/state", headers=employee["headers"])
    assert state.status_code == 200

    observe = await client.post("/api/v1/autonomy/observe", headers=employee["headers"])
    assert observe.status_code == 403

    generate = await client.post("/api/v1/predictions/generate", headers=employee["headers"])
    assert generate.status_code == 403

    predictions = await client.get("/api/v1/predictions", headers=employee["headers"])
    assert predictions.status_code == 200

    reason = await client.post(
        "/api/v1/intelligence/network/reason",
        json={"question": "Company summary?"},
        headers=employee["headers"],
    )
    assert reason.status_code == 200

    rebuild = await client.post("/api/v1/intelligence/network/graph/rebuild", headers=employee["headers"])
    assert rebuild.status_code == 403


async def test_autonomy_tenant_isolation(client):
    org_a = await register_org(client, email="p19auto_iso_a@test.co")
    org_b = await register_org(client, email="p19auto_iso_b@test.co")

    plan = (await client.post(
        "/api/v1/autonomy/plans/generate", json={"kinds": ["daily"]}, headers=org_a["headers"]
    )).json()["plans"][0]

    missing = await client.patch(
        f"/api/v1/autonomy/plans/{plan['id']}", json={"status": "approved"}, headers=org_b["headers"]
    )
    assert missing.status_code == 404
