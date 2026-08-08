"""Phase 11 — HR & Workforce Operations tests.

Covers the full human lifecycle inside VCOS: attendance (shifts, holidays,
clock in/out, corrections), leave (types, balances, approval workflow),
recruitment (jobs → candidates → interviews → offers → hire), performance
(cycles, goals, reviews), assets, offboarding → alumni, compliance,
workforce planning + succession + snapshots, wellbeing, payroll integration
references, the HR hub dashboard, the HR AI companion, RBAC gating,
multi-tenant isolation and the Phase 11 background workers.
"""

from datetime import date, datetime, timedelta

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _invite_employee(client, headers, *, email, role="employee", full_name="Emp Two"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": full_name, "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": full_name, "password": "EmpPass123!"},
    )
    assert registered.status_code == 201, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


async def _events(client, headers, name):
    response = await client.get(
        "/api/v1/events", headers=headers, params={"name": name, "page_size": 50}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"] if isinstance(body, dict) and "items" in body else body
    return [item for item in items if item.get("name") == name]


# ============================================================== attendance

@pytest.mark.asyncio
async def test_attendance_clock_in_out_and_summary(client):
    org = await register_org(client, email="p11att@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    shift = await client.post(
        "/api/v1/attendance/shifts",
        json={"name": "Standard", "start_time": "09:00", "end_time": "17:00", "work_hours": 8, "days": [0, 1, 2, 3, 4]},
        headers=headers,
    )
    assert shift.status_code == 200, shift.text
    shift_id = shift.json()["id"]

    holiday = await client.post(
        "/api/v1/attendance/holidays",
        json={"name": "Company Day", "date": "2026-07-04"},
        headers=headers,
    )
    assert holiday.status_code == 200, holiday.text
    assert len((await client.get("/api/v1/attendance/holidays", headers=headers)).json()) == 1

    clock_in = await client.post(
        "/api/v1/attendance/clock-in",
        json={"source": "app", "shift_id": shift_id, "work_mode": "office", "location": "HQ-1"},
        headers=headers,
    )
    assert clock_in.status_code == 200, clock_in.text
    assert clock_in.json()["check_in"]

    today = (await client.get("/api/v1/attendance/today", headers=headers)).json()
    assert today["checked_in"] is True and today["checked_out"] is False

    clock_out = await client.post("/api/v1/attendance/clock-out", json={}, headers=headers)
    assert clock_out.status_code == 200, clock_out.text
    assert clock_out.json()["check_out"]
    assert clock_out.json()["work_minutes"] >= 0

    records = (await client.get("/api/v1/attendance/my", headers=headers)).json()
    assert len(records) == 1
    assert records[0]["id"] == clock_in.json()["id"]

    summary = (await client.get("/api/v1/attendance/summary", headers=headers)).json()
    assert summary["days"] == 1
    assert summary["statuses"].get("present") == 1

    manual = await client.post(
        "/api/v1/attendance/manual",
        json={"employee_id": me, "date": "2026-06-15", "check_in": "2026-06-15T09:00:00",
              "check_out": "2026-06-15T17:00:00", "status": "present"},
        headers=headers,
    )
    assert manual.status_code == 200, manual.text

    correction = await client.post(
        "/api/v1/attendance/corrections",
        json={"date": "2026-06-15", "reason": "Wrong clock-out", "attendance_id": manual.json()["id"],
              "adjusted_check_out": "2026-06-15T18:00:00"},
        headers=headers,
    )
    assert correction.status_code == 200, correction.text
    reviewed = await client.post(
        f"/api/v1/attendance/corrections/{correction.json()['id']}/review",
        json={"decision": "approve"},
        headers=headers,
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_attendance_rbac_employee_cannot_manage(client):
    org = await register_org(client, email="p11att2@work.test.co")
    headers = org["headers"]
    employee = await _invite_employee(client, headers, email="emp.att2@work.test.co")
    response = await client.post(
        "/api/v1/attendance/shifts",
        json={"name": "Nope", "start_time": "09:00", "end_time": "17:00"},
        headers=employee,
    )
    assert response.status_code == 403
    response = await client.post("/api/v1/attendance/holidays", json={"name": "Nope", "date": "2026-12-25"}, headers=employee)
    assert response.status_code == 403
    # employee self-service still works
    response = await client.post("/api/v1/attendance/clock-in", json={"work_mode": "remote"}, headers=employee)
    assert response.status_code == 200, response.text


# ============================================================== leave

@pytest.mark.asyncio
async def test_leave_workflow_and_balances(client):
    org = await register_org(client, email="p11lve@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    types = (await client.get("/api/v1/leave/types", headers=headers)).json()
    codes = {item["code"] for item in types}
    assert "annual" in codes and "sick" in codes and "maternity" in codes
    annual = next(item for item in types if item["code"] == "annual")

    balances = (await client.get("/api/v1/leave/balances", headers=headers)).json()
    annual_balance = next(item for item in balances if item["leave_type_id"] == annual["id"])
    assert annual_balance["allocated"] == 20.0

    start = date.today().replace(day=1)
    end = start + timedelta(days=4)
    expected_days = sum(1 for d in range(5) if (start + timedelta(days=d)).weekday() < 5)
    request = await client.post(
        "/api/v1/leave/requests",
        json={
            "leave_type_id": annual["id"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "Planning a break",
        },
        headers=headers,
    )
    assert request.status_code == 200, request.text
    request_id = request.json()["id"]
    assert request.json()["days"] == expected_days

    # insufficient balance is rejected for paid types
    over = await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": annual["id"], "start_date": "2026-01-05", "end_date": "2026-03-30", "reason": "Too much"},
        headers=headers,
    )
    assert over.status_code == 400

    # overlap is rejected
    overlap = await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": annual["id"], "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "Again"},
        headers=headers,
    )
    assert overlap.status_code == 400

    # employee sees pending, no approve permission
    pending = (await client.get("/api/v1/leave/pending", headers=headers)).json()
    assert len(pending) == 1 and pending[0]["id"] == request_id

    approved = await client.post(
        f"/api/v1/leave/requests/{request_id}/approve", json={"note": "Enjoy"}, headers=headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    balances = (await client.get("/api/v1/leave/balances", headers=headers)).json()
    annual_balance = next(item for item in balances if item["leave_type_id"] == annual["id"])
    assert annual_balance["used"] == expected_days
    assert annual_balance["remaining"] == 20.0 - expected_days

    # reject flow
    sick = next(item for item in types if item["code"] == "sick")
    req2 = await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": sick["id"], "start_date": "2026-08-10", "end_date": "2026-08-11", "reason": "Recovery"},
        headers=headers,
    )
    assert req2.status_code == 200, req2.text
    rejected = await client.post(
        f"/api/v1/leave/requests/{req2.json()['id']}/reject", json={"note": "Coverage conflict"}, headers=headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    summary = (await client.get("/api/v1/leave/summary", headers=headers)).json()
    assert summary["approved_count"] == 1 and summary["pending_count"] == 0
    assert any(item["code"] == "annual" for item in summary["per_type"])

    calendar = await client.get(
        "/api/v1/leave/calendar",
        params={"start": start.isoformat(), "end": (start + timedelta(days=30)).isoformat()},
        headers=headers,
    )
    assert calendar.status_code == 200, calendar.text
    assert any(item["kind"] == "leave" for item in calendar.json())


@pytest.mark.asyncio
async def test_leave_manager_pending_scope(client):
    org = await register_org(client, email="p11lve2@work.test.co")
    headers = org["headers"]
    manager_emp = await _invite_employee(client, headers, email="mgr.lve2@work.test.co", role="manager")
    report_emp = await _invite_employee(client, headers, email="rep.lve2@work.test.co", role="employee")

    # set manager relationship via HR transfer endpoint
    me = await _employee_id(client, headers)
    report_id = (await client.get("/api/v1/employees/me", headers=report_emp)).json()["id"]
    manager_id = (await client.get("/api/v1/employees/me", headers=manager_emp)).json()["id"]
    response = await client.post(
        f"/api/v1/hr/employees/{report_id}/transfer", json={"manager_id": manager_id}, headers=headers
    )
    assert response.status_code == 200, response.text

    types = (await client.get("/api/v1/leave/types", headers=headers)).json()
    annual = next(item for item in types if item["code"] == "annual")
    req = await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": annual["id"], "start_date": "2026-10-05", "end_date": "2026-10-06", "reason": "Break"},
        headers=report_emp,
    )
    assert req.status_code == 200, req.text

    # manager sees the report's pending request
    pending = (await client.get("/api/v1/leave/pending", headers=manager_emp)).json()
    assert len(pending) == 1 and pending[0]["employee_id"] == report_id

    # a plain employee sees nothing in the org-wide queue
    plain = await _invite_employee(client, headers, email="plain.lve2@work.test.co")
    pending_plain = (await client.get("/api/v1/leave/pending", headers=plain)).json()
    assert pending_plain == []


# ============================================================== recruitment

@pytest.mark.asyncio
async def test_recruitment_pipeline_to_hire(client):
    org = await register_org(client, email="p11rec@work.test.co")
    headers = org["headers"]

    job = await client.post(
        "/api/v1/recruitment/jobs",
        json={
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "openings": 1,
            "status": "open",
        },
        headers=headers,
    )
    assert job.status_code == 200, job.text
    job_id = job.json()["id"]

    candidate = await client.post(
        "/api/v1/recruitment/candidates",
        json={
            "job_id": job_id,
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
            "experience_years": 9,
            "current_company": "Acme",
            "stage": "applied",
        },
        headers=headers,
    )
    assert candidate.status_code == 200, candidate.text
    assert candidate.json()["match_score"] > 80
    candidate_id = candidate.json()["id"]

    interview = await client.post(
        "/api/v1/recruitment/interviews",
        json={"job_id": job_id, "candidate_id": candidate_id, "mode": "video", "duration_minutes": 60,
              "panel": ["Reviewer"], "scheduled_at": "2026-09-01T10:00:00"},
        headers=headers,
    )
    assert interview.status_code == 200, interview.text
    interview_id = interview.json()["id"]

    completed = await client.post(
        f"/api/v1/recruitment/interviews/{interview_id}/complete",
        json={"rating": 4.5, "feedback": "Strong", "recommendation": "hire"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text

    offer = await client.post(
        "/api/v1/recruitment/offers",
        json={"job_id": job_id, "candidate_id": candidate_id, "salary": "120k", "start_date": "2026-10-01"},
        headers=headers,
    )
    assert offer.status_code == 200, offer.text
    offer_id = offer.json()["id"]

    sent = await client.post(
        f"/api/v1/recruitment/offers/{offer_id}/status", json={"status": "sent"}, headers=headers
    )
    assert sent.status_code == 200, sent.text

    accepted = await client.post(
        f"/api/v1/recruitment/offers/{offer_id}/status", json={"status": "accepted"}, headers=headers
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["hired_employee_id"]

    # the hire created an Employee and emitted employee.joined
    employees = (await client.get("/api/v1/employees", headers=headers)).json()
    hired = next((e for e in employees if e.get("email") == "grace@example.com"), None)
    assert hired is not None
    assert hired["designation"] == "Senior Backend Engineer"
    assert hired["status"] == "active"
    assert hired["joining_date"] == "2026-10-01"

    events = await _events(client, headers, "employee.joined")
    assert len(events) == 1

    stats = (await client.get("/api/v1/recruitment/stats", headers=headers)).json()
    assert stats["hires"] == 1
    assert stats["candidates_by_stage"].get("hired") == 1

    # job closed after the single opening filled
    jobs = (await client.get("/api/v1/recruitment/jobs", headers=headers)).json()
    assert next(item for item in jobs if item["id"] == job_id)["status"] == "closed"


# ============================================================== performance

@pytest.mark.asyncio
async def test_performance_cycles_goals_reviews(client):
    org = await register_org(client, email="p11perf@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    cycle = await client.post(
        "/api/v1/performance/cycles",
        json={"name": "H1 2026", "period": {"start": "2026-01-01", "end": "2026-06-30"}},
        headers=headers,
    )
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]

    opened = await client.post(
        f"/api/v1/performance/cycles/{cycle_id}/status", json={"status": "open"}, headers=headers
    )
    assert opened.status_code == 200 and opened.json()["status"] == "open"

    goal = await client.post(
        "/api/v1/performance/goals",
        json={"employee_id": me, "cycle_id": cycle_id, "title": "Ship platform v2", "kind": "project", "progress": 40},
        headers=headers,
    )
    assert goal.status_code == 200, goal.text
    progress = await client.patch(
        f"/api/v1/performance/goals/{goal.json()['id']}/progress", json={"progress": 100}, headers=headers
    )
    assert progress.status_code == 200 and progress.json()["status"] == "completed"

    review = await client.post(
        "/api/v1/performance/reviews",
        json={"employee_id": me, "cycle_id": cycle_id, "kind": "manager", "reviewer_id": me},
        headers=headers,
    )
    assert review.status_code == 200, review.text
    review_id = review.json()["id"]

    submitted = await client.post(
        f"/api/v1/performance/reviews/{review_id}/submit",
        json={"rating": 4.0, "feedback": "Great progress", "strengths": ["Delivery"], "improvements": ["Docs"]},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    completed = await client.post(
        f"/api/v1/performance/reviews/{review_id}/complete", headers=headers
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["ai_summary"]

    events = await _events(client, headers, "review.completed")
    assert len(events) == 1

    summary = (await client.get("/api/v1/performance/summary", headers=headers)).json()
    assert summary["reviews"]["completed"] == 1
    assert summary["reviews"]["average_rating"] == 4.0


# ============================================================== assets

@pytest.mark.asyncio
async def test_asset_lifecycle(client):
    org = await register_org(client, email="p11ast@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    asset = await client.post(
        "/api/v1/assets",
        json={"name": "MacBook Pro", "category": "laptop", "serial_number": "SN-001"},
        headers=headers,
    )
    assert asset.status_code == 200, asset.text
    asset_id = asset.json()["id"]

    assigned = await client.post(
        f"/api/v1/assets/{asset_id}/assign", json={"employee_id": me}, headers=headers
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "assigned"

    events = await _events(client, headers, "asset.assigned")
    assert len(events) == 1

    my_assets = (await client.get("/api/v1/assets", headers=headers, params={"employee_id": me})).json()
    assert len(my_assets) == 1 and my_assets[0]["employee_name"]

    returned = await client.post(
        f"/api/v1/assets/{asset_id}/status", json={"status": "returned"}, headers=headers
    )
    assert returned.status_code == 200 and returned.json()["status"] == "returned"

    summary = (await client.get("/api/v1/assets/summary", headers=headers)).json()
    assert summary["total"] == 1
    assert summary["returned"] == 1


# ============================================================== offboarding & alumni

@pytest.mark.asyncio
async def test_offboarding_to_alumni(client):
    org = await register_org(client, email="p11off@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    offboarding = await client.post(
        "/api/v1/offboarding",
        json={"employee_id": me, "reason": "New opportunity", "exit_date": "2026-11-30", "transitions_to_alumni": True},
        headers=headers,
    )
    assert offboarding.status_code == 200, offboarding.text
    offboarding_id = offboarding.json()["id"]

    detail = (await client.get(f"/api/v1/offboarding/{offboarding_id}", headers=headers)).json()
    assert len(detail["tasks"]) == 6  # default task checklist
    assert any(task["category"] == "knowledge" for task in detail["tasks"])

    for task in detail["tasks"]:
        done = await client.post(
            f"/api/v1/offboarding/{offboarding_id}/tasks/{task['id']}/complete",
            json={"notes": "done"}, headers=headers,
        )
        assert done.status_code == 200, done.text

    exit_interview = await client.post(
        f"/api/v1/offboarding/{offboarding_id}/exit-interview",
        json={"feedback": "Great culture, wanted more scope", "reason": "Growth"},
        headers=headers,
    )
    assert exit_interview.status_code == 200, exit_interview.text

    completed = await client.post(f"/api/v1/offboarding/{offboarding_id}/complete", headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    events = await _events(client, headers, "employee.offboarded")
    assert len(events) == 1

    # employee is now inactive and an alumni profile exists
    employees = (await client.get("/api/v1/employees", params={"status": "inactive"}, headers=headers)).json()
    assert next(e for e in employees if e["id"] == me)["status"] == "inactive"
    alumni = (await client.get("/api/v1/offboarding/alumni/list", headers=headers)).json()
    assert len(alumni) == 1
    assert alumni[0]["employee_id"] == me

    boomerang = await client.post(
        f"/api/v1/offboarding/alumni/{alumni[0]['id']}/boomerang", headers=headers
    )
    assert boomerang.status_code == 200 and boomerang.json()["status"] == "boomerang"


# ============================================================== compliance

@pytest.mark.asyncio
async def test_compliance_expiry_and_training(client):
    org = await register_org(client, email="p11cmp@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    doc = await client.post(
        "/api/v1/compliance/documents",
        json={"employee_id": me, "document_type": "visa", "title": "Work Visa",
              "expires_at": (date.today() + timedelta(days=10)).isoformat()},
        headers=headers,
    )
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["id"]

    expired = await client.post(
        "/api/v1/compliance/documents",
        json={"employee_id": me, "document_type": "contract", "title": "Contract",
              "expires_at": (date.today() - timedelta(days=5)).isoformat()},
        headers=headers,
    )
    assert expired.status_code == 200, expired.text

    requirement = await client.post(
        "/api/v1/compliance/requirements",
        json={"name": "Security Awareness", "category": "security", "frequency_days": 365},
        headers=headers,
    )
    assert requirement.status_code == 200, requirement.text
    requirement_id = requirement.json()["id"]

    training = await client.post(
        "/api/v1/compliance/trainings",
        json={"employee_id": me, "requirement_id": requirement_id, "provider": "VCOS Academy"},
        headers=headers,
    )
    assert training.status_code == 200, training.text

    docs = (await client.get("/api/v1/compliance/documents", headers=headers)).json()
    by_title = {item["title"]: item for item in docs}
    assert by_title["Work Visa"]["status"] == "expiring"
    assert by_title["Contract"]["status"] == "expired"

    overview = (await client.get("/api/v1/compliance/overview", headers=headers)).json()
    assert overview["documents"]["expiring_30"] >= 1
    assert overview["documents"]["expired"] >= 1
    assert overview["trainings"]["total_completions"] >= 1
    assert overview["trainings"]["missing"] == 0

    renewed = await client.post(
        f"/api/v1/compliance/documents/{doc_id}/renew",
        json={"expires_at": (date.today() + timedelta(days=400)).isoformat()},
        headers=headers,
    )
    assert renewed.status_code == 200 and renewed.json()["status"] == "valid"

    mine = (await client.get("/api/v1/compliance/my", headers=headers)).json()
    assert len(mine["documents"]) == 2


# ============================================================== workforce & succession

@pytest.mark.asyncio
async def test_workforce_planning_snapshot_and_succession(client):
    org = await register_org(client, email="p11wfs@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    plan = await client.post(
        "/api/v1/workforce/plans",
        json={"title": "Engineering expansion", "horizon": "quarter", "department": "Engineering",
              "headcount_target": 5, "skill_needs": ["Python", "AI"], "budget": 500000, "status": "approved"},
        headers=headers,
    )
    assert plan.status_code == 200, plan.text

    succession = await client.post(
        "/api/v1/workforce/succession",
        json={"position_title": "Engineering Director", "candidate_employee_id": me, "readiness": 85, "rationale": "Strong delivery"},
        headers=headers,
    )
    assert succession.status_code == 200, succession.text
    succession_id = succession.json()["id"]
    assert succession.json()["status"] == "ready"

    updated = await client.patch(
        f"/api/v1/workforce/succession/{succession_id}", json={"readiness": 20}, headers=headers
    )
    assert updated.status_code == 200 and updated.json()["status"] == "identified"

    snapshot = await client.post("/api/v1/workforce/snapshots", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["headcount"] >= 1

    analytics = (await client.get("/api/v1/workforce/analytics", headers=headers)).json()
    assert analytics["headcount"] >= 1
    assert analytics["succession_pipeline"]["total"] == 1

    needs = (await client.get("/api/v1/workforce/hiring-needs", headers=headers)).json()
    assert "total_open_positions" in needs

    snapshots = (await client.get("/api/v1/workforce/snapshots", headers=headers)).json()
    assert len(snapshots) >= 1


# ============================================================== wellbeing

@pytest.mark.asyncio
async def test_wellbeing_risk_patterns(client):
    org = await register_org(client, email="p11wb@work.test.co")
    headers = org["headers"]

    low = await client.post(
        "/api/v1/wellbeing/check-ins",
        json={"metrics": {"meeting_hours": 8, "task_load": 5, "leave_balance_days": 12, "recognitions": 3, "engagement": 4}},
        headers=headers,
    )
    assert low.status_code == 200, low.text
    assert low.json()["risk_level"] == "low"

    high = await client.post(
        "/api/v1/wellbeing/check-ins",
        json={"metrics": {"meeting_hours": 45, "task_load": 30, "learning_load": 8, "leave_balance_days": 1, "recognitions": 0, "engagement": 0}},
        headers=headers,
    )
    assert high.status_code == 200, high.text
    assert high.json()["risk_level"] == "high"
    assert len(high.json()["signals"]) >= 4

    my = (await client.get("/api/v1/wellbeing/my", headers=headers)).json()
    assert len(my) == 2

    overview = (await client.get("/api/v1/wellbeing/overview", headers=headers)).json()
    assert overview["total_checks"] == 2
    assert overview["high"] == 1
    assert overview["at_risk_employees"] == 1

    recommendations = (await client.get("/api/v1/wellbeing/recommendations", headers=headers)).json()
    assert recommendations[0]["priority"] == "high"


# ============================================================== payroll integration

@pytest.mark.asyncio
async def test_payroll_integration_references(client):
    org = await register_org(client, email="p11pay@work.test.co")
    headers = org["headers"]

    provider = await client.post(
        "/api/v1/payroll/providers",
        json={"name": "Global Payroll Co", "provider": "adp", "config": {"endpoint": "https://api.example.com"}},
        headers=headers,
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["id"]

    run = await client.post(
        "/api/v1/payroll/runs",
        json={"provider_id": provider_id, "period_start": "2026-07-01", "period_end": "2026-07-31",
              "employee_count": 3, "gross_amount": 45000.0, "payload": {"employees": ["e1", "e2", "e3"]}},
        headers=headers,
    )
    assert run.status_code == 200, run.text
    run_id = run.json()["id"]

    synced = await client.post(
        f"/api/v1/payroll/runs/{run_id}/synced", json={"reference_id": "ADP-RUN-9001"}, headers=headers
    )
    assert synced.status_code == 200 and synced.json()["status"] == "synced"

    runs = (await client.get("/api/v1/payroll/runs", headers=headers)).json()
    assert len(runs) == 1
    assert runs[0]["reference_id"] == "ADP-RUN-9001"
    assert runs[0]["provider_name"] == "Global Payroll Co"

    overview = (await client.get("/api/v1/payroll/overview", headers=headers)).json()
    assert overview["runs"]["synced"] == 1
    assert overview["latest_synced_gross"] == 45000.0


@pytest.mark.asyncio
async def test_payroll_rbac_finance_can_view_employee_cannot(client):
    org = await register_org(client, email="p11pay2@work.test.co")
    headers = org["headers"]
    finance = await _invite_employee(client, headers, email="fin.pay2@work.test.co", role="finance")
    employee = await _invite_employee(client, headers, email="emp.pay2@work.test.co")

    assert (await client.get("/api/v1/payroll/providers", headers=finance)).status_code == 200
    assert (await client.get("/api/v1/payroll/providers", headers=employee)).status_code == 403
    assert (await client.get("/api/v1/payroll/overview", headers=employee)).status_code == 403


# ============================================================== hub dashboard & AI

@pytest.mark.asyncio
async def test_hr_dashboard_aggregates(client):
    org = await register_org(client, email="p11hub@work.test.co")
    headers = org["headers"]

    dashboard = (await client.get("/api/v1/hr/dashboard", headers=headers)).json()
    for key in ("workforce", "recruitment", "leave", "performance", "offboarding", "compliance", "assets", "wellbeing", "payroll"):
        assert key in dashboard
    assert dashboard["workforce"]["headcount"] >= 1
    assert "hiring_needs" in dashboard["workforce"]


@pytest.mark.asyncio
async def test_hr_ai_companion(client):
    org = await register_org(client, email="p11ai@work.test.co")
    headers = org["headers"]

    answer = await client.post("/api/v1/hr/ai/ask", json={"question": "What is my leave balance?"}, headers=headers)
    assert answer.status_code == 200, answer.text
    assert "days" in answer.json()["answer"]

    answer = await client.post("/api/v1/hr/ai/ask", json={"question": "What does attrition look like?"}, headers=headers)
    assert answer.status_code == 200, answer.text
    assert "attrition" in answer.json()["answer"].lower()

    answer = await client.post("/api/v1/hr/ai/ask", json={"question": "Who should we hire next?"}, headers=headers)
    assert answer.status_code == 200, answer.text
    assert "open position" in answer.json()["answer"]

    bad = await client.post("/api/v1/hr/ai/ask", json={"question": ""}, headers=headers)
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_hr_employee_lifecycle_endpoint(client):
    org = await register_org(client, email="p11lc@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    promoted = await client.post(
        f"/api/v1/hr/employees/{me}/promote", json={"designation": "Senior Platform Engineer"}, headers=headers
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["new_designation"] == "Senior Platform Engineer"

    events = await _events(client, headers, "employee.promoted")
    assert len(events) == 1

    lifecycle = (await client.get(f"/api/v1/hr/employees/{me}/lifecycle", headers=headers)).json()
    assert lifecycle["employee"]["designation"] == "Senior Platform Engineer"
    assert "attendance" in lifecycle and "performance" in lifecycle and "assets" in lifecycle


# ============================================================== RBAC & multi-tenancy

@pytest.mark.asyncio
async def test_hr_rbac_and_multi_tenant_isolation(client):
    org_a = await register_org(client, email="a11iso@work.test.co")
    org_b = await register_org(client, email="b11iso@work.test.co", name="Other Corp", slug="other11")
    headers_a, headers_b = org_a["headers"], org_b["headers"]

    # org A configures a shift and leave
    await client.post(
        "/api/v1/attendance/shifts",
        json={"name": "A Shift", "start_time": "09:00", "end_time": "17:00"},
        headers=headers_a,
    )
    types_a = (await client.get("/api/v1/leave/types", headers=headers_a)).json()
    annual = next(item for item in types_a if item["code"] == "annual")
    await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": annual["id"], "start_date": "2026-12-01", "end_date": "2026-12-02", "reason": "Holiday"},
        headers=headers_a,
    )

    # org B cannot see org A's shifts, holidays, leave requests or dashboard data
    shifts_b = (await client.get("/api/v1/attendance/shifts", headers=headers_b)).json()
    assert all(shift["name"] != "A Shift" for shift in shifts_b)
    requests_b = (await client.get("/api/v1/leave/requests", headers=headers_b)).json()
    assert requests_b == []
    dashboard_b = (await client.get("/api/v1/hr/dashboard", headers=headers_b)).json()
    assert dashboard_b["leave"]["pending_count"] == 0

    # employees cannot manage HR
    employee = await _invite_employee(client, headers_a, email="emp.iso11@work.test.co")
    assert (await client.post("/api/v1/attendance/shifts", json={"name": "Nope"}, headers=employee)).status_code == 403
    assert (await client.post("/api/v1/recruitment/jobs", json={"title": "Nope"}, headers=employee)).status_code == 403
    assert (await client.post("/api/v1/workforce/plans", json={"title": "Nope"}, headers=employee)).status_code == 403
    assert (await client.post("/api/v1/payroll/providers", json={"name": "Nope"}, headers=employee)).status_code == 403
    # but self-service is allowed
    assert (await client.get("/api/v1/leave/balances", headers=employee)).status_code == 200
    assert (await client.get("/api/v1/attendance/today", headers=employee)).status_code == 200


# ============================================================== workers

@pytest.mark.asyncio
async def test_phase11_workers(db_session):
    from app.workers.attendance_worker import run_once as attendance_run
    from app.workers.compliance_worker import run_once as compliance_run
    from app.workers.hiring_worker import run_once as hiring_run
    from app.workers.performance_worker import run_once as performance_run
    from app.workers.wellbeing_worker import run_once as wellbeing_run
    from app.workers.workforce_worker import run_once as workforce_run

    assert await attendance_run(db=db_session) >= 0
    assert await compliance_run(db=db_session) >= 0
    assert await hiring_run(db=db_session) >= 0
    assert await performance_run(db=db_session) >= 0
    assert await wellbeing_run(db=db_session) >= 0
    assert await workforce_run(db=db_session) >= 0
