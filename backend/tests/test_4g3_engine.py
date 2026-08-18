"""Slice 4G.3 - Strategic Portfolio & Goal Execution Intelligence engine.

Under test:

* the coverage formula: execution factor (4G.1 health) weighted 0.5,
  capability factor (4F.6 org capability ledger) weighted 0.3, capacity
  factor (staffed projects) weighted 0.2; verdicts healthy >= 75,
  at_risk >= 45, critical below; an unlinked goal is coverage 0,
* goal -> work traceability: linking a project flips coverage from 0 to
  the evidence-backed value and unlink recomputes back to 0; both exact-once,
* temporal memory: priority changes land in StrategicHistory exactly once
  and replays never duplicate,
* incremental neighborhoods: an event on goal A never touches goal B's
  snapshot ledger,
* alignment: direct (active chain) / indirect (partly active) / weak (goal
  chain only) / none, feeding the strategic-gaps review list,
* strategy -> outcome learning: expected vs actual observations are
  exact-once and the verdict (over/under-optimistic) feeds 4E.7 memory,
* bounded impact propagation: a delay reaches downstream projects and the
  goal chain with a simulated coverage drop, explicitly not a forecast,
* bounded what-if: priority re-prioritization re-ranks focus deterministically,
* alternatives: three evidence-backed options plus an advisory recommendation,
* portfolio health and portfolio contention surfaces are deterministic.
"""

from types import SimpleNamespace

from sqlalchemy import select

from app.intelligence.strategic_execution_engine import strategic_execution_engine
from app.models.ai import AIMemory
from app.models.execution_intelligence import ProjectExecutionState
from app.models.execution_strategy import (
    CompanyGoal,
    StrategicHistory,
    StrategicLink,
    StrategicOutcome,
    StrategicSnapshot,
)
from app.models.org_capability_intelligence import OrgCapability
from app.models.notification import Event
from app.models.project import ProjectMember
from app.models.task import Task, TaskDependency
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


