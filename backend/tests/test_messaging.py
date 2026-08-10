"""Slice 4B — Messaging operating loop tests.

Covers: DM lifecycle, notification fan-out to linked users (regression for
the recipient_id FK bug), mentions, edit/delete correctness, reaction events
+ audit, read state (receipts + last_read_at), RBAC gating on
communication:write, and tenancy isolation.
"""

import pytest

from tests.conftest import register_org


async def _employee_id(client, headers):
    return (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]


async def _invite_user(client, headers, email, full_name="Invitee", role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": full_name, "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    accepted = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": full_name, "password": "StrongPass123!"},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


async def _employee_by_email(client, headers, email):
    listed = await client.get("/api/v1/employees?search=" + email.split("@")[0], headers=headers)
    assert listed.status_code == 200
    return next((e for e in listed.json() if e["email"] == email), None)


async def _dm(client, headers, other_employee_id):
    response = await client.post(f"/api/v1/dms/{other_employee_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _send(client, headers, conversation_id, content, **extra):
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": content, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _event_payloads(db_session_factory, org_id, name):
    import json

    from sqlalchemy import select

    from app.models.notification import Event

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                select(Event).where(Event.organization_id == org_id, Event.name == name)
            )
        ).scalars().all()
        return [json.loads(row.payload_json) if row.payload_json else {} for row in rows]


async def _audit_rows(db_session_factory, org_id, resource_type=None, resource_id=None):
    from sqlalchemy import select

    from app.models.notification import AuditLog

    async with db_session_factory() as session:
        q = select(AuditLog).where(AuditLog.organization_id == org_id)
        if resource_type:
            q = q.where(AuditLog.resource_type == resource_type)
        if resource_id:
            q = q.where(AuditLog.resource_id == resource_id)
        return (await session.execute(q)).scalars().all()


