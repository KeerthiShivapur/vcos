"""Vertical Slice 3 — Step 6 task execution & collaboration regression tests.

The task is the center of execution. Beyond create/update/transition, people
collaborate: comments with @mentions, attachments, labels/tags, subtasks, and a
per-task activity history. Every collaboration action is audited and emitted on
the event bus (task.commented / task.attachment_added / task.attachment_removed)
so the work stream and notifications stay consistent.
"""

import pytest
from sqlalchemy import func, select

from app.models.task import Task, TaskAttachment, TaskComment
from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=100):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _make_task(client, headers, **extra):
    r = await client.post("/api/v1/tasks", json={"title": "T", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _notification_count(db, organization_id, type=None):
    from app.models.notification import Notification

    stmt = select(func.count()).select_from(Notification).where(Notification.organization_id == organization_id)
    if type:
        stmt = stmt.where(Notification.type == type)
    return (await db.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_tags_and_subtask_updates(client, db_session_factory):
    org = await register_org(client, email="s6a1@test.co")
    parent = await _make_task(client, org["headers"], title="Parent", tags=["core", "ops"])
    assert parent["tags"] == ["core", "ops"]

    r = await client.patch(
        f"/api/v1/tasks/{parent['id']}", json={"tags": ["core", "urgent"]}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["core", "urgent"]

    child = await _make_task(client, org["headers"], title="Child", parent_task_id=parent["id"])
    assert child["parent_task_id"] == parent["id"]

    r = await client.patch(
        f"/api/v1/tasks/{child['id']}", json={"parent_task_id": None, "priority": "high"}, headers=org["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == "high"
    assert r.json()["parent_task_id"] is None

    r = await client.get("/api/v1/tasks?tag=urgent", headers=org["headers"])
    assert r.status_code == 200
    assert any(t["id"] == parent["id"] for t in r.json())

    r = await client.get("/api/v1/tasks?parent_task_id=__none__", headers=org["headers"])
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_list_pagination_and_filters(client, db_session_factory):
    org = await register_org(client, email="s6a2@test.co")
    for i in range(5):
        await _make_task(client, org["headers"], title=f"P{i}", priority="low")
    await _make_task(client, org["headers"], title="HighOne", priority="high", tags=["top"])

    r = await client.get("/api/v1/tasks?limit=3&offset=1", headers=org["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 3

    r = await client.get("/api/v1/tasks?priority=high", headers=org["headers"])
    assert len(r.json()) == 1 and r.json()[0]["title"] == "HighOne"

    r = await client.get("/api/v1/tasks?search=HighOne", headers=org["headers"])
    assert len(r.json()) == 1

    r = await client.get("/api/v1/tasks?sort=priority", headers=org["headers"])
    assert r.json()[0]["title"] == "HighOne"


@pytest.mark.asyncio
async def test_comments_mentions_and_notifications(client, db_session_factory):
    org = await register_org(client, email="s6a3@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    r = await client.post(
        "/api/v1/users/invite",
        json={"email": "s6b@test.co", "full_name": "Bob Mentioned", "role": "employee"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert token
    r = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "full_name": "Bob Mentioned", "username": "bob6", "password": "StrongPass123!"},
    )
    assert r.status_code == 201, r.text
    bob_user_id = r.json()["user"]["id"]
    bob_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    bob = (await client.get("/api/v1/employees/me", headers=bob_headers)).json()
    assert bob["email"] == "s6b@test.co"

    task = await _make_task(client, org["headers"], title="Mention Target")

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": f"hey @{bob['email']} please look"}, headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["author_name"] == me["full_name"]
    assert bob["id"] in comment["mentions"]
    assert me["id"] not in comment["mentions"]

    r = await client.get(f"/api/v1/tasks/{task['id']}/comments", headers=org["headers"])
    assert r.status_code == 200 and len(r.json()) == 1

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        assert await _notification_count(db, org["organization"]["id"], "task.mention") >= 1
        from app.models.notification import Notification

        rows = (
            await db.execute(
                select(Notification).where(
                    Notification.organization_id == org["organization"]["id"],
                    Notification.type == "task.mention",
                )
            )
        ).scalars().all()
    assert rows[0].recipient_id == bob_user_id
    assert rows[0].entity_id == task["id"]

    r = await client.delete(f"/api/v1/tasks/{task['id']}/comments/{comment['id']}", headers=org["headers"])
    assert r.status_code == 200

    async with db_session_factory() as db:
        remaining = (
            await db.execute(
                select(func.count()).select_from(TaskComment).where(
                    TaskComment.task_id == task["id"]
                )
            )
        ).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_attachments_lifecycle(client, db_session_factory):
    org = await register_org(client, email="s6a4@test.co")
    task = await _make_task(client, org["headers"], title="File Carrier")

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/attachments",
        json={"filename": "spec.pdf", "url": "https://files.test/spec.pdf", "size_bytes": 2048, "kind": "application/pdf"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    attachment = r.json()
    assert attachment["uploaded_by_name"]

    r = await client.get(f"/api/v1/tasks/{task['id']}/attachments", headers=org["headers"])
    assert r.status_code == 200 and len(r.json()) == 1

    await _process_pending(db_session_factory)
    async with db_session_factory() as db:
        assert await _notification_count(db, org["organization"]["id"], "task.attachment_added") == 0
        assert await _notification_count(db, org["organization"]["id"], "task.mention") == 0

    r = await client.delete(f"/api/v1/tasks/{task['id']}/attachments/{attachment['id']}", headers=org["headers"])
    assert r.status_code == 200

    async with db_session_factory() as db:
        remaining = (
            await db.execute(
                select(func.count()).select_from(TaskAttachment).where(
                    TaskAttachment.task_id == task["id"]
                )
            )
        ).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_activity_feed_covers_collaboration_and_changes(client, db_session_factory):
    org = await register_org(client, email="s6a5@test.co")
    task = await _make_task(client, org["headers"], title="Audited")
    r = await client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "first"}, headers=org["headers"])
    assert r.status_code == 201
    r = await client.post(
        f"/api/v1/tasks/{task['id']}/attachments",
        json={"filename": "a.txt", "url": "https://files.test/a.txt"}, headers=org["headers"],
    )
    assert r.status_code == 201
    await client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"status": "in_progress", "priority": "high"}, headers=org["headers"],
    )

    r = await client.get(f"/api/v1/tasks/{task['id']}/activity", headers=org["headers"])
    assert r.status_code == 200
    actions = [entry["action"] for entry in r.json()]
    assert "task.commented" in actions
    assert "task.attachment_added" in actions
    assert "task.updated" in actions
    for entry in r.json():
        assert entry["actor_email"] == org["user"]["email"]

    r = await client.get("/api/v1/tasks", headers=org["headers"])
    assert any(t["id"] == task["id"] and t["status"] == "in_progress" for t in r.json())


@pytest.mark.asyncio
async def test_collaboration_events_reach_event_catalog(client, db_session_factory):
    from app.events.event_models import EVENT_CATALOG

    for name in ("task.commented", "task.attachment_added", "task.attachment_removed"):
        assert name in EVENT_CATALOG

    org = await register_org(client, email="s6a6@test.co")
    task = await _make_task(client, org["headers"], title="Busy")
    await client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "x"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    from app.models.notification import Event as WorkEvent

    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(WorkEvent).where(
                    WorkEvent.organization_id == org["organization"]["id"],
                    WorkEvent.name == "task.commented",
                )
            )
        ).scalars().all()
    assert rows, "task.commented must land on the event bus"
