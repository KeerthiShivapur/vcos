"""Slice 4G.4 - Universal Resource & Capacity Allocation Intelligence engine.

Under test:

* the demand vs supply formula: demand and supply are measured inside the
  demand's EXECUTION WINDOW (never today's snapshot); gap = demand minus
  available supply, utilization = demand / available, bottleneck when the
  gap is positive or supply is stretched/constrained,
* gap WHY: commitments elsewhere, reservations, missing trusted expertise
  evidence at the demanded proficiency,
* contention: projects competing for the same scarce capability are ordered
  by their strategic stakes (goal priority) and grouped per window,
* alternatives: three bounded allocation courses with benefit/risk/
  confidence/evidence - human decides, nothing is executed,
* bounded what-if: moving units between two projects recomputes the
  simulated gaps and goal directions; never a prediction,
* allocation -> outcome learning: achieved/partial/missed pours into 4E.7
  memory tags capacity,4g4,
* exact-once replays: the same source_event_id converges to the same
  snapshot + history rows, and one event only refreshes its OWN
  (capability, window) neighborhood,
* history: create/update/remove land in the append-only trail with reasons,
* gaps: current windows vs FUTURE projections (clearly labeled),
* center: deterministic top constraint, utilization and goals at risk,
* overloads: capability, team and person level evidence.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.intelligence.resource_allocation_engine import resource_allocation_engine
from app.models.ai import AIMemory
from app.models.employee import Employee
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicLink,
)
from app.models.intelligence import LearningEvent
from app.models.notification import Event
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Project
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacityHistory,
    CapacitySnapshot,
)
from app.models.skill import ExpertiseScore, Skill
from app.models.task import Task
from app.models.team import Team
from tests.conftest import register_org

CAP = "/api/v1/brain/execution/capacity"


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


async def _publish(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _replay_capacity_event(db_session_factory, org_id, name, capability,
                                 payload):
    """Replay ONE real event row (matched by capability) through the capacity
    engine; the same source_event_id must converge (exact-once)."""
    async with db_session_factory() as db:
        import json

        rows = (
            await db.execute(
                select(Event).where(
                    Event.organization_id == org_id, Event.name == name,
                ).order_by(Event.occurred_at.desc(), Event.id.desc())
            )
        ).scalars().all()
        event = next(
            (r for r in rows if json.loads(r.payload_json or "{}").get("capability") == capability),
            None,
        )
        assert event is not None, f"no events named {name} for {capability}"
        await resource_allocation_engine.record_event(
            db, organization_id=org_id,
            event=SimpleNamespace(name=name, id=event.id),
            payload=payload,
        )
        await db.commit()


async def _project(db_session_factory, org_id, name):
    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g4d-{name.lower().replace(' ', '-')[:16]}", status="active",
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


async def _demand(client, headers, project_id, capability, units,
                  window_start=None, window_end=None, proficiency="high",
                  note=None, reason=None):
    body = {
        "project_id": project_id, "capability": capability, "units": units,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "proficiency": proficiency, "note": note, "reason": reason,
    }
    resp = await client.post(f"{CAP}/demands", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _window(today=None, offset=0, days=30):
    today = today or date.today()
    return today + timedelta(days=offset), today + timedelta(days=offset + days)


async def _capability(db_session_factory, org_id, name, available=8,
                      committed=0, reserved=0, state="available", experts=3,
                      potential=None):
    async with db_session_factory() as db:
        db.add(OrgCapability(
            organization_id=org_id, skill_id=f"sk-{name[:20]}",
            canonical_name=name,
            capacity_potential=potential if potential is not None else available + 2,
            capacity_committed=committed, capacity_reserved=reserved,
            capacity_available=available, capacity_state=state,
            expert_count=experts, evidence_count=3, lifecycle="established",
        ))
        await db.commit()


async def _expertise(db_session_factory, org_id, skill_id, employee_id, score):
    async with db_session_factory() as db:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == org_id,
                    Employee.id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if employee is None:
            db.add(Employee(
                id=employee_id, organization_id=org_id,
                employee_number=f"emp-{employee_id[-6:]}",
                first_name=employee_id[-6:], last_name="Tester",
                display_name=employee_id[-6:],
                email=f"{employee_id}@acme.test.co",
            ))
            await db.flush()
        skill = (
            await db.execute(
                select(Skill).where(
                    Skill.organization_id == org_id, Skill.id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if skill is None:
            db.add(Skill(id=skill_id, organization_id=org_id,
                         name=f"Skill {skill_id}", category="technical"))
            await db.flush()
        db.add(ExpertiseScore(
            organization_id=org_id, employee_id=employee_id,
            skill_id=skill_id, score=score,
        ))
        await db.commit()


async def _goal(client, headers, title, priority=3):
    created = await client.post(
        "/api/v1/brain/execution/strategy/goals",
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
        "/api/v1/brain/execution/strategy/objectives",
        json={"goal_id": goal_id, "title": "Obj"}, headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["objective_id"]


async def _initiative(client, headers, objective_id):
    created = await client.post(
        "/api/v1/brain/execution/strategy/initiatives",
        json={"objective_id": objective_id, "title": "Init"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["initiative_id"]


async def _link(client, headers, initiative_id, project_id):
    resp = await client.post(
        f"/api/v1/brain/execution/strategy/initiatives/{initiative_id}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text


async def _engine(db_session_factory, method, **kwargs):
    """Run one engine surface inside a real session (the engine needs a
    session, not the factory)."""
    async with db_session_factory() as db:
        return await method(db, **kwargs)


async def _snapshots(db_session_factory, org_id, capability=None):
    async with db_session_factory() as db:
        stmt = select(CapacitySnapshot).where(
            CapacitySnapshot.organization_id == org_id,
        )
        if capability:
            stmt = stmt.where(CapacitySnapshot.capability == capability)
        return list((await db.execute(stmt)).scalars().all())


async def _history_rows(db_session_factory, org_id, entity_type=None):
    async with db_session_factory() as db:
        stmt = select(CapacityHistory).where(
            CapacityHistory.organization_id == org_id,
        )
        if entity_type:
            stmt = stmt.where(CapacityHistory.entity_type == entity_type)
        return list((await db.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# 1. Demand vs supply in the execution window
# ---------------------------------------------------------------------------

async def test_demand_vs_supply_gap_in_window(client, db_session_factory):
    org = await register_org(client, email="4g4_gap@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    project_a = await _project(db_session_factory, org_id, "Alpha Shield")
    project_b = await _project(db_session_factory, org_id, "Beta Shield")
    await _capability(db_session_factory, org_id, "security_eng", available=4)
    await _demand(client, headers, project_a, "security_eng", 3, ws, we)
    await _demand(client, headers, project_b, "security_eng", 3, ws, we)
    await _drain(db_session_factory)

    snapshots = await _snapshots(db_session_factory, org_id, "security_eng")
    assert len(snapshots) == 2, "one snapshot per demand event (exact-once)"
    snap = snapshots[-1]
    assert snap.demand_total == 6
    assert snap.supply_available == 4
    assert snap.gap == 2
    assert snap.utilization == 150.0
    assert snap.is_bottleneck is True
    assert snap.supply_state == "available"
    assert snap.affected_projects == 2
    payload = snap.payload_json
    assert payload["demand"]["project_count"] == 2
    assert {p["project_name"] for p in payload["demand"]["projects"]} == {
        "Alpha Shield", "Beta Shield",
    }
    assert payload["state"] == "bottleneck"
    assert payload["advisory_only"] is True
    assert payload["window_start"] == ws.isoformat()
    assert payload["window_end"] == we.isoformat()


async def test_gap_reasons_why(client, db_session_factory):
    org = await register_org(client, email="4g4_why@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    project = await _project(db_session_factory, org_id, "Why Project")
    # committed + reserved elsewhere, and no trusted expertise evidence
    await _capability(
        db_session_factory, org_id, "data_ops", available=4, committed=3,
        reserved=1,
    )
    await _demand(client, headers, project, "data_ops", 6, ws, we)
    await _drain(db_session_factory)

    snap = (await _snapshots(db_session_factory, org_id, "data_ops"))[-1]
    reasons = snap.payload_json["gap_reasons"]
    assert any("committed elsewhere" in r for r in reasons), reasons
    assert any("reserved for other work" in r for r in reasons), reasons
    assert any("trusted evidence" in r for r in reasons), reasons

    # trusted expertise evidence changes the WHY: give 3 experts a strong score
    await _expertise(db_session_factory, org_id, "sk-data_ops", "g4d-exp1", 82)
    await _expertise(db_session_factory, org_id, "sk-data_ops", "g4d-exp2", 66)
    await _expertise(db_session_factory, org_id, "sk-data_ops", "g4d-exp3", 74)
    async with db_session_factory() as db:
        result = await resource_allocation_engine.assess(
            db,
            organization_id=org_id, capability="data_ops",
            window_start=ws, window_end=we,
        )
    assert result["supply"]["fit_high"] == 3
    assert result["supply"]["experts"] == 3
    reasons = result["gap_reasons"]
    assert any("only 3 person(s)" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# 2. Contention with strategic stakes
# ---------------------------------------------------------------------------

async def test_contention_orders_claimants_by_goal_priority(
    client, db_session_factory,
):
    org = await register_org(client, email="4g4_cont@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "data_eng", available=2)
    p1 = await _project(db_session_factory, org_id, "Priority One")
    p2 = await _project(db_session_factory, org_id, "Priority Five")
    p3 = await _project(db_session_factory, org_id, "Unaligned")
    for pid, units in ((p1, 3), (p2, 2), (p3, 2)):
        await _demand(client, headers, pid, "data_eng", units, ws, we)

    goal1 = await _goal(client, headers, "Enterprise Revenue", priority=1)
    goal5 = await _goal(client, headers, "Nice to Have", priority=5)
    obj1 = await _objective(client, headers, goal1)
    obj5 = await _objective(client, headers, goal5)
    init1 = await _initiative(client, headers, obj1)
    init5 = await _initiative(client, headers, obj5)
    await _link(client, headers, init1, p1)
    await _link(client, headers, init5, p2)
    await _drain(db_session_factory)

    contention = await _engine(
        db_session_factory, resource_allocation_engine.contention,
        organization_id=org_id,
    )
    assert contention["advisory_only"] is True
    assert contention["contention_count"] == 1
    group = contention["groups"][0]
    assert group["capability"] == "data_eng"
    assert group["gap"] == 5
    assert group["utilization"] == 350.0
    assert len(group["claimants"]) == 3
    assert group["claimants"][0]["project_id"] == p1
    assert group["claimants"][0]["goal_priority"] == 1
    assert group["claimants"][1]["goal_priority"] == 5
    assert group["strategic_stakes"][0]["goal_id"] == goal1
    assert group["strategic_stakes"][0]["priority"] == 1
    assert {c["project_id"] for c in group["claimants"]} == {p1, p2, p3}


# ---------------------------------------------------------------------------
# 3. Alternatives: three bounded courses
# ---------------------------------------------------------------------------

async def test_alternatives_three_bounded_options(client, db_session_factory):
    org = await register_org(client, email="4g4_alt@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "data_eng", available=2)
    p1 = await _project(db_session_factory, org_id, "Priority One")
    p2 = await _project(db_session_factory, org_id, "Priority Five")
    for pid in (p1, p2):
        await _demand(client, headers, pid, "data_eng", 3 if pid == p1 else 2, ws, we)
    await _drain(db_session_factory)

    result = await _engine(
        db_session_factory, resource_allocation_engine.alternatives,
        organization_id=org_id, project_id=p1,
    )
    assert result["advisory_only"] is True
    assert result["project_id"] == p1
    assert {o["key"] for o in result["options"]} == {
        "sequence", "reassign", "external_capability",
    }
    assert result["decision_linkage"]["requires_decision"] is True
    for option in result["options"]:
        assert option["benefit"]
        assert option["risk"]
        assert 0 < option["confidence"] <= 1
        assert option["evidence"]
        assert p1 in option["affected_projects"]
    assert result["recommendation"] in (
        "Option B balances the gap while preserving the highest-priority claim",
        "Option A sequences without changing capacity",
    )
    reassign = next(o for o in result["options"] if o["key"] == "reassign")
    assert reassign["capacity_change"] == 3, "moves the full gap (surveyed claim)"


# ---------------------------------------------------------------------------
# 4. Bounded what-if
# ---------------------------------------------------------------------------

async def test_what_if_bounded_and_not_a_prediction(client, db_session_factory):
    org = await register_org(client, email="4g4_wif@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "data_eng", available=2)
    p1 = await _project(db_session_factory, org_id, "From Project")
    p2 = await _project(db_session_factory, org_id, "To Project")
    await _demand(client, headers, p1, "data_eng", 5, ws, we)
    await _demand(client, headers, p2, "data_eng", 3, ws, we)
    await _drain(db_session_factory)

    result = await _engine(
        db_session_factory, resource_allocation_engine.what_if,
        organization_id=org_id,
        from_project_id=p1, to_project_id=p2,
        capability="data_eng", units=2, window_days=30,
    )
    assert result["not_a_prediction"] is True
    assert result["change"]["type"] == "reallocate"
    assert result["change"]["units"] == 2
    assert result["demand_before"] == {p1: 5, p2: 3}
    assert result["demand_after"] == {p1: 3, p2: 5}
    # shared supply of 2: moving units out reduces the source gap, the
    # destination gap grows — orders of magnitude are explicit, never facts
    assert result["gap_before"][p1] == 3
    assert result["gap_after"][p1] == 1
    assert result["gap_before"][p2] == 1
    assert result["gap_after"][p2] == 3
    for entry in result["goals_affected"]:
        assert entry["direction"] in ("improves", "worsens", "unchanged")
    assert result["assumptions"]
    assert "never moves people" in result["bounds"]

    # units never exceed the source demand
    clamped = await _engine(
        db_session_factory, resource_allocation_engine.what_if,
        organization_id=org_id,
        from_project_id=p1, to_project_id=p2,
        capability="data_eng", units=99, window_days=30,
    )
    assert clamped["change"]["units"] == 5

    # unrelated projects -> no shared window
    p3 = await _project(db_session_factory, org_id, "Isolated")
    none_result = await _engine(
        db_session_factory, resource_allocation_engine.what_if,
        organization_id=org_id,
        from_project_id=p1, to_project_id=p3,
        capability="data_eng", units=1, window_days=30,
    )
    assert none_result is None


# ---------------------------------------------------------------------------
# 5. Allocation -> outcome learning
# ---------------------------------------------------------------------------

async def test_allocation_outcome_pours_into_learning(client, db_session_factory):
    org = await register_org(client, email="4g4_lrn@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    project = await _project(db_session_factory, org_id, "Learning Project")
    await _capability(db_session_factory, org_id, "security_eng", available=8)
    created = await client.post(
        f"{CAP}/allocations",
        json={"project_id": project, "capability": "security_eng", "units": 3,
              "window_start": ws.isoformat(), "window_end": we.isoformat()},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    allocation_id = created.json()["allocation_id"]
    await _drain(db_session_factory)

    outcome = await client.post(
        f"{CAP}/allocations/{allocation_id}/outcome",
        json={"outcome": "missed", "note": "onboarding took twice as long"},
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        events = list(
            (
                await db.execute(
                    select(LearningEvent).where(
                        LearningEvent.organization_id == org_id,
                        LearningEvent.event_type == "capacity.allocation",
                    )
                )
            ).scalars().all()
        )
        assert len(events) == 1
        assert "missed" in events[0].lesson
        assert "ineffective" in events[0].lesson
        assert "capacity" in events[0].tags
        assert "4g4" in events[0].tags

        memories = list(
            (
                await db.execute(
                    select(AIMemory).where(
                        AIMemory.organization_id == org_id,
                        AIMemory.kind == "lesson",
                        AIMemory.content.like("%missed%"),
                    )
                )
            ).scalars().all()
        )
        assert len(memories) >= 1, "allocation learning reached organizational memory"
        assert "security_eng" in memories[0].content

    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(CapacityAllocation).where(
                    CapacityAllocation.organization_id == org_id,
                    CapacityAllocation.id == allocation_id,
                )
            )
        ).scalar_one()
        assert row.status == "completed"
        assert row.outcome == "missed"


# ---------------------------------------------------------------------------
# 6. Exact-once replays and incremental neighborhoods
# ---------------------------------------------------------------------------

async def test_exact_once_replay_and_neighborhood_isolation(
    client, db_session_factory,
):
    org = await register_org(client, email="4g4_rep@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    pa = await _project(db_session_factory, org_id, "Cap A Project")
    pb = await _project(db_session_factory, org_id, "Cap B Project")
    await _capability(db_session_factory, org_id, "cap_a", available=2)
    await _capability(db_session_factory, org_id, "cap_b", available=10)
    await _demand(client, headers, pa, "cap_a", 3, ws, we)
    await _demand(client, headers, pb, "cap_b", 2, ws, we)
    await _drain(db_session_factory)

    assert len(await _snapshots(db_session_factory, org_id, "cap_a")) == 1
    assert len(await _snapshots(db_session_factory, org_id, "cap_b")) == 1
    assert len(await _snapshots(db_session_factory, org_id)) == 2

    # replay the SAME event id -> nothing duplicates
    await _replay_capacity_event(
        db_session_factory, org_id, "capacity.demand.created", "cap_a",
        {"organization_id": org_id, "project_id": pa,
         "project_label": "Cap A Project", "capability": "cap_a",
         "units": 3, "window_start": ws.isoformat(),
         "window_end": we.isoformat(), "proficiency": "high"},
    )
    assert len(await _snapshots(db_session_factory, org_id, "cap_a")) == 1
    assert len(await _snapshots(db_session_factory, org_id, "cap_b")) == 1
    history = await _history_rows(db_session_factory, org_id)
    assert len(history) == 2, "one history row per demand, even after replay"

    # neighborhood isolation: cap_b's snapshot was never re-touched by cap_a's
    snap_b = (await _snapshots(db_session_factory, org_id, "cap_b"))[0]
    assert snap_b.event_name == "capacity.demand.created"
    assert snap_b.demand_total == 2
    assert snap_b.gap == 0
    assert snap_b.is_bottleneck is False


# ---------------------------------------------------------------------------
# 7. History trail with reasons
# ---------------------------------------------------------------------------

async def test_history_trail_captures_changes(client, db_session_factory):
    org = await register_org(client, email="4g4_hist@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    project = await _project(db_session_factory, org_id, "History Project")
    await _capability(db_session_factory, org_id, "design_eng", available=10)
    demand = await _demand(client, headers, project, "design_eng", 3, ws, we,
                           note="initial scope")
    await _drain(db_session_factory)

    update_resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": project, "capability": "design_eng", "units": 5,
              "window_start": ws.isoformat(), "window_end": we.isoformat(),
              "proficiency": "high",
              "reason": "scope grew by two more signatures"},
        headers=headers,
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["created"] is False
    await _drain(db_session_factory)

    removed = await client.post(
        f"{CAP}/demands/{demand['demand_id']}/remove",
        json={"reason": "de-scoped"}, headers=headers,
    )
    assert removed.status_code == 200, removed.text
    await _drain(db_session_factory)

    rows = await _history_rows(db_session_factory, org_id)
    assert len(rows) == 3, "created + updated + removed, all retained"
    updated_row = next(row for row in rows
                       if row.new_value and "5u" in row.new_value)
    assert updated_row.old_value and "3u" in updated_row.old_value
    assert updated_row.reason == "scope grew by two more signatures"
    removed_row = next(row for row in rows if row.new_value == "removed")
    assert removed_row.reason == "de-scoped"

    detail = await _engine(
        db_session_factory, resource_allocation_engine.capability_detail,
        organization_id=org_id, capability="design_eng",
    )
    assert detail is not None
    assert detail["history"], "capability detail exposes the demand trail"
    assert detail["history"][0]["new_value"] == "removed"
    assert detail["snapshot_count"] == 1, "latest snapshot per window, not per event"
    assert detail["demand"]["total"] == 0, "removal zeroes the demand"

    # live row is gone after the removal event
    async with db_session_factory() as db:
        live = (
            await db.execute(
                select(AllocationDemand).where(
                    AllocationDemand.organization_id == org_id,
                    AllocationDemand.id == demand["demand_id"],
                )
            )
        ).scalar_one_or_none()
        assert live is None


# ---------------------------------------------------------------------------
# 8. Gaps: current vs future projections
# ---------------------------------------------------------------------------

async def test_gaps_current_and_future_projection(client, db_session_factory):
    org = await register_org(client, email="4g4_gap2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    today = date.today()
    ws, we = _window(today)
    future_ws, future_we = today + timedelta(days=60), today + timedelta(days=120)
    project = await _project(db_session_factory, org_id, "Gap Project")
    await _capability(db_session_factory, org_id, "security_eng", available=2)
    await _demand(client, headers, project, "security_eng", 4, ws, we)
    await _demand(client, headers, project, "security_eng", 1,
                  future_ws, future_we)
    await _drain(db_session_factory)

    gaps_result = await _engine(
        db_session_factory, resource_allocation_engine.gaps,
        organization_id=org_id,
    )
    gaps = gaps_result
    assert gaps["advisory_only"] is True
    current = {g["capability"]: g for g in gaps["current_gaps"]}
    assert "security_eng" in current
    assert current["security_eng"]["gap"] == 2
    assert current["security_eng"]["gap_potential"] == 0
    assert "projection_notice" in gaps
    assert gaps["projection_notice"], "future gaps are labeled as projections"
    # the future window holds only the declared 1-unit demand: no gap yet
    future = {g["window_start"]: g for g in gaps["future_gaps_projection"]}
    assert future_ws.isoformat() in future
    assert future[future_ws.isoformat()]["gap"] == 0
    assert future[future_ws.isoformat()]["demand"] == 1


# ---------------------------------------------------------------------------
# 9. Center: deterministic top constraint
# ---------------------------------------------------------------------------

async def test_center_deterministic_top_constraint(client, db_session_factory):
    org = await register_org(client, email="4g4_ctr@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "data_eng", available=2)
    await _capability(db_session_factory, org_id, "security_eng", available=6)
    p1 = await _project(db_session_factory, org_id, "Priority One")
    p2 = await _project(db_session_factory, org_id, "Security Project")
    goal1 = await _goal(client, headers, "Enterprise Revenue", priority=1)
    obj1 = await _objective(client, headers, goal1)
    init1 = await _initiative(client, headers, obj1)
    await _link(client, headers, init1, p1)
    await _demand(client, headers, p1, "data_eng", 5, ws, we)
    await _demand(client, headers, p2, "security_eng", 8, ws, we)
    await _drain(db_session_factory)

    first = await _engine(
        db_session_factory, resource_allocation_engine.center,
        organization_id=org_id,
    )
    assert first["advisory_only"] is True
    assert first["top_constraint"]["capability"] == "data_eng"
    assert first["top_constraint"]["gap"] == 3
    assert first["top_constraint"]["affected_projects"] == 1
    assert first["top_constraint"]["affected_goals"] == 1
    assert first["top_constraint"]["recommended_action"]
    assert first["overloaded_capabilities"] == 2
    assert first["capability_gaps"] == 2
    assert len(first["critical_bottlenecks"]) == 2
    assert first["critical_bottlenecks"][0]["utilization"] == 250.0
    # company utilization is the mean of the demanded windows' utilization
    utilizations = [b["utilization"] for b in first["critical_bottlenecks"]]
    assert first["company_utilization"] == round(sum(utilizations) / len(utilizations), 1)
    assert first["goals_at_risk"][0]["goal_id"] == goal1
    assert first["goals_at_risk"][0]["causes"] == ["data_eng"]
    assert first["recommendations"][0]["capability"] == "data_eng"
    assert first["recommendations"][0]["advisory_only"] is True

    second = await _engine(
        db_session_factory, resource_allocation_engine.center,
        organization_id=org_id,
    )
    assert second == first, "center is deterministic"


# ---------------------------------------------------------------------------
# 10. Overloads at capability, team and person level
# ---------------------------------------------------------------------------

async def test_overloads_at_all_three_levels(client, db_session_factory):
    org = await register_org(client, email="4g4_ovr@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "security_eng", available=4)
    proj = await _project(db_session_factory, org_id, "Overload Project")
    await _demand(client, headers, proj, "security_eng", 6, ws, we)
    await _drain(db_session_factory)

    team_id = "g4d-team1"
    async with db_session_factory() as db:
        db.add(Team(id=team_id, organization_id=org_id,
                    name="Platform Guild", code="g4d-plat"))
        for emp, first, last, hours in (
            ("g4d-heavy", "Heavy", "Worker", 90.0),
            ("g4d-busy", "Busy", "Worker", 50.0),
            ("g4d-idle", "Idle", "Worker", 6.0),
        ):
            db.add(Employee(
                id=emp, organization_id=org_id,
                employee_number=f"emp-{emp[-6:]}",
                first_name=first, last_name=last,
                display_name=f"{first} {last}",
                email=f"{emp}@acme.test.co",
                team_id=team_id, status="active",
            ))
        for emp, hours in (("g4d-heavy", 90.0), ("g4d-busy", 50.0),
                           ("g4d-idle", 6.0)):
            db.add(Task(
                organization_id=org_id, project_id=proj,
                title=f"work for {emp}", status="in_progress",
                assignee_id=emp, estimate_hours=hours,
            ))
        await db.commit()

    overloads = await _engine(
        db_session_factory, resource_allocation_engine.overloads,
        organization_id=org_id,
    )
    assert overloads["advisory_only"] is True
    assert overloads["capability_overloads"][0]["capability"] == "security_eng"
    assert overloads["capability_overloads"][0]["utilization"] == 150.0

    by_person = {p["person_id"]: p for p in overloads["person_overloads"]}
    assert "g4d-heavy" in by_person, "person overload comes from open task hours"
    assert by_person["g4d-heavy"]["utilization"] == 225.0
    assert "g4d-idle" not in by_person

    under = {p["person_id"]: p for p in overloads["person_under_utilized"]}
    assert "g4d-idle" in under, "low-committed people are surfaced as under-utilized"
    assert under["g4d-idle"]["committed_hours"] == 6.0
    assert "g4d-heavy" not in under

    teams = {t["team_id"]: t for t in overloads["team_overloads"]}
    assert team_id in teams
    assert teams[team_id]["members"] == 3
    assert teams[team_id]["committed_hours"] == 146.0
    assert teams[team_id]["capacity_hours"] == 120.0
    assert teams[team_id]["utilization"] == 121.7
    assert teams[team_id]["utilization"] > 100.0, "the guild is over capacity"


# ---------------------------------------------------------------------------
# 11. Non-capacity events are ignored by the engine
# ---------------------------------------------------------------------------

async def test_non_capacity_event_is_ignored(client, db_session_factory):
    org = await register_org(client, email="4g4_ign@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _publish(
        db_session_factory, org_id, org["user"]["id"], "project.created",
        {"organization_id": org_id, "project_id": "x", "name": "Ignored"},
    )
    assert await _snapshots(db_session_factory, org_id) == []
    assert await _history_rows(db_session_factory, org_id) == []

    # a demand event without a window is also a no-op
    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name="No Window", code="g4d-nowin",
            status="active",
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    await _publish(
        db_session_factory, org_id, org["user"]["id"],
        "capacity.demand.created",
        {"organization_id": org_id, "project_id": pid,
         "project_label": "No Window", "capability": "security_eng",
         "units": 3},
    )
    assert await _snapshots(db_session_factory, org_id) == []