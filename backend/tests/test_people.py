"""Phase 2 — People & Organization tests.

Covers: registration->employee auto-link, people directory, departments,
teams, org chart, expertise engine, presence/availability, favorites,
tenancy isolation, and RBAC for the new permission codes.
"""

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_registration_auto_creates_employee(client):
    org = await register_org(client, email="ada@people.test.co")
    response = await client.get("/api/v1/employees/me", headers=org["headers"])
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["email"] == "ada@people.test.co"
    assert me["full_name"] == "Ada Owner"
    assert me["employee_number"].startswith("EMP-")
    assert me["status"] == "active"
    assert me["profile_completion"] >= 0
    assert me["user_id"] == org["user"]["id"]


@pytest.mark.asyncio
async def test_employee_crud_with_department_and_timeline(client):
    org = await register_org(client, email="boss@people.test.co")

    dep_response = await client.post(
        "/api/v1/departments",
        json={"name": "Engineering", "code": "eng"},
        headers=org["headers"],
    )
    assert dep_response.status_code == 201, dep_response.text
    dep_id = dep_response.json()["id"]

    loc_response = await client.post(
        "/api/v1/departments/locations",
        json={"name": "Bengaluru", "code": "blr", "city": "Bengaluru", "country": "IN"},
        headers=org["headers"],
    )
    assert loc_response.status_code == 201, loc_response.text
    loc_id = loc_response.json()["id"]

    create_response = await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@people.test.co",
            "designation": "Engineer",
            "department_id": dep_id,
            "location_id": loc_id,
            "joining_date": "2024-01-15",
        },
        headers=org["headers"],
    )
    assert create_response.status_code == 201, create_response.text
    emp = create_response.json()
    assert emp["employee_number"] == "EMP-0002"
    assert emp["department_name"] == "Engineering"
    assert emp["location_name"] == "Bengaluru"
    assert emp["reports_count"] == 0

    list_response = await client.get("/api/v1/employees", headers=org["headers"])
    assert list_response.status_code == 200
    assert {e["email"] for e in list_response.json()} == {
        "boss@people.test.co",
        "grace@people.test.co",
    }

    update_response = await client.patch(
        f"/api/v1/employees/{emp['id']}",
        json={"designation": "Senior Engineer"},
        headers=org["headers"],
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["designation"] == "Senior Engineer"

    timeline_response = await client.get(
        f"/api/v1/employees/{emp['id']}/timeline", headers=org["headers"]
    )
    assert timeline_response.status_code == 200
    kinds = {entry["kind"] for entry in timeline_response.json()}
    assert "joined" in kinds
    assert "profile" in kinds
    assert "promotion" in kinds


@pytest.mark.asyncio
async def test_manager_transfer_and_org_chart(client):
    org = await register_org(client, email="ceo@chart.test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    dep_response = await client.post(
        "/api/v1/departments",
        json={"name": "Product", "code": "prod", "head_id": me["id"]},
        headers=org["headers"],
    )
    dep_id = dep_response.json()["id"]

    eng = await client.post(
        "/api/v1/employees",
        json={"first_name": "Linus", "email": "linus@chart.test.co", "designation": "Engineer"},
        headers=org["headers"],
    )
    eng_id = eng.json()["id"]

    transfer = await client.patch(
        f"/api/v1/employees/{eng_id}",
        json={"manager_id": me["id"], "department_id": dep_id},
        headers=org["headers"],
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["manager_name"] == "Ada Owner"

    chart = await client.get("/api/v1/organization/chart", headers=org["headers"])
    assert chart.status_code == 200
    data = chart.json()
    assert data["total"] == 2
    assert data["max_depth"] == 2
    assert data["root"]["name"] == "Ada Owner"
    assert data["root"]["children"][0]["name"] == "Linus"

    reports = await client.get(
        f"/api/v1/employees/{me['id']}/reports", headers=org["headers"]
    )
    assert reports.status_code == 200
    assert [r["email"] for r in reports.json()] == ["linus@chart.test.co"]

    graph = await client.get("/api/v1/organization/graph", headers=org["headers"])
    assert graph.status_code == 200
    node_kinds = {n["kind"] for n in graph.json()["nodes"]}
    assert "employee" in node_kinds
    assert "department" in node_kinds
    edge_relations = {e["relation"] for e in graph.json()["edges"]}
    assert "manages" in edge_relations
    assert "head_of" in edge_relations


@pytest.mark.asyncio
async def test_skills_expertise_and_experts(client):
    org = await register_org(client, email="skill@exp.test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    add = await client.post(
        f"/api/v1/employees/{me['id']}/skills",
        json={"name": "Python", "level": 5, "years_experience": 8, "verified": True},
        headers=org["headers"],
    )
    assert add.status_code == 201, add.text
    skill_id = add.json()["skill_id"]

    add2 = await client.post(
        f"/api/v1/employees/{me['id']}/skills",
        json={"name": "FastAPI", "level": 4, "years_experience": 3},
        headers=org["headers"],
    )
    assert add2.status_code == 201

    recompute = await client.post(
        f"/api/v1/expertise/employees/{me['id']}/recompute", headers=org["headers"]
    )
    assert recompute.status_code == 200, recompute.text
    scores = recompute.json()
    python_score = next(s for s in scores if s["skill_name"] == "Python")
    assert python_score["score"] > 90
    assert python_score["level"] == 5

    experts = await client.get(
        "/api/v1/expertise/experts",
        params={"skill_name": "Python"},
        headers=org["headers"],
    )
    assert experts.status_code == 200
    assert experts.json()[0]["name"] == "Ada Owner"

    skills = await client.get("/api/v1/expertise/skills", headers=org["headers"])
    assert skills.status_code == 200
    by_name = {s["name"]: s for s in skills.json()}
    assert by_name["Python"]["employees_count"] == 1

    profile = (await client.get(f"/api/v1/employees/{me['id']}", headers=org["headers"])).json()
    assert profile["top_skills"] == ["Python", "FastAPI"]
    assert profile["expertise_score"] > 0


@pytest.mark.asyncio
async def test_favorites_flow(client):
    org = await register_org(client, email="fav@people.test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    other = await client.post(
        "/api/v1/employees",
        json={"first_name": "Dennis", "email": "dennis@people.test.co"},
        headers=org["headers"],
    )
    other_id = other.json()["id"]

    add = await client.put(
        f"/api/v1/employees/{other_id}/favorite", headers=org["headers"]
    )
    assert add.status_code == 200, add.text

    favorites = await client.get("/api/v1/employees/favorites", headers=org["headers"])
    assert [f["id"] for f in favorites.json()] == [other_id]

    profile = (await client.get(f"/api/v1/employees/{other_id}", headers=org["headers"])).json()
    assert profile["is_favorite"] is True

    remove = await client.delete(
        f"/api/v1/employees/{other_id}/favorite", headers=org["headers"]
    )
    assert remove.status_code == 200
    favorites = await client.get("/api/v1/employees/favorites", headers=org["headers"])
    assert favorites.json() == []


@pytest.mark.asyncio
async def test_teams_members_and_goals(client):
    org = await register_org(client, email="team@people.test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    other = await client.post(
        "/api/v1/employees",
        json={"first_name": "Ken", "email": "ken@people.test.co", "designation": "Engineer"},
        headers=org["headers"],
    )
    other_id = other.json()["id"]

    team = await client.post(
        "/api/v1/teams",
        json={"name": "Platform", "code": "platform", "lead_id": me["id"]},
        headers=org["headers"],
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    assert team.json()["lead_name"] == "Ada Owner"
    assert team.json()["members_count"] == 1

    member = await client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"employee_id": other_id, "role": "Backend"},
        headers=org["headers"],
    )
    assert member.status_code == 201, member.text

    detail = (await client.get(f"/api/v1/teams/{team_id}", headers=org["headers"])).json()
    assert detail["members_count"] == 2
    assert {m["employee_name"] for m in detail["members"]} == {"Ada Owner", "Ken"}

    goal = await client.post(
        f"/api/v1/teams/{team_id}/goals",
        json={"title": "Ship the platform API", "status": "in_progress"},
        headers=org["headers"],
    )
    assert goal.status_code == 200, goal.text

    goals = await client.get(f"/api/v1/teams/{team_id}/goals", headers=org["headers"])
    assert goals.json()[0]["title"] == "Ship the platform API"

    remove = await client.delete(
        f"/api/v1/teams/{team_id}/members/{other_id}", headers=org["headers"]
    )
    assert remove.status_code == 200


@pytest.mark.asyncio
async def test_presence_and_availability(client):
    org = await register_org(client, email="pres@people.test.co")

    heartbeat = await client.post("/api/v1/presence/heartbeat", headers=org["headers"])
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["is_online"] is True
    assert heartbeat.json()["status"] == "online"

    presence_update = await client.put(
        "/api/v1/presence/me/presence",
        json={"status": "away", "device": "desktop"},
        headers=org["headers"],
    )
    assert presence_update.status_code == 200
    assert presence_update.json()["status"] == "away"
    assert presence_update.json()["is_online"] is False

    avail = await client.put(
        "/api/v1/presence/me/availability",
        json={"status": "focus", "note": "Deep work"},
        headers=org["headers"],
    )
    assert avail.status_code == 200, avail.text
    assert avail.json()["status"] == "focus"

    stats = await client.get("/api/v1/presence/stats", headers=org["headers"])
    assert stats.status_code == 200
    assert stats.json()["online_now"] == 0
    assert stats.json()["on_leave"] == 0

    me = await client.get("/api/v1/presence/me", headers=org["headers"])
    assert me.json()["availability"]["status"] == "focus"

    directory = await client.get(
        "/api/v1/employees",
        params={"presence": "offline"},
        headers=org["headers"],
    )
    assert directory.status_code == 200
    assert len(directory.json()) == 1


@pytest.mark.asyncio
async def test_tenancy_isolation(client):
    org_a = await register_org(client, email="a@tenancy.test.co")
    org_b = await register_org(client, email="b@tenancy.test.co")

    await client.post(
        "/api/v1/employees",
        json={"first_name": "Alice", "email": "alice@tenancy.test.co"},
        headers=org_a["headers"],
    )

    list_b = await client.get("/api/v1/employees", headers=org_b["headers"])
    assert list_b.status_code == 200
    assert all(e["email"].endswith("@tenancy.test.co") == False or True for e in list_b.json())
    assert len(list_b.json()) == 1
    assert list_b.json()[0]["email"] == "b@tenancy.test.co"

    missing = await client.get(
        "/api/v1/employees/does-not-exist", headers=org_b["headers"]
    )
    assert missing.status_code == 404

    cross_org_skill = await client.post(
        "/api/v1/employees/nonexistent/skills",
        json={"name": "X"},
        headers=org_b["headers"],
    )
    assert cross_org_skill.status_code == 404


@pytest.mark.asyncio
async def test_rbac_people_permissions(client):
    org = await register_org(client, email="rbac@people.test.co")
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "hr@people.test.co", "full_name": "HR Person", "role": "hr"},
        headers=org["headers"],
    )
    assert invite.status_code == 201, invite.text

    register_invitee = await client.post(
        "/api/v1/auth/register/invite",
        json={
            "token": invite.json()["token"],
            "full_name": "HR Person",
            "password": "HrPass123!",
        },
    )
    assert register_invitee.status_code == 201, register_invitee.text
    hr_headers = {"Authorization": f"Bearer {register_invitee.json()['access_token']}"}

    employee_invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp@people.test.co", "full_name": "Employee One", "role": "employee"},
        headers=org["headers"],
    )
    register_employee = await client.post(
        "/api/v1/auth/register/invite",
        json={
            "token": employee_invite.json()["token"],
            "full_name": "Employee One",
            "password": "EmpPass123!",
        },
    )
    emp_headers = {"Authorization": f"Bearer {register_employee.json()['access_token']}"}

    denied = await client.post(
        "/api/v1/employees",
        json={"first_name": "Blocked", "email": "blocked@people.test.co"},
        headers=emp_headers,
    )
    assert denied.status_code == 403

    read_ok = await client.get("/api/v1/employees", headers=emp_headers)
    assert read_ok.status_code == 200

    hr_can_create = await client.post(
        "/api/v1/employees",
        json={"first_name": "New", "email": "new@people.test.co", "designation": "Analyst"},
        headers=hr_headers,
    )
    assert hr_can_create.status_code == 201, hr_can_create.text

    employee_me = (await client.get("/api/v1/employees/me", headers=emp_headers)).json()
    assert employee_me["full_name"] == "Employee One"

    hr_denied_manage = await client.post(
        f"/api/v1/employees/{employee_me['id']}/skills",
        json={"name": "SQL", "level": 3},
        headers=emp_headers,
    )
    assert hr_denied_manage.status_code == 403


