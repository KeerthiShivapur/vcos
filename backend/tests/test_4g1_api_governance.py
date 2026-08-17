"""Slice 4G.1 — API endpoints and governance.

* command/next are org-wide surfaces: scoped callers get 404,
* project detail is visible to scoped callers inside their scope only,
* outcome recording is a HUMAN write (projects:manage) and is advisory —
  the project row never changes, the events replay without duplicates,
* replaying an already-processed event never crashes the bus.
"""

from sqlalchemy import select

from app.models.project import Project
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
OUTCOME = "/execution/projects/{pid}/outcome"


async def _drain(db_session_factory, limit=200, rounds=4):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"ga-{name.lower().replace(' ', '-')[:20]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _drained_project(client, headers, db_session_factory, name):
    project = await _project(client, headers, name)
    await _drain(db_session_factory)
    return project


async def _scoped_reader(client, headers, scope_id, email):
    return await h.invite_scoped_reader(client, headers, scope_id, email)


async def _scope(client, headers, scope_type, entity_id, name):
    res = await client.post(
        "/api/v1/governance/scopes",
        json={"name": name, "scope_type": scope_type, "entity_id": entity_id},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# ---------------------------------------------------------------- org-wide only


async def test_command_and_next_are_org_wide_only(client, db_session_factory):
    org = await register_org(client, email="4g1_a1@test.co")
    headers = org["headers"]
    visible = await _drained_project(
        client, headers, db_session_factory, "Visible Vault")

    scope = await _scope(client, headers, "project", visible["id"],
                         "Visible scope")
    reader = await _scoped_reader(client, headers, scope["id"], "4g1-ar@test.co")

    for path in (f"{BRAIN}/execution/command", f"{BRAIN}/execution/next"):
        res = await client.get(path, headers=reader)
        assert res.status_code == 404, (path, res.text)
        res = await client.get(path, headers=headers)
        assert res.status_code == 200, (path, res.text)


async def test_project_detail_scope_rules(client, db_session_factory):
    org = await register_org(client, email="4g1_a2@test.co")
    headers = org["headers"]
    visible = await _drained_project(client, headers, db_session_factory, "In Scope")
    hidden = await _drained_project(client, headers, db_session_factory, "Out Scope")

    scope = await _scope(client, headers, "project", visible["id"], "In scope")
    reader = await _scoped_reader(client, headers, scope["id"], "4g1-ar2@test.co")

    # the scoped reader sees its own project
    res = await client.get(
        f"{BRAIN}/execution/projects/{visible['id']}", headers=reader)
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "In Scope"
    assert res.json()["health_status"] == "healthy"

    # other projects are not visible
    res = await client.get(
        f"{BRAIN}/execution/projects/{hidden['id']}", headers=reader)
    assert res.status_code == 404, res.text

    # org-wide owner sees both; unknown project 404
    for pid in (visible["id"], hidden["id"]):
        res = await client.get(
            f"{BRAIN}/execution/projects/{pid}", headers=headers)
        assert res.status_code == 200, res.text
    res = await client.get(
        f"{BRAIN}/execution/projects/not-a-project", headers=headers)
    assert res.status_code == 404, res.text


async def test_detail_lazy_materializes_missing_record(client, db_session_factory):
    org = await register_org(client, email="4g1_a3@test.co")
    headers = org["headers"]
    project = await _project(client, headers, "Lazy Vault")
    res = await client.get(
        f"{BRAIN}/execution/projects/{project['id']}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["health_status"] == "healthy"


# ---------------------------------------------------------------- outcome


async def test_outcome_record_is_human_and_advisory(client, db_session_factory):
    org = await register_org(client, email="4g1_a4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Doomed")
    url = OUTCOME.format(pid=project["id"])

    res = await client.post(
        f"{BRAIN}{url}", headers=headers,
        json={
            "status": "partial",
            "planned_outcome": "Ship the platform",
            "actual_outcome": "Ship the MVP only",
            "assessment": "Capacity held us back",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "partial"

    # the outcome is part of the execution detail
    detail = (await client.get(
        f"{BRAIN}/execution/projects/{project['id']}", headers=headers)).json()
    assert detail["outcome"]["assessment"] == "Capacity held us back"
    assert detail["outcome"]["recorded_by"] == org["user"]["id"]

    # advisory-only: the project row itself never changed
    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == org_id,
                    Project.id == project["id"],
                )
            )
        ).scalar_one()
        assert row.status == "draft"
        assert row.progress == 0

    # validation
    bad = await client.post(
        f"{BRAIN}{url}", headers=headers,
        json={"status": "whatever"},
    )
    assert bad.status_code == 400, bad.text
    missing = await client.post(
        f"{BRAIN}{OUTCOME.format(pid='not-a-project')}", headers=headers,
        json={"status": "successful"},
    )
    assert missing.status_code == 404, missing.text


async def test_outcome_requires_projects_manage(client, db_session_factory):
    org = await register_org(client, email="4g1_a5@test.co")
    headers = org["headers"]
    project = await _drained_project(
        client, headers, db_session_factory, "Guarded Outcome")
    scope = await _scope(client, headers, "project", project["id"], "Proj scope")
    reader = await _scoped_reader(client, headers, scope["id"], "4g1-ar5@test.co")

    res = await client.post(
        f"{BRAIN}{OUTCOME.format(pid=project['id'])}",
        headers=reader, json={"status": "successful"},
    )
    assert res.status_code in (403, 404), res.text


# ---------------------------------------------------------------- replay safety


async def test_replayed_events_never_crash_the_bus(client, db_session_factory):
    org = await register_org(client, email="4g1_a6@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Replay")

    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.created", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"task_id": "t-replay", "project_id": project["id"],
                     "status": "backlog"},
            enqueue=True, flush=False,
        )
        await db.commit()
    first = await _drain(db_session_factory)
    assert first >= 1
    again = await _drain(db_session_factory)
    assert again == 0

    detail = (await client.get(
        f"{BRAIN}/execution/projects/{project['id']}", headers=headers)).json()
    assert detail["health_status"] == "healthy"