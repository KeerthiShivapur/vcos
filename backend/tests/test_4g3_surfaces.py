"""Slice 4G.3 — surfaces: the strategy API walkthrough, the event stream
each write leaves behind, and the Universal Brain routing of strategy
questions (goal / focus / gaps / portfolio branches + the scoped answer).

Everything is the canonical goal record: advisory, evidence-backed and
deterministic — never a dashboard.
"""

import json

from sqlalchemy import select

from app.models.notification import Event
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
STRATEGY = f"{BRAIN}/execution/strategy"


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


async def _goal(client, headers, title, priority=3):
    created = await client.post(
        f"{STRATEGY}/goals",
        json={"title": title, "kind": "revenue", "priority": priority,
              "metric_kind": "revenue", "metric_unit": "pct",
              "target_value": 25, "current_value": 5,
              "timeline_label": "FY2026"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["goal_id"]


async def _objective(client, headers, goal_id, title="Conversion", caps=None):
    created = await client.post(
        f"{STRATEGY}/objectives",
        json={"goal_id": goal_id, "title": title,
              "required_capabilities": caps or []},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["objective_id"]


async def _initiative(client, headers, objective_id, title="Platform 3.0",
                      caps=None, expected=None, commitments=None):
    created = await client.post(
        f"{STRATEGY}/initiatives",
        json={"objective_id": objective_id, "title": title,
              "required_capabilities": caps or [],
              "expected_outcome": expected,
              "customer_commitments": commitments or []},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["initiative_id"]


async def _priority(client, headers, goal_id, priority, reason="executive review"):
    changed = await client.post(
        f"{STRATEGY}/goals/{goal_id}/priority",
        json={"priority": priority, "reason": reason}, headers=headers,
    )
    assert changed.status_code == 200, changed.text
    return changed.json()


async def _link(client, headers, initiative_id, project_id):
    resp = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _unlink(client, headers, initiative_id, project_id):
    resp = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/unlink",
        json={"project_id": project_id}, headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _outcome(client, headers, initiative_id, expected, actual,
                   metric="revenue", unit="pct"):
    recorded = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/outcome",
        json={"metric_kind": metric, "unit": unit,
              "expected_value": expected, "actual_value": actual},
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    return recorded.json()


async def _project(db_session_factory, org_id, name, status="active"):
    from app.models.project import Project

    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g3s-{name.lower().replace(' ', '-')[:16]}", status=status,
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return {"id": pid, "name": name}


async def _member(db_session_factory, org_id, project_id, employee_id):
    from app.models.employee import Employee

    async with db_session_factory() as db:
        existing = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == org_id, Employee.id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(Employee(
                id=employee_id, organization_id=org_id,
                employee_number=f"emp-{employee_id[-6:]}",
                first_name=employee_id[-6:], last_name="Tester",
                display_name=employee_id[-6:],
                email=f"{employee_id}@acme.test.co",
            ))
        from app.models.project import ProjectMember

        db.add(ProjectMember(
            organization_id=org_id, project_id=project_id,
            employee_id=employee_id, role="member",
        ))
        await db.commit()


async def _exec_state(db_session_factory, org_id, project_id, health_score):
    from app.models.execution_intelligence import ProjectExecutionState

    async with db_session_factory() as db:
        db.add(ProjectExecutionState(
            organization_id=org_id, project_id=project_id,
            health_score=health_score,
            health_status="healthy" if health_score >= 75 else "at_risk",
            source_event_id="g3s-seed",
        ))
        await db.commit()


async def _capability(db_session_factory, org_id, name, capacity_state="available",
                      available=8, experts=3):
    from app.models.org_capability_intelligence import OrgCapability

    async with db_session_factory() as db:
        db.add(OrgCapability(
            organization_id=org_id, skill_id=f"sk-{name[:20]}",
            canonical_name=name, capacity_potential=10,
            capacity_committed=2, capacity_reserved=0,
            capacity_available=available, capacity_state=capacity_state,
            expert_count=experts, evidence_count=3, lifecycle="established",
        ))
        await db.commit()


async def _scope(client, headers, scope_type, entity_id, name):
    res = await client.post(
        "/api/v1/governance/scopes",
        json={"name": name, "scope_type": scope_type, "entity_id": entity_id},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


async def _ask(client, headers, question):
    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": question}, headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_strategy_walkthrough_surfaces(client, db_session_factory):
    org = await register_org(client, email="4g3_s1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Revenue +25%", priority=2)
    obj = await _objective(client, headers, goal_id, caps=["localization"])
    init = await _initiative(
        client, headers, obj, caps=["localization"],
        expected={"metric_kind": "revenue", "target_value": 25, "unit": "pct"},
        commitments=[{"customer": "ACME", "summary": "Enterprise launch by Q3"}],
    )
    project = await _project(db_session_factory, org_id, "L10N Suite")
    await _member(db_session_factory, org_id, project["id"], "emp-s1")
    await _exec_state(db_session_factory, org_id, project["id"], 90)
    await _capability(db_session_factory, org_id, "localization")
    await _link(client, headers, init, project["id"])
    await _outcome(client, headers, init, expected=25, actual=10)
    await _priority(client, headers, goal_id, 1, reason="board escalation")
    await _drain(db_session_factory)

    portfolio = (await client.get(f"{STRATEGY}/portfolio", headers=headers)).json()
    assert portfolio["advisory_only"] is True
    assert portfolio["health_summary"]["total"] == 1
    assert portfolio["health_summary"]["healthy"] == 1
    assert portfolio["mean_goal_coverage"] == 95
    assert portfolio["confidence"]["outcome_samples"] == 1
    assert portfolio["focus"][0]["goal_id"] == goal_id
    assert portfolio["focus"][0]["why"]

    detail = (await client.get(f"{STRATEGY}/goals/{goal_id}", headers=headers)).json()
    assert detail["coverage"] == 95
    assert detail["factors"]["execution"] == 0.9
    assert detail["primary_reason"]
    assert detail["learning"][0]["verdict"] == "over-optimistic"
    assert detail["outcomes"][0]["actual_value"] == 10
    assert any(r["field"] == "priority" for r in detail["history"])
    assert detail["focus_rank"] == 1

    focus = (await client.get(f"{STRATEGY}/focus", headers=headers)).json()
    assert focus["focus"][0]["goal_id"] == goal_id
    assert focus["focus"][0]["score"] > 0
    assert focus["focus"][0]["why"]

    gaps = (await client.get(f"{STRATEGY}/gaps", headers=headers)).json()
    assert gaps["unaligned_count"] == 0
    assert gaps["under_covered_goals"] == []

    conflicts = (await client.get(f"{STRATEGY}/conflicts", headers=headers)).json()
    assert conflicts["conflicts"] == []
    assert conflicts["advisory_only"] is True

    impact = (await client.get(
        f"{STRATEGY}/impact", params={"project_id": project["id"], "delay_days": 14},
        headers=headers,
    )).json()
    sim = next(s for s in impact["strategic_chain"] if s["goal_id"] == goal_id)
    assert sim["coverage_simulated"] == 85, "95 - two weeks * 5 points"
    assert sim["customer_commitments"][0]["customer"] == "ACME"
    assert impact["bounds"]

    what_if = (await client.get(
        f"{STRATEGY}/what-if", params={"goal_id": goal_id, "priority": 3},
        headers=headers,
    )).json()
    assert what_if["not_a_prediction"] is True
    assert what_if["change"]["type"] == "priority"
    assert what_if["rank_after"] == 1
    assert what_if["assumptions"]

    alternatives = (await client.get(
        f"{STRATEGY}/alternatives", params={"project_id": project["id"]},
        headers=headers,
    )).json()
    assert alternatives["advisory_only"] is True
    assert len(alternatives["options"]) == 3
    assert alternatives["recommendation"]
    assert alternatives["decision_linkage"]["open_decisions"] == 0


async def test_every_write_publishes_a_stream_event(client, db_session_factory):
    org = await register_org(client, email="4g3_s2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Stream Goal")
    obj = await _objective(client, headers, goal_id)
    init = await _initiative(client, headers, obj)
    project = await _project(db_session_factory, org_id, "Stream Work")
    await _link(client, headers, init, project["id"])
    await _priority(client, headers, goal_id, 1)
    await _unlink(client, headers, init, project["id"])
    await _outcome(client, headers, init, expected=10, actual=8)
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        names = {
            name: len(list(
                (await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id, Event.name == name,
                    )
                )).scalars().all()
            ))
            for name in (
                "strategy.goal.created", "strategy.objective.created",
                "strategy.initiative.created", "strategy.initiative.linked",
                "strategy.goal.priority.changed", "strategy.initiative.unlinked",
                "strategy.outcome.recorded",
            )
        }
        assert names == {
            "strategy.goal.created": 1,
            "strategy.objective.created": 1,
            "strategy.initiative.created": 1,
            "strategy.initiative.linked": 1,
            "strategy.goal.priority.changed": 1,
            "strategy.initiative.unlinked": 1,
            "strategy.outcome.recorded": 1,
        }, names
        linked = (
            await db.execute(
                select(Event).where(
                    Event.organization_id == org_id,
                    Event.name == "strategy.initiative.linked",
                )
            )
        ).scalar_one()
        payload = json.loads(linked.payload_json)
        assert payload["project_id"] == project["id"]
        assert payload["goal_id"] == goal_id
        assert payload["initiative_id"] == init
        assert linked.actor_id == org["user"]["id"]


async def test_brain_questions_route_to_strategy_execution(client, db_session_factory):
    org = await register_org(client, email="4g3_s3@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Revenue +25%", priority=2)
    obj = await _objective(client, headers, goal_id, caps=["localization"])
    init = await _initiative(client, headers, obj, caps=["localization"])
    project = await _project(db_session_factory, org_id, "Question Work")
    await _member(db_session_factory, org_id, project["id"], "emp-s3")
    await _exec_state(db_session_factory, org_id, project["id"], 90)
    await _capability(db_session_factory, org_id, "localization")
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)

    res = await _ask(client, headers, "are we achieving our goals?")
    assert res["intent"] == "strategy_execution"
    assert res["health_summary"]["total"] == 1
    assert res["mean_goal_coverage"] == 95

    res = await _ask(client, headers, "what should leadership focus on?")
    assert res["intent"] == "strategy_execution"
    assert res["focus"][0]["goal_id"] == goal_id

    res = await _ask(client, headers, "which projects are not aligned to current priorities?")
    assert res["intent"] == "strategy_execution"
    assert res["gaps"]["unaligned_count"] == 0

    res = await _ask(client, headers, "what is the goal status of Enterprise Revenue?")
    assert res["intent"] == "strategy_execution"
    assert res["goal"]["goal"]["goal_id"] == goal_id
    assert res["goal"]["coverage"] == 95

    scope = await _scope(client, headers, "project", project["id"], "Question scope")
    scoped = await invite_scoped_reader(client, headers, scope["id"], "4g3-s3s@test.co")
    res = await _ask(client, scoped, "are we achieving our goals?")
    assert res["intent"] == "strategy_execution"
    assert res["scope"] == "project"
    assert "does not include" in res["answer"]
