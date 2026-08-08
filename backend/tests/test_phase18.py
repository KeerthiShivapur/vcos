"""Phase 18 — Autonomous Enterprise Intelligence, Developer Ecosystem &
AI Agent Ecosystem.

Covers the organizational digital twin (build/refresh/history), health engine,
explainable predictions, scenario simulations, strategic forecasts, executive
recommendations, optimization suggestions, decision history with lessons,
the executive intelligence center + morning brief, twin AI question engine,
RBAC gating, multi-tenant isolation, the Phase 18 event catalog and universal
search integration.
"""

import pytest

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Phase 18 Worker", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Phase 18 Worker", "password": "P18Pass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=100", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


# ------------------------------------------------------------ twin


async def test_digital_twin_build_refresh_history(client):
    org = await register_org(client, email="p18twin@test.co")
    headers = org["headers"]

    twin = (await client.get("/api/v1/twin", headers=headers)).json()
    assert twin["organization_id"] == org["organization"]["id"]
    assert twin["health_score"] is not None
    assert twin["refresh_count"] >= 1
    assert isinstance(twin["entity_counts"], dict)
    assert "employees" in twin["entity_counts"]
    assert isinstance(twin["dimensions"], dict)
    assert isinstance(twin["state"], dict)

    refreshed = (await client.post("/api/v1/twin/refresh", headers=headers)).json()
    assert refreshed["status"] == "refreshed"
    assert refreshed["organization_id"] == org["organization"]["id"]

    history = (await client.get("/api/v1/twin/history", headers=headers)).json()
    assert history["total"] >= 1
    assert all("captured_at" in h for h in history["history"])

    names = await _event_names(client, headers)
    assert "digital_twin.updated" in names


async def test_health_engine(client):
    org = await register_org(client, email="p18health@test.co")
    headers = org["headers"]

    health = (await client.get("/api/v1/twin/health", headers=headers)).json()
    assert 0 <= health["score"] <= 100
    assert health["status"] in ("excellent", "good", "watch", "at_risk", "stable")
    assert isinstance(health["breakdown"], dict)
    assert len(health["breakdown"]) >= 5

    history = (await client.get("/api/v1/twin/health/history", headers=headers)).json()
    assert history["total"] >= 1


# ------------------------------------------------------------ predictions


