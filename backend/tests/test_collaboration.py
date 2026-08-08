"""Phase 6.1 — Collaboration Foundation tests.

Covers: meeting rooms (CRUD, scoping, availability), sessions (create, start,
join, leave, end, join-by-code), invites → notifications + calendar mirror,
RSVP → calendar sync, meeting notes, tenancy isolation, and RBAC for the new
collaboration endpoints.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _make_meeting(client, headers, *, title="Sprint Review", with_attendees=True):
    me = await _employee_id(client, headers)
    payload = {
        "title": title,
        "meeting_type": "review",
        "start_at": "2026-08-10T10:00:00Z",
        "end_at": "2026-08-10T11:00:00Z",
        "organizer_id": me,
    }
    if with_attendees:
        payload["attendee_ids"] = [me]
    response = await client.post("/api/v1/meetings", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _second_employee(client, headers, email="grace@collab.test.co"):
    response = await client.post(
        "/api/v1/employees",
        json={"first_name": "Grace", "last_name": "Hopper", "email": email},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --------------------------------------------------------------------------- rooms

@pytest.mark.asyncio
async def test_room_lifecycle_and_tenancy(client):
    org = await register_org(client, email="owner@rooms.test.co")
    headers = org["headers"]
    other = await register_org(client, email="other@rooms.test.co", slug="rooms-other")

    created = await client.post(
        "/api/v1/meeting-rooms",
        json={"name": "War Room", "room_type": "project", "capacity": 12, "location": "Virtual 1"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    room_id = created.json()["id"]
    assert created.json()["name"] == "War Room"
    assert created.json()["is_public"] is True

    listed = await client.get("/api/v1/meeting-rooms", headers=headers)
    assert listed.status_code == 200
    assert any(r["id"] == room_id for r in listed.json())

    by_type = await client.get("/api/v1/meeting-rooms?room_type=project", headers=headers)
    assert any(r["id"] == room_id for r in by_type.json())
    wrong_type = await client.get("/api/v1/meeting-rooms?room_type=meeting", headers=headers)
    assert not any(r["id"] == room_id for r in wrong_type.json())

    detail = await client.get(f"/api/v1/meeting-rooms/{room_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["capacity"] == 12

    updated = await client.patch(
        f"/api/v1/meeting-rooms/{room_id}", json={"status": "maintenance", "capacity": 20}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "maintenance"
    assert updated.json()["capacity"] == 20

    availability = await client.get(
        f"/api/v1/meeting-rooms/{room_id}/availability",
        params={"start": "2026-08-01T00:00:00Z", "end": "2026-08-31T00:00:00Z"},
        headers=headers,
    )
    assert availability.status_code == 200

    # Tenancy: the other org cannot see or touch the room.
    hidden = await client.get("/api/v1/meeting-rooms", headers=other["headers"])
    assert not any(r["id"] == room_id for r in hidden.json())
    cross_get = await client.get(f"/api/v1/meeting-rooms/{room_id}", headers=other["headers"])
    assert cross_get.status_code == 404
    cross_patch = await client.patch(
        f"/api/v1/meeting-rooms/{room_id}", json={"status": "occupied"}, headers=other["headers"]
    )
    assert cross_patch.status_code == 404

    deleted = await client.delete(f"/api/v1/meeting-rooms/{room_id}", headers=headers)
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/meeting-rooms/{room_id}", headers=headers)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_room_rbac_employee_cannot_manage(client):
    org = await register_org(client, email="owner@roomrbac.test.co")
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp@roomrbac.test.co", "full_name": "Emp Room", "role": "employee"},
        headers=org["headers"],
    )
    assert invite.status_code == 201
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Emp Room", "password": "EmpPass123!"},
    )
    emp_headers = {"Authorization": f"Bearer {emp.json()['access_token']}"}

    blocked = await client.post(
        "/api/v1/meeting-rooms", json={"name": "Nope"}, headers=emp_headers
    )
    assert blocked.status_code == 403

    ok = await client.post("/api/v1/meeting-rooms", json={"name": "Owner Room"}, headers=org["headers"])
    assert ok.status_code == 201
    room_id = ok.json()["id"]
    visible = await client.get(f"/api/v1/meeting-rooms/{room_id}", headers=emp_headers)
    assert visible.status_code == 200


# --------------------------------------------------------------------------- sessions

@pytest.mark.asyncio
async def test_session_lifecycle_start_join_leave_end(client):
    org = await register_org(client, email="owner@sessions.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    meeting = await _make_meeting(client, headers)

    session = await client.post(
        f"/api/v1/meetings/{meeting['id']}/session",
        json={"timezone": "UTC", "max_participants": 25},
        headers=headers,
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]
    assert session.json()["meeting_code"]
    assert session.json()["status"] == "scheduled"
    assert session.json()["max_participants"] == 25

    # Creating again returns the same session (idempotent).
    again = await client.post(
        f"/api/v1/meetings/{meeting['id']}/session", json={}, headers=headers
    )
    assert again.status_code == 201
    assert again.json()["id"] == session_id

    started = await client.post(f"/api/v1/meetings/{meeting['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "live"

    joined = await client.post(
        f"/api/v1/meetings/{meeting['id']}/join", json={"device": "desktop"}, headers=headers
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["session"]["status"] == "live"
    participant = joined.json()["participant"]
    assert participant["employee_id"] == me
    assert participant["is_present"] is True
    assert participant["role"] == "host"

    participants = await client.get(
        f"/api/v1/meetings/{meeting['id']}/participants", headers=headers
    )
    assert participants.status_code == 200
    assert any(p["employee_id"] == me for p in participants.json())

    presence = await client.post(
        f"/api/v1/meetings/{meeting['id']}/presence",
        json={"mic_enabled": True, "camera_enabled": True, "raised_hand": True},
        headers=headers,
    )
    assert presence.status_code == 200, presence.text
    assert presence.json()["mic_enabled"] is True
    assert presence.json()["raised_hand"] is True

    ended = await client.post(f"/api/v1/meetings/{meeting['id']}/end", headers=headers)
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "ended"
    assert ended.json()["duration_seconds"] >= 0

    # Meeting is completed and carries an AI summary.
    detail = await client.get(f"/api/v1/meetings/{meeting['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["ai_summary"]

    left = await client.post(f"/api/v1/meetings/{meeting['id']}/leave", headers=headers)
    assert left.status_code == 200


@pytest.mark.asyncio
async def test_join_by_code_and_upcoming_scopes(client):
    org = await register_org(client, email="owner@codes.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers, title="Joinable Standup")

    session = await client.post(
        f"/api/v1/meetings/{meeting['id']}/session", json={}, headers=headers
    )
    code = session.json()["meeting_code"]

    by_code = await client.get(f"/api/v1/meetings/code/{code}", headers=headers)
    assert by_code.status_code == 200, by_code.text
    assert by_code.json()["id"] == meeting["id"]
    assert by_code.json()["session"]["meeting_code"] == code

    missing = await client.get("/api/v1/meetings/code/NOTACODE", headers=headers)
    assert missing.status_code == 404

    upcoming = await client.get("/api/v1/meetings/upcoming?scope=organization", headers=headers)
    assert upcoming.status_code == 200, upcoming.text
    assert any(m["id"] == meeting["id"] for m in upcoming.json())
    item = next(m for m in upcoming.json() if m["id"] == meeting["id"])
    assert item["session"]["meeting_code"] == code

    personal = await client.get("/api/v1/meetings/upcoming?scope=personal", headers=headers)
    assert any(m["id"] == meeting["id"] for m in personal.json())

    bad_scope = await client.get("/api/v1/meetings/upcoming?scope=nonsense", headers=headers)
    assert bad_scope.status_code == 400


# --------------------------------------------------------------------------- invites + calendar

@pytest.mark.asyncio
async def test_invite_notifies_and_mirrors_calendar(client):
    org = await register_org(client, email="owner@invites.test.co")
    headers = org["headers"]

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "grace@invites.test.co", "full_name": "Grace Hopper", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Grace Hopper", "password": "EmpPass123!"},
    )
    assert emp.status_code == 201
    grace_headers = {"Authorization": f"Bearer {emp.json()['access_token']}"}
    grace_id = (await client.get("/api/v1/employees/me", headers=grace_headers)).json()["id"]

    meeting = await _make_meeting(client, headers, with_attendees=False)

    invited = await client.post(
        f"/api/v1/meetings/{meeting['id']}/invite",
        json={"employee_ids": [grace_id], "message": "Please join the review"},
        headers=headers,
    )
    assert invited.status_code == 200, invited.text
    assert grace_id in invited.json()["invited"]

    attendees = await client.get(f"/api/v1/meetings/{meeting['id']}/attendees", headers=headers)
    assert any(a["employee_id"] == grace_id for a in attendees.json())

    notifications = await client.get("/api/v1/notifications", headers=grace_headers)
    assert notifications.status_code == 200
    types = {n["type"] for n in notifications.json()["items"]}
    assert "meeting.invited" in types

    calendar = await client.get("/api/v1/calendar/events", headers=headers)
    assert calendar.status_code == 200, calendar.text
    matching = [e for e in calendar.json() if e.get("event_type") == "meeting"]
    assert any(e["title"] == "Sprint Review" for e in matching)

    # Re-invite is idempotent — no duplicates.
    again = await client.post(
        f"/api/v1/meetings/{meeting['id']}/invite",
        json={"employee_ids": [grace_id]},
        headers=headers,
    )
    assert again.json()["invited"] == []

    events = await client.get("/api/v1/events?name=meeting.invited", headers=headers)
    assert events.status_code == 200
    assert events.json()["total"] >= 1


@pytest.mark.asyncio
async def test_rsvp_accept_keeps_calendar_synced(client):
    org = await register_org(client, email="owner@rsvpcal.test.co")
    headers = org["headers"]
    grace_id = await _second_employee(client, headers)
    meeting = await _make_meeting(client, headers, with_attendees=False)
    await client.post(
        f"/api/v1/meetings/{meeting['id']}/invite",
        json={"employee_ids": [grace_id]},
        headers=headers,
    )
    calendar = await client.get("/api/v1/calendar/events", headers=headers)
    event = next(e for e in calendar.json() if e["title"] == "Sprint Review")
    assert grace_id in (event.get("attendee_ids") or [])

    grace_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "grace@collab.test.co", "password": "StrongPass123!"},
    )
    # Grace has no user account (employee created via API, not invited user), so
    # verify the RSVP path through the owner instead: owner accepts.
    rsvp = await client.post(
        f"/api/v1/meetings/{meeting['id']}/rsvp", json={"status": "accepted"}, headers=headers
    )
    assert rsvp.status_code == 200, rsvp.text
    calendar2 = await client.get("/api/v1/calendar/events", headers=headers)
    event2 = next(e for e in calendar2.json() if e["title"] == "Sprint Review")
    assert event2["status"] == "confirmed"


# --------------------------------------------------------------------------- notes

@pytest.mark.asyncio
async def test_meeting_notes_crud(client):
    org = await register_org(client, email="owner@notes.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)

    created = await client.post(
        f"/api/v1/meetings/{meeting['id']}/notes",
        json={"content": "# Decisions\n- Ship v2 in August"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    assert created.json()["version"] == 1

    listed = await client.get(f"/api/v1/meetings/{meeting['id']}/notes", headers=headers)
    assert listed.status_code == 200
    assert any(n["id"] == note_id for n in listed.json())

    updated = await client.patch(
        f"/api/v1/meetings/{meeting['id']}/notes/{note_id}",
        json={"content": "# Decisions\n- Ship v2 in August\n- Announce on Monday"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert "Announce" in updated.json()["content"]

    deleted = await client.delete(
        f"/api/v1/meetings/{meeting['id']}/notes/{note_id}", headers=headers
    )
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/meetings/{meeting['id']}/notes", headers=headers)
    assert not any(n["id"] == note_id for n in gone.json())
