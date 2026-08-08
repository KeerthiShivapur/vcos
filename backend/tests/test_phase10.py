"""Phase 10 — Learning & Growth Operating System tests.

Covers the full learning lifecycle: profiles, course catalog + enrollment +
completion pipeline, learning paths, the skills graph / gap analysis / org
skill map, assessments with AI evaluation, certifications, mentorship,
career paths + promotion signals, academy, onboarding plans, personalized
recommendations, the learning AI companion, RBAC gating, multi-tenant
isolation and the Phase 10 background workers.
"""

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


async def _seed_course(client, headers, *, title="Python Mastery"):
    course = await client.post(
        "/api/v1/learning/courses",
        json={
            "title": title,
            "description": "Deep dive into Python for platform engineers.",
            "category": "Engineering",
            "difficulty": "intermediate",
            "duration_minutes": 120,
            "format": "self_paced",
            "certificate_title": "Python Mastery Certificate",
            "skills": ["Python", "Backend Engineering"],
            "tags": ["python", "backend"],
        },
        headers=headers,
    )
    assert course.status_code == 201, course.text
    return course.json()


async def _add_module_lesson_quiz(client, headers, course_id):
    module = await client.post(
        f"/api/v1/learning/courses/{course_id}/modules",
        json={"title": "Core Language", "description": "Fundamentals"},
        headers=headers,
    )
    assert module.status_code == 201, module.text
    lesson = await client.post(
        f"/api/v1/learning/courses/{course_id}/lessons",
        json={"title": "Data Structures", "module_id": module.json()["id"], "duration_minutes": 30},
        headers=headers,
    )
    assert lesson.status_code == 201, lesson.text
    quiz = await client.post(
        f"/api/v1/learning/courses/{course_id}/quizzes",
        json={
            "title": "Fundamentals quiz",
            "questions": [
                {"text": "Which type is immutable?", "options": ["list", "tuple", "dict", "set"],
                 "answer_index": 1, "points": 2},
            ],
            "passing_score": 70,
        },
        headers=headers,
    )
    assert quiz.status_code == 201, quiz.text
    return module.json()["id"], lesson.json()["id"]


# ============================================================== profile & history