async def test_predictions_generate_acknowledge_dismiss(client):
    org = await register_org(client, email="p18pred@test.co")
    headers = org["headers"]

    generated = (await client.post("/api/v1/twin/predictions/generate", headers=headers)).json()
    assert generated["total"] >= 1
    prediction = generated["predictions"][0]
    assert prediction["kind"]
    assert prediction["level"] in ("low", "medium", "high", "critical")
    assert isinstance(prediction["signals"], list)
    assert prediction["status"] == "active"

    listed = (await client.get("/api/v1/twin/predictions", headers=headers)).json()
    assert listed["total"] >= 1

    ack = await client.post(
        f"/api/v1/twin/predictions/{prediction['id']}/acknowledge", headers=headers
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    dismiss = await client.post(
        f"/api/v1/twin/predictions/{prediction['id']}/dismiss", headers=headers
    )
    assert dismiss.status_code == 200
    assert dismiss.json()["status"] == "dismissed"

    active = (await client.get("/api/v1/twin/predictions?status=active", headers=headers)).json()
    assert prediction["id"] not in {p["id"] for p in active["predictions"]}

    missing = await client.post("/api/v1/twin/predictions/nope/acknowledge", headers=headers)
    assert missing.status_code == 404

    names = await _event_names(client, headers)
    assert "prediction.generated" in names


# ------------------------------------------------------------ simulations


async def test_simulations_run_list_get(client):
    org = await register_org(client, email="p18sim@test.co")
    headers = org["headers"]

    result = await client.post(
        "/api/v1/twin/simulations/run",
        json={"scenario": "hire_engineers", "params": {"count": 3}},
        headers=headers,
    )
    assert result.status_code == 200
    data = result.json()
    assert data["scenario"] == "hire_engineers"
    assert 0 <= data["results"]["risk"] <= 100
    assert data["results"]["summary"]
    assert "outcomes" in data["results"]

    invalid = await client.post(
        "/api/v1/twin/simulations/run",
        json={"scenario": "fly_to_mars"},
        headers=headers,
    )
    assert invalid.status_code in (400, 422)

    listed = (await client.get("/api/v1/twin/simulations", headers=headers)).json()
    assert listed["total"] >= 1

    detail = await client.get(f"/api/v1/twin/simulations/{data['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == data["id"]

    missing = await client.get("/api/v1/twin/simulations/nope", headers=headers)
    assert missing.status_code == 404

    names = await _event_names(client, headers)
    assert "simulation.completed" in names


# ------------------------------------------------------------ forecasts


async def test_forecasts_generate_list(client):
    org = await register_org(client, email="p18forecast@test.co")
    headers = org["headers"]

    generated = (await client.post("/api/v1/twin/forecasts/generate", headers=headers)).json()
    assert generated["total"] >= 5
    forecast = generated["forecasts"][0]
    assert forecast["dimension"]
    assert forecast["horizon_days"] >= 30
    assert len(forecast["series"]) >= 2
    assert forecast["trend"] in ("up", "down", "flat")

    listed = (await client.get("/api/v1/twin/forecasts", headers=headers)).json()
    assert listed["total"] >= 5

    names = await _event_names(client, headers)
    assert "forecast.created" in names


# ------------------------------------------------------------ recommendations


async def test_recommendations_generate_status(client):
    org = await register_org(client, email="p18rec@test.co")
    headers = org["headers"]

    generated = (await client.post("/api/v1/twin/recommendations/generate", headers=headers)).json()
    assert generated["total"] >= 1
    recommendation = generated["recommendations"][0]
    assert recommendation["title"]
    assert recommendation["impact"] in ("critical", "high", "medium", "low")
    assert recommendation["status"] == "active"

    listed = (await client.get("/api/v1/twin/recommendations", headers=headers)).json()
    assert listed["total"] >= 1

    status = await client.post(
        f"/api/v1/twin/recommendations/{recommendation['id']}/status",
        json={"status": "accepted"},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "accepted"

    bad = await client.post(
        f"/api/v1/twin/recommendations/{recommendation['id']}/status",
        json={"status": "flying"},
        headers=headers,
    )
    assert bad.status_code in (422, 400)

    names = await _event_names(client, headers)
    assert "recommendation.generated" in names


# ------------------------------------------------------------ optimization


async def test_optimization_generate_apply(client):
    org = await register_org(client, email="p18opt@test.co")
    headers = org["headers"]

    generated = (await client.post("/api/v1/twin/optimization/generate", headers=headers)).json()
    assert generated["total"] >= 1
    suggestion = generated["optimizations"][0]
    assert suggestion["title"]
    assert suggestion["impact"] in ("high", "medium", "low")
    assert suggestion["status"] == "suggested"
    assert isinstance(suggestion["evidence"], list)

    applied = await client.post(
        f"/api/v1/twin/optimization/{suggestion['id']}/apply", headers=headers
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["applied_at"]

    missing = await client.post("/api/v1/twin/optimization/nope/apply", headers=headers)
    assert missing.status_code == 404

    names = await _event_names(client, headers)
    assert "optimization.suggested" in names


# ------------------------------------------------------------ decisions


async def test_decisions_create_outcome_analyze(client):
    org = await register_org(client, email="p18dec@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/twin/decisions",
        json={
            "decision": "Adopt elastic teams for delivery",
            "category": "strategy",
            "reason": "Improve delivery throughput",
            "alternatives": ["Keep fixed squads", "Outsource"],
            "evidence": [{"metric": "throughput", "value": 12}],
        },
        headers=headers,
    )
    assert created.status_code == 200
    decision = created.json()
    assert decision["status"] == "made"
    assert decision["category"] == "strategy"
    assert decision["alternatives"] == ["Keep fixed squads", "Outsource"]

    outcome = await client.post(
        f"/api/v1/twin/decisions/{decision['id']}/outcome",
        json={"outcome": "Delivery velocity up 20%", "outcome_score": 80},
        headers=headers,
    )
    assert outcome.status_code == 200
    assert outcome.json()["status"] == "reviewed"
    assert outcome.json()["analyzed"] is True
    assert len(outcome.json()["lessons"]) >= 1

    analyzed = await client.post(
        f"/api/v1/twin/decisions/{decision['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200
    assert analyzed.json()["verdict"] == "success"
    assert "analysis" in analyzed.json()

    listed = (await client.get("/api/v1/twin/decisions", headers=headers)).json()
    assert listed["total"] >= 1

    missing = await client.post("/api/v1/twin/decisions/nope/outcome",
                                json={"outcome": "x", "outcome_score": 10}, headers=headers)
    assert missing.status_code == 404

    names = await _event_names(client, headers)
    assert "decision.analyzed" in names


# ------------------------------------------------------------ brief + intelligence center


async def test_intelligence_center_and_brief(client):
    org = await register_org(client, email="p18brief@test.co")
    headers = org["headers"]

    intelligence = (await client.get("/api/v1/twin/intelligence", headers=headers)).json()
    assert intelligence["twin"] is not None
    assert intelligence["health"] is not None
    assert "predictions" in intelligence
    assert "recommendations" in intelligence
    assert "simulations" in intelligence
    assert "forecasts" in intelligence
    assert "optimizations" in intelligence
    assert "decisions" in intelligence

    brief = (await client.get("/api/v1/twin/brief", headers=headers)).json()
    assert brief["summary"]
    assert "Health is" in brief["summary"] or "health" in brief["summary"].lower()
    assert isinstance(brief["highlights"]["health_score"], (int, float))
    assert brief["highlights"]["employees"] is not None


# ------------------------------------------------------------ twin AI


async def test_twin_ai_ask(client):
    org = await register_org(client, email="p18ai@test.co")
    headers = org["headers"]

    answer = await client.post("/api/v1/twin/ask", json={"question": "How healthy is the company?"}, headers=headers)
    assert answer.status_code == 200
    data = answer.json()
    assert data["intent"] == "health"
    assert data["answer"]
    assert data["confidence"] > 0.5

    overview = await client.post("/api/v1/twin/ask", json={"question": "Give me an overview of everything"}, headers=headers)
    assert overview.json()["intent"] == "overview"
    assert overview.json()["answer"]

    risk = await client.post("/api/v1/twin/ask", json={"question": "What are the top risks?"}, headers=headers)
    assert risk.json()["intent"] == "risk"


# ------------------------------------------------------------ RBAC + tenancy


async def test_twin_rbac_and_tenancy(client):
    org = await register_org(client, email="p18rbac@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p18emp@test.co", role="employee")

    denied = await client.post("/api/v1/twin/predictions/generate", headers=employee["headers"])
    assert denied.status_code == 403

    can_view = await client.get("/api/v1/twin/health", headers=employee["headers"])
    assert can_view.status_code == 200

    other = await register_org(client, email="p18rbac2@test.co", slug="p18-other")
    other_headers = other["headers"]

    await client.post("/api/v1/twin/predictions/generate", headers=headers)
    other_predictions = (await client.get("/api/v1/twin/predictions", headers=other_headers)).json()
    assert other_predictions["total"] == 0

    other_brief = (await client.get("/api/v1/twin/brief", headers=other_headers)).json()
    assert other_brief["organization_id"] == other["organization"]["id"]


# ------------------------------------------------------------ search integration


async def test_twin_searchable(client):
    org = await register_org(client, email="p18search@test.co")
    headers = org["headers"]

    await client.get("/api/v1/twin", headers=headers)
    await client.post("/api/v1/twin/predictions/generate", headers=headers)
    await client.post("/api/v1/twin/forecasts/generate", headers=headers)

    results = (await client.get("/api/v1/search?q=twin", headers=headers)).json()["results"]
    types = {r["type"] for r in results}
    assert "digital_twin" in types

    results2 = (await client.get("/api/v1/search?q=forecast", headers=headers)).json()["results"]
    types2 = {r["type"] for r in results2}
    assert "forecast" in types2


# ============================================================ Part B: Developer Ecosystem


async def _register_developer(client, headers, email="dev@test.co", name="Dev Builders"):
    response = await client.post(
        "/api/v1/developers/register",
        json={"name": name, "email": email, "bio": "Building VCOS extensions"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_developer_registration_and_profile(client):
    org = await register_org(client, email="p18dev1@test.co")
    headers = org["headers"]

    developer = await _register_developer(client, headers)
    assert developer["developer_key"].startswith("dev_")
    assert developer["status"] == "active"
    assert developer["verified"] is False

    duplicate = await _register_developer(client, headers)
    assert duplicate["id"] == developer["id"]

    me = (await client.get("/api/v1/developers/me", headers=headers)).json()
    assert me["profile"]["id"] == developer["id"]
    assert me["subscription"]["plan"] == "free"
    assert me["subscription"]["monthly_quota"] == 1000

    listed = (await client.get("/api/v1/developers", headers=headers)).json()
    assert listed["total"] >= 1


async def test_developer_applications_and_api_keys(client):
    org = await register_org(client, email="p18dev2@test.co")
    headers = org["headers"]
    await _register_developer(client, headers)

    created = await client.post(
        "/api/v1/developers/me/applications",
        json={"name": "Analytics Widget", "app_type": "widget",
              "scopes": ["analytics:read"], "description": "Charts for dashboards"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    app = created.json()
    assert app["application_key"].startswith("app_")
    assert app["status"] == "draft"
    assert app["scopes"] == ["analytics:read"]

    published = await client.post(
        f"/api/v1/developers/me/applications/{app['id']}/publish", headers=headers
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_at"]

    bad_type = await client.post(
        "/api/v1/developers/me/applications",
        json={"name": "Bad", "app_type": "rocket"},
        headers=headers,
    )
    assert bad_type.status_code == 422

    key = await client.post(
        f"/api/v1/developers/me/applications/{app['id']}/keys",
        json={"name": "prod", "scopes": ["analytics:read"], "rate_limit_per_minute": 30},
        headers=headers,
    )
    assert key.status_code == 200, key.text
    assert key.json()["api_key"].startswith("vcod_")
    assert key.json()["key_prefix"] == key.json()["api_key"][:10]

    keys = (await client.get(
        f"/api/v1/developers/me/applications/{app['id']}/keys", headers=headers
    )).json()
    assert keys["total"] == 1
    assert "api_key" not in keys["keys"][0]
    assert keys["keys"][0]["status"] == "active"

    revoked = await client.post(
        f"/api/v1/developers/me/keys/{key.json()['id']}/revoke", headers=headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    delisted = await client.post(
        f"/api/v1/developers/me/applications/{app['id']}/delist", headers=headers
    )
    assert delisted.json()["status"] == "archived"


async def test_developer_usage_analytics(client):
    org = await register_org(client, email="p18dev3@test.co")
    headers = org["headers"]
    await _register_developer(client, headers)

    app = (
        await client.post(
            "/api/v1/developers/me/applications",
            json={"name": "API Service", "app_type": "app"},
            headers=headers,
        )
    ).json()

    for unit, value in (("requests", 1200), ("errors", 12), ("latency_ms", 340)):
        recorded = await client.post(
            "/api/v1/developers/usage/record",
            json={"application_id": app["id"], "usage_date": "2026-08-07", "unit": unit, "value": value},
            headers=headers,
        )
        assert recorded.status_code == 200, recorded.text

    bad_unit = await client.post(
        "/api/v1/developers/usage/record",
        json={"application_id": app["id"], "usage_date": "2026-08-07", "unit": "gigabytes", "value": 1},
        headers=headers,
    )
    assert bad_unit.status_code == 422

    summary = (await client.get("/api/v1/developers/me/analytics?days=30", headers=headers)).json()
    assert summary["totals"]["requests"] == 1200
    assert summary["totals"]["errors"] == 12
    assert summary["totals"]["latency_ms"] == 340
    assert "2026-08-07" in summary["by_day"]

    names = await _event_names(client, headers)
    assert "usage.recorded" in names


async def test_developer_billing_plan_change(client):
    org = await register_org(client, email="p18dev4@test.co")
    headers = org["headers"]
    await _register_developer(client, headers)

    changed = await client.post(
        "/api/v1/developers/me/subscription/plan", json={"plan": "pro"}, headers=headers
    )
    assert changed.status_code == 200
    assert changed.json()["plan"] == "pro"
    assert changed.json()["monthly_quota"] == 100000
    assert changed.json()["revenue_share"] == 0.1

    bad = await client.post(
        "/api/v1/developers/me/subscription/plan", json={"plan": "diamond"}, headers=headers
    )
    assert bad.status_code == 422

    names = await _event_names(client, headers)
    assert "subscription.changed" in names


async def test_developer_certifications(client):
    org = await register_org(client, email="p18dev5@test.co")
    headers = org["headers"]
    await _register_developer(client, headers)

    passed = await client.post(
        "/api/v1/developers/me/certifications/attempt",
        json={"exam": "plugin-developer", "score": 82.5},
        headers=headers,
    )
    assert passed.status_code == 200
    assert passed.json()["status"] == "passed"
    assert passed.json()["badge"] == "VCOS Certified Plugin Developer"
    assert passed.json()["expires_at"]

    failed = await client.post(
        "/api/v1/developers/me/certifications/attempt",
        json={"exam": "solution-architect", "score": 40},
        headers=headers,
    )
    assert failed.json()["status"] == "failed"

    bad_exam = await client.post(
        "/api/v1/developers/me/certifications/attempt",
        json={"exam": "wizard", "score": 99},
        headers=headers,
    )
    assert bad_exam.status_code == 422

    listed = (await client.get("/api/v1/developers/me/certifications", headers=headers)).json()
    assert listed["total"] == 2

    names = await _event_names(client, headers)
    assert "certification.issued" in names


async def test_agents_lifecycle(client):
    org = await register_org(client, email="p18agent@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/agents",
        json={"name": "CFO Copilot", "role": "finance",
              "capabilities": ["expense-analysis", "forecasting"],
              "permissions": ["finance:read"]},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    agent = created.json()
    assert agent["agent_key"].startswith("agent_")
    assert agent["status"] == "draft"
    assert agent["role"] == "finance"

    bad_role = await client.post(
        "/api/v1/agents", json={"name": "Rogue", "role": "dragon"}, headers=headers
    )
    assert bad_role.status_code == 422

    installed = await client.patch(
        f"/api/v1/agents/{agent['id']}/status", json={"status": "installed"}, headers=headers
    )
    assert installed.status_code == 200
    assert installed.json()["status"] == "installed"
    assert installed.json()["installed_at"]

    executed = await client.post(
        f"/api/v1/agents/{agent['id']}/execute",
        json={"input_text": "Analyze Q3 spend", "context": {"quarter": "Q3"}},
        headers=headers,
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    assert "CFO Copilot" in executed.json()["response"]

    listed = (await client.get("/api/v1/agents", headers=headers)).json()
    assert listed["total"] >= 1
    assert listed["agents"][0]["name"] == "CFO Copilot"

    missing = await client.patch(
        "/api/v1/agents/nope/status", json={"status": "installed"}, headers=headers
    )
    assert missing.status_code == 404

    names = await _event_names(client, headers)
    assert "agent.installed" in names


async def test_webhook_endpoints_and_deliveries(client):
    org = await register_org(client, email="p18hook@test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/webhooks",
        json={"name": "Pipeline", "url": "https://hooks.example.com/vcos",
              "events": ["digital_twin.updated", "webhook.test"], "secret": "s3cret"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    endpoint = created.json()
    assert endpoint["status"] == "active"
    assert endpoint["events"] == ["digital_twin.updated", "webhook.test"]

    listed = (await client.get("/api/v1/webhooks", headers=headers)).json()
    assert listed["total"] == 1

    test_hit = await client.post(
        f"/api/v1/webhooks/{endpoint['id']}/test", json={"ping": True}, headers=headers
    )
    assert test_hit.status_code == 200
    assert test_hit.json()["signature"]
    assert test_hit.json()["event"] == "webhook.test"

    deliveries = (await client.get("/api/v1/webhooks/deliveries", headers=headers)).json()
    assert deliveries["total"] == 0

    paused = await client.patch(
        f"/api/v1/webhooks/{endpoint['id']}/status", json={"status": "paused"}, headers=headers
    )
    assert paused.json()["status"] == "paused"

    bad_status = await client.patch(
        f"/api/v1/webhooks/{endpoint['id']}/status", json={"status": "exploded"}, headers=headers
    )
    assert bad_status.status_code == 422

    deleted = await client.delete(f"/api/v1/webhooks/{endpoint['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    missing = await client.delete("/api/v1/webhooks/nope", headers=headers)
    assert missing.status_code == 404


async def test_marketplace_listing_install_review(client):
    org = await register_org(client, email="p18mkt@test.co")
    headers = org["headers"]
    await _register_developer(client, headers, email="vendor@test.co", name="Vendor Labs")

    app = (
        await client.post(
            "/api/v1/developers/me/applications",
            json={"name": "Churn Predictor", "app_type": "plugin", "description": "AI churn plugin"},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/developers/me/applications/{app['id']}/publish", headers=headers)

    listing = await client.post(
        "/api/v1/marketplace/listings",
        json={"application_id": app["id"], "name": "Churn Predictor",
              "category": "analytics", "price": 19.99,
              "description": "Predict customer churn with AI"},
        headers=headers,
    )
    assert listing.status_code == 200, listing.text
    item = listing.json()
    assert item["plugin_key"] == app["application_key"]
    assert item["published"] is True
    assert item["downloads"] == 0

    browse = (await client.get("/api/v1/marketplace/listings?category=analytics", headers=headers)).json()
    assert browse["total"] >= 1

    installed = await client.post(
        "/api/v1/marketplace/install",
        json={"item_id": item["id"], "as_agent": True},
        headers=headers,
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["status"] == "installed"

    refreshed = (await client.get(f"/api/v1/marketplace/listings/{item['id']}", headers=headers)).json()
    assert refreshed["downloads"] == 1

    installed_list = (await client.get("/api/v1/marketplace/installed", headers=headers)).json()
    assert installed_list["total"] >= 1

    agents = (await client.get("/api/v1/agents", headers=headers)).json()
    assert any(a["agent_key"] == item["plugin_key"] for a in agents["agents"])

    reviewed = await client.post(
        "/api/v1/marketplace/reviews",
        json={"item_id": item["id"], "rating": 5, "comment": "Fantastic"},
        headers=headers,
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["rating"] == 5

    after = (await client.get(f"/api/v1/marketplace/listings/{item['id']}", headers=headers)).json()
    assert after["rating"] == 5.0
    assert after["review_count"] == 1

    reviews = (await client.get(f"/api/v1/marketplace/listings/{item['id']}/reviews", headers=headers)).json()
    assert reviews["total"] == 1

    names = await _event_names(client, headers)
    assert "marketplace.installed" in names


async def test_themes_crud_and_activation(client):
    org = await register_org(client, email="p18theme@test.co")
    headers = org["headers"]

    first = await client.post(
        "/api/v1/themes",
        json={"name": "Dark Ops", "config": {"colors": {"primary": "#0f0f0f"}}, "activate": True},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["active"] is True

    second = await client.post(
        "/api/v1/themes",
        json={"name": "Light Air", "config": {"colors": {"primary": "#ffffff"}}},
        headers=headers,
    )
    assert second.json()["active"] is False

    activated = await client.post(f"/api/v1/themes/{second.json()['id']}/activate", headers=headers)
    assert activated.json()["active"] is True

    listed = (await client.get("/api/v1/themes", headers=headers)).json()
    assert listed["total"] == 2
    assert sum(1 for t in listed["themes"] if t["active"]) == 1

    updated = await client.patch(
        f"/api/v1/themes/{second.json()['id']}",
        json={"name": "Light Air v2", "config": {"colors": {"primary": "#fefefe"}}},
        headers=headers,
    )
    assert updated.json()["name"] == "Light Air v2"

    deleted = await client.delete(f"/api/v1/themes/{first.json()['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    missing = await client.delete("/api/v1/themes/nope", headers=headers)
    assert missing.status_code == 404


async def test_developers_rbac_and_search(client):
    org = await register_org(client, email="p18dev6@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "p18deve@test.co", role="employee")
    await _register_developer(client, headers, email="maker@test.co", name="Maker Studio")

    app = (
        await client.post(
            "/api/v1/developers/me/applications",
            json={"name": "Revenue Bot", "app_type": "agent"},
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/developers/me/applications/{app['id']}/publish", headers=headers)

    await client.post(
        "/api/v1/agents",
        json={"name": "Revenue Agent", "role": "sales", "capabilities": ["pipeline"]},
        headers=headers,
    )

    employee_denied_manage = await client.post("/api/v1/agents", json={"name": "X"}, headers=employee["headers"])
    assert employee_denied_manage.status_code == 403

    employee_denied_hooks = await client.post(
        "/api/v1/webhooks", json={"name": "X", "url": "https://x.test"}, headers=employee["headers"]
    )
    assert employee_denied_hooks.status_code == 403

    employee_denied_marketplace = await client.get(
        "/api/v1/marketplace/listings", headers=employee["headers"]
    )
    assert employee_denied_marketplace.status_code == 403

    employee_denied_apps = await client.post(
        "/api/v1/developers/me/applications", json={"name": "Sneaky", "app_type": "app"},
        headers=employee["headers"],
    )
    assert employee_denied_apps.status_code == 404

    results = (await client.get("/api/v1/search?q=revenue", headers=headers)).json()["results"]
    types = {r["type"] for r in results}
    assert "developer_app" in types
    assert "agent" in types

    other = await register_org(client, email="p18dev7@test.co", slug="p18-other")
    other_agents = (await client.get("/api/v1/agents", headers=other["headers"])).json()
    assert other_agents["total"] == 0