async def _publish(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _replay_last_event(db_session_factory, org_id, name, payload):
    """Replay the last real event row for `name` through the strategy engine;
    the same source_event_id must converge (exact-once), never duplicate."""
    async with db_session_factory() as db:
        event = (
            await db.execute(
                select(Event)
                .where(Event.organization_id == org_id, Event.name == name)
                .order_by(Event.occurred_at.desc(), Event.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        assert event is not None, f"no events named {name} in stream"
        await strategic_execution_engine.record_event(
            db, organization_id=org_id,
            event=SimpleNamespace(name=name, id=event.id),
            payload=payload,
        )
        await db.commit()


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


async def _link(client, headers, initiative_id, project_id):
    resp = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/link",
        json={"project_id": project_id}, headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _project(db_session_factory, org_id, name, status="active"):
    from app.models.project import Project

    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g3d-{name.lower().replace(' ', '-')[:16]}",
            status=status,
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
        db.add(ProjectMember(
            organization_id=org_id, project_id=project_id,
            employee_id=employee_id, role="member",
        ))
        await db.commit()


async def _exec_state(db_session_factory, org_id, project_id, health_score, status=None):
    async with db_session_factory() as db:
        db.add(ProjectExecutionState(
            organization_id=org_id, project_id=project_id,
            health_score=health_score,
            health_status=status or ("healthy" if health_score >= 75 else "at_risk"),
            source_event_id="g3seed-state",
        ))
        await db.commit()


async def _capability(db_session_factory, org_id, name, capacity_state="available",
                      available=8, experts=3):
    async with db_session_factory() as db:
        db.add(OrgCapability(
            organization_id=org_id, skill_id=f"sk-{name[:20]}",
            canonical_name=name, capacity_potential=10,
            capacity_committed=2, capacity_reserved=0,
            capacity_available=available, capacity_state=capacity_state,
            expert_count=experts, evidence_count=3, lifecycle="established",
        ))
        await db.commit()


async def _task(db_session_factory, org_id, project_id, title, status="todo"):
    async with db_session_factory() as db:
        task = Task(organization_id=org_id, project_id=project_id, title=title,
                    status=status)
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()
        return task_id


async def _dep(db_session_factory, org_id, task_id, depends_on_task_id, kind="blocking"):
    async with db_session_factory() as db:
        db.add(TaskDependency(
            organization_id=org_id, task_id=task_id,
            depends_on_task_id=depends_on_task_id, kind=kind,
        ))
        await db.commit()


async def _snapshots(db_session_factory, org_id, goal_id):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(StrategicSnapshot).where(
                        StrategicSnapshot.organization_id == org_id,
                        StrategicSnapshot.goal_id == goal_id,
                    )
                )
            ).scalars().all()
        )


# ---------------------------------------------------------------------------
# 1. The coverage formula and its verdicts
# ---------------------------------------------------------------------------

async def test_coverage_formula_and_verdicts(client, db_session_factory):
    org = await register_org(client, email="4g3_cov@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Revenue +25%")
    obj = await _objective(client, headers, goal_id, caps=["localization"])
    init = await _initiative(client, headers, obj, caps=["localization"])
    project = await _project(db_session_factory, org_id, "Localization Suite")
    await _member(db_session_factory, org_id, project["id"], "emp-x1")
    await _exec_state(db_session_factory, org_id, project["id"], 90)
    await _capability(db_session_factory, org_id, "localization")
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)

    snapshots = await _snapshots(db_session_factory, org_id, goal_id)
    assert len(snapshots) == 4, "one snapshot per strategy event (goal, objective, initiative, link)"
    payload = snapshots[-1].payload_json
    # execution 0.9*0.5 + capability 1.0*0.3 + capacity 1.0*0.2 = 95
    assert payload["coverage"] == 95, payload["coverage"]
    assert payload["health"] == "healthy"
    assert payload["factors"]["execution"] == 0.9
    assert payload["factors"]["capability"] == 1.0
    assert payload["factors"]["capacity"] == 1.0
    assert payload["projects"][0]["health_score"] == 90
    assert payload["people"], "contributing people are evidence"
    assert payload["coverage"] == snapshots[-1].coverage


async def test_verdict_boundaries_at_risk_and_critical(client, db_session_factory):
    org = await register_org(client, email="4g3_bnd@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    at_risk_id = await _goal(client, headers, "Operational Efficiency")
    obj = await _objective(client, headers, at_risk_id)
    init = await _initiative(client, headers, obj)
    project = await _project(db_session_factory, org_id, "Efficiency Project")
    await _member(db_session_factory, org_id, project["id"], "emp-x2")
    await _exec_state(db_session_factory, org_id, project["id"], 40)
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)
    snap = (await _snapshots(db_session_factory, org_id, at_risk_id))[-1]
    # execution 0.4*0.5 + capability 1.0*0.3 + capacity 1.0*0.2 = 70
    assert snap.coverage == 70
    assert snap.health == "at_risk"

    critical_id = await _goal(client, headers, "Security Hardening")
    project2 = await _project(db_session_factory, org_id, "Security Project")
    obj2 = await _objective(client, headers, critical_id, caps=["data_ops"])
    init2 = await _initiative(client, headers, obj2, caps=["data_ops"])
    await _member(db_session_factory, org_id, project2["id"], "emp-x2b")
    await _exec_state(db_session_factory, org_id, project2["id"], 20)
    await _link(client, headers, init2, project2["id"])
    await _drain(db_session_factory)
    snap2 = (await _snapshots(db_session_factory, org_id, critical_id))[-1]
    # execution 20/100 * 0.5 = 0.1; capability 0/1 (claimed but absent from
    # the org capability ledger) *0.3 = 0; capacity 1.0*0.2 = 0.2 => 30
    assert snap2.coverage == 30, snap2.coverage
    assert snap2.health == "critical"

    unlinked = await _goal(client, headers, "Unlinked Goal")
    obj3 = await _objective(client, headers, unlinked)
    await _initiative(client, headers, obj3)
    await _drain(db_session_factory)
    snap3 = (await _snapshots(db_session_factory, org_id, unlinked))[-1]
    assert snap3.coverage == 0, "unlinked goal has no execution coverage"
    assert snap3.health == "critical"
    assert "No active execution is linked" in snap3.payload_json["primary_reason"]


