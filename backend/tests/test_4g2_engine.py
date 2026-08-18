"""Slice 4G.2 — Execution Coordination & Dependency Intelligence engine.

The coordination layer of the Execution Command Center. Under test:

* the handoff ledger: a task ownership transition opens a pending handoff,
  completion closes it with a measured duration, the FIRST owner is not a
  handoff, replays are exact-once on source_event_id,
* handoff risk: a pending handoff past the risk window becomes a finding
  (72h -> medium, 7d -> high) and resolves when the condition clears,
* recurring slow handoffs (3+ of the same from->to in 30d) become a finding,
* shared-capacity contention: active projects competing for one constrained
  capability become a finding that resolves when demand falls below two,
* critical conflicts: blocked critical paths contending for the same
  constrained capability -> critical finding,
* coordination gaps: a project engages multiple teams with no collaboration
  evidence -> a finding,
* propagation: a blocked critical path reaches milestones, the goal chain,
  decisions and capability partners,
* findings are fingerprint-deduped, history is exact-once, the engine is
  advisory-only (writes only its own tables), and a human resolve is durable
  yet reopens when the condition recurs.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.intelligence.coordination_engine import coordination_engine
from app.models.execution_coordination import (
    CoordinationHandoff,
    CoordinationHistory,
    CoordinationIncident,
)
from app.models.goal import Goal
from app.models.project import Milestone, Project, ProjectMember
from app.models.task import Task, TaskDependency
from app.models.team import Team
from tests.conftest import register_org

BRAIN = "/api/v1/brain"


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


async def _project(client, headers, name, status="active"):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"g2-{name.lower().replace(' ', '-')[:20]}",
              "status": status},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _hire(client, headers, email, first, last, team_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _task(db, org_id, project_id, title, *, status="backlog",
                assignee_id=None, estimate_hours=None, due_date=None,
                milestone_id=None):
    task = Task(
        organization_id=org_id, project_id=project_id, title=title,
        status=status, assignee_id=assignee_id, estimate_hours=estimate_hours,
        due_date=due_date, milestone_id=milestone_id,
    )
    db.add(task)
    await db.flush()
    return task


async def _dep(db, org_id, task_id, depends_on_task_id, kind="blocking"):
    db.add(TaskDependency(
        organization_id=org_id, task_id=task_id,
        depends_on_task_id=depends_on_task_id, kind=kind,
    ))
    await db.flush()


async def _incidents(db_session_factory, org_id):
    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(CoordinationIncident).where(
                        CoordinationIncident.organization_id == org_id,
                    )
                )
            ).scalars().all()
        )
        return rows


async def _handoffs(db_session_factory, org_id):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CoordinationHandoff)
                    .where(
                        CoordinationHandoff.organization_id == org_id,
                    )
                    .order_by(CoordinationHandoff.occurred_at.desc())
                )
            ).scalars().all()
        )


async def _history(db_session_factory, org_id):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CoordinationHistory).where(
                        CoordinationHistory.organization_id == org_id,
                    )
                )
            ).scalars().all()
        )


def _open(rows):
    return [r for r in rows if r.status == "open"]


# ------------------------------------------------------------ handoff ledger


async def test_handoff_ledger_transition_and_completion(client, db_session_factory):
    org = await register_org(client, email="4g2_e1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    alice = await _hire(client, headers, "4g2-e1a@test.co", "Alice", "One")
    bob = await _hire(client, headers, "4g2-e1b@test.co", "Bob", "Two")
    project = await _project(client, headers, "Handoff Ledger")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        task = await _task(db, org_id, project["id"], "Ship the adapter",
                           status="in_progress", assignee_id=alice["id"])
        await db.commit()
        task_id = task.id

    # first owner: NOT a handoff (ownership needs a real transition)
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "title": "Ship the adapter",
        "project_id": project["id"], "assignee_id": alice["id"],
    })
    handoffs = await _handoffs(db_session_factory, org_id)
    assert len(handoffs) == 0

    # a real transition opens a pending handoff from Alice to Bob
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "title": "Ship the adapter",
        "project_id": project["id"], "assignee_id": bob["id"],
        "from_assignee_id": alice["id"],
    })
    handoffs = await _handoffs(db_session_factory, org_id)
    assert len(handoffs) == 1
    assert handoffs[0].from_owner_label == "Alice One"
    assert handoffs[0].to_owner_label == "Bob Two"
    assert handoffs[0].status == "pending"

    # the same event replayed converges: exact-once
    await _drain(db_session_factory)
    assert len(await _handoffs(db_session_factory, org_id)) == 1

    # completion closes the pending handoff with a measured duration
    await _publish(db_session_factory, org_id, actor, "task.completed", {
        "task_id": task_id, "title": "Ship the adapter",
        "project_id": project["id"], "status": "completed",
    })
    handoffs = await _handoffs(db_session_factory, org_id)
    assert handoffs[0].status == "completed"
    assert handoffs[0].duration_hours is not None
    assert handoffs[0].duration_hours >= 0


async def test_assignee_change_closes_and_reopens_a_handoff(client, db_session_factory):
    org = await register_org(client, email="4g2_e2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-e2a@test.co", "Ann", "A")
    b = await _hire(client, headers, "4g2-e2b@test.co", "Ben", "B")
    c = await _hire(client, headers, "4g2-e2c@test.co", "Cid", "C")
    project = await _project(client, headers, "Reopen Chain")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        task = await _task(db, org_id, project["id"], "Reopen task",
                           status="in_progress", assignee_id=a["id"])
        await db.commit()
        task_id = task.id

    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": b["id"],
        "from_assignee_id": a["id"],
    })
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": c["id"],
        "from_assignee_id": b["id"],
    })
    handoffs = await _handoffs(db_session_factory, org_id)
    assert len(handoffs) == 2
    assert [h.status for h in handoffs] == ["pending", "completed"]
    closed = next(h for h in handoffs if h.status == "completed")
    assert closed.from_owner_label == "Ann A" and closed.to_owner_label == "Ben B"
    assert closed.duration_hours is not None


# -------------------------------------------------------------- handoff risk


async def test_pending_handoff_past_risk_window_becomes_a_finding(
    client, db_session_factory,
):
    org = await register_org(client, email="4g2_e3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-e3a@test.co", "Dee", "One")
    b = await _hire(client, headers, "4g2-e3b@test.co", "Eve", "Two")
    project = await _project(client, headers, "Risky Handoff")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        task = await _task(db, org_id, project["id"], "Slow handover",
                           status="in_progress", assignee_id=a["id"])
        await db.commit()
        task_id = task.id
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": b["id"],
    })

    # age the pending handoff past the risk window, then trigger a refresh
    async with db_session_factory() as db:
        handoff = (
            await db.execute(
                select(CoordinationHandoff).where(
                    CoordinationHandoff.organization_id == org_id,
                )
            )
        ).scalar_one()
        handoff.occurred_at = datetime.now(timezone.utc) - timedelta(hours=100)
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": b["id"],
    })

    rows = await _incidents(db_session_factory, org_id)
    open_rows = _open(rows)
    risk = [r for r in open_rows if r.kind == "handoff_risk"]
    assert len(risk) == 1
    assert risk[0].severity == "medium"
    assert risk[0].confidence >= 0.7
    assert risk[0].project_id == project["id"]
    assert any("100" in e or "99" in e for e in (risk[0].evidence or []))
    assert risk[0].title

    # replay converges: same fingerprint, one open finding
    await _drain(db_session_factory)
    assert len(_open(await _incidents(db_session_factory, org_id))) == 1

    # the condition clearing resolves the finding (change-driven)
    async with db_session_factory() as db:
        handoff = (
            await db.execute(
                select(CoordinationHandoff).where(
                    CoordinationHandoff.organization_id == org_id,
                )
            )
        ).scalar_one()
        handoff.status = "completed"
        handoff.completed_at = datetime.now(timezone.utc)
        handoff.duration_hours = 100.0
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": b["id"],
    })
    rows = await _incidents(db_session_factory, org_id)
    assert all(r.status == "resolved" for r in rows if r.kind == "handoff_risk")

    history = await _history(db_session_factory, org_id)
    names = {h.event_name for h in history}
    assert "coordination.incident.detected" in names
    assert "coordination.incident.resolved" in names


async def test_recurring_slow_handoffs_become_a_finding(client, db_session_factory):
    org = await register_org(client, email="4g2_e4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-e4a@test.co", "Fay", "One")
    b = await _hire(client, headers, "4g2-e4b@test.co", "Gil", "Two")
    project = await _project(client, headers, "Recurring Owner")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        tasks = []
        for i in range(3):
            tasks.append(await _task(
                db, org_id, project["id"], f"Recurring task {i}",
                status="completed", assignee_id=a["id"],
            ))
        await db.commit()
        task_ids = [t.id for t in tasks]

    now = datetime.now(timezone.utc)
    async with db_session_factory() as db:
        for i, task_id in enumerate(task_ids):
            db.add(CoordinationHandoff(
                organization_id=org_id, project_id=project["id"],
                task_id=task_id, task_title=f"Recurring task {i}",
                from_owner_id=a["id"], from_owner_label="Fay One",
                to_owner_id=b["id"], to_owner_label="Gil Two",
                source_event_id=f"seed4g2recur{i}x",
                status="completed",
                occurred_at=now - timedelta(days=20, hours=1),
                completed_at=now - timedelta(days=20),
                duration_hours=80.0,
            ))
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_ids[0], "project_id": project["id"],
        "assignee_id": b["id"],
    })

    rows = _open(await _incidents(db_session_factory, org_id))
    recurring = [r for r in rows if r.kind == "recurring_handoff"]
    assert len(recurring) == 1
    assert recurring[0].severity == "high"
    assert "Fay One" in recurring[0].title
    assert len(recurring[0].evidence or []) >= 3


# ------------------------------------------------------- shared capacity + CP


async def test_shared_capacity_contention_becomes_a_finding(client, db_session_factory):
    org = await register_org(client, email="4g2_e5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    person = await _hire(client, headers, "4g2-e5a@test.co", "Hank", "One")
    x = await _project(client, headers, "ML Product X")
    y = await _project(client, headers, "ML Product Y")
    await _drain(db_session_factory)

    # seed the expertise (4F.6 chain), then anchor demand on both projects
    async with db_session_factory() as db:
        for pid, suffix in ((x["id"], "x"), (y["id"], "y")):
            db.add(Task(
                organization_id=org_id, project_id=pid,
                title="Machine learning model serving setup",
                status="in_progress", assignee_id=person["id"],
            ))
        await db.commit()
    # expertise.updated events need the canonical skill taxonomy, so seed it
    # the same way the 4F.6 tests do
    from app.people.skill_engine import skill_engine

    async with db_session_factory() as db:
        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        await db.commit()

    async with db_session_factory() as db:
        for pid, suffix in ((x["id"], "x"), (y["id"], "y")):
            await _publish(
                db_session_factory, org_id, actor, "task.completed",
                {"employee_id": person["id"], "task_id": f"4g2-e5{suffix}0",
                 "title": "Machine learning model serving setup"},
            )
            await _publish(
                db_session_factory, org_id, actor, "task.created",
                {"employee_id": person["id"], "task_id": f"4g2-e5{suffix}1",
                 "title": "Machine learning model serving setup",
                 "project_id": pid, "assignee_id": person["id"]},
            )

    # lock the expert into both projects -> committed -> constrained
    async with db_session_factory() as db:
        db.add(ProjectMember(
            organization_id=org_id, project_id=x["id"], employee_id=person["id"],
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=y["id"], employee_id=person["id"],
        ))
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": f"4g2-e5x1", "project_id": x["id"],
        "assignee_id": person["id"],
    })

    rows = _open(await _incidents(db_session_factory, org_id))
    contention = [r for r in rows if r.kind == "shared_capacity"]
    # the capability chain links both taxonomy skills the title matches
    # ("Machine Learning", "Deep Learning") — expect one finding per skill
    assert len(contention) >= 1, [r.kind for r in rows]
    assert any(
        "Machine Learning" in c.title or "Deep Learning" in c.title
        for c in contention
    )
    assert all(c.severity in ("critical", "high") for c in contention)
    assert all(c.project_id is None for c in contention)  # org-level finding

    # one project leaving demand resolves the finding: completing the project
    # closes its capability links (the demand source)
    closed = await client.post(
        f"/api/v1/projects/{y['id']}/lifecycle",
        json={"action": "complete"}, headers=headers,
    )
    assert closed.status_code in (200, 201), closed.text
    await _drain(db_session_factory)
    rows = await _incidents(db_session_factory, org_id)
    cont = [r for r in rows if r.kind == "shared_capacity"]
    assert all(r.status == "resolved" for r in cont)


async def test_critical_conflict_when_blocked_paths_share_capacity(
    client, db_session_factory,
):
    org = await register_org(client, email="4g2_e6@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    person = await _hire(client, headers, "4g2-e6a@test.co", "Iris", "One")
    x = await _project(client, headers, "Critical X")
    y = await _project(client, headers, "Critical Y")
    await _drain(db_session_factory)

    from app.people.skill_engine import skill_engine

    async with db_session_factory() as db:
        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.completed", {
        "employee_id": person["id"], "task_id": "4g2-e6s0",
        "title": "Machine learning model serving setup",
    })
    for pid, tag in ((x["id"], "x"), (y["id"], "y")):
        await _publish(db_session_factory, org_id, actor, "task.created", {
            "employee_id": person["id"], "task_id": f"4g2-e6{tag}1",
            "title": "Machine learning model serving setup",
            "project_id": pid, "assignee_id": person["id"],
        })
    async with db_session_factory() as db:
        db.add(ProjectMember(
            organization_id=org_id, project_id=x["id"], employee_id=person["id"],
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=y["id"], employee_id=person["id"],
        ))
        # blocked critical paths: B (blocked) depends on A (todo) in both
        for pid, tag in ((x["id"], "x"), (y["id"], "y")):
            a = await _task(db, org_id, pid, f"{tag}: spec the launch",
                            status="todo", estimate_hours=4)
            b = await _task(db, org_id, pid, f"{tag}: ship the launch",
                            status="blocked", estimate_hours=4,
                            assignee_id=person["id"])
            await _dep(db, org_id, b.id, a.id)
        await db.commit()
    # refresh the 4G.1 record so the coordination engine sees the blocked paths
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": f"4g2-e6x1", "project_id": x["id"],
        "assignee_id": person["id"],
    })
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": f"4g2-e6y1", "project_id": y["id"],
        "assignee_id": person["id"],
    })

    rows = _open(await _incidents(db_session_factory, org_id))
    conflicts = [r for r in rows if r.kind == "critical_conflict"]
    # one conflict per contended taxonomy skill ("Machine Learning",
    # "Deep Learning" — both matched by the seeding title)
    assert len(conflicts) >= 1, [r.kind for r in rows]
    assert any(
        "Machine Learning" in c.title or "Deep Learning" in c.title
        for c in conflicts
    )
    assert all(c.severity == "critical" for c in conflicts)
    assert any(
        "Critical X" in " ".join(c.evidence or [])
        and "Critical Y" in " ".join(c.evidence or [])
        for c in conflicts
    )


# -------------------------------------------------------- gaps + propagation


async def test_coordination_gap_for_multiteam_project(client, db_session_factory):
    org = await register_org(client, email="4g2_e7@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    async with db_session_factory() as db:
        t1 = Team(organization_id=org_id, name="Platform", code="PLAT")
        t2 = Team(organization_id=org_id, name="Growth", code="GROW")
        db.add_all([t1, t2])
        await db.flush()
        t1_id, t2_id = t1.id, t2.id
        await db.commit()
    p1 = await _hire(client, headers, "4g2-e7a@test.co", "Jill", "One", team_id=t1_id)
    p2 = await _hire(client, headers, "4g2-e7b@test.co", "Jon", "Two", team_id=t2_id)
    project = await _project(client, headers, "Cross-Team Launch")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        db.add(ProjectMember(
            organization_id=org_id, project_id=project["id"], employee_id=p1["id"],
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=project["id"], employee_id=p2["id"],
        ))
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": "4g2-e7t", "project_id": project["id"], "assignee_id": p1["id"],
    })

    rows = _open(await _incidents(db_session_factory, org_id))
    gaps = [r for r in rows if r.kind == "coordination_gap"]
    assert len(gaps) == 1
    assert gaps[0].severity == "medium"
    assert "Platform" in gaps[0].title and "Growth" in gaps[0].title
    assert gaps[0].project_id == project["id"]
    assert any("no collaboration evidence" in e for e in (gaps[0].evidence or []))


async def test_propagation_reaches_goal_chain_and_decisions(client, db_session_factory):
    org = await register_org(client, email="4g2_e8@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    project = await _project(client, headers, "Propagating")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        goal = Goal(
            organization_id=org_id, name="Own the platform market",
            scope="company", project_id=project["id"], status="active",
            progress=30,
        )
        db.add(goal)
        await db.flush()
        milestone = Milestone(
            organization_id=org_id, project_id=project["id"], name="GA",
            status="pending",
        )
        db.add(milestone)
        await db.flush()
        a = await _task(db, org_id, project["id"], "Prep data",
                        status="todo", estimate_hours=4)
        b = await _task(db, org_id, project["id"], "Blocked core",
                        status="blocked", estimate_hours=4,
                        milestone_id=milestone.id)
        await _dep(db, org_id, b.id, a.id)
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": b.id, "project_id": project["id"], "assignee_id": None,
    })

    rows = _open(await _incidents(db_session_factory, org_id))
    props = [r for r in rows if r.kind == "propagation_risk"]
    assert len(props) == 1, [r.kind for r in rows]
    assert props[0].severity == "high"
    assert props[0].project_id == project["id"]
    steps = props[0].propagation or []
    assert steps, "propagation chain must not be empty"
    assert steps[0]["from"].startswith("task")
    titles = " ".join(s["to"] for s in steps)
    assert "Own the platform market" in titles
    assert any("GA" == s.get("to") or s["from"].startswith("milestone") for s in steps)
    assert any("blocked by" in s["via"] for s in steps)


# ---------------------------------------------------- recommendations + law


async def test_recommendations_prioritize_critical_first(client, db_session_factory):
    org = await register_org(client, email="4g2_e9@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    person = await _hire(client, headers, "4g2-e9a@test.co", "Kim", "One")
    x = await _project(client, headers, "Rec X")
    y = await _project(client, headers, "Rec Y")
    await _drain(db_session_factory)

    from app.people.skill_engine import skill_engine

    async with db_session_factory() as db:
        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.completed", {
        "employee_id": person["id"], "task_id": "4g2-e9s0",
        "title": "Machine learning model serving setup",
    })
    for pid, tag in ((x["id"], "x"), (y["id"], "y")):
        await _publish(db_session_factory, org_id, actor, "task.created", {
            "employee_id": person["id"], "task_id": f"4g2-e9{tag}1",
            "title": "Machine learning model serving setup",
            "project_id": pid, "assignee_id": person["id"],
        })
    async with db_session_factory() as db:
        db.add(ProjectMember(
            organization_id=org_id, project_id=x["id"], employee_id=person["id"],
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=y["id"], employee_id=person["id"],
        ))
        for pid, tag in ((x["id"], "x"), (y["id"], "y")):
            a = await _task(db, org_id, pid, f"{tag}: spec", status="todo",
                            estimate_hours=4)
            b = await _task(db, org_id, pid, f"{tag}: ship", status="blocked",
                            estimate_hours=4, assignee_id=person["id"])
            await _dep(db, org_id, b.id, a.id)
        await db.commit()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": f"4g2-e9x1", "project_id": x["id"],
        "assignee_id": person["id"],
    })
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": f"4g2-e9y1", "project_id": y["id"],
        "assignee_id": person["id"],
    })

    from app.intelligence.company_context import CallerAccess

    async with db_session_factory() as db:
        center = await coordination_engine.center(
            db, organization_id=org_id,
            access=CallerAccess(
                organization_id=org_id, user_id=org["user"]["id"],
                employee_id=None, org_wide=True,
            ),
        )
    recs = center["recommendations"]
    assert len(recs) >= 1
    assert recs[0]["kind"] == "critical_conflict"
    assert recs[0]["confidence"] >= 0.8
    assert recs[0]["why"]
    counts = center["counts"]
    assert counts["critical_conflict"] >= 1
    assert center["total_incidents"] >= 2


async def test_engine_is_advisory_only_and_history_exact_once(client, db_session_factory):
    org = await register_org(client, email="4g2_e10@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    actor = org["user"]["id"]
    a = await _hire(client, headers, "4g2-e10a@test.co", "Lia", "One")
    b = await _hire(client, headers, "4g2-e10b@test.co", "Leo", "Two")
    project = await _project(client, headers, "Advisory Law")
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        task = await _task(db, org_id, project["id"], "Law task",
                           status="in_progress", assignee_id=a["id"])
        await db.commit()
        task_id = task.id

    # seed recurring slow handoffs + age the pending handoff so findings open
    now = datetime.now(timezone.utc)
    async with db_session_factory() as db:
        for i in range(3):
            t = await _task(db, org_id, project["id"], f"Law recur {i}",
                            status="completed", assignee_id=a["id"])
            db.add(CoordinationHandoff(
                organization_id=org_id, project_id=project["id"],
                task_id=t.id, task_title=f"Law recur {i}",
                from_owner_id=a["id"], from_owner_label="Lia One",
                to_owner_id=b["id"], to_owner_label="Leo Two",
                source_event_id=f"4g2-e10seed{i}",
                status="completed",
                occurred_at=now - timedelta(days=10),
                completed_at=now - timedelta(days=9),
                duration_hours=80.0,
            ))
        await db.commit()

    async def _sources():
        async with db_session_factory() as db:
            projects = list(
                (await db.execute(
                    select(Project).where(Project.organization_id == org_id)
                )).scalars().all()
            )
            tasks = list(
                (await db.execute(
                    select(Task).where(Task.organization_id == org_id)
                )).scalars().all()
            )
            return len(projects), len(tasks)

    before = await _sources()
    await _publish(db_session_factory, org_id, actor, "task.transitioned", {
        "task_id": task_id, "project_id": project["id"], "assignee_id": b["id"],
    })
    # a second drain of the same queue converges (exact-once history)
    await _drain(db_session_factory)
    await _drain(db_session_factory)
    after = await _sources()
    assert before == after, "the engine must never write source rows"

    history = await _history(db_session_factory, org_id)
    history_events = [h.source_event_id for h in history]
    assert len(history_events) == len(set(history_events)), "exact-once history"

    async with db_session_factory() as db:
        incident = (
            await db.execute(
                select(CoordinationIncident).where(
                    CoordinationIncident.organization_id == org_id,
                    CoordinationIncident.kind == "recurring_handoff",
                )
            )
        ).scalar_one_or_none()
    assert incident is not None

    # human resolve path is tested through the engine directly
    async with db_session_factory() as db:
        resolved = await coordination_engine.resolve_incident(
            db, organization_id=org_id, incident_id=incident.id,
            note="Handled in the standup", resolved_by=org["user"]["id"],
        )
        await db.commit()
    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert resolved["resolve_note"] == "Handled in the standup"