@pytest.mark.asyncio
async def test_learning_profile_and_history(client):
    org = await register_org(client, email="p10prof@work.test.co")
    headers = org["headers"]

    profile = (await client.get("/api/v1/learning/profile", headers=headers)).json()
    assert profile["learning_score"] >= 0
    assert profile["employee_id"]

    updated = await client.patch(
        "/api/v1/learning/profile",
        json={
            "career_stage": "mid",
            "preferred_learning": ["video", "hands-on"],
            "weekly_learning_hours": 5,
            "career_goals": "Become a staff engineer",
            "learning_goals": ["Python", "System Design"],
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["career_stage"] == "mid"
    assert updated.json()["career_goals"] == "Become a staff engineer"

    history = (await client.get("/api/v1/learning/history", headers=headers)).json()
    assert isinstance(history, list)


@pytest.mark.asyncio
async def test_learning_dashboard_aggregates(client):
    org = await register_org(client, email="p10dash@work.test.co")
    headers = org["headers"]
    course = await _seed_course(client, headers)
    await _add_module_lesson_quiz(client, headers, course["id"])

    dashboard = (await client.get("/api/v1/learning/dashboard", headers=headers)).json()
    assert dashboard["profile"]["learning_score"] >= 0
    enroll = await client.post(f"/api/v1/learning/courses/{course['id']}/enroll", headers=headers)
    assert enroll.status_code == 201, enroll.text
    dashboard = (await client.get("/api/v1/learning/dashboard", headers=headers)).json()
    assert any(c["id"] == course["id"] for c in dashboard["trending"])
    assert "skill_gaps" in dashboard
    assert "certificates" in dashboard
    assert "learning_paths" in dashboard
    assert "upcoming_assessments" in dashboard


# ============================================================== courses

@pytest.mark.asyncio
async def test_course_lifecycle_and_completion(client):
    org = await register_org(client, email="p10crse@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    course = await _seed_course(client, headers)
    _, lesson_id = await _add_module_lesson_quiz(client, headers, course["id"])

    detail = (await client.get(f"/api/v1/learning/courses/{course['id']}", headers=headers)).json()
    assert detail["skills"] == ["Python", "Backend Engineering"]
    assert len(detail["modules"]) == 1
    assert len(detail["lessons"]) == 1
    assert len(detail["quizzes"]) == 1

    enroll = await client.post(
        f"/api/v1/learning/courses/{course['id']}/enroll", headers=headers
    )
    assert enroll.status_code == 201, enroll.text
    enrollment_id = enroll.json()["id"]

    mine = (await client.get("/api/v1/learning/courses/my/enrollments", headers=headers)).json()
    assert any(e["id"] == enrollment_id for e in mine)

    progress = await client.post(
        f"/api/v1/learning/courses/enrollments/{enrollment_id}/lessons/{lesson_id}/complete",
        headers=headers,
    )
    assert progress.status_code == 200, progress.text
    assert progress.json()["progress"] == 100.0

    done = await client.post(
        f"/api/v1/learning/courses/enrollments/{enrollment_id}/complete", headers=headers
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"

    profile = (await client.get("/api/v1/learning/profile", headers=headers)).json()
    assert profile["completed_courses"] >= 1

    graph = (await client.get("/api/v1/learning/skills", headers=headers)).json()
    levels = {row["name"].lower(): row["level"] for row in graph}
    assert levels.get("python", 0) >= 2

    history = (await client.get("/api/v1/learning/history", headers=headers)).json()
    assert any(h["kind"] == "course_completion" for h in history)

    certificates = (await client.get("/api/v1/learning/certifications/my/earned", headers=headers)).json()
    assert any(c["name"] == "Python Mastery Certificate" and c["course_id"] == course["id"] for c in certificates)

    events = (await client.get("/api/v1/intelligence/events", headers=headers)).json()
    assert any(e["name"] == "course.completed" for e in events)

    await client.post("/api/v1/intelligence/events/process", headers=headers)
    lessons = (await client.get("/api/v1/intelligence/learning/lessons", headers=headers)).json()
    assert any("Course completed" in l["title"] for l in lessons)

    # cleanup endpoints
    assert (await client.delete(f"/api/v1/learning/courses/{course['id']}", headers=headers)).status_code == 200
    assert me  # keep me referenced for lint


# ============================================================== learning paths

@pytest.mark.asyncio
async def test_learning_path_flow(client):
    org = await register_org(client, email="p10path@work.test.co")
    headers = org["headers"]
    course_a = await _seed_course(client, headers, title="Python Mastery")
    course_b = await _seed_course(client, headers, title="Backend Architecture")

    path = await client.post(
        "/api/v1/learning/paths",
        json={
            "title": "Backend Engineer Track",
            "description": "Grow into a backend engineer.",
            "category": "Engineering",
            "target_role": "Backend Engineer",
            "difficulty": "intermediate",
            "estimated_days": 30,
            "tags": ["backend"],
        },
        headers=headers,
    )
    assert path.status_code == 201, path.text
    path_id = path.json()["id"]

    step_a = await client.post(
        f"/api/v1/learning/paths/{path_id}/steps",
        json={"title": "Learn Python", "course_id": course_a["id"], "order": 1, "expected_days": 7},
        headers=headers,
    )
    assert step_a.status_code == 201, step_a.text
    step_b = await client.post(
        f"/api/v1/learning/paths/{path_id}/steps",
        json={"title": "Learn Backend Architecture", "course_id": course_b["id"], "order": 2, "expected_days": 10},
        headers=headers,
    )
    assert step_b.status_code == 201, step_b.text

    enroll = await client.post(f"/api/v1/learning/paths/{path_id}/enroll", headers=headers)
    assert enroll.status_code == 201, enroll.text

    detail = (await client.get(f"/api/v1/learning/paths/{path_id}", headers=headers)).json()
    assert detail["enrolled"] is True
    assert len(detail["steps"]) == 2

    done = await client.post(
        f"/api/v1/learning/paths/enrollments/{enroll.json()['id']}/steps/{step_a.json()['id']}/complete",
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["progress"] == 50.0

    done_b = await client.post(
        f"/api/v1/learning/paths/enrollments/{enroll.json()['id']}/steps/{step_b.json()['id']}/complete",
        headers=headers,
    )
    assert done_b.status_code == 200, done_b.text
    assert done_b.json()["status"] == "completed"

    mine = (await client.get("/api/v1/learning/paths/my/enrollments", headers=headers)).json()
    assert any(e["path_id"] == path_id and e["progress"] == 100.0 for e in mine)


# ============================================================== skills & gaps

@pytest.mark.asyncio
async def test_skill_gaps_and_org_skill_map(client):
    org = await register_org(client, email="p10skill@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    career_path = await client.post(
        "/api/v1/learning/career",
        json={
            "title": "Engineering Ladder",
            "description": "From engineer to staff.",
            "department": "Engineering",
            "levels": ["Engineer", "Senior Engineer", "Staff Engineer"],
            "steps": [
                {
                    "title": "Senior Engineer",
                    "position": 1,
                    "level": "Senior Engineer",
                    "required_skills": [{"name": "Python", "level": 4}, {"name": "System Design", "level": 3}],
                    "required_years": 3,
                    "criteria": {"mentorship": True},
                }
            ],
        },
        headers=headers,
    )
    assert career_path.status_code == 201, career_path.text

    gaps = await client.post("/api/v1/learning/skills/gaps/refresh", headers=headers)
    assert gaps.status_code == 200, gaps.text
    assert gaps.json()["gaps"] >= 2

    gap_list = (await client.get("/api/v1/learning/skills/gaps", headers=headers)).json()
    assert any(g["skill_name"] == "Python" for g in gap_list)

    boost = await client.post(
        "/api/v1/learning/skills/Python/boost",
        json={"points": 3, "reason": "Course completed"},
        headers=headers,
    )
    assert boost.status_code == 200, boost.text
    assert boost.json()["level"] == 5

    refreshed = await client.post("/api/v1/learning/skills/gaps/refresh", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["gaps"] == 1

    snapshot = await client.post("/api/v1/learning/skills/snapshot/refresh", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["skill_count"] >= 1

    org_map = (await client.get("/api/v1/learning/skills/org-map", headers=headers)).json()
    assert any(row["skill_name"] == "Python" for row in org_map)

    who = (await client.get("/api/v1/learning/skills/who/Python?min_level=3", headers=headers)).json()
    assert any(row["employee_id"] == me for row in who)

    mentors = (await client.get("/api/v1/learning/skills/mentors/Python?min_level=4", headers=headers)).json()
    assert isinstance(mentors, list)


# ============================================================== assessments

@pytest.mark.asyncio
async def test_assessment_workflow(client):
    org = await register_org(client, email="p10assess@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    assessment = await client.post(
        "/api/v1/learning/assessments",
        json={
            "title": "Python Skill Assessment",
            "description": "Measures Python proficiency.",
            "category": "Engineering",
            "difficulty": "intermediate",
            "skills": ["Python"],
            "passing_score": 70,
            "duration_minutes": 30,
            "questions": [
                {"text": "Which type is immutable?", "options": ["list", "tuple", "dict", "set"], "answer_index": 1, "points": 2},
                {"text": "What is 2**3?", "options": ["6", "8", "9", "10"], "answer_index": 1, "points": 1},
            ],
        },
        headers=headers,
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["id"]

    assign = await client.post(
        f"/api/v1/learning/assessments/{assessment_id}/assign",
        json={"employee_id": me},
        headers=headers,
    )
    assert assign.status_code == 201, assign.text
    attempt_id = assign.json()["id"]

    submit = await client.post(
        f"/api/v1/learning/assessments/attempts/{attempt_id}/submit",
        json={"answers": [{"question_index": 0, "answer": 1}, {"question_index": 1, "answer": 1}]},
        headers=headers,
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] in ("submitted", "evaluated")

    evaluated = await client.post(
        f"/api/v1/learning/assessments/attempts/{attempt_id}/evaluate",
        json={},
        headers=headers,
    )
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["passed"] is True
    assert evaluated.json()["score"] == 100.0

    attempts = (await client.get("/api/v1/learning/assessments/my/attempts", headers=headers)).json()
    assert attempts, "attempt history should exist"

    pending = (await client.get("/api/v1/learning/assessments/reviews/pending", headers=headers)).json()
    assert isinstance(pending, list)

    history = (await client.get("/api/v1/learning/history", headers=headers)).json()
    assert any(h["kind"] == "assessment" for h in history)


# ============================================================== certifications

@pytest.mark.asyncio
async def test_certification_workflow(client):
    org = await register_org(client, email="p10cert@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    certification = await client.post(
        "/api/v1/learning/certifications",
        json={
            "name": "Certified Python Developer",
            "issuer": "VCOS Academy",
            "category": "Engineering",
            "description": "Industry certification for Python.",
            "skills": ["Python"],
            "cost": 0.0,
            "validity_years": 2,
        },
        headers=headers,
    )
    assert certification.status_code == 201, certification.text
    cert_id = certification.json()["id"]

    categories = (await client.get("/api/v1/learning/certifications/categories", headers=headers)).json()
    assert "Engineering" in categories

    started = await client.post(
        f"/api/v1/learning/certifications/{cert_id}/attempts", headers=headers
    )
    assert started.status_code == 201, started.text
    attempt_id = started.json()["id"]

    completed = await client.post(
        f"/api/v1/learning/certifications/attempts/{attempt_id}/complete",
        json={"score": 92, "passed": True, "evidence": "External exam transcript"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["passed"] is True
    assert completed.json()["credential_id"].startswith("VCOS-")

    earned = (await client.get("/api/v1/learning/certifications/my/earned", headers=headers)).json()
    assert any(c["certification_id"] == cert_id and c["status"] == "valid" for c in earned)

    recommended = (await client.get("/api/v1/learning/certifications/my/recommended", headers=headers)).json()
    assert isinstance(recommended, list)

    expiring = (await client.get("/api/v1/learning/certifications/expiring?days=90", headers=headers)).json()
    assert isinstance(expiring, list)

    expired = await client.post("/api/v1/learning/certifications/expired/mark", headers=headers)
    assert expired.status_code == 200, expired.text

    detail = (await client.get(f"/api/v1/learning/certifications/{cert_id}", headers=headers)).json()
    assert detail["name"] == "Certified Python Developer"
    assert me  # keep referenced


# ============================================================== mentorship

@pytest.mark.asyncio
async def test_mentorship_workflow(client):
    org = await register_org(client, email="p10mentor@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    mentee = await _invite_employee(client, headers, email="mentee@mentor.test.co")

    mentor = await client.post(
        "/api/v1/learning/mentorship/profile",
        json={
            "expertise": ["Python", "System Design"],
            "skills": ["Python"],
            "availability": "weekly",
            "weekly_slots": 2,
            "bio": "Senior engineer happy to mentor.",
            "topics": ["Career growth", "Python"],
        },
        headers=headers,
    )
    assert mentor.status_code == 200, mentor.text

    my_profile = (await client.get("/api/v1/learning/mentorship/profile", headers=headers)).json()
    assert my_profile["exists"] is True
    assert my_profile["availability"] == "weekly"

    mentors = (await client.get("/api/v1/learning/mentorship/mentors", headers=headers)).json()
    assert any(m["employee_id"] == me for m in mentors)

    recommended = (await client.get(
        "/api/v1/learning/mentorship/mentors/recommend", headers=mentee
    )).json()
    assert recommended, "mentee should get mentor recommendations"

    requested = await client.post(
        f"/api/v1/learning/mentorship/mentors/{me}/request",
        json={"topic": "Career growth", "goals": ["Lead projects"]},
        headers=mentee,
    )
    assert requested.status_code == 201, requested.text
    mentorship_id = requested.json()["id"]

    incoming = (await client.get(
        "/api/v1/learning/mentorship/requests?role=mentor&status=pending", headers=headers
    )).json()
    assert any(m["id"] == mentorship_id for m in incoming)

    accepted = await client.post(
        f"/api/v1/learning/mentorship/{mentorship_id}/respond",
        json={"accept": True},
        headers=headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"

    session = await client.post(
        f"/api/v1/learning/mentorship/{mentorship_id}/sessions",
        json={"title": "Kickoff", "notes": "Set goals", "kind": "call", "duration_minutes": 45},
        headers=mentee,
    )
    assert session.status_code == 201, session.text

    feedback = await client.post(
        f"/api/v1/learning/mentorship/{mentorship_id}/feedback",
        json={"rating": 5, "comment": "Great session"},
        headers=mentee,
    )
    assert feedback.status_code == 201, feedback.text

    finished = await client.post(
        f"/api/v1/learning/mentorship/{mentorship_id}/complete", headers=headers
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "completed"


# ============================================================== career

@pytest.mark.asyncio
async def test_career_path_and_promotion_signal(client):
    org = await register_org(client, email="p10career@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    path = await client.post(
        "/api/v1/learning/career",
        json={
            "title": "Engineering Ladder",
            "description": "Engineer to staff.",
            "department": "Engineering",
            "levels": ["Engineer", "Senior Engineer", "Staff Engineer"],
            "steps": [
                {
                    "title": "Senior Engineer",
                    "position": 1,
                    "level": "Senior Engineer",
                    "required_skills": [{"name": "Python", "level": 4}],
                    "required_years": 2,
                }
            ],
        },
        headers=headers,
    )
    assert path.status_code == 201, path.text
    path_id = path.json()["id"]

    detail = (await client.get(f"/api/v1/learning/career/{path_id}", headers=headers)).json()
    assert len(detail["steps"]) == 1
    assert detail["steps"][0]["required_skills"] == [{"name": "Python", "level": 4}]

    progress = (await client.get("/api/v1/learning/career/my/progress", headers=headers)).json()
    assert "readiness" in progress
    assert "current_role" in progress
    assert "next_role" in progress

    required = (await client.get("/api/v1/learning/career/my/required-skills", headers=headers)).json()
    assert any(r["skill"] == "Python" for r in required)

    signal = await client.post(
        "/api/v1/learning/career/my/promotion-signals/detect", headers=headers
    )
    assert signal.status_code == 200, signal.text

    signals = (await client.get("/api/v1/learning/career/signals", headers=headers)).json()
    if signal.json()["detected"]:
        signal_id = signal.json()["id"]
        assert any(s["id"] == signal_id for s in signals)
        reviewed = await client.post(
            f"/api/v1/learning/career/signals/{signal_id}/review",
            json={"status": "approved"},
            headers=headers,
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "approved"


# ============================================================== academy

@pytest.mark.asyncio
async def test_academy_flow(client):
    org = await register_org(client, email="p10acad@work.test.co")
    headers = org["headers"]
    course = await _seed_course(client, headers)

    academy = await client.post(
        "/api/v1/learning/academies",
        json={
            "name": "Engineering Academy",
            "description": "All engineering tracks.",
            "category": "Engineering",
            "curriculum": ["Foundations", "Advanced"],
        },
        headers=headers,
    )
    assert academy.status_code == 201, academy.text
    academy_id = academy.json()["id"]

    linked = await client.post(
        f"/api/v1/learning/academies/{academy_id}/courses",
        json={"course_id": course["id"]},
        headers=headers,
    )
    assert linked.status_code == 201, linked.text

    joined = await client.post(f"/api/v1/learning/academies/{academy_id}/join", headers=headers)
    assert joined.status_code == 201, joined.text

    mine = (await client.get("/api/v1/learning/academies/my", headers=headers)).json()
    assert any(a["id"] == academy_id for a in mine)

    removed = await client.delete(
        f"/api/v1/learning/academies/{academy_id}/courses/{course['id']}", headers=headers
    )
    assert removed.status_code == 200, removed.text

    left = await client.post(f"/api/v1/learning/academies/{academy_id}/leave", headers=headers)
    assert left.status_code == 200, left.text


# ============================================================== onboarding

@pytest.mark.asyncio
async def test_onboarding_plan(client):
    org = await register_org(client, email="p10onb@work.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    plan = await client.post(
        "/api/v1/learning/onboarding/plans",
        json={"employee_id": me, "target_days": 14},
        headers=headers,
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    plans = (await client.get("/api/v1/learning/onboarding/plans", headers=headers)).json()
    assert any(p["id"] == plan_id for p in plans)

    detail = (await client.get(f"/api/v1/learning/onboarding/plans/{plan_id}", headers=headers)).json()
    tasks = detail["tasks"]
    assert tasks, "plan should auto-generate a checklist"
    assert any(t["category"] == "introduction" for t in tasks)

    last = None
    for task in tasks:
        done = await client.post(
            f"/api/v1/learning/onboarding/plans/{plan_id}/tasks/{task['id']}/complete",
            headers=headers,
        )
        assert done.status_code == 200, done.text
        last = done.json()

    assert last["plan_status"] == "completed"

    profile = (await client.get("/api/v1/learning/profile", headers=headers)).json()
    assert profile["learning_score"] >= 8

    history = (await client.get("/api/v1/learning/history", headers=headers)).json()
    assert any(h["kind"] == "onboarding" for h in history)


# ============================================================== recommendations & AI

@pytest.mark.asyncio
async def test_recommendations_refresh_and_ai_ask(client):
    org = await register_org(client, email="p10rec@work.test.co")
    headers = org["headers"]
    await _seed_course(client, headers, title="Python Mastery")
    await client.post("/api/v1/learning/career",
        json={
            "title": "Engineering Ladder",
            "description": "Engineer to staff.",
            "department": "Engineering",
            "levels": ["Engineer", "Senior Engineer"],
            "steps": [
                {
                    "title": "Senior Engineer",
                    "position": 1,
                    "level": "Senior Engineer",
                    "required_skills": [{"name": "Python", "level": 4}],
                    "required_years": 2,
                }
            ],
        },
        headers=headers,
    )
    await client.post("/api/v1/learning/skills/gaps/refresh", headers=headers)

    refreshed = await client.post(
        "/api/v1/recommendations/refresh", headers=headers
    )
    assert refreshed.status_code == 200, refreshed.text

    feed = (await client.get("/api/v1/recommendations", headers=headers)).json()
    items = feed if isinstance(feed, list) else feed.get("items", [])
    assert any(item.get("kind") == "course" for item in items)

    ask = await client.post(
        "/api/v1/learning/ai/ask",
        json={"question": "What should I learn next to become a senior engineer?"},
        headers=headers,
    )
    assert ask.status_code == 200, ask.text
    payload = ask.json()
    assert payload["intent"] in {"learn", "roadmap", "promotion", "plan"}
    assert payload["response"]


# ============================================================== RBAC & tenancy

@pytest.mark.asyncio
async def test_learning_rbac_employee_denied(client):
    org = await register_org(client, email="p10rbac@work.test.co")
    headers = org["headers"]
    employee = await _invite_employee(client, headers, email="worker@rbac.test.co")

    denied = await client.post(
        "/api/v1/learning/courses",
        json={"title": "Nope", "category": "X"},
        headers=employee,
    )
    assert denied.status_code == 403

    denied_path = await client.post(
        "/api/v1/learning/paths",
        json={"title": "Nope"},
        headers=employee,
    )
    assert denied_path.status_code == 403

    # self-service learning stays open
    profile = await client.get("/api/v1/learning/profile", headers=employee)
    assert profile.status_code == 200
    dashboard = await client.get("/api/v1/learning/dashboard", headers=employee)
    assert dashboard.status_code == 200

    # employees can enroll and learn
    course = await _seed_course(client, headers)
    enroll = await client.post(f"/api/v1/learning/courses/{course['id']}/enroll", headers=employee)
    assert enroll.status_code == 201, enroll.text


@pytest.mark.asyncio
async def test_learning_tenancy_isolation(client):
    org_a = await register_org(client, email="p10tenA@work.test.co")
    org_b = await register_org(client, email="p10tenB@work.test.co")
    course_a = await _seed_course(client, org_a["headers"], title="Org A Course")

    listing_b = (await client.get("/api/v1/learning/courses", headers=org_b["headers"])).json()
    assert all(c["title"] != "Org A Course" for c in listing_b)

    missing = await client.get(
        f"/api/v1/learning/courses/{course_a['id']}", headers=org_b["headers"]
    )
    assert missing.status_code == 404

    profile_a = (await client.get("/api/v1/learning/profile", headers=org_a["headers"])).json()
    profile_b = (await client.get("/api/v1/learning/profile", headers=org_b["headers"])).json()
    assert profile_a["employee_id"] != profile_b["employee_id"]


# ============================================================== workers

@pytest.mark.asyncio
async def test_learning_workers_run_on_demand(client):
    org = await register_org(client, email="p10wrk@work.test.co")
    headers = org["headers"]
    await _seed_course(client, headers)

    workers = (await client.get("/api/v1/intelligence/workers", headers=headers)).json()
    names = {w["name"] for w in workers}
    assert {"skill", "certification", "mentor", "assessment"} <= names

    for name in ("skill", "certification", "mentor", "assessment"):
        run = await client.post(f"/api/v1/intelligence/workers/{name}/run", headers=headers)
        assert run.status_code == 200, run.text
        assert "processed" in run.json()

    org_map = (await client.get("/api/v1/learning/skills/org-map", headers=headers)).json()
    assert isinstance(org_map, list)
