"""Phase 6.2–6.5 — Live collaboration tests.

Covers the live engine hub (presence fan-out, targeted RTC signaling) and the
REST surface for in-session chat and shared whiteboards, plus tenancy and RBAC
isolation for both.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _make_meeting(client, headers, *, title="Live Review", with_attendees=True):
    me = await _employee_id(client, headers)
    payload = {
        "title": title,
        "meeting_type": "review",
        "start_at": "2026-08-11T10:00:00Z",
        "end_at": "2026-08-11T11:00:00Z",
        "organizer_id": me,
    }
    if with_attendees:
        payload["attendee_ids"] = [me]
    response = await client.post("/api/v1/meetings", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _invite_employee(client, headers, email):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Grace Hopper", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Grace Hopper", "password": "EmpPass123!"},
    )
    assert emp.status_code == 201, emp.text
    return {"Authorization": f"Bearer {emp.json()['access_token']}"}


# --------------------------------------------------------------------------- live hub

class FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    def fail_next(self) -> None:
        self._fail = True

    def send_json_boom(self, payload: dict) -> None:
        raise ConnectionError("socket closed")


@pytest.mark.asyncio
async def test_live_hub_register_broadcast_targeted_and_unregister():
    from app.collaboration.live import LiveConnection, LiveHub

    hub = LiveHub()
    a = LiveConnection(ws=FakeSocket(), employee_id="emp-a", name="Ada")
    b = LiveConnection(ws=FakeSocket(), employee_id="emp-b", name="Bob")
    c = LiveConnection(ws=FakeSocket(), employee_id="emp-c", name="Carol")

    key_a = hub.register("s1", a)
    hub.register("s1", b)
    hub.register("s1", c)
    assert hub.count("s1") == 3

    # Broadcast reaches everyone except the excluded connection.
    delivered = await hub.broadcast("s1", "hello", {"n": 1}, exclude=b)
    assert delivered == 2
    assert a.ws.sent[-1]["type"] == "hello"
    assert c.ws.sent[-1]["type"] == "hello"
    assert not b.ws.sent

    # Targeted delivery reaches only the target employee.
    ok = await hub.send_to_employee("s1", "emp-b", "signal", {"kind": "offer"})
    assert ok is True
    assert b.ws.sent[-1]["type"] == "signal"
    assert b.ws.sent[-1]["data"]["kind"] == "offer"
    assert len(a.ws.sent) == 1

    # Peers listing excludes the viewer.
    names = {p["employee_id"] for p in hub.peers("s1", exclude_employee="emp-a")}
    assert names == {"emp-b", "emp-c"}

    # Unregister removes only that connection; a second tab can coexist.
    gone = hub.unregister("s1", key_a)
    assert gone is a
    assert hub.count("s1") == 2
    assert not await hub.send_to_employee("s1", "emp-a", "signal", {})
    assert hub.unregister("s1", 9999) is None
    hub.unregister("s1", id(b))
    hub.unregister("s1", id(c))
    assert hub.count("s1") == 0


@pytest.mark.asyncio
async def test_live_hub_survives_dead_sockets():
    from app.collaboration.live import LiveConnection, LiveHub

    hub = LiveHub()
    dead = FakeSocket()
    alive = FakeSocket()
    dead.send_json = dead.send_json_boom
    hub.register("s9", LiveConnection(ws=dead, employee_id="d"))
    hub.register("s9", LiveConnection(ws=alive, employee_id="a"))
    await hub.broadcast("s9", "ping")
    assert hub.count("s9") == 1
    assert alive.sent[-1]["type"] == "ping"


# --------------------------------------------------------------------------- chat

@pytest.mark.asyncio
async def test_chat_send_list_and_delete(client):
    org = await register_org(client, email="owner@chat.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)

    sent = await client.post(
        f"/api/v1/meetings/{meeting['id']}/chat",
        json={"content": "Kickoff in 5 — join the session"},
        headers=headers,
    )
    assert sent.status_code == 201, sent.text
    message_id = sent.json()["id"]
    assert sent.json()["kind"] == "message"
    assert sent.json()["sender_name"]

    listed = await client.get(f"/api/v1/meetings/{meeting['id']}/chat", headers=headers)
    assert listed.status_code == 200
    assert any(m["id"] == message_id for m in listed.json())

    # Empty messages are rejected.
    bad = await client.post(
        f"/api/v1/meetings/{meeting['id']}/chat", json={"content": "   "}, headers=headers
    )
    assert bad.status_code == 400

    # Author can delete their own message.
    deleted = await client.delete(
        f"/api/v1/meetings/{meeting['id']}/chat/{message_id}", headers=headers
    )
    assert deleted.status_code == 200, deleted.text
    after = await client.get(f"/api/v1/meetings/{meeting['id']}/chat", headers=headers)
    assert not any(m["id"] == message_id for m in after.json())


@pytest.mark.asyncio
async def test_chat_tenancy_and_delete_rbac(client):
    org = await register_org(client, email="owner@chatt.test.co")
    headers = org["headers"]
    other = await register_org(client, email="other@chatt.test.co", slug="chatt-other")
    meeting = await _make_meeting(client, headers)

    sent = await client.post(
        f"/api/v1/meetings/{meeting['id']}/chat", json={"content": "internal note"}, headers=headers
    )
    message_id = sent.json()["id"]

    hidden = await client.get(f"/api/v1/meetings/{meeting['id']}/chat", headers=other["headers"])
    assert hidden.status_code == 404

    grace_headers = await _invite_employee(client, headers, "grace@chatt.test.co")
    grace_id = (await client.get("/api/v1/employees/me", headers=grace_headers)).json()["id"]

    # Another employee (not author, not host) cannot delete the owner's message.
    blocked = await client.delete(
        f"/api/v1/meetings/{meeting['id']}/chat/{message_id}", headers=grace_headers
    )
    assert blocked.status_code == 403
    assert grace_id

    # Grace can post into the meeting chat.
    grace_msg = await client.post(
        f"/api/v1/meetings/{meeting['id']}/chat",
        json={"content": "I can see this meeting too"},
        headers=grace_headers,
    )
    assert grace_msg.status_code == 201, grace_msg.text

    # Host can delete anyone's message.
    host_delete = await client.delete(
        f"/api/v1/meetings/{meeting['id']}/chat/{grace_msg.json()['id']}", headers=headers
    )
    assert host_delete.status_code == 200


@pytest.mark.asyncio
async def test_chat_increments_participant_message_count(client):
    org = await register_org(client, email="owner@chatcnt.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)
    joined = await client.post(f"/api/v1/meetings/{meeting['id']}/join", json={}, headers=headers)
    assert joined.status_code == 200

    for text in ("one", "two", "three"):
        response = await client.post(
            f"/api/v1/meetings/{meeting['id']}/chat", json={"content": text}, headers=headers
        )
        assert response.status_code == 201, response.text

    participants = await client.get(
        f"/api/v1/meetings/{meeting['id']}/participants", headers=headers
    )
    mine = next(p for p in participants.json() if p["role"] == "host")
    assert mine["messages_count"] == 3


# --------------------------------------------------------------------------- whiteboard

@pytest.mark.asyncio
async def test_whiteboard_get_update_and_version_conflict(client):
    org = await register_org(client, email="owner@board.test.co")
    headers = org["headers"]
    meeting = await _make_meeting(client, headers)

    created = await client.get(f"/api/v1/meetings/{meeting['id']}/whiteboard", headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert created.json()["content"]["shapes"] == []

    updated = await client.put(
        f"/api/v1/meetings/{meeting['id']}/whiteboard",
        json={"version": 1, "content": {"shapes": [{"kind": "rect", "id": "s1", "x": 10, "y": 20}]}},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["content"]["shapes"][0]["id"] == "s1"

    # Re-saving with a stale version conflicts.
    stale = await client.put(
        f"/api/v1/meetings/{meeting['id']}/whiteboard",
        json={"version": 1, "content": {"shapes": []}},
        headers=headers,
    )
    assert stale.status_code == 409

    # Fresh read shows the saved snapshot.
    reread = await client.get(f"/api/v1/meetings/{meeting['id']}/whiteboard", headers=headers)
    assert reread.json()["version"] == 2


@pytest.mark.asyncio
async def test_whiteboard_tenancy(client):
    org = await register_org(client, email="owner@boardt.test.co")
    headers = org["headers"]
    other = await register_org(client, email="other@boardt.test.co", slug="boardt-other")
    meeting = await _make_meeting(client, headers)

    hidden = await client.get(f"/api/v1/meetings/{meeting['id']}/whiteboard", headers=other["headers"])
    assert hidden.status_code == 404

    cross_write = await client.put(
        f"/api/v1/meetings/{meeting['id']}/whiteboard",
        json={"version": 0, "content": {"shapes": []}},
        headers=other["headers"],
    )
    assert cross_write.status_code == 404

    # RBAC: chat read is open to any meeting reader, whiteboard write needs manage.
    grace_headers = await _invite_employee(client, headers, "grace@boardt.test.co")
    blocked = await client.put(
        f"/api/v1/meetings/{meeting['id']}/whiteboard",
        json={"version": 1, "content": {"shapes": []}},
        headers=grace_headers,
    )
    assert blocked.status_code == 403
    allowed = await client.get(f"/api/v1/meetings/{meeting['id']}/whiteboard", headers=grace_headers)
    assert allowed.status_code == 200
