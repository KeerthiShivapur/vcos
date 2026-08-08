"""Phase 8 — Executive Intelligence & Company Digital Twin tests.

Covers the executive dashboard, company health engine, strategic risks,
recommendations, digital twin + organization memory, timeline, trends,
predictions, simulations, executive reports, strategy goals/plan/ask,
RBAC gating and multi-tenant isolation.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _seed_project(client, headers, *, code, title="Nebula Prime", overdue=False, status="active"):
    me = await _employee_id(client, headers)
    project = await client.post(
        "/api/v1/projects",
        json={"name": title, "code": code, "owner_id": me, "status": status,
              "end_date": "2020-01-01" if overdue else None},
        headers=headers,
    )
    assert project.status_code == 201, project.text
    pid = project.json()["id"]
    task = await client.post(
        "/api/v1/tasks",
        json={
            "project_id": pid,
            "title": "Core deliverable",
            "assignee_id": me,
            "estimate_hours": 8,
            "due_date": "2020-01-01" if overdue else None,
        },
        headers=headers,
    )
    assert task.status_code == 201, task.text
    return pid


async def _invite_employee(client, headers, email):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Emp Worker", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Worker", "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


@pytest.mark.asyncio
async def test_executive_dashboard_refresh(client):
    org = await register_org(client, email="exec@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="EX-1", overdue=True)

    response = await client.get("/api/v1/executive/dashboard?refresh=true", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "summary" in data and data["summary"]
    assert "attention" in data
    assert data["attention"]["critical_risks"] >= 0
    health = data["health"]
    assert 0 <= health["score"] <= 100
    assert health["status"] in ("excellent", "good", "watch", "at_risk")
    assert isinstance(data["risks"], list)
    assert isinstance(data["recommendations"], list)
    assert data["digital_twin"]["employees_active"] >= 1
    assert isinstance(data["executive_calendar"], list)
    assert isinstance(data["recent_decisions"], list)
    assert isinstance(data["recent_activity"], list)
    assert "strategy" in data


@pytest.mark.asyncio
async def test_company_health_endpoint(client):
    org = await register_org(client, email="health@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="HL-1")

    response = await client.get("/api/v1/executive/health", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert 0 <= data["score"] <= 100
    assert data["status"] in ("excellent", "good", "watch", "at_risk")
    for dim in ("project_execution", "task_completion", "knowledge_growth",
                "employee_workload", "community_engagement", "innovation",
                "policy_compliance", "risk_management", "goals"):
        assert dim in data["breakdown"], data["breakdown"].keys()


@pytest.mark.asyncio
async def test_department_health(client):
    org = await register_org(client, email="dept@work.test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/departments",
        json={"name": "Platform Engineering", "code": "platform-eng"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    dept_id = created.json()["id"]

    response = await client.get("/api/v1/executive/health/departments", headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()["departments"]
    assert any(r["department_id"] == dept_id for r in rows)
    assert all(0 <= r["health"] <= 100 for r in rows)

    single = await client.get(
        f"/api/v1/executive/health/departments/{dept_id}", headers=headers
    )
    assert single.status_code == 200, single.text
    assert single.json()["department_id"] == dept_id


@pytest.mark.asyncio
async def test_strategic_risks_detection_and_status(client):
    org = await register_org(client, email="risk@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="RK-1", overdue=True)

    response = await client.get("/api/v1/executive/risks?refresh=true", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] > 0, data

    risk = next((r for r in data["risks"] if r["level"] in ("high", "critical")), data["risks"][0])
    assert risk["kind"]
    assert risk["description"] and risk["evidence"]
    assert 0 <= risk["score"] <= 1

    patched = await client.patch(
        f"/api/v1/executive/risks/{risk['id']}/status",
        json={"status": "accepted"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "accepted"

    detail = await client.get(f"/api/v1/executive/risks/{risk['id']}", headers=headers)
    assert detail.status_code == 200, detail.text


@pytest.mark.asyncio
async def test_recommendations_refresh_and_accept(client):
    org = await register_org(client, email="rec@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="RC-1", overdue=True)

    response = await client.get("/api/v1/executive/recommendations?refresh=true", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] > 0, data

    for rec in data["recommendations"]:
        assert rec["rationale"]
        assert rec["expected_outcome"]
        assert rec["kind"] in ("hire", "assign", "document", "reduce_meetings",
                               "review", "testing", "risk_review")

    patched = await client.patch(
        f"/api/v1/executive/recommendations/{data['recommendations'][0]['id']}/status",
        json={"status": "accepted"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text


@pytest.mark.asyncio
async def test_simulations_run_list_and_get(client):
    org = await register_org(client, email="sim@work.test.co")
    headers = org["headers"]

    scenarios = await client.get("/api/v1/executive/simulations/scenarios/list", headers=headers)
    assert scenarios.status_code == 200, scenarios.text
    assert "hire_engineers" in scenarios.json()["scenarios"]

    ran = await client.post(
        "/api/v1/executive/simulations",
        json={"scenario": "hire_engineers", "params": {"count": 3}},
        headers=headers,
    )
    assert ran.status_code == 200, ran.text
    sim = ran.json()
    assert sim["scenario"] == "hire_engineers"
    assert isinstance(sim["assumptions"], list) and sim["assumptions"]
    assert "workload_relief_percent" in sim["results"], sim["results"].keys()

    listing = await client.get("/api/v1/executive/simulations", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] >= 1

    fetched = await client.get(f"/api/v1/executive/simulations/{sim['id']}", headers=headers)
    assert fetched.status_code == 200, fetched.text


@pytest.mark.asyncio
async def test_predictions_refresh(client):
    org = await register_org(client, email="pred@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="PR-1", overdue=True)

    response = await client.get("/api/v1/executive/predictions?refresh=true", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] > 0, data

    metrics = {p["metric"] for p in data["predictions"]}
    assert {"project_miss", "hiring_need", "turnover_risk", "knowledge_growth",
            "meeting_effectiveness", "innovation_momentum"} & metrics
    for p in data["predictions"]:
        assert p["level"] in ("high", "medium", "low")
        assert "rationale" in p


@pytest.mark.asyncio
async def test_report_generation_and_listing(client):
    org = await register_org(client, email="rep@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="RP-1")

    types = await client.get("/api/v1/executive/reports/types", headers=headers)
    assert types.status_code == 200, types.text
    assert "weekly" in types.json()["report_types"]

    generated = await client.post(
        "/api/v1/executive/reports",
        json={"report_type": "weekly"},
        headers=headers,
    )
    assert generated.status_code == 200, generated.text
    report = generated.json()
    assert report["report_type"] == "weekly"
    assert "content" in report and "Executive Summary" in report["content"]

    listing = await client.get("/api/v1/executive/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] >= 1


@pytest.mark.asyncio
async def test_strategy_goals_plan_ask(client):
    org = await register_org(client, email="strat@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="ST-1", overdue=True)

    created = await client.post(
        "/api/v1/executive/strategy/goals",
        json={"name": "Ship Nebula 2.0", "focus": "growth", "timeframe": "quarter"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    goal_id = created.json()["id"]

    listed = await client.get("/api/v1/executive/strategy/goals", headers=headers)
    assert listed.status_code == 200
    assert any(g["id"] == goal_id for g in listed.json()["goals"])

    updated = await client.patch(
        f"/api/v1/executive/strategy/goals/{goal_id}",
        json={"status": "active", "progress": 40},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "active"
    assert updated.json()["progress"] == 40

    plan = await client.post(
        "/api/v1/executive/strategy/plan?horizon=quarter", json={}, headers=headers
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["horizon"] == "quarter"
    assert plan.json()["priorities"]

    risks = await client.post(
        "/api/v1/executive/strategy/ask",
        json={"question": "Show me the biggest risks right now"},
        headers=headers,
    )
    assert risks.status_code == 200, risks.text
    assert risks.json()["kind"] == "risks"
    assert risks.json()["answer"]

    board = await client.post(
        "/api/v1/executive/strategy/ask",
        json={"question": "Prepare a board meeting summary"},
        headers=headers,
    )
    assert board.status_code == 200, board.text
    assert board.json()["kind"] == "report"


@pytest.mark.asyncio
async def test_digital_twin_and_organization_memory(client):
    org = await register_org(client, email="twin@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="TW-1")

    twin = await client.get("/api/v1/executive/twin", headers=headers)
    assert twin.status_code == 200, twin.text
    assert twin.json()["entity_counts"]["employees_active"] >= 1
    assert twin.json()["entity_counts"]["projects"] >= 1
    assert twin.json()["twin"]["graph"]["nodes"] >= 1

    decision = await client.post(
        "/api/v1/decisions",
        json={"title": "Quantum leap hiring for Q3", "context": "Scale engineering"},
        headers=headers,
    )
    assert decision.status_code in (200, 201), decision.text

    memory = await client.post(
        "/api/v1/executive/twin/search-memory",
        json={"query": "quantum", "limit": 5},
        headers=headers,
    )
    assert memory.status_code == 200, memory.text
    sources = memory.json()["results"]
    assert any(m["source"] == "decision" and "quantum" in (m.get("name") or "").lower()
               for m in sources), sources


@pytest.mark.asyncio
async def test_snapshot_and_timeline(client):
    org = await register_org(client, email="snap@work.test.co")
    headers = org["headers"]

    snapshot = await client.get("/api/v1/executive/snapshot?persist=true", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["entity_counts"]["employees_active"] >= 1

    timeline = await client.get("/api/v1/executive/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    entries = timeline.json()["entries"]
    assert entries, entries
    sources = {e["source"] for e in entries}
    assert "audit" in sources or "event" in sources, sources


@pytest.mark.asyncio
async def test_analytics_trends_and_metrics(client):
    org = await register_org(client, email="trend@work.test.co")
    headers = org["headers"]
    await _seed_project(client, headers, code="TR-1")

    trends = await client.get("/api/v1/executive/analytics/trends?period=weekly", headers=headers)
    assert trends.status_code == 200, trends.text
    series = {t["metric"]: t for t in trends.json()["trends"]}
    assert "tasks_created" in series, list(series.keys())
    assert series["tasks_created"]["last"] >= 1
    assert "direction" in series["tasks_created"]

    metrics = await client.get("/api/v1/executive/analytics/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["total"] >= 1


@pytest.mark.asyncio
async def test_executive_rbac_employee_denied(client):
    org = await register_org(client, email="rbac@work.test.co")
    headers = org["headers"]
    emp_headers = await _invite_employee(client, headers, "emp@rbac.test.co")

    blocked = await client.get("/api/v1/executive/dashboard", headers=emp_headers)
    assert blocked.status_code == 403, blocked.text

    blocked_sim = await client.post(
        "/api/v1/executive/simulations",
        json={"scenario": "hire_engineers", "params": {"count": 1}},
        headers=emp_headers,
    )
    assert blocked_sim.status_code == 403, blocked_sim.text

    no_auth = await client.get("/api/v1/executive/dashboard")
    assert no_auth.status_code == 401


@pytest.mark.asyncio
async def test_executive_tenancy_isolation(client):
    org_a = await register_org(client, email="tena@work.test.co")
    headers_a = org_a["headers"]
    await _seed_project(client, headers_a, code="TEN-A", title="TEN-A Flagship", overdue=True)

    org_b = await register_org(client, email="tenb@work.test.co", slug="tenant-b-isolated")
    headers_b = org_b["headers"]

    risks_a = await client.get("/api/v1/executive/risks?refresh=true", headers=headers_a)
    risks_b = await client.get("/api/v1/executive/risks?refresh=true", headers=headers_b)
    assert risks_a.status_code == risks_b.status_code == 200

    names_a = {r["subject_name"] for r in risks_a.json()["risks"]}
    names_b = {r["subject_name"] for r in risks_b.json()["risks"]}
    assert "TEN-A" in names_a or any("TEN-A" in (n or "") for n in names_a)
    assert not any("TEN-A" in (n or "") for n in names_b), names_b
