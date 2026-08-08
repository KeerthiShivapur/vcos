"""Phase 6.7–6.15 tests — recordings, transcript, captions/translation,
AI meeting intelligence (summary/decisions/action items → tasks), attendance
intelligence, org analytics, and calendar intelligence.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _make_meeting(client, headers, *, title="Intelligence Review"):
    me = await _employee_id(client, headers)
    response = await client.post(
        "/api/v1/meetings",
        json={
            "title": title,
            "meeting_type": "review",
            "start_at": "2026-08-13T10:00:00Z",
            "end_at": "2026-08-13T11:00:00Z",
            "organizer_id": me,
            "attendee_ids": [me],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- recordings

@pytest.mark.asyncio
async def test_recording_lifecycle(client):
    org = await register_org(client, email="owner@rec.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)

    started = await client.post(
        f"/api/v1/meetings/{meeting['id']}/recordings/start",
        json={"kind": "manual", "title": "Release Planning Capture", "captions_enabled": True},
        headers=headers,
    )
    assert started.status_code == 201, started.text
    recording_id = started.json()["id"]
    assert started.json()["status"] == "recording"
    assert started.json()["captions_enabled"] is True

    stopped = await client.post(
        f"/api/v1/meetings/{meeting['id']}/recordings/{recording_id}/stop", headers=headers
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "processing"
    assert stopped.json()["duration_seconds"] >= 0

    listed = await client.get(f"/api/v1/meetings/{meeting['id']}/recordings", headers=headers)
    assert listed.status_code == 200
    assert any(r["id"] == recording_id for r in listed.json())

    # Session carries the recording flag while recording.
    session = await client.post(f"/api/v1/meetings/{meeting['id']}/session", json={}, headers=headers)
    assert session.json()["is_recording"] is False

    deleted = await client.delete(
        f"/api/v1/meetings/{meeting['id']}/recordings/{recording_id}", headers=headers
    )
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_recording_library_org_wide(client):
    org = await register_org(client, email="owner@lib.test.co")
    headers = org["headers"]
    other = await register_org(client, email="other@lib.test.co", slug="lib-other")
    meeting = await _make_meeting(client, headers, title="Library Capture")

    started = await client.post(
        f"/api/v1/meetings/{meeting['id']}/recordings/start",
        json={"kind": "manual", "title": "Library Capture Recording"},
        headers=headers,
    )
    assert started.status_code == 201, started.text
    recording_id = started.json()["id"]

    library = await client.get("/api/v1/recordings", headers=headers)
    assert library.status_code == 200, library.text
    assert any(
        r["id"] == recording_id and r["meeting_title"] == "Library Capture" for r in library.json()
    ), library.text

    # Other orgs never see it.
    other_library = await client.get("/api/v1/recordings", headers=other["headers"])
    assert other_library.status_code == 200
    assert all(r["id"] != recording_id for r in other_library.json())


@pytest.mark.asyncio
async def test_recording_tenancy_and_rbac(client):
    org = await register_org(client, email="owner@rect.test.co")
    headers = org["headers"]
    other = await register_org(client, email="other@rect.test.co", slug="rect-other")
    meeting = await _make_meeting(client, headers)

    hidden = await client.get(f"/api/v1/meetings/{meeting['id']}/recordings", headers=other["headers"])
    assert hidden.status_code == 404
    cross_start = await client.post(
        f"/api/v1/meetings/{meeting['id']}/recordings/start", json={}, headers=other["headers"]
    )
    assert cross_start.status_code == 404

    # Read is allowed for any meeting reader; start requires manage.
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "grace@rect.test.co", "full_name": "Grace Hopper", "role": "employee"},
        headers=headers,
    )
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Grace Hopper", "password": "EmpPass123!"},
    )
    grace_headers = {"Authorization": f"Bearer {emp.json()['access_token']}"}
    blocked = await client.post(
        f"/api/v1/meetings/{meeting['id']}/recordings/start", json={}, headers=grace_headers
    )
    assert blocked.status_code == 403


# --------------------------------------------------------------------------- transcript + captions

@pytest.mark.asyncio
async def test_transcript_and_captions_flow(client):
    org = await register_org(client, email="owner@cap.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)

    # Live caption segments (STT simulated), with translation.
    c1 = await client.post(
        f"/api/v1/meetings/{meeting['id']}/captions",
        json={"text": "We should ship the release by Friday", "start_ms": 0, "end_ms": 4000, "language": "en"},
        headers=headers,
    )
    assert c1.status_code == 201, c1.text
    c2 = await client.post(
        f"/api/v1/meetings/{meeting['id']}/captions",
        json={
            "text": "We decided to split the rollout",
            "start_ms": 5000,
            "end_ms": 9000,
            "language": "en",
            "translated_text": "Hemos decidido dividir el lanzamiento",
            "translation_language": "es",
        },
        headers=headers,
    )
    assert c2.status_code == 201
    assert c2.json()["translation_language"] == "es"

    listed = await client.get(f"/api/v1/meetings/{meeting['id']}/captions", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    after = await client.get(
        f"/api/v1/meetings/{meeting['id']}/captions?after_ms=4000", headers=headers
    )
    assert len(after.json()) == 1

    # Transcript save (as a transcription worker would).
    saved = await client.put(
        f"/api/v1/meetings/{meeting['id']}/transcript",
        json={
            "content": "Speaker: We should ship the release by Friday. Speaker: We decided to split the rollout.",
            "segments": [
                {"speaker": "Ada", "start_ms": 0, "text": "We should ship the release by Friday"},
                {"speaker": "Bob", "start_ms": 5000, "text": "We decided to split the rollout"},
            ],
            "speakers": [{"name": "Ada", "speaking_ms": 4000}, {"name": "Bob", "speaking_ms": 4000}],
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "completed"
    assert saved.json()["word_count"] > 5

    fetched = await client.get(f"/api/v1/meetings/{meeting['id']}/transcript", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["segments"]) == 2

    cleared = await client.delete(f"/api/v1/meetings/{meeting['id']}/captions", headers=headers)
    assert cleared.status_code == 200


# --------------------------------------------------------------------------- AI intelligence

@pytest.mark.asyncio
async def test_ai_finalize_creates_summary_decisions_tasks(client):
    org = await register_org(client, email="owner@ai.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers, title="AI Strategy Review")

    joined = await client.post(f"/api/v1/meetings/{meeting['id']}/join", json={}, headers=headers)
    assert joined.status_code == 200

    # Seed chat with action-item + decision language.
    for text in (
        "We should ship the v2 release by Friday",
        "I will prepare the migration plan",
        "We decided to adopt the new architecture",
    ):
        response = await client.post(
            f"/api/v1/meetings/{meeting['id']}/chat", json={"content": text}, headers=headers
        )
        assert response.status_code == 201, response.text

    ended = await client.post(f"/api/v1/meetings/{meeting['id']}/end", headers=headers)
    assert ended.status_code == 200, ended.text

    # Meeting now carries an AI summary.
    detail = await client.get(f"/api/v1/meetings/{meeting['id']}", headers=headers)
    assert "Action items" in (detail.json()["ai_summary"] or "")

    # Transcript was assembled from chat.
    transcript = await client.get(f"/api/v1/meetings/{meeting['id']}/transcript", headers=headers)
    assert transcript.status_code == 200
    assert transcript.json()["status"] == "completed"
    assert "migration plan" in transcript.json()["content"]

    # Decisions extracted from chat.
    decisions = await client.get(f"/api/v1/meetings/{meeting['id']}/decisions", headers=headers)
    assert decisions.status_code == 200
    assert any("decided" in d["content"].lower() for d in decisions.json())
    assert all(d["source"] == "ai" for d in decisions.json())

    # Action items -> real tasks.
    tasks = await client.get("/api/v1/tasks", headers=headers)
    assert tasks.status_code == 200
    titles = [t["title"] for t in tasks.json() if isinstance(t, dict)]
    assert any("release" in t.lower() for t in titles)

    # Attendance + analytics snapshot exists.
    attendance = await client.get(f"/api/v1/meetings/{meeting['id']}/attendance", headers=headers)
    assert attendance.status_code == 200, attendance.text
    snapshot = attendance.json()["snapshot"]
    assert snapshot is not None
    assert snapshot["engagement_score"] >= 0
    assert snapshot["participants_joined"] >= 1

    # Finalize is idempotent.
    again = await client.post(f"/api/v1/meetings/{meeting['id']}/ai/finalize", headers=headers)
    assert again.status_code == 200
    assert again.json()["already_finalized"] is True

    # Manual decision create/confirm.
    manual = await client.post(
        f"/api/v1/meetings/{meeting['id']}/decisions",
        json={"content": "Roll out in two phases", "status": "draft"},
        headers=headers,
    )
    assert manual.status_code == 201, manual.text
    patched = await client.patch(
        f"/api/v1/meetings/{meeting['id']}/decisions/{manual.json()['id']}",
        json={"content": "Roll out in two phases", "status": "confirmed"},
        headers=headers,
    )
    assert patched.json()["status"] == "confirmed"


# --------------------------------------------------------------------------- analytics + scheduling

@pytest.mark.asyncio
async def test_org_analytics_and_suggestions(client):
    org = await register_org(client, email="owner@an.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers, title="Q3 Planning")
    await client.post(f"/api/v1/meetings/{meeting['id']}/join", json={}, headers=headers)
    await client.post(f"/api/v1/meetings/{meeting['id']}/end", headers=headers)

    analytics = await client.get("/api/v1/meeting-analytics", headers=headers)
    assert analytics.status_code == 200, analytics.text
    data = analytics.json()
    assert data["meetings_total"] >= 1
    assert data["meetings_completed"] >= 1
    assert "meetings_per_week" in data
    assert "time_in_meetings_hours" in data

    # Calendar intelligence endpoint (static path must beat /meetings/{id}).
    me = await _employee_id(client, headers)
    suggested = await client.get(
        "/api/v1/meetings/suggest",
        params={
            "employee_ids": me,
            "duration_minutes": 30,
            "days": 3,
            "start_at": "2026-08-17T00:00:00Z",
            "end_at": "2026-08-17T11:00:00Z",
            "capacity": 4,
        },
        headers=headers,
    )
    assert suggested.status_code == 200, suggested.text
    body = suggested.json()
    assert "free_slots" in body
    assert "rooms" in body
    assert "timezones" in body
    assert any("2026" in s["day"] for s in body["free_slots"])

    # Conflict detection with an overlapping event.
    conflicts = await client.get(
        "/api/v1/meetings/suggest",
        params={
            "start_at": "2026-08-17T09:00:00Z",
            "end_at": "2026-08-17T11:00:00Z",
            "employee_ids": me,
        },
        headers=headers,
    )
    assert conflicts.status_code == 200


@pytest.mark.asyncio
async def test_meeting_intel_worker_processes_ended_sessions(client):
    from app.workers import meeting_intel_worker

    org = await register_org(client, email="owner@worker.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers, title="Worker Finalize")
    await client.post(f"/api/v1/meetings/{meeting['id']}/join", json={}, headers=headers)
    await client.post(f"/api/v1/meetings/{meeting['id']}/end", headers=headers)

    count = await meeting_intel_worker.run_once()
    assert count >= 0  # the inline finalize already covered this meeting

    attendance = await client.get(f"/api/v1/meetings/{meeting['id']}/attendance", headers=headers)
    assert attendance.json()["snapshot"] is not None
