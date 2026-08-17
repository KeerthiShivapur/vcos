"""Slice 4G.1 — Project & Execution Intelligence engine behaviors.

The engine is fed change-driven by the durable events the platform already
emits (never write-through): health is deterministic (fixed penalty budget
per surface), the critical path is real CPM with slack, blockers carry
root-cause chains with systemic grouping, capacity is read from the 4F.6
record, pending decisions come from the 4A registry, the goal chain is
materialized root-first, every event-driven refresh is exact-once on
source_event_id, snapshot history is capped, the outcome record is the only
human write, and the engine NEVER touches projects/tasks/people itself.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.intelligence.execution_engine import execution_engine
from app.models.execution_intelligence import (
    ProjectExecutionSnapshot,
    ProjectExecutionState,
)
from app.models.goal import Goal
from app.models.knowledge import Decision
from app.models.project import Milestone, Project
from app.models.task import Task, TaskDependency
from tests.conftest import register_org


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


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"g1-{name.lower().replace(' ', '-')[:20]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _drained_project(client, headers, db_session_factory, name):
    project = await _project(client, headers, name)
    await _drain(db_session_factory)
    return project


async def _task(db, org_id, project_id, title, *, status="backlog",
                priority="medium", estimate_hours=None, due_date=None,
                decision_id=None):
    task = Task(
        organization_id=org_id, project_id=project_id, title=title,
        status=status, priority=priority, estimate_hours=estimate_hours,
        due_date=due_date, decision_id=decision_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _state(db_session_factory, org_id, project_id):
    async with db_session_factory() as db:
        return (
            await db.execute(
                select(ProjectExecutionState).where(
                    ProjectExecutionState.organization_id == org_id,
                    ProjectExecutionState.project_id == project_id,
                )
            )
        ).scalar_one_or_none()


async def _detail(db_session_factory, org_id, project_id):
    async with db_session_factory() as db:
        return await execution_engine.project_detail(
            db, organization_id=org_id, project_id=project_id,
        )


async def _snapshot_count(db_session_factory, org_id, project_id):
    async with db_session_factory() as db:
        return len(
            list(
                (
                    await db.execute(
                        select(ProjectExecutionSnapshot.id).where(
                            ProjectExecutionSnapshot.organization_id == org_id,
                            ProjectExecutionSnapshot.project_id == project_id,
                        )
                    )
                ).scalars().all()
            )
        )


# ------------------------------------------------------------ health baseline


async def test_baseline_record_is_healthy_and_advisory(client, db_session_factory):
    org = await register_org(client, email="4g1_e1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Baseline")
    state = await _state(db_session_factory, org_id, project["id"])
    assert state is not None
    assert state.health_score == 80
    assert state.health_status == "healthy"
    assert state.factors["ownership"]["no_owner"] is False
    detail = await _detail(db_session_factory, org_id, project["id"])
    assert detail["health_status"] == "healthy"
    assert detail["counts"]["project_status"] == "draft"

    # the engine never wrote the source rows: one project, no tasks added
    async with db_session_factory() as db:
        projects = list(
            (
                await db.execute(
                    select(Project).where(Project.organization_id == org_id)
                )
            ).scalars().all()
        )
        tasks = list(
            (
                await db.execute(
                    select(Task).where(Task.organization_id == org_id)
                )
            ).scalars().all()
        )
    assert len(projects) == 1
    assert projects[0].status == "draft"
    assert tasks == []


async def test_unowned_project_penalty_and_explain(client, db_session_factory):
    org = await register_org(client, email="4g1_e2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id,
            code="g1-unowned", name="Ownerless", status="active",
        )
        db.add(project)
        await db.commit()
        project_id = project.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "project.created",
        {"project_id": project_id, "name": "Ownerless"},
    )
    state = await _state(db_session_factory, org_id, project_id)
    assert state.health_score == 70
    assert state.health_status == "watch"
    assert "no project owner assigned" in state.explain


# ------------------------------------------------------------- blocker chains


async def test_blocked_chain_root_cause_and_primary_cause(client, db_session_factory):
    org = await register_org(client, email="4g1_e3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Blocked Work")

    async with db_session_factory() as db:
        root = await _task(db, org_id, project["id"], "Root work", status="todo")
        leaf = await _task(db, org_id, project["id"], "Leaf work", status="blocked")
        db.add(TaskDependency(
            organization_id=org_id, task_id=leaf.id,
            depends_on_task_id=root.id, kind="blocking",
        ))
        await db.commit()
        root_id, leaf_id = root.id, leaf.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.blocked",
        {"task_id": leaf_id, "project_id": project["id"], "status": "blocked"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    assert detail["health_status"] in ("watch", "at_risk", "critical")
    assert detail["primary_cause"] == "Dependency blockage"
    assert detail["counts"]["blocked_tasks"] == 1
    blockers = detail["blockers"]
    assert len(blockers) == 1
    assert blockers[0]["task_id"] == leaf_id
    assert blockers[0]["chain"][0]["task_id"] == root_id
    assert blockers[0]["chain"][0]["title"] == "Root work"
    assert "blocked task(s)" in detail["explain"]


async def test_deeply_blocked_chain_materializes(client, db_session_factory):
    org = await register_org(client, email="4g1_e4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Deep Block")

    async with db_session_factory() as db:
        ground = await _task(db, org_id, project["id"], "Ground", status="todo")
        mid = await _task(db, org_id, project["id"], "Middle", status="blocked")
        top = await _task(db, org_id, project["id"], "Top", status="blocked")
        db.add(TaskDependency(organization_id=org_id, task_id=mid.id,
                              depends_on_task_id=ground.id, kind="blocking"))
        db.add(TaskDependency(organization_id=org_id, task_id=top.id,
                              depends_on_task_id=mid.id, kind="blocking"))
        await db.commit()
        top_id = top.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.blocked",
        {"task_id": top_id, "project_id": project["id"], "status": "blocked"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    assert detail["counts"]["deeply_blocked_tasks"] == 1
    top_row = next(b for b in detail["blockers"] if b["task_id"] == top_id)
    assert top_row["chain_depth"] == 2
    assert [c["title"] for c in top_row["chain"]] == ["Middle", "Ground"]


async def test_systemic_blockers_group_by_shared_root(client, db_session_factory):
    org = await register_org(client, email="4g1_e5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Systemic")

    async with db_session_factory() as db:
        root = await _task(db, org_id, project["id"], "Shared bottleneck",
                           status="todo")
        leaves = []
        for i in range(3):
            leaf = await _task(db, org_id, project["id"], f"Affected {i}",
                               status="blocked")
            db.add(TaskDependency(organization_id=org_id, task_id=leaf.id,
                                  depends_on_task_id=root.id, kind="blocking"))
            leaves.append(leaf)
        await db.commit()
        root_id = root.id
        leaf_ids = [l.id for l in leaves]
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.blocked",
        {"task_id": leaf_ids[0], "project_id": project["id"], "status": "blocked"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    grouped = detail["systemic_blockers"]
    assert len(grouped) == 1, grouped
    assert grouped[0]["subject_id"] == root_id
    assert grouped[0]["affected_count"] == 3
    assert set(grouped[0]["affected_tasks"]) == set(leaf_ids)


# ---------------------------------------------------------------- critical path


async def test_critical_path_cpm_slack(client, db_session_factory):
    org = await register_org(client, email="4g1_e6@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "CPM Project")

    async with db_session_factory() as db:
        a = await _task(db, org_id, project["id"], "A", estimate_hours=4)
        b = await _task(db, org_id, project["id"], "B", estimate_hours=2)
        c = await _task(db, org_id, project["id"], "C", estimate_hours=3)
        d = await _task(db, org_id, project["id"], "D", estimate_hours=2)
        e = await _task(db, org_id, project["id"], "E", estimate_hours=2)
        for pred, succ in ((a, b), (b, c)):
            db.add(TaskDependency(organization_id=org_id, task_id=succ.id,
                                  depends_on_task_id=pred.id,
                                  kind="finish_to_start"))
        db.add(TaskDependency(organization_id=org_id, task_id=e.id,
                              depends_on_task_id=d.id, kind="finish_to_start"))
        await db.commit()
        a_id, b_id, c_id, d_id, e_id = a.id, b.id, c.id, d.id, e.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.created",
        {"task_id": a_id, "project_id": project["id"], "status": "backlog"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    cpath = detail["critical_path"]
    assert cpath["total_hours"] == 13.0
    assert cpath["projected_finish_hours"] == 9.0
    assert cpath["min_slack"] == 0.0
    critical = set(cpath["critical_task_ids"])
    assert critical == {a_id, b_id, c_id}
    assert d_id not in critical and e_id not in critical
    for row in cpath["tasks"]:
        if row["task_id"] in (a_id, b_id, c_id):
            assert row["critical"] is True
        if row["task_id"] in (d_id, e_id):
            assert row["critical"] is False
            assert row["slack_hours"] == 5.0


async def test_overdue_critical_task_primary_cause(client, db_session_factory):
    org = await register_org(client, email="4g1_e7@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Slipping")

    yesterday = date.today() - timedelta(days=1)
    async with db_session_factory() as db:
        a = await _task(db, org_id, project["id"], "A", estimate_hours=4)
        b = await _task(db, org_id, project["id"], "B", estimate_hours=2,
                        due_date=yesterday)
        c = await _task(db, org_id, project["id"], "C", estimate_hours=3)
        for pred, succ in ((a, b), (b, c)):
            db.add(TaskDependency(organization_id=org_id, task_id=succ.id,
                                  depends_on_task_id=pred.id,
                                  kind="finish_to_start"))
        await db.commit()
        b_id = b.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.created",
        {"task_id": a.id, "project_id": project["id"], "status": "backlog"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    assert detail["primary_cause"] == "Timeline pressure"
    assert detail["counts"]["critical_overdue_tasks"] == 1
    assert detail["critical_path"]["overdue_critical_ids"] == 1
    assert "critical-path task(s) past due" in detail["explain"]
    assert detail["health_score"] < 80
    assert detail["factors"]["timeline"]["critical_overdue_tasks"] == 1


async def test_overdue_milestone_counts_and_penalty(client, db_session_factory):
    org = await register_org(client, email="4g1_e8@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Milestone Drift")

    yesterday = date.today() - timedelta(days=2)
    async with db_session_factory() as db:
        db.add(Milestone(organization_id=org_id, project_id=project["id"],
                         name="Launch", due_date=yesterday, status="pending"))
        db.add(Milestone(organization_id=org_id, project_id=project["id"],
                         name="Done", due_date=yesterday, status="completed"))
        await db.commit()
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "milestone.created",
        {"project_id": project["id"], "name": "Launch"},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    assert detail["counts"]["overdue_milestones"] == 1
    assert "overdue milestone(s)" in detail["explain"]


# --------------------------------------------------------------- integrations


async def test_capacity_constraint_read_from_4f6(client, db_session_factory):
    from app.models.org_capability_intelligence import CapabilityProjectLink
    from app.models.project import ProjectMember
    from app.models.skills_intelligence import CanonicalSkill, Expertise
    from app.people.skill_engine import skill_engine

    org = await register_org(client, email="4g1_e9@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    expert = (await client.post(
        "/api/v1/employees",
        json={"first_name": "Tight", "last_name": "Fit", "email": "4g1-e9@test.co"},
        headers=headers,
    )).json()
    p1 = await _project(client, headers, "Constrained One")
    p2 = await _project(client, headers, "Constrained Two")

    async with db_session_factory() as db:
        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        skill_id = (
            await db.execute(
                select(CanonicalSkill.id).where(
                    CanonicalSkill.organization_id == org_id,
                    CanonicalSkill.canonical_name == "Kubernetes",
                )
            )
        ).scalar_one_or_none()
        assert skill_id is not None
        db.add(Expertise(
            organization_id=org_id, person_id=expert["id"], skill_id=skill_id,
            score=85.0, evidence_count=8, lifecycle="strong",
            successful_count=8,
            last_observed=datetime.now(timezone.utc),
        ))
        for pid, pname in ((p1["id"], "Constrained One"),
                           (p2["id"], "Constrained Two")):
            db.add(CapabilityProjectLink(
                organization_id=org_id, project_id=pid, project_name=pname,
                skill_id=skill_id, skill_name="Kubernetes",
                source_event_id=f"4g1-cap-{pid}", status="active",
            ))
            db.add(ProjectMember(
                organization_id=org_id, project_id=pid, employee_id=expert["id"],
            ))
        await db.commit()
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "skill.updated",
        {"skill_id": skill_id},
    )
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "task.created",
        {"task_id": "none", "project_id": p1["id"], "status": "backlog"},
    )

    detail = await _detail(db_session_factory, org_id, p1["id"])
    names = [c["skill_name"] for c in detail["capacity_constraints"]]
    assert "Kubernetes" in names, names
    assert detail["factors"]["capacity"]["constrained_skills"] == ["Kubernetes"]
    assert "capacity constrained" in detail["explain"]
    assert detail["health_score"] <= 80 - 8


async def test_pending_decisions_from_4a_registry(client, db_session_factory):
    org = await register_org(client, email="4g1_e10@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Decisions Gate")

    async with db_session_factory() as db:
        decision = Decision(
            organization_id=org_id, title="Which vendor for the platform?",
            slug=f"4g1-vendor-{org_id[:8]}", status="proposed",
            project_id=project["id"],
        )
        db.add(decision)
        await db.flush()
        action = await _task(db, org_id, project["id"], "Evaluate vendor A",
                             status="todo", decision_id=decision.id)
        await db.commit()
        decision_id, action_id = decision.id, action.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "decision.made",
        {"decision_id": decision_id, "project_id": project["id"]},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    pending = detail["pending_decisions"]
    assert len(pending) == 1
    assert pending[0]["decision_id"] == decision_id
    assert pending[0]["open_actions"] == 1
    assert detail["factors"]["decisions"]["total_pending"] == 1
    assert detail["primary_cause"] == "Pending decisions"
    assert "pending decision(s) with open action task(s)" in detail["explain"]


async def test_goal_chain_root_first(client, db_session_factory):
    org = await register_org(client, email="4g1_e11@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Chained Work")

    async with db_session_factory() as db:
        company = Goal(organization_id=org_id, name="Company goal",
                       scope="company", status="in_progress")
        db.add(company)
        await db.flush()
        objective = Goal(organization_id=org_id, name="Business objective",
                         scope="department", parent_goal_id=company.id,
                         status="in_progress")
        db.add(objective)
        await db.flush()
        anchored = Goal(organization_id=org_id, name="Project goal",
                        scope="project", parent_goal_id=objective.id,
                        project_id=project["id"], status="in_progress")
        db.add(anchored)
        await db.commit()
        anchored_id = anchored.id
    await _publish(
        db_session_factory, org_id, org["user"]["id"], "goal.created",
        {"goal_id": anchored_id, "project_id": project["id"]},
    )

    detail = await _detail(db_session_factory, org_id, project["id"])
    chain = detail["goal_chain"]
    assert [g["title"] for g in chain] == [
        "Company goal", "Business objective", "Project goal",
    ]
    assert chain[0]["scope"] == "company"
    assert chain[2]["scope"] == "project"


# ------------------------------------------------------------- exact-once & cap


async def test_replay_guard_is_exact_once(client, db_session_factory):
    org = await register_org(client, email="4g1_e12@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "Replay")

    async with db_session_factory() as db:
        first = await execution_engine.refresh_project(
            db, organization_id=org_id, project_id=project["id"],
            event_name="project.created", source_event_id="evt-replay-1",
        )
        await db.commit()
        assert first is not None and first["health_status"] == "healthy"
        second = await execution_engine.refresh_project(
            db, organization_id=org_id, project_id=project["id"],
            event_name="project.created", source_event_id="evt-replay-1",
        )
        await db.commit()
        assert second is None
    assert await _snapshot_count(
        db_session_factory, org_id, project["id"]) == 2
    async with db_session_factory() as db:
        replays = len(
            list(
                (
                    await db.execute(
                        select(ProjectExecutionSnapshot.id).where(
                            ProjectExecutionSnapshot.organization_id == org_id,
                            ProjectExecutionSnapshot.project_id == project["id"],
                            ProjectExecutionSnapshot.source_event_id == "evt-replay-1",
                        )
                    )
                ).scalars().all()
            )
        )
    assert replays == 1
    states = 0
    async with db_session_factory() as db:
        states = len(
            list(
                (
                    await db.execute(
                        select(ProjectExecutionState).where(
                            ProjectExecutionState.organization_id == org_id,
                            ProjectExecutionState.project_id == project["id"],
                        )
                    )
                ).scalars().all()
            )
        )
    assert states == 1


async def test_snapshot_history_is_bounded(client, db_session_factory):
    org = await register_org(client, email="4g1_e13@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _drained_project(client, headers, db_session_factory, "History")

    async with db_session_factory() as db:
        for i in range(45):
            await execution_engine.refresh_project(
                db, organization_id=org_id, project_id=project["id"],
                event_name="task.transitioned",
                source_event_id=f"evt-hist-{i}",
            )
        await db.commit()
    assert await _snapshot_count(
        db_session_factory, org_id, project["id"]) == 40


async def test_outcome_record_and_lifecycle_states(client, db_session_factory):
    org = await register_org(client, email="4g1_e14@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    # completed -> healthy, 100, primary cause cleared
    done = await _project(client, headers, "Finished")
    res = await client.post(
        f"/api/v1/projects/{done['id']}/lifecycle",
        json={"action": "complete"}, headers=headers,
    )
    assert res.status_code == 200, res.text
    await _drain(db_session_factory)
    detail = await _detail(db_session_factory, org_id, done["id"])
    assert detail["health_status"] == "healthy"
    assert detail["health_score"] == 100
    assert detail["primary_cause"] is None

    # cancelled -> critical
    cancelled = await _project(client, headers, "Axed")
    res = await client.post(
        f"/api/v1/projects/{cancelled['id']}/lifecycle",
        json={"action": "cancel"}, headers=headers,
    )
    assert res.status_code == 200, res.text
    await _drain(db_session_factory)
    detail = await _detail(db_session_factory, org_id, cancelled["id"])
    assert detail["health_status"] == "critical"

    # mandatory outcome record: human write, snapshotted, advisory-only
    async with db_session_factory() as db:
        outcome = await execution_engine.record_outcome(
            db, organization_id=org_id, project_id=done["id"],
            outcome={
                "status": "successful",
                "planned_outcome": "Ship on time",
                "actual_outcome": "Shipped early",
                "assessment": "Milestones held",
            },
            recorded_by=org["user"]["id"],
        )
        await db.commit()
    assert outcome["status"] == "successful"
    assert outcome["planned_outcome"] == "Ship on time"

    before = await _detail(db_session_factory, org_id, done["id"])
    assert before["outcome"]["assessment"] == "Milestones held"
    assert before["health_status"] == "healthy"

    # advisory-only: project lifecycle untouched by the record
    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == org_id,
                    Project.id == done["id"],
                )
            )
        ).scalar_one()
        assert row.status == "completed"
        assert row.progress == 100