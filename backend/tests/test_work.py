"""Phase 3 — Work Execution Engine tests.

Covers: project lifecycle, epics/milestones/sprints, task engine with
dependencies (blocking + cycle rejection), goals/key results, meetings,
calendar, approvals, risks, workload, my-work, executive analytics,
tenancy isolation, and RBAC for the new permission codes.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers, email=None):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


@pytest.mark.asyncio
async def test_project_lifecycle_with_structure(client):
    org = await register_org(client, email="pm@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    roadmap = await client.post(
        "/api/v1/roadmaps",
        json={"name": "2026 Product Roadmap", "timeframe": "year", "owner_id": me},
        headers=headers,
    )
    assert roadmap.status_code == 201, roadmap.text
    roadmap_id = roadmap.json()["id"]

    project = await client.post(
        "/api/v1/projects",
        json={
            "name": "Nova Platform",
            "code": "NOVA-1",
            "description": "The intelligent work platform",
            "status": "active",
            "owner_id": me,
            "roadmap_id": roadmap_id,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "budget": 250000,
            "tags": ["platform", "ai"],
        },
        headers=headers,
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    assert project.json()["code"] == "NOVA-1"

    epic = await client.post(
        "/api/v1/epics",
        json={"project_id": project_id, "name": "Intelligent Workspaces"},
        headers=headers,
    )
    assert epic.status_code == 201, epic.text
    epic_id = epic.json()["id"]

    milestone = await client.post(
        "/api/v1/milestones",
        json={"project_id": project_id, "name": "MVP", "due_date": "2026-06-30"},
        headers=headers,
    )
    assert milestone.status_code == 201, milestone.text
    milestone_id = milestone.json()["id"]

    sprint = await client.post(
        "/api/v1/sprints",
        json={"project_id": project_id, "name": "Sprint 1", "start_date": "2026-01-15", "end_date": "2026-01-30"},
        headers=headers,
    )
    assert sprint.status_code == 201, sprint.text
    sprint_id = sprint.json()["id"]

    emp2 = await client.post(
        "/api/v1/employees",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@work.test.co"},
        headers=headers,
    )
    assert emp2.status_code == 201, emp2.text

    member = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"employee_id": emp2.json()["id"], "role": "engineer"},
        headers=headers,
    )
    assert member.status_code == 201, member.text

    detail = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["members_count"] == 2
    assert detail.json()["owner_name"] == "Ada Owner"

    stats = await client.get(f"/api/v1/projects/{project_id}/stats", headers=headers)
    assert stats.status_code == 200

    health = await client.get(f"/api/v1/projects/{project_id}/health", headers=headers)
    assert health.status_code == 200, health.text
    assert "health" in health.json()

    timeline = await client.get(f"/api/v1/projects/{project_id}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert any(e["kind"] == "project.created" for e in timeline.json())

    sprint_start = await client.post(f"/api/v1/sprints/{sprint_id}/start", headers=headers)
    assert sprint_start.status_code == 200
    assert sprint_start.json()["status"] == "active"

    milestone_done = await client.post(f"/api/v1/milestones/{milestone_id}/complete", headers=headers)
    assert milestone_done.status_code == 200
    assert milestone_done.json()["status"] == "completed"
    assert milestone_done.json()["progress"] == 100

    epics = await client.get(f"/api/v1/epics?project_id={project_id}", headers=headers)
    assert epics.status_code == 200
    assert any(e["id"] == epic_id for e in epics.json())

    listed = await client.get("/api/v1/projects", headers=headers)
    assert listed.status_code == 200
    assert any(p["id"] == project_id for p in listed.json())


@pytest.mark.asyncio
async def test_task_engine_dependencies_and_cycles(client):
    org = await register_org(client, email="dev@tasks.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    t1 = await client.post(
        "/api/v1/tasks",
        json={"title": "Design database schema", "assignee_id": me, "priority": "high"},
        headers=headers,
    )
    assert t1.status_code == 201, t1.text
    t1_id = t1.json()["id"]

    t2 = await client.post(
        "/api/v1/tasks",
        json={"title": "Implement migrations", "assignee_id": me},
        headers=headers,
    )
    t2_id = t2.json()["id"]

    dep = await client.post(
        f"/api/v1/tasks/{t2_id}/dependencies",
        json={"depends_on_task_id": t1_id, "kind": "finish_to_start"},
        headers=headers,
    )
    assert dep.status_code == 201, dep.text

    cycle = await client.post(
        f"/api/v1/tasks/{t1_id}/dependencies",
        json={"depends_on_task_id": t2_id},
        headers=headers,
    )
    assert cycle.status_code == 400
    assert "cycle" in cycle.json()["detail"].lower()

    duplicate = await client.post(
        f"/api/v1/tasks/{t2_id}/dependencies",
        json={"depends_on_task_id": t1_id},
        headers=headers,
    )
    assert duplicate.status_code == 400

    transition = await client.post(
        f"/api/v1/tasks/{t2_id}/transition",
        json={"status": "in_progress"},
        headers=headers,
    )
    assert transition.status_code == 200
    assert transition.json()["status"] == "in_progress"

    blocked = await client.post(
        f"/api/v1/tasks/{t2_id}/transition",
        json={"status": "blocked"},
        headers=headers,
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"

    done1 = await client.post(
        f"/api/v1/tasks/{t1_id}/transition",
        json={"status": "completed"},
        headers=headers,
    )
    assert done1.status_code == 200
    assert done1.json()["completed_at"] is not None

    done2 = await client.post(
        f"/api/v1/tasks/{t2_id}/transition",
        json={"status": "completed"},
        headers=headers,
    )
    assert done2.status_code == 200
    assert done2.json()["progress"] == 100

    detail = await client.get(f"/api/v1/tasks/{t2_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json().get("dependencies", [])) == 1

    bad_status = await client.post(
        f"/api/v1/tasks/{t1_id}/transition",
        json={"status": "unknown"},
        headers=headers,
    )
    assert bad_status.status_code in (400, 422)


@pytest.mark.asyncio
async def test_goals_and_key_results(client):
    org = await register_org(client, email="lead@goals.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    goal = await client.post(
        "/api/v1/goals",
        json={
            "name": "Double adoption",
            "scope": "company",
            "owner_id": me,
            "key_results": [
                {"title": "Reach 1000 users", "metric": "users", "unit": "count", "target": 1000, "current": 100},
                {"title": "NPS above 40", "metric": "nps", "target": 40, "current": 20},
            ],
        },
        headers=headers,
    )
    assert goal.status_code == 201, goal.text
    goal_id = goal.json()["id"]
    created_goal = await client.get(f"/api/v1/goals/{goal_id}", headers=headers)
    assert created_goal.status_code == 200
    assert created_goal.json()["progress"] == 30.0  # (100/1000 + 20/40) / 2 * 100

    krs = await client.get(f"/api/v1/goals/{goal_id}/key-results", headers=headers)
    assert krs.status_code == 200
    assert len(krs.json()) == 2
    kr0 = next(kr for kr in krs.json() if kr["title"].startswith("Reach"))
    kr1 = next(kr for kr in krs.json() if kr["title"].startswith("NPS"))

    update = await client.patch(
        f"/api/v1/goals/{goal_id}/key-results/{kr0['id']}",
        json={"current": 1000},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["status"] == "completed"

    detail = await client.get(f"/api/v1/goals/{goal_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["key_results_count"] == 2

    goals = await client.get("/api/v1/goals?scope=company", headers=headers)
    assert goals.status_code == 200
    assert any(g["id"] == goal_id for g in goals.json())


@pytest.mark.asyncio
async def test_meetings_attendees_action_items(client):
    org = await register_org(client, email="ops@meet.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    meeting = await client.post(
        "/api/v1/meetings",
        json={
            "title": "Weekly sync",
            "meeting_type": "standup",
            "organizer_id": me,
            "start_at": "2026-08-10T09:00:00Z",
            "end_at": "2026-08-10T09:30:00Z",
            "attendee_ids": [me],
            "agenda": [{"title": "Status update", "duration_minutes": 15}],
        },
        headers=headers,
    )
    assert meeting.status_code == 201, meeting.text
    meeting_id = meeting.json()["id"]

    attendees = await client.get(f"/api/v1/meetings/{meeting_id}/attendees", headers=headers)
    assert attendees.status_code == 200
    assert len(attendees.json()) == 1

    rsvp = await client.post(f"/api/v1/meetings/{meeting_id}/rsvp", json={"status": "accepted"}, headers=headers)
    assert rsvp.status_code == 200, rsvp.text
    assert rsvp.json()["status"] == "accepted"

    agenda = await client.get(f"/api/v1/meetings/{meeting_id}/agenda", headers=headers)
    assert agenda.status_code == 200
    assert len(agenda.json()) == 1

    action = await client.post(
        f"/api/v1/meetings/{meeting_id}/action-items",
        json={"title": "Prepare deck", "assignee_id": me},
        headers=headers,
    )
    assert action.status_code == 201, action.text
    action_id = action.json()["id"]

    done = await client.post(f"/api/v1/meetings/{meeting_id}/action-items/{action_id}/complete", headers=headers)
    assert done.status_code == 200
    assert done.json()["status"] == "completed"

    complete = await client.post(f"/api/v1/meetings/{meeting_id}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"
    assert complete.json()["ai_summary"] is not None

    detail = await client.get(f"/api/v1/meetings/{meeting_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["organizer_name"] == "Ada Owner"


@pytest.mark.asyncio
async def test_calendar_events(client):
    org = await register_org(client, email="cal@cal.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    event = await client.post(
        "/api/v1/calendar/events",
        json={
            "title": "Launch event",
            "event_type": "milestone",
            "calendar_scope": "organization",
            "start_at": "2026-09-01T10:00:00Z",
            "end_at": "2026-09-01T12:00:00Z",
            "attendee_ids": [me],
        },
        headers=headers,
    )
    assert event.status_code == 201, event.text
    event_id = event.json()["id"]

    events = await client.get(
        "/api/v1/calendar/events?start=2026-08-01T00:00:00Z&end=2026-10-01T00:00:00Z",
        headers=headers,
    )
    assert events.status_code == 200
    assert any(e["id"] == event_id for e in events.json())

    mine = await client.get(
        f"/api/v1/calendar/events?employee_id={me}&start=2026-08-01T00:00:00Z&end=2026-10-01T00:00:00Z",
        headers=headers,
    )
    assert mine.status_code == 200
    assert any(e["id"] == event_id for e in mine.json())

    update = await client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"title": "Launch event (moved)"},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["title"] == "Launch event (moved)"


@pytest.mark.asyncio
async def test_approvals_and_risks(client):
    org = await register_org(client, email="fin@risk.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    approval = await client.post(
        "/api/v1/approvals",
        json={
            "title": "Purchase: new laptops",
            "approval_type": "purchase",
            "approver_id": me,
            "priority": "high",
        },
        headers=headers,
    )
    assert approval.status_code == 201, approval.text
    approval_id = approval.json()["id"]
    assert approval.json()["status"] == "pending"

    decided = await client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json={"decision": "approved", "note": "Budget approved"},
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert decided.json()["decided_at"] is not None

    double = await client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json={"decision": "approved"},
        headers=headers,
    )
    assert double.status_code == 400

    stats = await client.get("/api/v1/approvals/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["approved"] == 1

    project = await client.post(
        "/api/v1/projects",
        json={"name": "Risky build", "code": "RISK-1", "status": "active"},
        headers=headers,
    )
    project_id = project.json()["id"]

    risk = await client.post(
        "/api/v1/risks",
        json={
            "project_id": project_id,
            "title": "Vendor delay",
            "probability": 4,
            "impact": 3,
            "mitigation": "Dual vendor",
        },
        headers=headers,
    )
    assert risk.status_code == 201, risk.text
    assert risk.json()["risk_score"] == 12
    assert risk.json()["severity"] == "high"

    updated = await client.patch(f"/api/v1/risks/{risk.json()['id']}", json={"impact": 5}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["risk_score"] == 20
    assert updated.json()["severity"] == "critical"

    closed = await client.post(f"/api/v1/risks/{risk.json()['id']}/close", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_workload_and_analytics(client):
    org = await register_org(client, email="exe@ana.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    await client.post(
        "/api/v1/tasks",
        json={"title": "Heavy lift", "assignee_id": me, "estimate_hours": 30, "status": "todo"},
        headers=headers,
    )
    await client.post(
        "/api/v1/projects",
        json={"name": "Core", "code": "CORE-1", "status": "active"},
        headers=headers,
    )

    my_work = await client.get("/api/v1/my-work", headers=headers)
    assert my_work.status_code == 200, my_work.text
    assert my_work.json()["tasks"]["total"] == 1

    workload = await client.get("/api/v1/workload/me", headers=headers)
    assert workload.status_code == 200, workload.text
    assert workload.json()["capacity_hours"] == 40
    assert workload.json()["allocated_hours"] == 30

    snapshot = await client.post("/api/v1/workload/snapshot", headers=headers)
    assert snapshot.status_code == 200
    assert snapshot.json()["snapshots_created"] >= 1

    exec_dash = await client.get("/api/v1/analytics/executive", headers=headers)
    assert exec_dash.status_code == 200, exec_dash.text
    assert exec_dash.json()["projects_total"] == 1
    assert exec_dash.json()["tasks_total"] == 1

    org_load = await client.get("/api/v1/workload/organization", headers=headers)
    assert org_load.status_code == 200
    assert org_load.json()["employees_tracked"] >= 1


@pytest.mark.asyncio
async def test_work_search(client):
    org = await register_org(client, email="find@search.test.co")
    headers = org["headers"]

    await client.post(
        "/api/v1/projects",
        json={"name": "Quantum Engine", "code": "Q-1"},
        headers=headers,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Calibrate quantum gate"},
        headers=headers,
    )
    await client.post(
        "/api/v1/goals",
        json={"name": "Ship quantum engine", "scope": "company"},
        headers=headers,
    )

    response = await client.get("/api/v1/search?q=quantum", headers=headers)
    assert response.status_code == 200, response.text
    types = {r["type"] for r in response.json()["results"]}
    assert "project" in types
    assert "task" in types
    assert "goal" in types


@pytest.mark.asyncio
async def test_work_rbac_and_tenancy(client):
    org = await register_org(client, email="boss@rbac.test.co")
    headers = org["headers"]

    created = await client.post(
        "/api/v1/projects",
        json={"name": "Tenant A project", "code": "TA-1"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp@rbac.test.co", "full_name": "Emp Worker", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    invite_token = invite.json()["token"]

    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite_token, "full_name": "Emp Worker", "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    emp_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    can_read = await client.get("/api/v1/projects", headers=emp_headers)
    assert can_read.status_code == 200, can_read.text
    assert any(p["code"] == "TA-1" for p in can_read.json())

    can_read_tasks = await client.get("/api/v1/tasks", headers=emp_headers)
    assert can_read_tasks.status_code == 200

    create_denied = await client.post(
        "/api/v1/projects",
        json={"name": "Should fail", "code": "NOPE-1"},
        headers=emp_headers,
    )
    assert create_denied.status_code == 403

    manage_denied = await client.post(
        "/api/v1/tasks",
        json={"title": "Should fail"},
        headers=emp_headers,
    )
    assert manage_denied.status_code == 403

    tenant_b = await register_org(client, name="Tenant B", slug="rbac-b", email="b@rbac.test.co")
    b_headers = tenant_b["headers"]
    projects_b = await client.get("/api/v1/projects", headers=b_headers)
    assert projects_b.status_code == 200
    assert all(p["code"] != "TA-1" for p in projects_b.json())

    b_cannot_see_project = await client.get(
        f"/api/v1/projects/{created.json()['id']}", headers=b_headers
    )
    assert b_cannot_see_project.status_code == 404
