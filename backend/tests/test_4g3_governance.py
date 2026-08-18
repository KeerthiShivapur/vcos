"""Slice 4G.3 — governance: strategy surfaces are org-wide, writes are
projects:manage, the ledgers are exact-once, and every advisory surface is
read-only on evidence tables.

* scoped callers 404 on the org-wide strategy surfaces (portfolio / focus /
  gaps / conflicts) — the same idiom as 4G.1/4G.2/4F.6/4F.7,
* strategy writes require projects:manage (a delegated brain reader gets 403),
* exact-once is enforced by unique constraints on every strategic ledger
  (uq_sl_live_link / uq_sl_exact_once / uq_sh_exact_once / uq_so_exact_once /
  uq_ss_exact_once) — a duplicate snapshot row is rejected by the database,
* every GET surface is read-only: portfolio / detail / focus / gaps /
  conflicts / impact / what-if / alternatives never touch the evidence
  tables,
* the ten strategy.* events are registered handlers and catalogued.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.execution_strategy import (
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicHistory,
    StrategicLink,
    StrategicOutcome,
    StrategicSnapshot,
)
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
STRATEGY = f"{BRAIN}/execution/strategy"

STRATEGY_EVENT_NAMES = (
    "strategy.goal.created",
    "strategy.goal.updated",
    "strategy.goal.priority.changed",
    "strategy.objective.created",
    "strategy.objective.updated",
    "strategy.initiative.created",
    "strategy.initiative.updated",
    "strategy.initiative.linked",
    "strategy.initiative.unlinked",
    "strategy.outcome.recorded",
)

EXACT_ONCE_CONSTRAINTS = {
    StrategicLink: {"uq_sl_live_link", "uq_sl_exact_once"},
    StrategicHistory: {"uq_sh_exact_once"},
    StrategicOutcome: {"uq_so_exact_once"},
    StrategicSnapshot: {"uq_ss_exact_once"},
}


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


async def _project(db_session_factory, org_id, name, status="active"):
    from app.models.project import Project

    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"g3g-{name.lower().replace(' ', '-')[:16]}", status=status,
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return {"id": pid}


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


async def _scope(client, headers, scope_type, entity_id, name):
    res = await client.post(
        "/api/v1/governance/scopes",
        json={"name": name, "scope_type": scope_type, "entity_id": entity_id},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


async def test_scoped_caller_404s_on_org_wide_surfaces(client, db_session_factory):
    org = await register_org(client, email="4g3_g1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    project = await _project(db_session_factory, org_id, "Gov One")
    scope = await _scope(client, headers, "project", project["id"], "Gov scope")
    scoped = await invite_scoped_reader(client, headers, scope["id"], "4g3-g1s@test.co")

    for path in ("portfolio", "focus", "gaps", "conflicts"):
        res = await client.get(f"{STRATEGY}/{path}", headers=scoped)
        assert res.status_code == 404, f"{path}: {res.status_code}"
        res = await client.get(f"{STRATEGY}/{path}", headers=headers)
        assert res.status_code == 200, f"{path}: {res.status_code}"


async def test_strategy_writes_require_projects_manage(client, db_session_factory):
    org = await register_org(client, email="4g3_g2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    project = await _project(db_session_factory, org_id, "Gov Two")
    scope = await _scope(client, headers, "project", project["id"], "Gov scope 2")
    scoped = await invite_scoped_reader(client, headers, scope["id"], "4g3-g2s@test.co")

    res = await client.post(
        f"{STRATEGY}/goals",
        json={"title": "Sneaky Goal", "kind": "revenue", "priority": 3},
        headers=scoped,
    )
    assert res.status_code == 403, f"scoped reader must not write strategy: {res.status_code}"
    res = await client.post(
        f"{STRATEGY}/goals",
        json={"title": "Owned Goal", "kind": "revenue", "priority": 3},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text


async def test_exact_once_constraints_guard_the_ledgers(client, db_session_factory):
    org = await register_org(client, email="4g3_g3@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    for model, names in EXACT_ONCE_CONSTRAINTS.items():
        present = {c.name for c in model.__table__.constraints if c.name}
        assert names <= present, (
            f"{model.__tablename__} missing exact-once constraints "
            f"{sorted(names - present)}"
        )

    created = await client.post(
        f"{STRATEGY}/goals",
        json={"title": "Ledger Goal", "kind": "revenue", "priority": 3},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    goal_id = created.json()["goal_id"]

    def snapshot():
        return StrategicSnapshot(
            organization_id=org_id, goal_id=goal_id, source_event_id="dup-1",
            event_name="strategy.goal.created", coverage=0, health="critical",
            payload_json={}, occurred_at=datetime.now(timezone.utc),
        )

    async with db_session_factory() as db:
        db.add(snapshot())
        await db.commit()
    async with db_session_factory() as db:
        db.add(snapshot())
        try:
            await db.flush()
            raise AssertionError("duplicate snapshot must violate uq_ss_exact_once")
        except IntegrityError:
            await db.rollback()


async def test_surfaces_are_read_only_on_evidence_tables(client, db_session_factory):
    org = await register_org(client, email="4g3_g4@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    created = await client.post(
        f"{STRATEGY}/goals",
        json={"title": "Read Only Goal", "kind": "revenue", "priority": 3},
        headers=headers,
    )
    goal_id = created.json()["goal_id"]
    objective = await client.post(
        f"{STRATEGY}/objectives",
        json={"goal_id": goal_id, "title": "Read Only Objective",
              "required_capabilities": ["localization"]},
        headers=headers,
    )
    objective_id = objective.json()["objective_id"]
    initiative = await client.post(
        f"{STRATEGY}/initiatives",
        json={"objective_id": objective_id, "title": "Read Only Initiative",
              "required_capabilities": ["localization"]},
        headers=headers,
    )
    initiative_id = initiative.json()["initiative_id"]
    project = await _project(db_session_factory, org_id, "Read Only Work")
    await _member(db_session_factory, org_id, project["id"], "emp-g4")
    async with db_session_factory() as db:
        from app.models.execution_intelligence import ProjectExecutionState
        from app.models.org_capability_intelligence import OrgCapability

        db.add(ProjectExecutionState(
            organization_id=org_id, project_id=project["id"], health_score=85,
            health_status="healthy", source_event_id="g3g-seed",
        ))
        db.add(OrgCapability(
            organization_id=org_id, skill_id="sk-localization",
            canonical_name="localization", capacity_potential=10,
            capacity_committed=2, capacity_reserved=0,
            capacity_available=8, capacity_state="available",
            expert_count=3, evidence_count=3, lifecycle="established",
        ))
        await db.commit()
    link = await client.post(
        f"{STRATEGY}/initiatives/{initiative_id}/link",
        json={"project_id": project["id"]}, headers=headers,
    )
    assert link.status_code in (200, 201), link.text
    await _drain(db_session_factory)

    from app.models.execution_intelligence import ProjectExecutionState
    from app.models.org_capability_intelligence import OrgCapability
    from app.models.project import Project, ProjectMember

    evidence = [
        CompanyGoal, CompanyObjective, CompanyInitiative, Project,
        ProjectMember, ProjectExecutionState, OrgCapability,
    ]
    async with db_session_factory() as db:
        before = {
            m.__tablename__: len(list(
                (await db.execute(select(m).where(m.organization_id == org_id)))
                .scalars().all()
            ))
            for m in evidence
        }

    await client.get(f"{STRATEGY}/portfolio", headers=headers)
    await client.get(f"{STRATEGY}/goals/{goal_id}", headers=headers)
    await client.get(f"{STRATEGY}/focus", headers=headers)
    await client.get(f"{STRATEGY}/gaps", headers=headers)
    await client.get(f"{STRATEGY}/conflicts", headers=headers)
    await client.get(
        f"{STRATEGY}/impact", params={"project_id": project["id"], "delay_days": 14},
        headers=headers,
    )
    await client.get(
        f"{STRATEGY}/what-if", params={"goal_id": goal_id, "priority": 1},
        headers=headers,
    )
    await client.get(
        f"{STRATEGY}/alternatives", params={"project_id": project["id"]},
        headers=headers,
    )
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        after = {
            m.__tablename__: len(list(
                (await db.execute(select(m).where(m.organization_id == org_id)))
                .scalars().all()
            ))
            for m in evidence
        }
    assert after == before, (
        f"advisory surfaces mutated evidence: { {k: (v, after[k]) for k, v in before.items() if v != after[k]} }"
    )


async def test_strategy_events_registered_and_catalogued():
    from app.events.event_models import EVENT_CATALOG
    from app.intelligence.event_processor import ensure_handlers_imported
    from app.intelligence.event_processor import registered_handlers

    ensure_handlers_imported()
    assert set(STRATEGY_EVENT_NAMES) <= set(EVENT_CATALOG)
    assert set(STRATEGY_EVENT_NAMES) <= set(registered_handlers())
