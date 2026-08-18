"""Slice 4G.2 — governance: filters run BEFORE assembly.

Scoped callers:
* 404 on the org-wide Coordination Center (same idiom as 4G.1/4F.6/4F.7),
* see project coordination views only for projects inside their governance
  scope, and only project-scoped finding kinds — pair/org findings
  (shared_capacity, critical_conflict) never leak names or capacity,
* cannot resolve findings (projects:manage required), and org-level
  findings are unreachable by id,
* brain coordination questions return only their own projects (scope
  "project"), never aggregated org counts.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.execution_coordination import CoordinationHandoff
from app.models.task import Task
from tests import _brain4d6_helpers as h
from tests.conftest import register_org
from tests.test_4g2_engine import _drain, _hire, _project

BRAIN = "/api/v1/brain"


async def _make_recurring(client, db_session_factory, org_id, actor,
                          a, b, project_id):
    from app.events.event_bus import event_bus

    now = datetime.now(timezone.utc)
    async with db_session_factory() as db:
        for i in range(3):
            t = Task(
                organization_id=org_id, project_id=project_id,
                title=f"Gov recur {i}", status="completed",
                assignee_id=a["id"],
            )
            db.add(t)
            await db.flush()
            db.add(CoordinationHandoff(
                organization_id=org_id, project_id=project_id,
                task_id=t.id, task_title=f"Gov recur {i}",
                from_owner_id=a["id"], from_owner_label=a["full_name"],
                to_owner_id=b["id"], to_owner_label=b["full_name"],
                source_event_id=f"4g2-govseed{i}",
                status="completed",
                occurred_at=now - timedelta(days=10),
                completed_at=now - timedelta(days=9),
                duration_hours=80.0,
            ))
        await db.commit()
    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.transitioned", organization_id=org_id,
            actor_id=actor, payload={"task_id": "gov-trigger",
                                     "project_id": project_id,
                                     "assignee_id": a["id"]},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _scope(client, headers, scope_type, entity_id, name):
    res = await client.post(
        "/api/v1/governance/scopes",
        json={"name": name, "scope_type": scope_type, "entity_id": entity_id},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


async def _scoped_reader(client, headers, scope_id, email):
    return await h.invite_scoped_reader(client, headers, scope_id, email)


async def test_scoped_caller_404s_on_center(client, db_session_factory):
    org = await register_org(client, email="4g2_g1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-g1a@test.co", "Quinn", "One")
    b = await _hire(client, headers, "4g2-g1b@test.co", "Quincy", "Two")
    project = await _project(client, headers, "Gov One")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )
    scope = await _scope(client, headers, "project", project["id"], "Gov scope")
    scoped = await _scoped_reader(client, headers, scope["id"], "4g2-g1s@test.co")

    res = await client.get(f"{BRAIN}/execution/coordination/center", headers=scoped)
    assert res.status_code == 404
    res = await client.get(
        f"{BRAIN}/execution/coordination/center", headers=headers)
    assert res.status_code == 200


async def test_scoped_caller_sees_only_project_scoped_kinds(
    client, db_session_factory,
):
    org = await register_org(client, email="4g2_g2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-g2a@test.co", "Ria", "One")
    b = await _hire(client, headers, "4g2-g2b@test.co", "Ray", "Two")
    project = await _project(client, headers, "Gov Two")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )
    scope = await _scope(client, headers, "project", project["id"], "Gov scope 2")
    scoped = await _scoped_reader(client, headers, scope["id"], "4g2-g2s@test.co")

    center = (await client.get(
        f"{BRAIN}/execution/coordination/center", headers=headers,
    )).json()
    assert center["counts"]["recurring_handoff"] >= 1

    res = await client.get(
        f"{BRAIN}/execution/coordination/projects/{project['id']}",
        headers=scoped,
    )
    assert res.status_code == 200, res.text
    detail = res.json()
    assert any(i["kind"] == "recurring_handoff" for i in detail["incidents"])
    assert all(
        i["kind"] in ("handoff_risk", "recurring_handoff", "coordination_gap",
                      "propagation_risk")
        for i in detail["incidents"]
    )
    assert "shared_capacity" not in detail
    assert "critical_conflict" not in detail

    res = await client.get(
        f"{BRAIN}/execution/coordination/projects/{project['id']}/what-if",
        headers=scoped,
    )
    assert res.status_code == 200, res.text

    res = await client.get(
        f"{BRAIN}/execution/coordination/projects/other-project-id",
        headers=scoped,
    )
    assert res.status_code == 404

    res = await client.post(
        f"{BRAIN}/knowledge/query", headers=scoped,
        json={"question": "where are handoffs failing?"},
    )
    assert res.status_code == 200, res.text
    answer = res.json()
    assert answer["intent"] == "coordination"
    assert answer["scope"] == "project"
    assert "total_incidents" not in answer
    assert "projects" in answer


async def test_scoped_caller_cannot_resolve_findings(client, db_session_factory):
    org = await register_org(client, email="4g2_g3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-g3a@test.co", "Sam", "One")
    b = await _hire(client, headers, "4g2-g3b@test.co", "Sue", "Two")
    project = await _project(client, headers, "Gov Three")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )
    center = (await client.get(
        f"{BRAIN}/execution/coordination/center", headers=headers,
    )).json()
    incident = next(
        r for r in center["incidents"] if r["kind"] == "recurring_handoff"
    )
    scope = await _scope(client, headers, "project", project["id"], "Gov scope 3")
    scoped = await _scoped_reader(client, headers, scope["id"], "4g2-g3s@test.co")

    res = await client.post(
        f"{BRAIN}/execution/coordination/incidents/{incident['incident_id']}/resolve",
        json={"note": "nope"},
        headers=scoped,
    )
    assert res.status_code == 403, res.text

    res = await client.post(
        f"{BRAIN}/execution/coordination/incidents/{incident['incident_id']}/resolve",
        json={"note": "owner confirmed"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "resolved"