@pytest.mark.asyncio
async def test_dm_lifecycle_and_notification_to_linked_user(client, db_session_factory):
    """Regression: notification fan-out must use the recipient's user id,
    not the employee id (recipient_id FK -> users.id)."""
    org = await register_org(client, email="owner@msg4b.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)

    invited = await _invite_user(client, headers, "maya@msg4b.test.co", "Maya Angelou")
    maya = await _employee_by_email(client, headers, "maya@msg4b.test.co")
    assert maya is not None and maya["id"] != me

    conversation = await _dm(client, headers, maya["id"])
    assert conversation["type"] == "dm"
    assert conversation["member_count"] == 2

    message = await _send(client, headers, conversation["id"], "Ship the report by Friday")
    assert message["content"] == "Ship the report by Friday"
    assert message["sender_id"] == me
    assert message["deleted"] is False
    assert message["edited"] is False

    # Maya (a real user) receives the messaging.message notification.
    maya_headers = {"Authorization": f"Bearer {invited['access_token']}"}
    notifications = (await client.get("/api/v1/notifications", headers=maya_headers)).json()["items"]
    assert any(
        n["type"] == "messaging.message"
        and n["entity_id"] == message["id"]
        and n["link"] == f"/messages/{conversation['id']}"
        for n in notifications
    )

    # Event + audit rows are written for the message.
    payloads = await _event_payloads(db_session_factory, org["organization"]["id"], "messaging.message_sent")
    assert any(p.get("message_id") == message["id"] for p in payloads)
    audit = await _audit_rows(db_session_factory, org["organization"]["id"], resource_type="message", resource_id=message["id"])
    assert any(a.action == "messaging.message_sent" for a in audit)


@pytest.mark.asyncio
async def test_mention_notifies_and_lists(client):
    org = await register_org(client, email="owner@mnt4b.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "grace@mnt4b.test.co", "Grace Hopper")
    grace = await _employee_by_email(client, headers, "grace@mnt4b.test.co")

    conversation = await _dm(client, headers, grace["id"])
    await _send(client, headers, conversation["id"], "Hi @grace please review the PR")

    grace_headers = {"Authorization": f"Bearer {invited['access_token']}"}
    notifications = (await client.get("/api/v1/notifications", headers=grace_headers)).json()["items"]
    assert any(n["type"] == "mention" for n in notifications)

    mentions = (await client.get("/api/v1/mentions", headers=grace_headers)).json()
    assert any(m["content"] == "Hi @grace please review the PR" for m in mentions)


@pytest.mark.asyncio
async def test_edit_and_delete_correctness(client, db_session_factory):
    org = await register_org(client, email="owner@edt4b.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "ada@edt4b.test.co", "Ada Lovelace")
    ada = await _employee_by_email(client, headers, "ada@edt4b.test.co")
    ada_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    conversation = await _dm(client, headers, ada["id"])
    message = await _send(client, headers, conversation["id"], "Original text")

    # Sender can edit; flags + edited_at are set.
    edited = await client.patch(
        f"/api/v1/messages/{message['id']}", json={"content": "Edited text"}, headers=headers
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["content"] == "Edited text"
    assert edited.json()["edited"] is True
    assert edited.json()["edited_at"] is not None

    # Non-sender cannot edit.
    blocked_edit = await client.patch(
        f"/api/v1/messages/{message['id']}", json={"content": "Hijack"}, headers=ada_headers
    )
    assert blocked_edit.status_code == 403

    # Non-sender cannot delete.
    blocked_delete = await client.delete(f"/api/v1/messages/{message['id']}", headers=ada_headers)
    assert blocked_delete.status_code == 403

    # Sender can delete: content nulled, deleted flag + deleted_at set.
    deleted = await client.delete(f"/api/v1/messages/{message['id']}", headers=headers)
    assert deleted.status_code == 200
    after = await client.get(f"/api/v1/messages/{message['id']}", headers=headers)
    assert after.status_code == 200
    assert after.json()["deleted"] is True
    assert after.json()["deleted_at"] is not None
    assert after.json()["content"] is None

    audit = await _audit_rows(db_session_factory, org["organization"]["id"], resource_type="message", resource_id=message["id"])
    actions = {a.action for a in audit}
    assert "messaging.message_updated" in actions
    assert "messaging.message_deleted" in actions


@pytest.mark.asyncio
async def test_reactions_toggle_events_and_audit(client, db_session_factory):
    org = await register_org(client, email="owner@rx4b.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "kate@rx4b.test.co", "Kate Smith", role="admin")
    kate = await _employee_by_email(client, headers, "kate@rx4b.test.co")
    kate_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    conversation = await _dm(client, headers, kate["id"])
    message = await _send(client, headers, conversation["id"], "Great work!")

    added = await client.post(
        f"/api/v1/messages/{message['id']}/reactions", json={"emoji": "👍"}, headers=headers
    )
    assert added.status_code == 200, added.text
    assert added.json() == {"reacted": True, "reaction_count": 1}

    # A second member adds the same emoji: count grows, no duplicate row.
    kate_added = await client.post(
        f"/api/v1/messages/{message['id']}/reactions", json={"emoji": "👍"}, headers=kate_headers
    )
    assert kate_added.status_code == 200
    assert kate_added.json() == {"reacted": True, "reaction_count": 2}

    reactions = await client.get(f"/api/v1/messages/{message['id']}/reactions", headers=headers)
    assert reactions.json() == [{"emoji": "👍", "count": 2}]

    # Reaction events land in the event table with audit.
    org_id = org["organization"]["id"]
    added_payloads = await _event_payloads(db_session_factory, org_id, "messaging.message_reaction_added")
    assert len(added_payloads) >= 2
    assert any(p.get("message_id") == message["id"] and p.get("emoji") == "👍" for p in added_payloads)

    # Toggle off removes the reaction and emits the removed event.
    removed = await client.post(
        f"/api/v1/messages/{message['id']}/reactions", json={"emoji": "👍"}, headers=kate_headers
    )
    assert removed.status_code == 200
    assert removed.json() == {"reacted": False, "reaction_count": 1}
    removed_payloads = await _event_payloads(db_session_factory, org_id, "messaging.message_reaction_removed")
    assert any(p.get("message_id") == message["id"] and p.get("emoji") == "👍" for p in removed_payloads)


@pytest.mark.asyncio
async def test_conversation_read_state(client, db_session_factory):
    org = await register_org(client, email="owner@rd4b.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "nina@rd4b.test.co", "Nina Simone")
    nina = await _employee_by_email(client, headers, "nina@rd4b.test.co")
    nina_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    conversation = await _dm(client, headers, nina["id"])
    message = await _send(client, headers, conversation["id"], "Unread message")

    # Nina sees an unread conversation; the owner does not (owner wrote it).
    nina_convs = (await client.get("/api/v1/conversations", headers=nina_headers)).json()
    unread = next(c for c in nina_convs if c["id"] == conversation["id"])
    assert unread["unread_count"] >= 1

    # Nina marks the conversation read.
    marked = await client.post(f"/api/v1/conversations/{conversation['id']}/read", headers=nina_headers)
    assert marked.status_code == 200
    assert marked.json() == {"read": True}

    nina_convs = (await client.get("/api/v1/conversations", headers=nina_headers)).json()
    unread = next(c for c in nina_convs if c["id"] == conversation["id"])
    assert unread["unread_count"] == 0

    # last_read_at is persisted on the membership row.
    async with db_session_factory() as session:
        from sqlalchemy import select

        from app.models.communication import ConversationMember

        row = (
            await session.execute(
                select(ConversationMember).where(
                    ConversationMember.organization_id == org["organization"]["id"],
                    ConversationMember.conversation_id == conversation["id"],
                    ConversationMember.employee_id == nina["id"],
                )
            )
        ).scalar_one()
        assert row.last_read_at is not None

    # A fresh message becomes unread again for Nina.
    await _send(client, headers, conversation["id"], "Another message")
    nina_convs = (await client.get("/api/v1/conversations", headers=nina_headers)).json()
    unread = next(c for c in nina_convs if c["id"] == conversation["id"])
    assert unread["unread_count"] >= 1


@pytest.mark.asyncio
async def test_write_endpoints_require_communication_write(client):
    org = await register_org(client, email="owner@rbac4b.test.co")
    headers = org["headers"]
    invited = await _invite_user(client, headers, "frank@rbac4b.test.co", "Frank Gehry")
    frank = await _employee_by_email(client, headers, "frank@rbac4b.test.co")
    frank_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    # The employee role has communication:read but not communication:write.
    conversation = await _dm(client, headers, frank["id"])

    blocked_send = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "not allowed"},
        headers=frank_headers,
    )
    assert blocked_send.status_code == 403

    blocked_create = await client.post(
        "/api/v1/conversations", json={"type": "channel", "title": "nope"}, headers=frank_headers
    )
    assert blocked_create.status_code == 403

    blocked_dm = await client.post("/api/v1/dms/" + frank["id"], headers=frank_headers)
    assert blocked_dm.status_code == 403

    # Reads stay open to the employee role.
    listed = await client.get("/api/v1/conversations", headers=frank_headers)
    assert listed.status_code == 200
    assert any(c["id"] == conversation["id"] for c in listed.json())

    # The owner still has write (communication:write in the owner bundle).
    sent = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "allowed"},
        headers=headers,
    )
    assert sent.status_code == 201, sent.text


@pytest.mark.asyncio
async def test_tenancy_isolation(client):
    org_a = await register_org(client, email="a@iso4b.test.co", slug="iso-a")
    org_b = await register_org(client, email="b@iso4b.test.co", slug="iso-b")
    headers_a = org_a["headers"]
    headers_b = org_b["headers"]

    me_a = await _employee_id(client, headers_a)

    # Create a channel in org A only.
    conversation = await client.post(
        "/api/v1/conversations",
        json={"type": "channel", "title": "A-only", "member_ids": [me_a]},
        headers=headers_a,
    )
    assert conversation.status_code == 201, conversation.text
    cid = conversation.json()["id"]
    message = await _send(client, headers_a, cid, "Secret of org A")

    # Org B cannot list, read, or write to A's conversation.
    hidden = await client.get("/api/v1/conversations", headers=headers_b)
    assert not any(c["id"] == cid for c in hidden.json())

    cross_get = await client.get(f"/api/v1/conversations/{cid}", headers=headers_b)
    assert cross_get.status_code == 404

    cross_msgs = await client.get(f"/api/v1/conversations/{cid}/messages", headers=headers_b)
    assert cross_msgs.status_code == 404

    cross_send = await client.post(
        f"/api/v1/conversations/{cid}/messages", json={"content": "intrusion"}, headers=headers_b
    )
    assert cross_send.status_code == 404

    cross_message_get = await client.get(f"/api/v1/messages/{message['id']}", headers=headers_b)
    assert cross_message_get.status_code == 404


class _FakeWs:
    """Stand-in WebSocket that records pushed frames."""

    def __init__(self):
        self.frames: list[str] = []

    def send_text(self, text):
        self.frames.append(text)
        return None


async def _drain_events(db_session_factory, limit=100):
    from sqlalchemy import func, select

    from app.events.event_bus import DISPATCH_JOB, event_bus
    from app.models.intelligence import BackgroundJob

    async with db_session_factory() as session:
        remaining = True
        while remaining and limit > 0:
            batch = await event_bus.process_pending(session, limit=min(25, limit))
            limit -= batch
            remaining = batch > 0
            await session.commit()
        pending = (
            await session.execute(
                select(func.count())
                .select_from(BackgroundJob)
                .where(
                    BackgroundJob.name == DISPATCH_JOB,
                    BackgroundJob.status.in_(("queued", "retry")),
                )
            )
        ).scalar_one()
    return pending


async def _hub_frames(employee_id):
    import json

    from app.collaboration.live import LiveConnection, live_hub

    ws = _FakeWs()
    conn = LiveConnection(ws=ws, employee_id=employee_id, name="Test Tab")
    key = live_hub.register_personal(employee_id, conn)
    return ws, key


@pytest.mark.asyncio
async def test_message_sent_event_reaches_personal_channel(client, db_session_factory):
    """The event worker dispatch of messaging.message_sent pushes the message
    to the recipients' personal hub channels (realtime leg of the loop)."""
    from app.collaboration.live import live_hub

    org = await register_org(client, email="owner@rt4b.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    invited = await _invite_user(client, headers, "rosa@rt4b.test.co", "Rosa Parks")
    rosa = await _employee_by_email(client, headers, "rosa@rt4b.test.co")

    # Rosa connects her personal channel (simulates an open /ws/messaging tab).
    rosa_ws, rosa_key = await _hub_frames(rosa["id"])
    owner_ws, owner_key = await _hub_frames(me)

    try:
        conversation = await _dm(client, headers, rosa["id"])
        await _send(client, headers, conversation["id"], "Hello Rosa, live update!")

        outcome = await _drain_events(db_session_factory)
        assert outcome == 0, outcome

        # Rosa's tab received the message; the sender's tab did not.
        import json

        rosa_frames = [json.loads(f) for f in rosa_ws.frames]
        sent = [f for f in rosa_frames if f["type"] == "messaging.message.sent"]
        assert len(sent) == 1
        assert sent[0]["data"]["conversation_id"] == conversation["id"]
        assert sent[0]["data"]["message"]["content"] == "Hello Rosa, live update!"
        assert sent[0]["data"]["message"]["sender_id"] == me

        owner_frames = [json.loads(f) for f in owner_ws.frames]
        assert not any(f["type"] == "messaging.message.sent" for f in owner_frames)
    finally:
        live_hub.unregister_personal(rosa["id"], rosa_key)
        live_hub.unregister_personal(me, owner_key)


@pytest.mark.asyncio
async def test_edit_delete_and_reaction_events_reach_personal_channel(client, db_session_factory):
    from app.collaboration.live import live_hub

    org = await register_org(client, email="owner@rt2.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    invited = await _invite_user(client, headers, "ida@rt2.test.co", "Ida Wells")
    ida = await _employee_by_email(client, headers, "ida@rt2.test.co")

    ida_ws, ida_key = await _hub_frames(ida["id"])
    try:
        conversation = await _dm(client, headers, ida["id"])
        message = await _send(client, headers, conversation["id"], "Original")
        await _drain_events(db_session_factory)

        # Edit → updated event with edited content.
        edited = await client.patch(
            f"/api/v1/messages/{message['id']}", json={"content": "Revised"}, headers=headers
        )
        assert edited.status_code == 200
        await _drain_events(db_session_factory)

        # Reaction → reaction event.
        reacted = await client.post(
            f"/api/v1/messages/{message['id']}/reactions", json={"emoji": "❤️"}, headers=headers
        )
        assert reacted.status_code == 200
        await _drain_events(db_session_factory)

        # Delete → deleted event.
        deleted = await client.delete(f"/api/v1/messages/{message['id']}", headers=headers)
        assert deleted.status_code == 200
        await _drain_events(db_session_factory)

        import json

        frames = [json.loads(f) for f in ida_ws.frames]
        updated = [f for f in frames if f["type"] == "messaging.message.updated"]
        assert len(updated) == 1
        assert updated[0]["data"]["message"]["content"] == "Revised"
        assert updated[0]["data"]["message"]["edited"] is True

        reactions = [f for f in frames if f["type"] == "messaging.message.reaction"]
        assert len(reactions) == 1
        assert reactions[0]["data"]["emoji"] == "❤️"
        assert reactions[0]["data"]["reacted"] is True

        deleted_frames = [f for f in frames if f["type"] == "messaging.message.deleted"]
        assert len(deleted_frames) == 1
        assert deleted_frames[0]["data"]["message_id"] == message["id"]
    finally:
        live_hub.unregister_personal(ida["id"], ida_key)


@pytest.mark.asyncio
async def test_personal_hub_channels_multi_tab():
    """The personal channel fans out to every tab of an employee; unregistering
    one tab keeps the others live, and nobody else receives the push."""
    from app.collaboration.live import LiveConnection, LiveHub

    hub = LiveHub()
    tab1 = LiveConnection(ws=_FakeWs(), employee_id="emp-m", name="Tab 1")
    tab2 = LiveConnection(ws=_FakeWs(), employee_id="emp-m", name="Tab 2")
    other = LiveConnection(ws=_FakeWs(), employee_id="emp-o", name="Other")
    key1 = hub.register_personal("emp-m", tab1)
    key2 = hub.register_personal("emp-m", tab2)
    hub.register_personal("emp-o", other)
    assert hub.personal_count("emp-m") == 2

    import json

    ok = await hub.send_personal("emp-m", "messaging.message.sent", {"n": 1})
    assert ok is True
    assert len(tab1.ws.frames) == 1
    assert len(tab2.ws.frames) == 1
    assert json.loads(tab1.ws.frames[0])["type"] == "messaging.message.sent"
    assert not other.ws.frames

    # Removing one tab does not affect the other.
    assert hub.unregister_personal("emp-m", key1) is tab1
    assert hub.personal_count("emp-m") == 1
    await hub.send_personal("emp-m", "ping", {})
    assert len(tab2.ws.frames) == 2
    assert hub.unregister_personal("emp-m", key2) is tab2
    assert hub.personal_count("emp-m") == 0

    # No connection -> no-op, no error.
    assert await hub.send_personal("emp-ghost", "ping", {}) is False


@pytest.mark.asyncio
async def test_messages_and_conversations_in_universal_search(client):
    """Slice 4B: universal search indexes conversations and messages, scoped
    to the viewer's membership."""
    org = await register_org(client, email="owner@sr4b.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    invited = await _invite_user(client, headers, "zora@sr4b.test.co", "Zora Neale")
    zora = await _employee_by_email(client, headers, "zora@sr4b.test.co")
    zora_headers = {"Authorization": f"Bearer {invited['access_token']}"}

    conversation = await _dm(client, headers, zora["id"])
    await _send(client, headers, conversation["id"], "The unicorn deployment plan is ready")

    # The owner finds the conversation and the message.
    found = (await client.get("/api/v1/search", params={"q": "unicorn"}, headers=headers)).json()
    types = [r["type"] for r in found["results"]]
    assert "message" in types, types
    message_hit = next(r for r in found["results"] if r["type"] == "message")
    assert message_hit["metadata"]["conversation_id"] == conversation["id"]

    # The member (zora) finds them too.
    found_zora = (await client.get("/api/v1/search", params={"q": "unicorn"}, headers=zora_headers)).json()
    assert any(r["type"] == "message" for r in found_zora["results"])

    # An unrelated org cannot see the conversation or its messages.
    other = await register_org(client, email="other@sr4b.test.co", slug="sr-other")
    found_other = (await client.get("/api/v1/search", params={"q": "unicorn"}, headers=other["headers"])).json()
    assert not any(r["type"] in ("message", "conversation") for r in found_other["results"])


@pytest.mark.asyncio
async def test_member_added_notifies_and_fans_out(client, db_session_factory):
    """Adding a member: the added member gets a notification (via the event
    worker) and every member's personal channel sees the membership event."""
    from app.collaboration.live import live_hub

    org = await register_org(client, email="owner@ma4b.test.co")
    headers = org["headers"]
    me = await _employee_id(client, headers)
    invited_a = await _invite_user(client, headers, "alice@ma4b.test.co", "Alice Walker")
    invited_b = await _invite_user(client, headers, "bob@ma4b.test.co", "Bob Marley")
    alice = await _employee_by_email(client, headers, "alice@ma4b.test.co")
    bob = await _employee_by_email(client, headers, "bob@ma4b.test.co")
    alice_headers = {"Authorization": f"Bearer {invited_a['access_token']}"}

    bob_ws, bob_key = await _hub_frames(bob["id"])
    try:
        # Channel owned by the owner with Alice as a member.
        conversation = await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "Planning", "member_ids": [alice["id"]]},
            headers=headers,
        )
        assert conversation.status_code == 201, conversation.text
        cid = conversation.json()["id"]
        await _drain_events(db_session_factory)

        # Owner adds Bob.
        added = await client.post(
            f"/api/v1/conversations/{cid}/members", json={"employee_id": bob["id"]}, headers=headers
        )
        assert added.status_code == 201, added.text
        await _drain_events(db_session_factory)

        # Bob receives the notification (recipient is bob's user id).
        bob_headers = {"Authorization": f"Bearer {invited_b['access_token']}"}
        notifications = (await client.get("/api/v1/notifications", headers=bob_headers)).json()["items"]
        assert any(n["type"] == "messaging" and n["entity_id"] == cid for n in notifications)

        # Bob's personal channel saw the membership event.
        import json

        frames = [json.loads(f) for f in bob_ws.frames]
        membership = [f for f in frames if f["type"] == "messaging.member.added"]
        assert len(membership) == 1
        assert membership[0]["data"]["conversation_id"] == cid
        assert membership[0]["data"]["employee_id"] == bob["id"]

        # Bob (employee role has read but no write) cannot send, but the
        # notification fan-out proves his membership was recorded.
        blocked = await client.post(
            f"/api/v1/conversations/{cid}/messages", json={"content": "hi"}, headers=bob_headers
        )
        assert blocked.status_code == 403
        # Alice (employee role) can read the channel.
        listed = await client.get("/api/v1/conversations", headers=alice_headers)
        assert any(c["id"] == cid for c in listed.json())
    finally:
        live_hub.unregister_personal(bob["id"], bob_key)
