"""Vertical Slice 3 — Step 2 security/integrity regression tests.

Covers the org-mutation vector on raw PATCH routes (1-4), FK revalidation
on update paths (5-8), risk list_all severity/limit filters (9-10), meeting
employee filter pushed into SQL (11-12), and task transition/input hardening
(13-14).
"""

import pytest

from tests.conftest import register_org


async def _create_project(client, headers, name="Core Platform"):
    r = await client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_roadmap(client, headers, name="FY Roadmap"):
    r = await client.post("/api/v1/roadmaps", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_epic(client, headers, name="Auth Rework", project_id=None):
    payload = {"name": name}
    if project_id:
        payload["project_id"] = project_id
    r = await client.post("/api/v1/epics", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_milestone(client, headers, name="Alpha", project_id=None):
    payload = {"name": name}
    if project_id:
        payload["project_id"] = project_id
    r = await client.post("/api/v1/milestones", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_sprint(client, headers, name="Sprint 1", project_id=None):
    payload = {"name": name}
    if project_id:
        payload["project_id"] = project_id
    r = await client.post("/api/v1/sprints", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_employee(client, headers, first_name, email):
    r = await client.post(
        "/api/v1/employees",
        json={"first_name": first_name, "email": email},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------ org-mutation vector (1-4)


@pytest.mark.asyncio
async def test_org_mutation_vector_blocked_roadmap(client):
    org_a = await register_org(client, email="s3i1a@test.co")
    org_b = await register_org(client, email="s3i1b@test.co")
    roadmap = await _create_roadmap(client, org_a["headers"], "Roadmap A")

    r = await client.patch(
        f"/api/v1/roadmaps/{roadmap['id']}",
        json={"organization_id": org_b["organization"]["id"], "name": "Hijacked"},
        headers=org_a["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.patch(
        f"/api/v1/roadmaps/{roadmap['id']}",
        json={"name": "Renamed"},
        headers=org_a["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"

    listing = (await client.get("/api/v1/roadmaps", headers=org_b["headers"])).json()
    assert all(x["name"] != "Hijacked" for x in listing)


@pytest.mark.asyncio
async def test_org_mutation_vector_blocked_epic(client):
    org_a = await register_org(client, email="s3i2a@test.co")
    org_b = await register_org(client, email="s3i2b@test.co")
    epic = await _create_epic(client, org_a["headers"], "Epic A")

    r = await client.patch(
        f"/api/v1/epics/{epic['id']}",
        json={"organization_id": org_b["organization"]["id"], "name": "Hijacked"},
        headers=org_a["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.patch(
        f"/api/v1/epics/{epic['id']}", json={"name": "Renamed"}, headers=org_a["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_org_mutation_vector_blocked_milestone(client):
    org_a = await register_org(client, email="s3i3a@test.co")
    org_b = await register_org(client, email="s3i3b@test.co")
    milestone = await _create_milestone(client, org_a["headers"], "Milestone A")

    r = await client.patch(
        f"/api/v1/milestones/{milestone['id']}",
        json={"organization_id": org_b["organization"]["id"], "name": "Hijacked"},
        headers=org_a["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.patch(
        f"/api/v1/milestones/{milestone['id']}",
        json={"name": "Renamed"},
        headers=org_a["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_org_mutation_vector_blocked_sprint(client):
    org_a = await register_org(client, email="s3i4a@test.co")
    org_b = await register_org(client, email="s3i4b@test.co")
    sprint = await _create_sprint(client, org_a["headers"], "Sprint A")

    r = await client.patch(
        f"/api/v1/sprints/{sprint['id']}",
        json={"organization_id": org_b["organization"]["id"], "name": "Hijacked"},
        headers=org_a["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.patch(
        f"/api/v1/sprints/{sprint['id']}",
        json={"name": "Renamed"},
        headers=org_a["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


# ------------------------------------------------ FK revalidation (5-8)


@pytest.mark.asyncio
async def test_cross_org_project_ref_rejected_on_epic(client):
    org_a = await register_org(client, email="s3i5a@test.co")
    org_b = await register_org(client, email="s3i5b@test.co")
    project_a = await _create_project(client, org_a["headers"], "Project A")
    epic = await _create_epic(client, org_b["headers"], "Epic B")

    r = await client.patch(
        f"/api/v1/epics/{epic['id']}",
        json={"project_id": project_a["id"]},
        headers=org_b["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.patch(
        f"/api/v1/epics/{epic['id']}",
        json={"name": "Still Ours"},
        headers=org_b["headers"],
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_cross_org_project_ref_rejected_on_sprint(client):
    org_a = await register_org(client, email="s3i6a@test.co")
    org_b = await register_org(client, email="s3i6b@test.co")
    project_a = await _create_project(client, org_a["headers"], "Project A")
    sprint = await _create_sprint(client, org_b["headers"], "Sprint B")

    r = await client.patch(
        f"/api/v1/sprints/{sprint['id']}",
        json={"project_id": project_a["id"]},
        headers=org_b["headers"],
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_cross_org_owner_ref_rejected_on_roadmap(client):
    org_a = await register_org(client, email="s3i7a@test.co")
    org_b = await register_org(client, email="s3i7b@test.co")
    emp_a = await _create_employee(client, org_a["headers"], "Alice", "alice@s3i7.test.co")
    roadmap = await _create_roadmap(client, org_b["headers"], "Roadmap B")

    r = await client.patch(
        f"/api/v1/roadmaps/{roadmap['id']}",
        json={"owner_id": emp_a["id"]},
        headers=org_b["headers"],
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_task_goal_id_rejected_create_and_update(client):
    org = await register_org(client, email="s3i8@test.co")
    project = await _create_project(client, org["headers"], "Project")
    bogus_goal = "00000000-0000-0000-0000-0000000000ff"

    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Task with fake goal", "project_id": project["id"], "goal_id": bogus_goal},
        headers=org["headers"],
    )
    assert r.status_code == 400, r.text

    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Legit task", "project_id": project["id"]},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    task = r.json()

    r = await client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"goal_id": bogus_goal},
        headers=org["headers"],
    )
    assert r.status_code == 400, r.text

    listing = (await client.get("/api/v1/tasks", headers=org["headers"])).json()
    assert any(t["id"] == task["id"] for t in listing)


# ------------------------------------------------ risk list filters (9-10)


@pytest.mark.asyncio
async def test_risk_list_severity_filter(client):
    org = await register_org(client, email="s3i9@test.co")
    project = await _create_project(client, org["headers"], "Project")

    for title, prob, impact in [
        ("Critical one", 4, 4),
        ("High one", 3, 3),
        ("Medium one", 2, 2),
        ("Low one", 1, 1),
    ]:
        r = await client.post(
            "/api/v1/risks",
            json={"title": title, "project_id": project["id"], "probability": prob, "impact": impact},
            headers=org["headers"],
        )
        assert r.status_code == 201, r.text

    critical = (await client.get("/api/v1/risks?severity=critical", headers=org["headers"])).json()
    assert len(critical) == 1
    assert critical[0]["title"] == "Critical one"

    low = (await client.get("/api/v1/risks?severity=low", headers=org["headers"])).json()
    assert len(low) == 1
    assert low[0]["title"] == "Low one"


@pytest.mark.asyncio
async def test_risk_list_limit_honored(client):
    org = await register_org(client, email="s3i10@test.co")
    for i in range(5):
        r = await client.post(
            "/api/v1/risks",
            json={"title": f"Risk {i}", "probability": 2, "impact": 2},
            headers=org["headers"],
        )
        assert r.status_code == 201, r.text

    limited = (await client.get("/api/v1/risks?limit=2", headers=org["headers"])).json()
    assert len(limited) == 2


# ------------------------------------------------ meeting filters (11-12)


@pytest.mark.asyncio
async def test_meeting_employee_filter_applies_before_limit(client):
    org = await register_org(client, email="s3i11@test.co")
    emp = await _create_employee(client, org["headers"], "Dana", "dana@s3i11.test.co")
    other = await _create_employee(client, org["headers"], "Eve", "eve@s3i11.test.co")

    for i in range(3):
        payload = {"title": f"Meeting {i}", "attendee_ids": [other["id"]]}
        if i == 2:
            payload["attendee_ids"] = [emp["id"]]
        r = await client.post("/api/v1/meetings", json=payload, headers=org["headers"])
        assert r.status_code == 201, r.text

    mine = (
        await client.get(
            f"/api/v1/meetings?employee_id={emp['id']}&limit=2", headers=org["headers"]
        )
    ).json()
    assert len(mine) == 1
    assert mine[0]["title"] == "Meeting 2"


@pytest.mark.asyncio
async def test_meeting_update_revalidates_refs(client):
    org_a = await register_org(client, email="s3i12a@test.co")
    org_b = await register_org(client, email="s3i12b@test.co")
    project_a = await _create_project(client, org_a["headers"], "Project A")

    r = await client.post("/api/v1/meetings", json={"title": "Meeting B"}, headers=org_b["headers"])
    assert r.status_code == 201, r.text
    meeting = r.json()

    r = await client.patch(
        f"/api/v1/meetings/{meeting['id']}",
        json={"project_id": project_a["id"]},
        headers=org_b["headers"],
    )
    assert r.status_code == 400, r.text


# ------------------------------------------------ task transition (13-14)


@pytest.mark.asyncio
async def test_task_transition_typed_body_rejects_unknown_status(client):
    org = await register_org(client, email="s3i13@test.co")
    r = await client.post("/api/v1/tasks", json={"title": "T"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    task = r.json()

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition",
        json={"status": "done"},
        headers=org["headers"],
    )
    assert r.status_code == 422, r.text

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition",
        json={"status": "in_progress", "title": "Smuggled"},
        headers=org["headers"],
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_task_transition_valid_status_works(client):
    org = await register_org(client, email="s3i14@test.co")
    r = await client.post("/api/v1/tasks", json={"title": "T2"}, headers=org["headers"])
    assert r.status_code == 201, r.text
    task = r.json()

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/transition",
        json={"status": "completed"},
        headers=org["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