# ---------------------------------------------------------------------------
# 2. Temporal priority memory, exact-once history
# ---------------------------------------------------------------------------

async def test_priority_changes_are_temporal_and_exact_once(client, db_session_factory):
    org = await register_org(client, email="4g3_tmp@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Security", priority=3)
    changed = await client.post(
        f"{STRATEGY}/goals/{goal_id}/priority",
        json={"priority": 1, "reason": "board escalation"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["changed"] is True
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(StrategicHistory).where(
                        StrategicHistory.organization_id == org_id,
                        StrategicHistory.entity_type == "goal",
                        StrategicHistory.entity_id == goal_id,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 2, "created + priority change"
        assert {r.field for r in rows} == {"created", "priority"}
        prio = next(r for r in rows if r.field == "priority")
        assert prio.old_value == "3"
        assert prio.new_value == "1"
        assert prio.reason == "board escalation"

    # handler-level replay of the same event id converges
    await _replay_last_event(
        db_session_factory, org_id, "strategy.goal.priority.changed",
        {"organization_id": org_id, "goal_id": goal_id, "id": goal_id,
         "title": "Enterprise Security", "priority": 1,
         "old_priority": 3, "reason": "board escalation"},
    )
    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(StrategicHistory).where(
                        StrategicHistory.organization_id == org_id,
                        StrategicHistory.entity_id == goal_id,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 2, "replayed priority change never duplicates history"


# ---------------------------------------------------------------------------
# 3. Incremental neighborhoods: one event, one goal
# ---------------------------------------------------------------------------

async def test_events_do_not_touch_other_goals(client, db_session_factory):
    org = await register_org(client, email="4g3_inc@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_a = await _goal(client, headers, "Goal A Growth")
    goal_b = await _goal(client, headers, "Goal B Expansion")
    obj_a = await _objective(client, headers, goal_a)
    obj_b = await _objective(client, headers, goal_b)
    init_a = await _initiative(client, headers, obj_a)
    init_b = await _initiative(client, headers, obj_b)
    project_a = await _project(db_session_factory, org_id, "Project A work")
    project_b = await _project(db_session_factory, org_id, "Project B work")
    await _member(db_session_factory, org_id, project_a["id"], "emp-x3")
    await _member(db_session_factory, org_id, project_b["id"], "emp-x4")
    await _exec_state(db_session_factory, org_id, project_a["id"], 85)
    await _exec_state(db_session_factory, org_id, project_b["id"], 85)
    await _link(client, headers, init_a, project_a["id"])
    await _link(client, headers, init_b, project_b["id"])
    await _drain(db_session_factory)

    before_a = len(await _snapshots(db_session_factory, org_id, goal_a))
    before_b = len(await _snapshots(db_session_factory, org_id, goal_b))
    assert before_a >= 3 and before_b >= 3

    # an event on goal B must not produce a snapshot on goal A
    await client.post(
        f"{STRATEGY}/goals/{goal_b}/priority", json={"priority": 1},
        headers=headers,
    )
    await _drain(db_session_factory)
    after_a = len(await _snapshots(db_session_factory, org_id, goal_a))
    after_b = len(await _snapshots(db_session_factory, org_id, goal_b))
    assert after_a == before_a, "goal A was not in the affected neighborhood"
    assert after_b == before_b + 1, "goal B recomputed exactly once for its event"


# ---------------------------------------------------------------------------
# 4. Link / unlink recompute, exact-once
# ---------------------------------------------------------------------------

async def test_link_unlink_recompute_is_exact_once(client, db_session_factory):
    org = await register_org(client, email="4g3_lku@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Localization Rollout")
    obj = await _objective(client, headers, goal_id, caps=["localization"])
    init = await _initiative(client, headers, obj, caps=["localization"])
    project = await _project(db_session_factory, org_id, "L10N Ops")
    await _member(db_session_factory, org_id, project["id"], "emp-x5")
    await _exec_state(db_session_factory, org_id, project["id"], 80)
    await _capability(db_session_factory, org_id, "localization")
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)

    linked = (await _snapshots(db_session_factory, org_id, goal_id))[-1]
    assert linked.coverage == 90, "0.4 + 0.3 + 0.2 = 0.9 with health 80"

    unlink = await client.post(
        f"{STRATEGY}/initiatives/{init}/unlink",
        json={"project_id": project["id"]}, headers=headers,
    )
    assert unlink.status_code == 200, unlink.text
    await _drain(db_session_factory)
    after = await _snapshots(db_session_factory, org_id, goal_id)
    assert after[-1].coverage == 0, "unlink recomputed coverage back to 0"
    async with db_session_factory() as db:
        live = list(
            (
                await db.execute(
                    select(StrategicLink).where(
                        StrategicLink.organization_id == org_id,
                        StrategicLink.initiative_id == init,
                    )
                )
            ).scalars().all()
        )
        assert len(live) == 0, "live link removed"

    # replay the unlink event row: no extra snapshot, no crash
    await _replay_last_event(
        db_session_factory, org_id, "strategy.initiative.unlinked",
        {"organization_id": org_id, "goal_id": goal_id,
         "objective_id": obj, "initiative_id": init,
         "project_id": project["id"]},
    )
    after_replay = await _snapshots(db_session_factory, org_id, goal_id)
    assert len(after_replay) == len(after), "replay converges, no new snapshot"


# ---------------------------------------------------------------------------
# 5. Alignment and strategic gaps
# ---------------------------------------------------------------------------

async def test_alignment_tiers_and_gaps(client, db_session_factory):
    org = await register_org(client, email="4g3_alg@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Retention Program")
    obj = await _objective(client, headers, goal_id)
    init = await _initiative(client, headers, obj)
    direct = await _project(db_session_factory, org_id, "Direct Project")
    await _link(client, headers, init, direct["id"])
    bare = await _project(db_session_factory, org_id, "Bare Project")
    await _member(db_session_factory, org_id, direct["id"], "emp-x6b")
    await _publish(db_session_factory, org_id, "emp-x6", "project.started",
                   {"organization_id": org_id, "project_id": bare["id"]})
    await _drain(db_session_factory)

    gaps = (await client.get(f"{STRATEGY}/gaps", headers=headers)).json()
    assert "unaligned_projects" in gaps
    bare_rows = [g for g in gaps["unaligned_projects"] if g["project_id"] == bare["id"]]
    assert len(bare_rows) == 1
    assert bare_rows[0]["alignment"] == "none"
    assert "no explicit relationship" in bare_rows[0]["reason"]

    portfolio = (await client.get(f"{STRATEGY}/portfolio", headers=headers)).json()
    assert portfolio["alignment"]["total_active_projects"] == 2
    assert portfolio["alignment"]["direct"] == 1, \
        "linked under an active chain counts as direct alignment"
    assert portfolio["alignment"]["none"] == 1


# ---------------------------------------------------------------------------
# 6. Strategy -> outcome learning (exact-once, verdict drives 4E.7 memory)
# ---------------------------------------------------------------------------

async def test_strategy_outcome_learning_is_exact_once(client, db_session_factory):
    org = await register_org(client, email="4g3_lrn@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Retention")
    obj = await _objective(client, headers, goal_id)
    init = await _initiative(
        client, headers, obj, expected={"metric_kind": "retention",
                                        "target_value": 8, "unit": "pct"},
    )
    recorded = await client.post(
        f"{STRATEGY}/initiatives/{init}/outcome",
        json={"metric_kind": "retention", "unit": "pct",
              "expected_value": 8, "actual_value": 2},
        headers=headers,
    )
    assert recorded.status_code == 200, recorded.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(StrategicOutcome).where(
                        StrategicOutcome.organization_id == org_id,
                        StrategicOutcome.initiative_id == init,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        assert rows[0].expected_value == 8
        assert rows[0].actual_value == 2

    # the assumption closed with a verdict -> 4E.7 memory
    async with db_session_factory() as db:
        lessons = list(
            (
                await db.execute(
                    select(AIMemory).where(
                        AIMemory.organization_id == org_id,
                        AIMemory.kind == "lesson",
                        AIMemory.content.like("%over-optimistic%"),
                    )
                )
            ).scalars().all()
        )
        assert len(lessons) >= 1, "strategy learning reached organizational memory"
        assert "retention" in lessons[0].content

    detail = (await client.get(
        f"{STRATEGY}/goals/{goal_id}", headers=headers)).json()
    assert detail["learning"], "goal detail exposes the learning"
    assert detail["learning"][0]["metric_kind"] == "retention"
    assert detail["learning"][0]["verdict"] == "over-optimistic"
    assert detail["outcomes"][0]["expected_value"] == 8

    # replay of the same event id converges
    await _replay_last_event(
        db_session_factory, org_id, "strategy.outcome.recorded",
        {"organization_id": org_id, "goal_id": goal_id,
         "objective_id": obj, "initiative_id": init,
         "metric_kind": "retention", "unit": "pct",
         "expected_value": 8, "actual_value": 2},
    )
    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(StrategicOutcome).where(
                        StrategicOutcome.organization_id == org_id,
                        StrategicOutcome.initiative_id == init,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 1, "replayed outcome never double counts"


# ---------------------------------------------------------------------------
# 7. Bounded impact propagation
# ---------------------------------------------------------------------------

async def test_delay_impact_reaches_downstream_and_the_goal(client, db_session_factory):
    org = await register_org(client, email="4g3_imp@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Apollo Expansion")
    obj = await _objective(client, headers, goal_id)
    init = await _initiative(
        client, headers, obj,
        commitments=[{"customer": "ACME", "summary": "Enterprise launch by Q3"}],
    )
    apollo = await _project(db_session_factory, org_id, "Apollo")
    zeus = await _project(db_session_factory, org_id, "Zeus")
    await _link(client, headers, init, apollo["id"])
    await _member(db_session_factory, org_id, apollo["id"], "emp-x7")
    await _exec_state(db_session_factory, org_id, apollo["id"], 60)
    t1 = await _task(db_session_factory, org_id, apollo["id"], "core engine")
    t2 = await _task(db_session_factory, org_id, zeus["id"], "zeus adapter")
    await _dep(db_session_factory, org_id, t2, t1)
    await _drain(db_session_factory)

    impact = (await client.get(
        f"{STRATEGY}/impact", params={"project_id": apollo["id"],
                                      "delay_days": 14},
        headers=headers)).json()
    assert impact["project_name"] == "Apollo"
    assert any(p["project_id"] == zeus["id"] for p in impact["downstream_projects"])
    assert impact["downstream_count"] >= 1
    assert impact["portfolio_projects_affected"] >= 2
    assert any(s["goal_id"] == goal_id for s in impact["strategic_chain"])
    sim = next(s for s in impact["strategic_chain"] if s["goal_id"] == goal_id)
    assert sim["coverage_simulated"] < sim["coverage_now"], "delay lowers coverage"
    assert sim["customer_commitments"][0]["customer"] == "ACME"
    assert impact["bounds"], "every impact states what it does NOT claim"
    assert impact["risk"] in ("high", "medium")


# ---------------------------------------------------------------------------
# 8. Bounded what-if: priority re-ranking
# ---------------------------------------------------------------------------

async def test_what_if_priority_reranks_focus(client, db_session_factory):
    org = await register_org(client, email="4g3_wif@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    # Goal A: priority 3 with high coverage (least attention)
    goal_a = await _goal(client, headers, "Steady Growth", priority=3)
    obj_a = await _objective(client, headers, goal_a)
    init_a = await _initiative(client, headers, obj_a)
    proj_a = await _project(db_session_factory, org_id, "Steady work")
    await _member(db_session_factory, org_id, proj_a["id"], "emp-x8")
    await _exec_state(db_session_factory, org_id, proj_a["id"], 95)
    await _link(client, headers, init_a, proj_a["id"])

    # Goal B: priority 1 already at risk (top attention)
    goal_b = await _goal(client, headers, "Global Expansion", priority=1)
    obj_b = await _objective(client, headers, goal_b)
    init_b = await _initiative(client, headers, obj_b)
    proj_b = await _project(db_session_factory, org_id, "Expansion work")
    await _member(db_session_factory, org_id, proj_b["id"], "emp-x8b")
    await _exec_state(db_session_factory, org_id, proj_b["id"], 40)
    await _link(client, headers, init_b, proj_b["id"])

    # Goal C: priority 2 healthy (middle attention)
    goal_c = await _goal(client, headers, "Regional Push", priority=2)
    obj_c = await _objective(client, headers, goal_c)
    init_c = await _initiative(client, headers, obj_c)
    proj_c = await _project(db_session_factory, org_id, "Regional work")
    await _member(db_session_factory, org_id, proj_c["id"], "emp-x8c")
    await _exec_state(db_session_factory, org_id, proj_c["id"], 95)
    await _link(client, headers, init_c, proj_c["id"])
    await _drain(db_session_factory)

    focus = (await client.get(f"{STRATEGY}/focus", headers=headers)).json()
    ranks = {f["goal_id"]: i for i, f in enumerate(focus["focus"])}
    assert ranks[goal_b] < ranks[goal_c] < ranks[goal_a], \
        "at-risk P1 outranks healthy P2, which outranks healthy P3"
    why = focus["focus"][ranks[goal_b]]["why"]
    assert any("priority P1" in w for w in why)
    assert any("coverage" in w for w in why)

    what_if = (await client.get(
        f"{STRATEGY}/what-if", params={"goal_id": goal_a, "priority": 1},
        headers=headers)).json()
    assert what_if["not_a_prediction"] is True
    assert what_if["change"]["type"] == "priority"
    assert what_if["rank_after"] < what_if["rank_before"], \
        "P1 lift reranks the healthy goal above P2 while P1-at-risk stays on top"
    assert what_if["assumptions"]


# ---------------------------------------------------------------------------
# 9. Alternatives: advisory options and a recommendation
# ---------------------------------------------------------------------------

async def test_alternatives_are_bounded_and_advisory(client, db_session_factory):
    org = await register_org(client, email="4g3_alt@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "EU Compliance")
    obj = await _objective(client, headers, goal_id, caps=["legal"])
    init = await _initiative(client, headers, obj, caps=["legal"])
    project = await _project(db_session_factory, org_id, "Compliance Engine")
    await _link(client, headers, init, project["id"])
    await _capability(db_session_factory, org_id, "legal", capacity_state="constrained",
                      available=0)
    await _drain(db_session_factory)

    result = (await client.get(
        f"{STRATEGY}/alternatives", params={"project_id": project["id"]},
        headers=headers)).json()
    assert result["advisory_only"] is True
    assert len(result["options"]) == 3
    keys = {o["key"] for o in result["options"]}
    assert keys == {"keep_scope", "reduce_scope", "add_external_capability"}
    external = next(o for o in result["options"] if o["key"] == "add_external_capability")
    assert "legal" in external["effects"][0], "constrained capability is evidence"
    assert "recommendation" in result
    best = result["recommendation"]
    assert "balance" in best.lower() or "Option" in best


# ---------------------------------------------------------------------------
# 10. Portfolio health + contention
# ---------------------------------------------------------------------------

async def test_portfolio_surface_is_deterministic(client, db_session_factory):
    org = await register_org(client, email="4g3_pf@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Enterprise Growth", priority=1)
    obj = await _objective(client, headers, goal_id, caps=["localization"])
    init = await _initiative(client, headers, obj, caps=["localization"])
    project = await _project(db_session_factory, org_id, "Growth work")
    await _member(db_session_factory, org_id, project["id"], "emp-x9")
    await _exec_state(db_session_factory, org_id, project["id"], 90)
    await _capability(db_session_factory, org_id, "localization")
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)

    portfolio = (await client.get(f"{STRATEGY}/portfolio", headers=headers)).json()
    assert portfolio["advisory_only"] is True
    assert portfolio["health_summary"]["total"] == 1
    assert portfolio["health_summary"]["healthy"] == 1
    assert portfolio["mean_goal_coverage"] == 95
    assert portfolio["alignment"]["total_active_projects"] >= 1
    assert portfolio["alignment"]["direct"] >= 1
    assert portfolio["confidence"]["outcome_samples"] == 0
    assert portfolio["focus"][0]["goal_id"] == goal_id
    assert portfolio["focus"][0]["why"]

    second = (await client.get(f"{STRATEGY}/portfolio", headers=headers)).json()
    assert {k: v for k, v in second.items() if k != "generated_at"} == \
        {k: v for k, v in portfolio.items() if k != "generated_at"}, \
        "portfolio is deterministic on the same evidence"


async def test_portfolio_conflicts_surface(client, db_session_factory):
    org = await register_org(client, email="4g3_cfl@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    for idx, (title, cap) in enumerate([
        ("Revenue Northstar", "localization"),
        ("Expansion Europe", "localization"),
    ]):
        goal_id = await _goal(client, headers, title, priority=1 + idx)
        obj = await _objective(client, headers, goal_id, caps=[cap])
        init = await _initiative(client, headers, obj, caps=[cap])
        project = await _project(db_session_factory, org_id, f"Work {title}")
        await _member(db_session_factory, org_id, project["id"], f"emp-c{idx}")
        await _exec_state(db_session_factory, org_id, project["id"], 80)
        await _link(client, headers, init, project["id"])
    await _capability(db_session_factory, org_id, "localization",
                      capacity_state="constrained", available=0)
    await _drain(db_session_factory)

    result = (await client.get(f"{STRATEGY}/conflicts", headers=headers)).json()
    assert result["advisory_only"] is True
    conflicts = [c for c in result["conflicts"] if c["capability"] == "localization"]
    assert len(conflicts) == 1
    assert len(conflicts[0]["claimants"]) == 2, "two goals claim the capability"
    assert conflicts[0]["strategic_stakes"]
    priorities = [c["priority"] for c in conflicts[0]["claimants"]]
    assert priorities == sorted(priorities), "claimants ordered by priority"


# ---------------------------------------------------------------------------
# 11. Advisory-only: the engine never mutates projects/people/capacity
# ---------------------------------------------------------------------------

async def test_engine_is_advisory_only(client, db_session_factory):
    org = await register_org(client, email="4g3_adv@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    goal_id = await _goal(client, headers, "Advisory Goal")
    obj = await _objective(client, headers, goal_id)
    init = await _initiative(client, headers, obj)
    project = await _project(db_session_factory, org_id, "Advisory project")
    await _link(client, headers, init, project["id"])
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        from app.models.project import Project

        row = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == org_id,
                    Project.id == project["id"],
                )
            )
        ).scalar_one()
        assert row.status == "active", "engine never changes the project"
        parent = (
            await db.execute(
                select(CompanyGoal).where(
                    CompanyGoal.organization_id == org_id,
                    CompanyGoal.id == goal_id,
                )
            )
        ).scalar_one()
        assert parent.priority == 3, "engine never changes the goal"