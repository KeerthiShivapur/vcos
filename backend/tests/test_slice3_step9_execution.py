"""Vertical Slice 3 — Step 9 complete work execution collaboration.

A real employee must be able to receive a task, open it, understand it, edit
what they are permitted to edit, communicate about it, attach material,
create and complete subtasks, see dependencies and blockers, complete the
work, and have the full execution history preserved — with RBAC and tenancy
enforced on every operation.
"""

import pytest
from sqlalchemy import select

from app.models.notification import Event as WorkEvent
from tests.conftest import register_org


async def _process_pending(db_session_factory, limit=150):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        processed = await event_bus.process_pending(db, limit=limit)
        await db.commit()
        return processed


async def _task(client, headers, **extra):
    r = await client.post("/api/v1/tasks", json={"title": "T", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _dep(client, headers, task_id, depends_on_task_id, kind="finish_to_start"):
    r = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": depends_on_task_id, "kind": kind},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _events(db, organization_id, name):
    return (
        await db.execute(
            select(WorkEvent).where(
                WorkEvent.organization_id == organization_id, WorkEvent.name == name
            )
        )
    ).scalars().all()


async def _notifications(db, organization_id, type):
    from app.models.notification import Notification

    return (
        await db.execute(
            select(Notification).where(
                Notification.organization_id == organization_id, Notification.type == type
            )
        )
    ).scalars().all()


async def _invite_employee(client, owner_headers, email, role="employee", full_name="Emp Worker"):
    r = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": full_name, "role": role},
        headers=owner_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


async def _join_invite(client, token, email, password="StrongPass123!"):
    r = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "full_name": "Emp Worker", "password": password},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "email": email}


