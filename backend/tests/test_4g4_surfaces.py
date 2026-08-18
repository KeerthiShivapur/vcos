"""Slice 4G.4 — surfaces: the capacity API walkthrough and the Universal
Brain routing of allocation questions.

Everything is the canonical capacity ledger: advisory, evidence-backed and
deterministic. The brain questions ("which capability is our biggest
bottleneck", "which projects contend for the same scarce capability",
"where should we allocate capacity", "where are we wasting capacity")
route to the capacity intent, and the 4F.6/4G.1/4G.3 questions keep their
own intents (no keyword theft).
"""

import json

from datetime import date, timedelta

from sqlalchemy import select

from app.models.notification import Event
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
CAP = f"{BRAIN}/execution/capacity"


async def _drain(db_session_factory, limit=200, rounds=6):
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


async def _project(db_session_factory, org_id, name):
    from app.models.project import Project

    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g4s-{name.lower().replace(' ', '-')[:16]}", status="active",
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


async def _capability(db_session_factory, org_id, name, available=8, state="available"):
    from app.models.org_capability_intelligence import OrgCapability

    async with db_session_factory() as db:
        db.add(OrgCapability(
            organization_id=org_id, skill_id=f"sk-{name[:20]}",
            canonical_name=name, capacity_potential=10,
            capacity_committed=2, capacity_reserved=0,
            capacity_available=available, capacity_state=state,
            expert_count=3, evidence_count=3, lifecycle="established",
        ))
        await db.commit()


