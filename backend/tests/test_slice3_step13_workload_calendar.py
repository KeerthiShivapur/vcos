"""Vertical Slice 3 — Step 13 workload & calendar integration tests.

The calendar feed merges calendar events, scheduled meetings, task
deadlines and approved leave into one time-sorted stream. Tasks gain
server-side due-date filtering. Workload gains a per-team summary and
crossing the overload threshold notifies the employee (and only on the
first crossing, so the worker never spams).
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _notifications(db, organization_id, type=None):
    from app.models.notification import Notification

    stmt = select(Notification).where(Notification.organization_id == organization_id)
    if type:
        stmt = stmt.where(Notification.type == type)
    return (await db.execute(stmt)).scalars().all()


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _create_project(client, headers, name="Step13 Project"):
    r = await client.post("/api/v1/projects", json={"name": name, "status": "active"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_task(client, headers, title, due_date, estimate_hours=None, assignee_id=None, status="todo"):
    payload = {"title": title, "due_date": due_date, "estimate_hours": estimate_hours, "status": status}
    if assignee_id:
        payload["assignee_id"] = assignee_id
    r = await client.post("/api/v1/tasks", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_leave(client, headers, start, end, reason="Break"):
    r = await client.get("/api/v1/leave/types", headers=headers)
    assert r.status_code == 200, r.text
    annual = next(t for t in r.json() if t["code"] == "annual")
    r = await client.post(
        "/api/v1/leave/requests",
        json={"leave_type_id": annual["id"], "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": reason},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    req = r.json()
    r = await client.post(f"/api/v1/leave/requests/{req['id']}/approve", json={"note": "OK"}, headers=headers)
    assert r.status_code == 200, r.text
    return req


@pytest.mark.asyncio
async def test_calendar_feed_merges_all_sources(client):
    org = await register_org(client, email="s13a1@test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    r = await client.post(
        "/api/v1/calendar/events",
        json={"title": "All-hands", "event_type": "meeting", "start_at": f"{today}T15:00:00", "end_at": f"{today}T16:00:00"},
        headers=headers,
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        "/api/v1/meetings",
        json={
            "title": "Sprint review",
            "meeting_type": "review",
            "start_at": f"{today}T10:00:00",
            "end_at": f"{today}T11:00:00",
            "organizer_id": me,
            "attendee_ids": [me],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    meeting = r.json()

    r = await client.post(
        "/api/v1/meetings",
        json={
            "title": "Cancelled sync",
            "meeting_type": "sync",
            "start_at": f"{tomorrow}T09:00:00",
            "end_at": f"{tomorrow}T09:30:00",
            "organizer_id": me,
            "attendee_ids": [me],
            "status": "cancelled",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    await _create_task(client, headers, "Ship v1", today, estimate_hours=40)
    await _create_task(client, headers, "Next quarter planning", (date.today() + timedelta(days=60)).isoformat())

    leave_start = date.today() + timedelta(days=3)
    await _create_leave(client, headers, leave_start, leave_start + timedelta(days=2))

    r = await client.get(
        "/api/v1/calendar/feed",
        params={"start": today, "end": (date.today() + timedelta(days=30)).isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    feed = r.json()

    by_source = {}
    for item in feed:
        by_source.setdefault(item["source"], []).append(item)

    assert any(i["title"] == "All-hands" for i in by_source.get("event", [])), "calendar events must appear"
    assert any(i["title"] == "Sprint review" for i in by_source.get("meeting", [])), "meetings must appear"
    assert not any("Cancelled sync" in i["title"] for i in feed), "cancelled meetings must be excluded"
    assert any(i["title"] == "Ship v1" and i["due_date"] == today for i in by_source.get("task", [])), "task deadlines must appear"
    assert not any(i["title"] == "Next quarter planning" for i in feed), "deadlines outside the range must not appear"
    leave_items = by_source.get("leave", [])
    assert leave_items and "·" in leave_items[0]["title"], "approved leave must appear with the employee name"

    starts = [i.get("start_at") or i.get("due_date") for i in feed]
    assert starts == sorted(starts), "feed must be time-sorted"


@pytest.mark.asyncio
async def test_tasks_due_date_filter(client):
    org = await register_org(client, email="s13a2@test.co")
    headers = org["headers"]
    today = date.today().isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()

    await _create_task(client, headers, "Due now", today)
    await _create_task(client, headers, "Due later", next_week)

    r = await client.get("/api/v1/tasks", params={"due_from": today, "due_to": today}, headers=headers)
    assert r.status_code == 200, r.text
    titles = [t["title"] for t in r.json()]
    assert "Due now" in titles and "Due later" not in titles

    r = await client.get("/api/v1/tasks", params={"due_from": next_week}, headers=headers)
    titles = [t["title"] for t in r.json()]
    assert "Due later" in titles and "Due now" not in titles


@pytest.mark.asyncio
async def test_team_load_summary(client):
    org = await register_org(client, email="s13a3@test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    r = await client.post(
        "/api/v1/employees",
        json={"first_name": "Lee", "last_name": "Load", "email": "lee13@test.co"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    second = r.json()["id"]

    r = await client.post("/api/v1/teams", json={"name": "Platform", "code": "plf13"}, headers=headers)
    assert r.status_code == 201, r.text
    team = r.json()
    for member_id in (me, second):
        r = await client.post(
            f"/api/v1/teams/{team['id']}/members", json={"employee_id": member_id}, headers=headers
        )
        assert r.status_code == 201, r.text

    await _create_task(client, headers, "Load 40h", date.today().isoformat(), estimate_hours=40, assignee_id=me)

    r = await client.get("/api/v1/workload/teams", headers=headers)
    assert r.status_code == 200, r.text
    summary = next(t for t in r.json() if t["team_id"] == team["id"])
    assert summary["team_name"] == "Platform"
    assert summary["member_count"] == 2
    assert summary["avg_utilization"] >= 50.0
    assert summary["overloaded_count"] == 1


@pytest.mark.asyncio
async def test_overload_snapshot_notifies_once(client, db_session_factory):
    org = await register_org(client, email="s13a4@test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    await _create_task(client, headers, "Full week", date.today().isoformat(), estimate_hours=40, assignee_id=me)

    r = await client.post("/api/v1/workload/snapshot", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["snapshots_created"] >= 1

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "workload.overload")
        assert notes, "the overloaded employee must be notified"
        assert notes[0].title == "Your workload is over capacity"
        assert notes[0].link == "/my-work"
        assert "100%" in notes[0].body

    r = await client.post("/api/v1/workload/snapshot", headers=headers)
    assert r.status_code == 200, r.text
    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        notes = await _notifications(db, org["organization"]["id"], "workload.overload")
        assert len(notes) == 1, "the threshold crossing must only be flagged once"

    r = await client.get("/api/v1/audit", params={"action": "workload.overload"}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    entries = data if isinstance(data, list) else data.get("items", data.get("entries", []))
    assert any(e["resource_type"] == "employee" for e in entries), "overload must be audited"

    r = await client.get("/api/v1/events", params={"type": "workload.overload"}, headers=headers)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_workload_me_and_org_load(client):
    org = await register_org(client, email="s13a5@test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    await _create_task(client, headers, "30h allocation", date.today().isoformat(), estimate_hours=30, assignee_id=me)

    r = await client.get("/api/v1/workload/me", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["capacity_hours"] == 40.0
    assert data["allocated_hours"] == 30.0
    assert data["utilization"] == 75.0
    assert data["is_overloaded"] is False

    r = await client.post("/api/v1/workload/snapshot", headers=headers)
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/workload/organization", headers=headers)
    assert r.status_code == 200, r.text
    org_load = r.json()
    assert org_load["employees_tracked"] >= 1
    assert org_load["overloaded"] == 0