@pytest.mark.asyncio
async def test_employee_executes_own_task(client, db_session_factory):
    """The assigned employee can run their own task end-to-end; nothing more."""
    org = await register_org(client, email="s9a1@test.co")
    owner_me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()

    token = await _invite_employee(client, org["headers"], "s9a1-emp@test.co")
    emp = await _join_invite(client, token, "s9a1-emp@test.co")
    emp_me = (await client.get("/api/v1/employees/me", headers=emp["headers"])).json()

    theirs = await _task(client, org["headers"], title="Their task", assignee_id=emp_me["id"])
    mine = await _task(client, org["headers"], title="Owner task", assignee_id=owner_me["id"])

    # Read their own task.
    r = await client.get(f"/api/v1/tasks/{theirs['id']}", headers=emp["headers"])
    assert r.status_code == 200

    # Transition their own task.
    r = await client.post(
        f"/api/v1/tasks/{theirs['id']}/transition", json={"status": "in_progress"}, headers=emp["headers"]
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/tasks/{theirs['id']}/transition", json={"status": "completed"}, headers=emp["headers"]
    )
    assert r.status_code == 200, r.text

    # Edit fields on their own task.
    r = await client.patch(
        f"/api/v1/tasks/{theirs['id']}",
        json={"priority": "high", "due_date": "2026-12-31", "title": "Their task v2"},
        headers=emp["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == "high"

    # Collaborate on their own task.
    r = await client.post(
        f"/api/v1/tasks/{theirs['id']}/comments", json={"body": "Done here"}, headers=emp["headers"]
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/api/v1/tasks/{theirs['id']}/attachments",
        json={"filename": "proof.pdf", "url": "https://files.test/proof.pdf", "size_bytes": 42, "kind": "application/pdf"},
        headers=emp["headers"],
    )
    assert r.status_code == 201, r.text

    # Add a subtask under their own task.
    r = await client.post(
        "/api/v1/tasks",
        json={"title": "Sub of theirs", "parent_task_id": theirs["id"], "assignee_id": emp_me["id"]},
        headers=emp["headers"],
    )
    assert r.status_code == 201, r.text

    # Boundary: nothing outside their own assignment.
    r = await client.post(f"/api/v1/tasks/{mine['id']}/transition", json={"status": "in_progress"}, headers=emp["headers"])
    assert r.status_code == 403
    r = await client.patch(f"/api/v1/tasks/{mine['id']}", json={"title": "Hijack"}, headers=emp["headers"])
    assert r.status_code == 403
    r = await client.delete(f"/api/v1/tasks/{mine['id']}", headers=emp["headers"])
    assert r.status_code == 403
    r = await client.post("/api/v1/tasks", json={"title": "Own project"}, headers=emp["headers"])
    assert r.status_code == 403
    r = await client.post(
        f"/api/v1/tasks/{mine['id']}/dependencies",
        json={"depends_on_task_id": theirs["id"]},
        headers=emp["headers"],
    )
    assert r.status_code == 403

    # Cannot delete someone else's comment on their own task either.
    owner_comment = await client.post(
        f"/api/v1/tasks/{theirs['id']}/comments", json={"body": "Owner note"}, headers=org["headers"]
    )
    r = await client.delete(
        f"/api/v1/tasks/{theirs['id']}/comments/{owner_comment.json()['id']}", headers=emp["headers"]
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assignee_cannot_touch_unassigned_task(client, db_session_factory):
    org = await register_org(client, email="s9a2@test.co")
    token = await _invite_employee(client, org["headers"], "s9a2-emp@test.co")
    emp = await _join_invite(client, token, "s9a2-emp@test.co")
    unassigned = await _task(client, org["headers"], title="Nobody's task")

    r = await client.post(
        f"/api/v1/tasks/{unassigned['id']}/transition", json={"status": "in_progress"}, headers=emp["headers"]
    )
    assert r.status_code == 403, "unassigned tasks are not self-service"


@pytest.mark.asyncio
async def test_subtask_lifecycle_and_parent_progress(client, db_session_factory):
    org = await register_org(client, email="s9a3@test.co")
    parent = await _task(client, org["headers"], title="Parent")
    sub1 = await _task(client, org["headers"], title="Sub 1", parent_task_id=parent["id"])
    sub2 = await _task(client, org["headers"], title="Sub 2", parent_task_id=parent["id"])

    # Subtasks show up under the parent via the filter.
    r = await client.get(f"/api/v1/tasks?parent_task_id={parent['id']}", headers=org["headers"])
    assert {t["id"] for t in r.json()} == {sub1["id"], sub2["id"]}

    # Parent cannot complete while subtasks are open.
    r = await client.post(f"/api/v1/tasks/{parent['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 400, "parent completion must be gated on subtasks"
    assert "subtask" in r.json()["detail"].lower()

    # Completing one subtask moves parent progress to 50%.
    await client.post(f"/api/v1/tasks/{sub1['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/tasks/{parent['id']}", headers=org["headers"])
    assert r.json()["progress"] == 50, "parent progress must follow subtask completion"
    assert r.json()["subtasks_count"] == 2
    assert r.json()["subtasks_completed"] == 1

    # All subtasks done → parent may complete.
    await client.post(f"/api/v1/tasks/{sub2['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)
    r = await client.get(f"/api/v1/tasks/{parent['id']}", headers=org["headers"])
    assert r.json()["progress"] == 100
    r = await client.post(f"/api/v1/tasks/{parent['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    assert r.status_code == 200, r.text

    # Cycle guard: a task cannot become its own parent.
    r = await client.patch(f"/api/v1/tasks/{sub1['id']}", json={"parent_task_id": sub1["id"]}, headers=org["headers"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_labels_filter_and_display(client, db_session_factory):
    org = await register_org(client, email="s9a4@test.co")
    tagged = await _task(client, org["headers"], title="Tagged", tags=["urgent", "sales"])
    await _task(client, org["headers"], title="Plain")

    r = await client.get("/api/v1/tasks?tag=urgent", headers=org["headers"])
    ids = {t["id"] for t in r.json()}
    assert tagged["id"] in ids
    assert len(ids) == 1

    r = await client.patch(f"/api/v1/tasks/{tagged['id']}", json={"tags": ["urgent", "billing"]}, headers=org["headers"])
    assert r.status_code == 200
    assert r.json()["tags"] == ["urgent", "billing"]

    r = await client.get("/api/v1/tasks?tag=sales", headers=org["headers"])
    assert r.json() == []


@pytest.mark.asyncio
async def test_comment_mention_notifies_assignee(client, db_session_factory):
    org = await register_org(client, email="s9a5@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    token = await _invite_employee(client, org["headers"], "s9a5-bob@test.co", full_name="Bob Mentioned")
    bob = await _join_invite(client, token, "s9a5-bob@test.co")
    bob_me = (await client.get("/api/v1/employees/me", headers=bob["headers"])).json()
    task = await _task(client, org["headers"], title="Mentioned", assignee_id=me["id"])

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": f"hey @{bob_me['email']} please review this one"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    await _process_pending(db_session_factory)

    async with db_session_factory() as db:
        notifs = await _notifications(db, org["organization"]["id"], "task.mention")
        assert notifs, "mention must produce a notification"
        assert notifs[0].entity_id == task["id"]

    r = await client.get(f"/api/v1/tasks/{task['id']}/comments", headers=org["headers"])
    assert r.status_code == 200
    assert r.json() and r.json()[0]["body"].startswith("hey @")


@pytest.mark.asyncio
async def test_attachment_lifecycle_and_activity(client, db_session_factory):
    org = await register_org(client, email="s9a6@test.co")
    task = await _task(client, org["headers"], title="Attachments")

    r = await client.post(
        f"/api/v1/tasks/{task['id']}/attachments",
        json={"filename": "spec.pdf", "url": "https://files.test/spec.pdf", "size_bytes": 1234, "kind": "application/pdf"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    attachment_id = r.json()["id"]

    r = await client.get(f"/api/v1/tasks/{task['id']}/attachments", headers=org["headers"])
    assert len(r.json()) == 1
    assert r.json()[0]["filename"] == "spec.pdf"

    r = await client.delete(f"/api/v1/tasks/{task['id']}/attachments/{attachment_id}", headers=org["headers"])
    assert r.status_code == 200
    r = await client.get(f"/api/v1/tasks/{task['id']}/attachments", headers=org["headers"])
    assert r.json() == []

    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "task.attachment_added")
        assert await _events(db, org["organization"]["id"], "task.attachment_removed")


@pytest.mark.asyncio
async def test_activity_history_preserves_execution(client, db_session_factory):
    org = await register_org(client, email="s9a7@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    task = await _task(client, org["headers"], title="History")
    await client.patch(f"/api/v1/tasks/{task['id']}", json={"assignee_id": me["id"], "priority": "high"}, headers=org["headers"])
    await client.post(f"/api/v1/tasks/{task['id']}/transition", json={"status": "in_progress"}, headers=org["headers"])
    await client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "First note"}, headers=org["headers"])
    await client.post(
        f"/api/v1/tasks/{task['id']}/attachments",
        json={"filename": "a.txt", "url": "https://files.test/a.txt", "size_bytes": 1, "kind": "text/plain"},
        headers=org["headers"],
    )
    prereq = await _task(client, org["headers"], title="Prereq")
    await client.post(f"/api/v1/tasks/{prereq['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _dep(client, org["headers"], task["id"], prereq["id"])
    await client.post(f"/api/v1/tasks/{task['id']}/transition", json={"status": "completed"}, headers=org["headers"])

    r = await client.get(f"/api/v1/tasks/{task['id']}/activity", headers=org["headers"])
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()]
    assert "task.created" in actions
    assert "task.updated" in actions
    assert "task.transitioned" in actions
    assert "task.commented" in actions
    assert "task.attachment_added" in actions
    assert "dependency.added" in actions
    assert "task.completed" in actions

    updated = next(a for a in r.json() if a["action"] == "task.updated")
    changes = (updated["details"] or {}).get("changes") or {}
    assert "assignee_id" in changes and "priority" in changes, "edits must record field-level changes"

    # Activity is tenant-scoped and time-ordered (newest first).
    assert r.json()[0]["action"] == "task.completed"


@pytest.mark.asyncio
async def test_dependency_blocking_and_unblocking_flow(client, db_session_factory):
    org = await register_org(client, email="s9a8@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    prereq = await _task(client, org["headers"], title="Prereq")
    dependent = await _task(client, org["headers"], title="Dependent", assignee_id=me["id"])
    await _dep(client, org["headers"], dependent["id"], prereq["id"], "blocking")

    # Blocked: cannot start while the blocking dependency is open.
    r = await client.post(
        f"/api/v1/tasks/{dependent['id']}/transition", json={"status": "in_progress"}, headers=org["headers"]
    )
    assert r.status_code == 400
    assert "unsatisfied" in r.json()["detail"].lower()

    # Marked blocked explicitly → the API explains why.
    await client.post(f"/api/v1/tasks/{dependent['id']}/transition", json={"status": "blocked"}, headers=org["headers"])
    r = await client.get(f"/api/v1/tasks/{dependent['id']}", headers=org["headers"])
    blocked_by = r.json()["blocked_by"] or []
    assert any(b["task_id"] == prereq["id"] for b in blocked_by), "blocked task must surface its blockers"

    # Completing the prerequisite unblocks automatically.
    await client.post(f"/api/v1/tasks/{prereq['id']}/transition", json={"status": "completed"}, headers=org["headers"])
    await _process_pending(db_session_factory)

    r = await client.get(f"/api/v1/tasks/{dependent['id']}", headers=org["headers"])
    assert r.json()["status"] == "todo"

    r = await client.post(
        f"/api/v1/tasks/{dependent['id']}/transition", json={"status": "in_progress"}, headers=org["headers"]
    )
    assert r.status_code == 200

    async with db_session_factory() as db:
        assert await _events(db, org["organization"]["id"], "task.unblocked")
        assert await _notifications(db, org["organization"]["id"], "task.unblocked")


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="s9a9@test.co")
    org_b = await register_org(client, email="s9b0@test.co", name="Other Corp")
    task = await _task(client, org_a["headers"], title="Secret")

    r = await client.get(f"/api/v1/tasks/{task['id']}", headers=org_b["headers"])
    assert r.status_code == 404
    r = await client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "x"}, headers=org_b["headers"])
    assert r.status_code == 404
    r = await client.post(f"/api/v1/tasks/{task['id']}/transition", json={"status": "completed"}, headers=org_b["headers"])
    assert r.status_code == 404
    r = await client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "hi"}, headers=org_b["headers"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_manager_controls_dependencies_and_lifecycle(client, db_session_factory):
    org = await register_org(client, email="s9c1@test.co")
    me = (await client.get("/api/v1/employees/me", headers=org["headers"])).json()
    token = await _invite_employee(client, org["headers"], "s9c1-mgr@test.co", role="manager")
    mgr = await _join_invite(client, token, "s9c1-mgr@test.co")
    a = await _task(client, org["headers"], title="A", assignee_id=me["id"])
    b = await _task(client, org["headers"], title="B", assignee_id=me["id"])

    # A manager can wire dependencies and reassign work.
    r = await client.post(
        f"/api/v1/tasks/{b['id']}/dependencies",
        json={"depends_on_task_id": a["id"], "kind": "finish_to_start"},
        headers=mgr["headers"],
    )
    assert r.status_code == 201, r.text

    # A manager can also execute a task they are not assigned to.
    r = await client.post(f"/api/v1/tasks/{a['id']}/transition", json={"status": "completed"}, headers=mgr["headers"])
    assert r.status_code == 200, r.text

    # Manager can delete an employee's comment (moderation).
    comment = await client.post(f"/api/v1/tasks/{b['id']}/comments", json={"body": "mine"}, headers=org["headers"])
    r = await client.delete(
        f"/api/v1/tasks/{b['id']}/comments/{comment.json()['id']}", headers=mgr["headers"]
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_blocked_task_explains_reason(client, db_session_factory):
    org = await register_org(client, email="s9d1@test.co")
    prereq = await _task(client, org["headers"], title="Gate")
    dependent = await _task(client, org["headers"], title="Waits")
    await _dep(client, org["headers"], dependent["id"], prereq["id"], "blocking")

    r = await client.post(f"/api/v1/tasks/{dependent['id']}/transition", json={"status": "in_progress"}, headers=org["headers"])
    assert r.status_code == 400
    assert r.json()["detail"].lower() == "task has unsatisfied dependencies: gate"
