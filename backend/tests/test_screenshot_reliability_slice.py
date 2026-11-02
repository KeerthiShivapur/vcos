"""Screenshot-driven product reliability slice (P0 regression suite).

Reproduces the defects observed in the live session and locks the fixes:

- My Day 500: Task.due_at lookup, employee.job_title, getMyWorkload import
- Company Home 500: CompanyGoal import + CompanyObjective field mapping
- Learning 500s: route/service filter drift (search/category/limit/department)
- Learning dashboard: profile ensure idempotency (uq_learning_profile_employee)
- Enterprise security rules: event_types contract (dict -> sorted string list)
- Feature flags: canonical /feature-flags router path + evaluate contract
"""

import uuid

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_my_day_returns_200_with_task_and_workload(client):
    org = await register_org(client, email=f"mday-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Day Project", "code": f"DAY-{uuid.uuid4().hex[:6]}", "owner_id": me},
        headers=headers,
    )
    assert project.status_code in (200, 201), project.text
    project_id = project.json()["id"]

    task = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Reliability slice task",
            "project_id": project_id,
            "assignee_id": me,
            "due_date": "2026-10-20",
        },
        headers=headers,
    )
    assert task.status_code in (200, 201), task.text
    task_id = task.json()["id"]

    resp = await client.get("/api/v1/workspace/my-day", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["id"] == me
    task_row = next(t for t in data["tasks"] if t["id"] == task_id)
    assert task_row["due_at"].startswith("2026-10-20")
    assert "utilization" in data["capacity_context"]


@pytest.mark.asyncio
async def test_my_day_isolates_tenants(client):
    org_a = await register_org(client, email=f"iso-a-{uuid.uuid4().hex[:8]}@acme.test.co")
    org_b = await register_org(client, email=f"iso-b-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers_a, headers_b = org_a["headers"], org_b["headers"]
    me_a = (await client.get("/api/v1/employees/me", headers=headers_a)).json()["id"]

    project = await client.post(
        "/api/v1/projects",
        json={"name": "A Project", "code": f"AP-{uuid.uuid4().hex[:6]}", "owner_id": me_a},
        headers=headers_a,
    )
    assert project.status_code in (200, 201), project.text
    project_id = project.json()["id"]

    task = await client.post(
        "/api/v1/tasks",
        json={"title": "A-only task", "project_id": project_id, "assignee_id": me_a},
        headers=headers_a,
    )
    assert task.status_code in (200, 201), task.text
    task_id = task.json()["id"]

    resp_b = await client.get("/api/v1/workspace/my-day", headers=headers_b)
    assert resp_b.status_code == 200, resp_b.text
    assert task_id not in [t["id"] for t in resp_b.json()["tasks"]]


@pytest.mark.asyncio
async def test_company_home_returns_200_and_maps_objective_progress(client, db_session):
    org = await register_org(client, email=f"home-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    from app.models.execution_strategy import CompanyGoal, CompanyObjective

    goal = CompanyGoal(
        organization_id=org_id,
        title="Grow ARR",
        kind="growth",
        status="active",
    )
    db_session.add(goal)
    await db_session.flush()

    objective = CompanyObjective(
        organization_id=org_id,
        goal_id=goal.id,
        title="Reach 100 customers",
        status="active",
        current_value=40.0,
        target_value=100.0,
        fingerprint=f"fp-{uuid.uuid4().hex}",
    )
    db_session.add(objective)
    await db_session.commit()

    resp = await client.get("/api/v1/workspace/company-home", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["objectives"], list)
    row = next(o for o in data["objectives"] if o["id"] == objective.id)
    assert row["state"] == "active"
    assert row["progress"] == 40.0
    assert row["target_date"] is None


@pytest.mark.asyncio
async def test_manager_workspace_returns_capacity_projects_and_commitments(client, db_session):
    org = await register_org(client, email=f"mgr-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]

    from app.models.project import Project
    from app.models.team import Team, TeamMember

    team = Team(
        organization_id=org_id,
        name="Delivery",
        code=f"DEL-{uuid.uuid4().hex[:6]}",
        description="Ships the product",
    )
    db_session.add(team)
    await db_session.flush()

    db_session.add(
        TeamMember(
            organization_id=org_id, team_id=team.id, employee_id=me, role="manager"
        )
    )
    db_session.add(
        Project(
            organization_id=org_id,
            code=f"MGR-{uuid.uuid4().hex[:6]}",
            name="Team Project",
            status="active",
            team_id=team.id,
            owner_id=me,
        )
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/workspace/manager/{team.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["team"]["id"] == team.id
    assert "utilization" in data["capacity"]
    assert any(p["state"] == "active" for p in data["projects"])
    assert isinstance(data["commitments"], list)
    assert isinstance(data["communication"], dict)


@pytest.mark.asyncio
async def test_learning_list_endpoints_accept_filters(client):
    org = await register_org(client, email=f"learn-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]

    for url in (
        "/api/v1/learning/paths?search=lead&limit=10",
        "/api/v1/learning/assessments?category=quiz&limit=10",
        "/api/v1/learning/certifications?limit=10",
        "/api/v1/learning/career?department=engineering",
    ):
        resp = await client.get(url, headers=headers)
        assert resp.status_code == 200, f"{url}: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_learning_dashboard_profile_is_idempotent(client):
    org = await register_org(client, email=f"dash-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]

    first = await client.get("/api/v1/learning/dashboard", headers=headers)
    assert first.status_code == 200, first.text
    second = await client.get("/api/v1/learning/dashboard", headers=headers)
    assert second.status_code == 200, second.text


@pytest.mark.asyncio
async def test_ensure_profile_recovers_when_row_already_exists(client, db_session_factory):
    org = await register_org(client, email=f"prof-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    org_id = org["organization"]["id"]

    from app.learning.profile_service import profile_service

    async with db_session_factory() as s1:
        p1 = await profile_service.ensure_profile(s1, organization_id=org_id, employee_id=me)
        await s1.commit()
    async with db_session_factory() as s2:
        p2 = await profile_service.ensure_profile(s2, organization_id=org_id, employee_id=me)
        await s2.commit()
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_security_rules_event_types_is_sorted_string_list(client):
    org = await register_org(client, email=f"sec-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]

    resp = await client.get("/api/v1/enterprise/security/rules", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["event_types"], list)
    assert all(isinstance(x, str) for x in data["event_types"])
    assert data["event_types"] == sorted(data["event_types"])
    assert data["brute_force_threshold"] == 5


@pytest.mark.asyncio
async def test_feature_flags_canonical_router_and_evaluate_contract(client):
    org = await register_org(client, email=f"ff-{uuid.uuid4().hex[:8]}@acme.test.co")
    headers = org["headers"]

    listing = await client.get("/api/v1/feature-flags", headers=headers)
    assert listing.status_code == 200, listing.text
    assert isinstance(listing.json(), list)

    created = await client.post(
        "/api/v1/feature-flags",
        json={
            "key": f"slice-{uuid.uuid4().hex[:8]}",
            "name": "Slice Flag",
            "description": "regression",
            "status": "enabled",
        },
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    key = created.json()["key"]

    evaluated = await client.post(
        "/api/v1/feature-flags/evaluate",
        json={"key": key, "actor_roles": ["admin"]},
        headers=headers,
    )
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["flag_key"] == key
    assert isinstance(body["available"], bool)
    assert "reason" in body