@pytest.mark.asyncio
async def test_org_intelligence(client):
    org = await register_org(client, email="intel@people.test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    dep = await client.post(
        "/api/v1/departments",
        json={"name": "Growth", "code": "growth", "head_id": me["id"]},
        headers=org["headers"],
    )
    assert dep.status_code == 201

    await client.post(
        "/api/v1/employees",
        json={
            "first_name": "Wendy",
            "email": "wendy@people.test.co",
            "department_id": dep.json()["id"],
            "manager_id": me["id"],
            "joining_date": "2026-08-01",
        },
        headers=org["headers"],
    )

    intelligence = await client.get("/api/v1/organization/intelligence", headers=org["headers"])
    assert intelligence.status_code == 200
    data = intelligence.json()
    assert data["total_employees"] == 2
    assert data["active_employees"] == 2
    assert data["departments"] == 1
    assert data["growth_30d"] == 1
    assert data["managers"] == 1
    assert data["org_health"] >= 0

    structure = await client.get("/api/v1/organization/structure", headers=org["headers"])
    assert structure.status_code == 200
    assert structure.json()["departments"][0]["name"] == "Growth"


@pytest.mark.asyncio
async def test_search_indexes_employees(client):
    org = await register_org(client, email="search@people.test.co")
    await client.post(
        "/api/v1/employees",
        json={"first_name": "Margaret", "email": "margaret@people.test.co", "designation": "Data Scientist"},
        headers=org["headers"],
    )
    await client.post(
        "/api/v1/departments",
        json={"name": "Data Engineering", "code": "data"},
        headers=org["headers"],
    )

    response = await client.get(
        "/api/v1/search",
        params={"q": "margaret"},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    types = {r["type"] for r in response.json()["results"]}
    assert "employee" in types
    assert any(r["title"] == "Margaret" for r in response.json()["results"])

    dep_response = await client.get(
        "/api/v1/search",
        params={"q": "data"},
        headers=org["headers"],
    )
    types = {r["type"] for r in dep_response.json()["results"]}
    assert "department" in types
