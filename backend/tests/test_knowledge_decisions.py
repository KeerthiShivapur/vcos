"""Phase 4 — Decision registry, semantic search, knowledge graph, analytics."""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _decision(client, headers, **overrides):
    payload = {
        "title": "Choose the new database",
        "context": "We need a primary datastore for the analytics platform.",
        "content": "Evaluated Postgres, DynamoDB and ClickHouse against cost and velocity.",
        "status": "proposed",
        "options": [
            {"title": "Postgres", "pros": "Familiar, relational", "cons": "Scaling"},
            {"title": "ClickHouse", "pros": "Fast analytics", "cons": "Newer"},
        ],
        "participants": [],
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/decisions", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_decision_registry_and_choose(client):
    org = await register_org(client, email="dec@phase4.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    decision = await _decision(
        client, headers,
        decision_maker_id=me,
        participants=[{"employee_id": me, "role": "maker"}],
    )
    decision_id = decision["id"]
    assert decision["status"] == "proposed"
    assert len(decision["options"]) == 2
    assert len(decision["participants"]) == 1
    assert decision["participants"][0]["employee_name"] is not None

    options = await client.get(f"/api/v1/decisions/{decision_id}/options", headers=headers)
    assert options.status_code == 200
    option_id = options.json()[0]["id"]

    chosen = await client.post(
        f"/api/v1/decisions/{decision_id}/choose",
        json={"option_id": option_id, "reason": "Team already knows Postgres"},
        headers=headers,
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["status"] == "made"
    assert chosen.json()["decided_at"] is not None
    chosen_option = next(o for o in chosen.json()["options"] if o["chosen"])
    assert chosen_option["id"] == option_id
    assert chosen_option["chosen_reason"] == "Team already knows Postgres"

    implemented = await client.post(
        f"/api/v1/decisions/{decision_id}/status",
        json={"status": "implemented", "note": "Migrated all pipelines"},
        headers=headers,
    )
    assert implemented.status_code == 200, implemented.text
    assert implemented.json()["status"] == "implemented"

    listed = await client.get("/api/v1/decisions?status=implemented", headers=headers)
    assert listed.status_code == 200
    assert any(d["id"] == decision_id for d in listed.json())


@pytest.mark.asyncio
async def test_semantic_search_finds_entities(client):
    org = await register_org(client, email="search@phase4.test.co")
    headers = org["headers"]

    await client.post(
        "/api/v1/documents",
        json={
            "title": "Budget Planning Guide",
            "content": "Quarterly budget reviews happen with finance. Approved budgets are locked into the ledger.",
            "category": "finance",
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/wiki",
        json={"title": "Budget approval process", "content": "Finance approves the budget before spend.", "space": "organization"},
        headers=headers,
    )
    await client.post(
        "/api/v1/policies",
        json={"title": "Travel Budget Policy", "content": "Travel expenses are charged to the travel budget code.", "category": "travel"},
        headers=headers,
    )

    resp = await client.get("/api/v1/knowledge/search", params={"q": "budget finance", "mode": "hybrid"}, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] >= 2
    kinds = {r["kind"] for r in data["results"]}
    assert "document" in kinds

    filtered = await client.get(
        "/api/v1/knowledge/search", params={"q": "budget", "kind": "policy"}, headers=headers,
    )
    assert filtered.status_code == 200
    assert all(r["kind"] == "policy" for r in filtered.json()["results"])

    universal = await client.get("/api/v1/search", params={"q": "budget", "limit": 20}, headers=headers)
    assert universal.status_code == 200, universal.text
    types = {r["type"] for r in universal.json()["results"]}
    assert "document" in types


@pytest.mark.asyncio
async def test_knowledge_graph_and_recommendations(client):
    org = await register_org(client, email="graph4@phase4.test.co")
    headers = org["headers"]

    project = await client.post(
        "/api/v1/projects", json={"name": "Graph Project 4", "code": "G4", "owner_id": (await _employee_id(client, headers))},
        headers=headers,
    )
    project_id = project.json()["id"]

    doc = await client.post(
        "/api/v1/documents",
        json={"title": "Graph doc", "content": "Linked to the project", "project_id": project_id},
        headers=headers,
    )
    doc_id = doc.json()["id"]
    await client.post(f"/api/v1/documents/{doc_id}/publish", headers=headers)

    graph = await client.get("/api/v1/knowledge/graph", headers=headers)
    assert graph.status_code == 200, graph.text
    assert any(n["kind"] == "document" for n in graph.json()["nodes"])

    org_graph = await client.get("/api/v1/organization/graph", headers=headers)
    assert org_graph.status_code == 200, org_graph.text
    assert any("kb:" in n["id"] for n in org_graph.json()["nodes"])

    focused = await client.get(f"/api/v1/knowledge/graph?focus=document:{doc_id}", headers=headers)
    assert focused.status_code == 200

    recs = await client.get("/api/v1/knowledge/recommendations", headers=headers)
    assert recs.status_code == 200

    experts = await client.get("/api/v1/knowledge/experts", headers=headers)
    assert experts.status_code == 200
    assert len(experts.json()) >= 1

    stale = await client.get("/api/v1/knowledge/stale?days=0", headers=headers)
    assert stale.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_analytics_and_quality(client):
    org = await register_org(client, email="analytics@phase4.test.co")
    headers = org["headers"]

    await client.post(
        "/api/v1/documents",
        json={
            "title": "Analytics source doc",
            "content": "A long enough body so the quality scoring sees real content. " * 20,
        },
        headers=headers,
    )
    await client.post("/api/v1/wiki", json={"title": "Analytics wiki page", "content": "Short."}, headers=headers)

    analytics = await client.get("/api/v1/knowledge/analytics", headers=headers)
    assert analytics.status_code == 200, analytics.text
    data = analytics.json()
    assert data["total_items"] >= 2
    assert data["totals"]["document"] >= 1
    assert data["totals"]["wiki"] >= 1

    categories = await client.get("/api/v1/knowledge/categories", headers=headers)
    assert categories.status_code == 200
    created_cat = await client.post(
        "/api/v1/knowledge/categories", json={"name": "Operations"}, headers=headers,
    )
    assert created_cat.status_code == 201, created_cat.text
    categories = await client.get("/api/v1/knowledge/categories", headers=headers)
    assert len(categories.json()) >= 1

    tags = await client.get("/api/v1/knowledge/tags", headers=headers)
    assert tags.status_code == 200
