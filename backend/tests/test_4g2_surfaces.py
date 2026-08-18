"""Slice 4G.2 — Execution Coordination surfaces (API + brain questions).

The Coordination Center and per-project coordination views fold into the
Execution Command Center surface (one surface, not a separate module):

* GET /execution/coordination/center is the org-wide coordination view,
* GET /execution/coordination/projects/{id} is one project's coordination
  view (findings + handoff ledger + propagation history + alternatives +
  what-if options with honest boundaries),
* GET /execution/coordination/projects/{id}/what-if returns only the
  bounded options,
* POST /execution/coordination/incidents/{id}/resolve is the human action,
* brain questions ("which projects compete for the same people", "what
  should we coordinate first", "where are handoffs failing", "what happens
  if we delay <project>") route to the coordination surface with evidence
  and confidence.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.execution_coordination import (
    CoordinationHandoff,
    CoordinationIncident,
)
from app.models.task import Task
from app.models.team import Team
from tests.conftest import register_org
from tests.test_4g2_engine import (
    _drain,
    _hire,
    _project,
    _publish,
)

BRAIN = "/api/v1/brain"


async def _center(client, headers):
    res = await client.get(f"{BRAIN}/execution/coordination/center", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _ask(client, headers, question):
    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": question},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _make_recurring(client, db_session_factory, org_id, actor,
                          a, b, project_id):
    now = datetime.now(timezone.utc)
    async with db_session_factory() as db:
        for i in range(3):
            t = Task(
                organization_id=org_id, project_id=project_id,
                title=f"Surface recur {i}", status="completed",
                assignee_id=a["id"],
            )
            db.add(t)
            await db.flush()
            db.add(CoordinationHandoff(
                organization_id=org_id, project_id=project_id,
                task_id=t.id, task_title=f"Surface recur {i}",
                from_owner_id=a["id"], from_owner_label=a["full_name"],
                to_owner_id=b["id"], to_owner_label=b["full_name"],
                source_event_id=f"4g2-surfseed{i}",
                status="completed",
                occurred_at=now - timedelta(days=10),
                completed_at=now - timedelta(days=9),
                duration_hours=80.0,
            ))
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": "surface-trigger", "project_id": project_id,
        "assignee_id": a["id"],
    })


async def test_coordination_center_org_wide_surface(client, db_session_factory):
    org = await register_org(client, email="4g2_s1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-s1a@test.co", "Mia", "One")
    b = await _hire(client, headers, "4g2-s1b@test.co", "Max", "Two")
    project = await _project(client, headers, "Surface One")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )

    center = await _center(client, headers)
    assert center["total_incidents"] >= 1
    counts = center["counts"]
    assert counts["recurring_handoff"] >= 1
    assert "generated_at" in center
    kinds = {r["kind"] for r in center["incidents"]}
    assert "recurring_handoff" in kinds
    incident = next(r for r in center["incidents"] if r["kind"] == "recurring_handoff")
    assert incident["confidence"] > 0.7
    assert incident["evidence"]
    assert incident["project_name"] == "Surface One"
    assert center["handoffs"]["pending"] == 0
    assert center["handoffs"]["slow_30d"] == 3
    assert center["recommendations"], "center must surface recommendations"
    rec = center["recommendations"][0]
    assert rec["kind"] == "recurring_handoff"
    assert rec["why"]
    assert rec["incident_id"] == incident["incident_id"]
    assert any(p["name"] == "Surface One" for p in center["projects_affected"])


async def test_project_coordination_view_and_what_if(client, db_session_factory):
    org = await register_org(client, email="4g2_s2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-s2a@test.co", "Nia", "One")
    b = await _hire(client, headers, "4g2-s2b@test.co", "Noah", "Two")
    project = await _project(client, headers, "Surface Two")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )

    res = await client.get(
        f"{BRAIN}/execution/coordination/projects/{project['id']}",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["name"] == "Surface Two"
    assert any(i["kind"] == "recurring_handoff" for i in detail["incidents"])
    assert detail["handoffs"]["recent_completed"] or detail["handoffs"]["pending"]
    assert detail["propagation"], "history entries must be present"
    assert any(h["event_name"] == "coordination.incident.detected"
               for h in detail["propagation"])
    assert detail["what_if"]["boundary"]
    assert detail["what_if"]["options"]
    kinds = {o["kind"] for o in detail["what_if"]["options"]}
    assert "knowledge" in kinds or "delay" in kinds
    assert all(o["boundary"] for o in detail["what_if"]["options"])

    res = await client.get(
        f"{BRAIN}/execution/coordination/projects/{project['id']}/what-if",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    what_if = res.json()["what_if"]
    assert what_if["boundary"]
    assert what_if["options"]


async def test_incident_resolve_is_a_human_action(client, db_session_factory):
    org = await register_org(client, email="4g2_s3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-s3a@test.co", "Ola", "One")
    b = await _hire(client, headers, "4g2-s3b@test.co", "Omar", "Two")
    project = await _project(client, headers, "Surface Three")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )
    center = await _center(client, headers)
    incident = next(
        r for r in center["incidents"] if r["kind"] == "recurring_handoff"
    )

    res = await client.post(
        f"{BRAIN}/execution/coordination/incidents/{incident['incident_id']}/resolve",
        json={"note": "Standup agreement reached"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    resolved = res.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolve_note"] == "Standup agreement reached"

    center = await _center(client, headers)
    assert all(r["incident_id"] != incident["incident_id"]
               for r in center["incidents"])
    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(CoordinationIncident).where(
                    CoordinationIncident.id == incident["incident_id"],
                )
            )
        ).scalar_one()
        assert row.status == "resolved"
        assert row.resolved_by == org["user"]["id"]


async def test_brain_questions_route_to_coordination(client, db_session_factory):
    org = await register_org(client, email="4g2_s4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-s4a@test.co", "Pia", "One")
    b = await _hire(client, headers, "4g2-s4b@test.co", "Pete", "Two")
    project = await _project(client, headers, "Surface Four")
    await _drain(db_session_factory)
    await _make_recurring(
        client, db_session_factory, org_id, actor, a, b, project["id"],
    )

    res = await _ask(client, headers, "where are handoffs failing?")
    assert res["intent"] == "coordination"
    assert res["total_incidents"] >= 1
    assert res["counts"]["recurring_handoff"] >= 1

    res = await _ask(client, headers, "what should we coordinate first?")
    assert res["intent"] == "coordination"

    res = await _ask(client, headers, "how do our projects coordinate?")
    assert res["intent"] == "coordination"

    res = await _ask(client, headers, "what happens if we delay Surface Four?")
    assert res["intent"] == "coordination"
    assert res["project"]["name"] == "Surface Four"
    assert res["project"]["what_if"]["options"]

    res = await _ask(client, headers, "which projects compete for the same people?")
    assert res["intent"] == "coordination"
    assert res["scope"] == "org"