async def _goal(client, headers, title, priority=3):
    created = await client.post(
        f"{BRAIN}/execution/strategy/goals",
        json={"title": title, "kind": "revenue", "priority": priority,
              "metric_kind": "revenue", "metric_unit": "pct",
              "target_value": 25, "current_value": 5,
              "timeline_label": "FY2026"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["goal_id"]


async def _objective(client, headers, goal_id):
    created = await client.post(
        f"{BRAIN}/execution/strategy/objectives",
        json={"goal_id": goal_id, "title": "Obj"}, headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["objective_id"]


async def _initiative(client, headers, objective_id):
    created = await client.post(
        f"{BRAIN}/execution/strategy/initiatives",
        json={"objective_id": objective_id, "title": "Init"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["initiative_id"]


async def _link(client, headers, initiative_id, project_id):
    resp = await client.post(
        f"{BRAIN}/execution/strategy/initiatives/{initiative_id}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text


async def _ask(client, headers, question):
    res = await client.post(
        f"{BRAIN}/knowledge/query",
        json={"question": question}, headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _walkthrough_org(client, db_session_factory):
    """The flagship capacity state: three initiatives competing for ONE
    scarce capability (security_eng, available 4) inside the same window."""
    org = await register_org(client, email="4g4_walk@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws = date.today()
    we = ws + timedelta(days=30)
    await _capability(db_session_factory, org_id, "security_eng", available=4)
    await _capability(db_session_factory, org_id, "localization", available=10)

    projects = {}
    for name in ("Compliance Sprint", "Penetration Blitz", "Zero Trust", "L10N Push"):
        projects[name] = await _project(db_session_factory, org_id, name)

    goal1 = await _goal(client, headers, "GDPR Certification", priority=1)
    goal2 = await _goal(client, headers, "Security Leadership", priority=2)
    for name, goal, units in (
        ("Compliance Sprint", goal1, 4),
        ("Penetration Blitz", goal2, 3),
        ("Zero Trust", goal2, 3),
    ):
        obj = await _objective(client, headers, goal)
        init = await _initiative(client, headers, obj)
        await _link(client, headers, init, projects[name])
        resp = await client.post(
            f"{CAP}/demands",
            json={"project_id": projects[name], "capability": "security_eng",
                  "units": units, "window_start": ws.isoformat(),
                  "window_end": we.isoformat(), "proficiency": "high"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
    # an unaligned project adds idle pressure on an available capability
    resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": projects["L10N Push"], "capability": "localization",
              "units": 2, "window_start": ws.isoformat(),
              "window_end": we.isoformat(), "proficiency": "high"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await _drain(db_session_factory)
    return org, headers, org_id, projects, goal1, goal2, ws, we


async def test_capacity_walkthrough_surfaces(client, db_session_factory):
    org, headers, org_id, projects, goal1, goal2, ws, we = (
        await _walkthrough_org(client, db_session_factory)
    )

    center = (await client.get(f"{CAP}/center", headers=headers)).json()
    assert center["advisory_only"] is True
    assert center["top_constraint"]["capability"] == "security_eng"
    assert center["top_constraint"]["gap"] == 6
    assert center["overloaded_capabilities"] == 1
    assert center["capability_gaps"] == 1
    assert {g["goal_id"] for g in center["goals_at_risk"]} == {goal1, goal2}
    assert center["recommendations"][0]["capability"] == "security_eng"

    gaps = (await client.get(f"{CAP}/gaps", headers=headers)).json()
    assert gaps["advisory_only"] is True
    assert gaps["current_gaps"][0]["capability"] == "security_eng"
    assert gaps["current_gaps"][0]["utilization"] == 250.0
    assert gaps["projection_notice"]

    contention = (await client.get(f"{CAP}/contention", headers=headers)).json()
    assert contention["advisory_only"] is True
    assert contention["contention_count"] == 1
    group = contention["groups"][0]
    assert group["capability"] == "security_eng"
    assert len(group["claimants"]) == 3
    assert group["claimants"][0]["project_id"] == projects["Compliance Sprint"]
    assert group["claimants"][0]["goal_priority"] == 1
    assert {s["goal_id"] for s in group["strategic_stakes"]} == {goal1, goal2}

    trace = (await client.get(f"{CAP}/traceability", headers=headers)).json()
    assert trace["advisory_only"] is True
    by_cap = {c["capability"]: c for c in trace["capabilities"]}
    assert "security_eng" in by_cap
    assert by_cap["security_eng"]["demand_total"] == 10
    assert by_cap["security_eng"]["goals"][0]["goal_id"] == goal2
    assert {g["goal_id"] for g in by_cap["security_eng"]["goals"]} == {goal1, goal2}
    assert by_cap["localization"]["unaligned_units"] == 2
    assert by_cap["localization"]["unaligned_pct"] == 100.0

    overloads = (await client.get(f"{CAP}/overloads", headers=headers)).json()
    assert overloads["advisory_only"] is True
    assert overloads["capability_overloads"][0]["capability"] == "security_eng"

    detail = (await client.get(
        f"{CAP}/capabilities/security_eng", headers=headers)).json()
    assert detail["capability"] == "security_eng"
    assert detail["demand"]["total"] == 10
    assert detail["demand"]["project_count"] == 3
    assert detail["supply"]["available"] == 4
    assert detail["gap"] == 6
    assert detail["history"], "the demand trail is part of the capability record"

    alternatives = (await client.get(
        f"{CAP}/alternatives",
        params={"project_id": projects["Penetration Blitz"]},
        headers=headers,
    )).json()
    assert alternatives["advisory_only"] is True
    assert {o["key"] for o in alternatives["options"]} == {
        "sequence", "reassign", "external_capability",
    }
    assert alternatives["decision_linkage"]["requires_decision"] is True

    what_if = (await client.get(
        f"{CAP}/what-if",
        params={"from_project_id": projects["Compliance Sprint"],
                "to_project_id": projects["Penetration Blitz"],
                "capability": "security_eng", "units": 2},
        headers=headers,
    )).json()
    assert what_if["not_a_prediction"] is True
    assert what_if["change"]["units"] == 2
    assert what_if["demand_after"][projects["Compliance Sprint"]] == 2
    assert what_if["demand_after"][projects["Penetration Blitz"]] == 5
    assert what_if["assumptions"]
    assert "never moves people" in what_if["bounds"]


async def test_brain_routes_capacity_questions(client, db_session_factory):
    org, headers, org_id, projects, goal1, goal2, ws, we = (
        await _walkthrough_org(client, db_session_factory)
    )

    bottleneck = await _ask(
        client, headers, "which capability is our biggest bottleneck",
    )
    assert bottleneck["intent"] == "capacity"
    assert bottleneck["scope"] == "org"
    assert bottleneck["top_constraint"]["capability"] == "security_eng"
    assert bottleneck["critical_bottlenecks"]
    assert bottleneck["generated_at"]

    contention = await _ask(
        client, headers,
        "which projects contend for the same scarce capability",
    )
    assert contention["intent"] == "capacity"
    assert contention["contention_count"] == 1
    assert contention["groups"][0]["capability"] == "security_eng"

    allocate = await _ask(
        client, headers, "where should we allocate capacity",
    )
    assert allocate["intent"] == "capacity"
    assert allocate["gaps"]["current_gaps"]
    assert allocate["traceability"]["capabilities"]
    assert allocate["top_constraint"]["capability"] == "security_eng"

    waste = await _ask(client, headers, "where are we wasting capacity")
    assert waste["intent"] == "capacity"
    assert waste["capability_overloads"][0]["capability"] == "security_eng"
    assert "person_overloads" in waste

    hire = await _ask(
        client, headers, "what capability do we need to hire or develop",
    )
    assert hire["intent"] == "capacity"
    assert hire["gaps"]["current_gaps"]


async def test_brain_keeps_owning_intents(client, db_session_factory):
    """The capacity rule never steals 4F.6 / 4G.1 / 4G.3 questions."""
    org, headers, org_id, projects, goal1, goal2, ws, we = (
        await _walkthrough_org(client, db_session_factory)
    )

    capability_ledger = await _ask(
        client, headers, "are we capacity constrained anywhere",
    )
    assert capability_ledger["intent"] in ("capability_constraint", "expertise")
    assert capability_ledger["intent"] != "capacity"

    blocked = await _ask(client, headers, "what is blocked")
    assert blocked["intent"] == "blocked"
    assert blocked["intent"] != "capacity"

    goals = await _ask(client, headers, "are we achieving our goals")
    assert goals["intent"] == "strategy_execution"
    assert goals["intent"] != "capacity"


async def test_capacity_event_stream_and_demand_ledger(client, db_session_factory):
    org, headers, org_id, projects, goal1, goal2, ws, we = (
        await _walkthrough_org(client, db_session_factory)
    )

    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name.in_((
                            "capacity.demand.created",
                            "capacity.demand.updated",
                            "capacity.demand.removed",
                            "capacity.allocation.created",
                            "capacity.allocation.completed",
                        )),
                    ).order_by(Event.occurred_at)
                )
            ).scalars().all()
        )
    names = [r.name for r in rows]
    assert names.count("capacity.demand.created") == 4
    capabilities = [
        json.loads(r.payload_json or "{}").get("capability")
        for r in rows
        if json.loads(r.payload_json or "{}").get("capability") is not None
    ]
    assert capabilities.count("security_eng") == 3
    assert capabilities.count("localization") == 1

    # update one demand through the governed write -> capacity.demand.updated
    demand_id = None
    async with db_session_factory() as db:
        from app.models.resource_allocation_intelligence import AllocationDemand

        demand = (
            await db.execute(
                select(AllocationDemand).where(
                    AllocationDemand.organization_id == org_id,
                    AllocationDemand.project_id == projects["Zero Trust"],
                )
            )
        ).scalar_one()
        demand_id = demand.id
    updated = await client.post(
        f"{CAP}/demands",
        json={"project_id": projects["Zero Trust"], "capability": "security_eng",
              "units": 5, "window_start": ws.isoformat(),
              "window_end": we.isoformat(), "proficiency": "high",
              "reason": "assessment scope doubled"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        later = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name == "capacity.demand.updated",
                    ).order_by(Event.occurred_at.desc())
                )
            ).scalars().all()
        )
        assert later, "the update left an event in the stream"
        payload = json.loads(later[0].payload_json or "{}")
        assert payload["units"] == 5
        assert payload["old_units"] == 3
        assert payload["reason"] == "assessment scope doubled"

    center = (await client.get(f"{CAP}/center", headers=headers)).json()
    assert center["top_constraint"]["gap"] == 8, "demand 12 vs supply 4"

    removed = await client.post(
        f"{CAP}/demands/{demand_id}/remove",
        json={"reason": "de-scoped after review"}, headers=headers,
    )
    assert removed.status_code == 200, removed.text
    await _drain(db_session_factory)
    center = (await client.get(f"{CAP}/center", headers=headers)).json()
    assert center["top_constraint"]["gap"] == 3, "demand 7 vs supply 4"

    # a governed allocation + outcome completes the walkthrough
    allocation = await client.post(
        f"{CAP}/allocations",
        json={"project_id": projects["Compliance Sprint"],
              "capability": "security_eng", "units": 4,
              "window_start": ws.isoformat(), "window_end": we.isoformat(),
              "note": "four external contractors"},
        headers=headers,
    )
    assert allocation.status_code == 200, allocation.text
    outcome = await client.post(
        f"{CAP}/allocations/{allocation.json()['allocation_id']}/outcome",
        json={"outcome": "partial", "note": "two onboarded, two delayed"},
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        events = list(
            (
                await db.execute(
                    select(Event).where(
                        Event.organization_id == org_id,
                        Event.name.in_((
                            "capacity.allocation.created",
                            "capacity.allocation.completed",
                        )),
                    ).order_by(Event.occurred_at)
                )
            ).scalars().all()
        )
        assert len(events) == 2, "allocation created + completed in the stream"
        completed = json.loads(events[-1].payload_json or "{}")
        assert completed["outcome"] == "partial"
        assert completed["allocation_id"] == allocation.json()["allocation_id"]

    trace = (await client.get(f"{CAP}/traceability", headers=headers)).json()
    by_cap = {c["capability"]: c for c in trace["capabilities"]}
    assert by_cap["security_eng"]["demand_total"] == 7
    assert by_cap["security_eng"]["goals"][0]["share_pct"] > 0