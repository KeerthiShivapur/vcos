"""Slice 4F.6 — capacity & demand model.

Capacity is Potential minus Committed minus Reserved, derived from bounded
indexed evidence — never fake hour math. Under test:

* task.* events inside a project create project<->capability links
  (exact-once keyed on the source event),
* committed = experts engaged on active linked projects (project members),
* reserved = experts with open task load,
* available = potential - busy, states unknown|available|stretched|constrained,
* demand is current active projects only (none|low|moderate|high),
* demand with no experts surfaces capacity_without_expertise (advisory).
"""

from sqlalchemy import select

from app.models.org_capability_intelligence import CapabilityProjectLink
from app.models.task import Task as TaskState
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


async def _hire(client, headers, email, first, last, team_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _publish_task(client, db_session_factory, org_id, actor_id, employee_id,
                        task_id, title, project_id=None, event_name="task.completed",
                        status=None):
    from app.events.event_bus import event_bus

    payload = {"employee_id": employee_id, "task_id": task_id, "title": title}
    if project_id:
        payload["project_id"] = project_id
        payload["assignee_id"] = employee_id
    if status:
        payload["status"] = status
    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=event_name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _project(client, headers, name, status="active"):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"p6-{name.lower()[:8]}", "status": status},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _overview(client, headers):
    res = await client.get(f"{BRAIN}/capabilities/overview", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _capability(client, headers, name):
    view = await _overview(client, headers)
    return next(c for c in view["capabilities"] if c["name"] == name)


# --------------------------------------------------------------- capacity


async def test_project_links_are_created_exact_once(client, db_session_factory):
    org = await register_org(client, email="4f6_cap1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-ca@test.co", "Ken", "Thompson")
    project = await _project(client, headers, "Kube Ops")

    # the expert must exist BEFORE the project link: task.completed is what
    # chains expertise.updated -> the capability record is created
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-c1seed", title="Kubernetes cluster operations",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-c1", title="Kubernetes cluster operations",
        project_id=project["id"], event_name="task.created",
    )
    # a second drain (same pending queue) converges: exact-once, no duplicate
    await _drain(db_session_factory)
    async with db_session_factory() as db:
        links = list(
            (
                await db.execute(
                    select(CapabilityProjectLink).where(
                        CapabilityProjectLink.organization_id == org_id,
                        CapabilityProjectLink.project_id == project["id"],
                    )
                )
            ).scalars().all()
        )
    assert len(links) >= 1
    kube_links = [l for l in links if l.skill_name == "Kubernetes"]
    assert len(kube_links) == 1, f"exact-once violated: {len(kube_links)}"

    capability = await _capability(client, headers, "Kubernetes")
    assert capability["demand_count"] >= 1
    assert capability["demand_state"] in ("low", "moderate", "high")

    detail = (
        await client.get(
            f"{BRAIN}/capabilities/{capability['skill_id']}", headers=headers,
        )
    ).json()
    assert any(p["project_name"] == "Kube Ops" for p in detail["projects"])


async def test_capacity_committed_reserved_available(client, db_session_factory):
    org = await register_org(client, email="4f6_cap2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f6-c2a@test.co", "Dana", "Scott")
    grace = await _hire(client, headers, "4f6-c2b@test.co", "Ravi", "Gupta")
    project = await _project(client, headers, "ML Platform")

    # both experts first (task.completed chains expertise.updated -> the
    # capability record exists BEFORE the project links)
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], ada["id"],
        task_id="4f6-c2a0", title="Machine learning training pipelines",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], grace["id"],
        task_id="4f6-c2b0", title="Machine learning model benchmarking and tuning",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], ada["id"],
        task_id="4f6-c2a1", title="Machine learning training pipelines",
        project_id=project["id"], event_name="task.created",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], grace["id"],
        task_id="4f6-c2b1", title="Machine learning model benchmarking and tuning",
        project_id=project["id"], event_name="task.created",
    )

    async with db_session_factory() as db:
        from app.models.project import ProjectMember

        # Dana is a project member of the active project -> committed
        db.add(ProjectMember(
            organization_id=org_id, project_id=project["id"], employee_id=ada["id"],
        ))
        # Ravi has an open task assigned (not in a project) -> reserved
        db.add(TaskState(
            organization_id=org_id, title="ML tuning continued",
            status="in_progress", assignee_id=grace["id"],
        ))
        await db.commit()

    # re-trigger the capability refresh so the membership/task load lands
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], ada["id"],
        task_id="4f6-c2a2", title="Machine learning data validation",
        project_id=project["id"], event_name="task.transitioned",
    )

    capability = await _capability(client, headers, "Machine Learning")
    assert capability["capacity_potential"] >= 2
    assert capability["capacity_committed"] >= 1
    assert capability["capacity_reserved"] >= 1
    assert capability["capacity_available"] == (
        capability["capacity_potential"] - capability["capacity_committed"]
        - capability["capacity_reserved"]
    )

    # every expert engaged -> constrained (no free experts)
    async with db_session_factory() as db:
        from app.models.project import ProjectMember

        db.add(ProjectMember(
            organization_id=org_id, project_id=project["id"], employee_id=grace["id"],
        ))
        await db.commit()
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], grace["id"],
        task_id="4f6-c2b2", title="Machine learning serving and monitoring setup",
        project_id=project["id"], event_name="task.completed",
    )
    capability = await _capability(client, headers, "Machine Learning")
    assert capability["capacity_available"] == 0
    assert capability["capacity_state"] in ("stretched", "constrained")
    assert capability["demand_count"] >= 1


async def test_project_completion_closes_demand(client, db_session_factory):
    org = await register_org(client, email="4f6_cap3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-c3@test.co", "Linus", "Torvalds")
    project = await _project(client, headers, "Kernel Work")

    # expertise first, then a project-anchored demand event
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-c3seed", title="Python kernel automation scripts",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f6-c3a", title="Python kernel automation scripts",
        project_id=project["id"], event_name="task.created",
    )
    capability = await _capability(client, headers, "Python")
    assert capability["demand_count"] == 1

    async with db_session_factory() as db:
        from app.events.event_bus import event_bus

        await event_bus.publish(
            db, name="project.completed", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"project_id": project["id"], "project_name": "Kernel Work",
                     "status": "completed"},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    capability = await _capability(client, headers, "Python")
    assert capability["demand_count"] == 0
    assert capability["demand_state"] == "none"


async def test_demand_without_expertise_is_a_signal(client, db_session_factory):
    org = await register_org(client, email="4f6_cap4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _project(client, headers, "DX Initiative")

    # deterministic seed: an active demand link for a capability with no
    # evidence-backed experts (e.g. from an event the person's skills could
    # not match). Refresh the capability -> capacity_without_expertise.
    async with db_session_factory() as db:
        from app.models.org_capability_intelligence import CapabilityProjectLink
        from app.models.skills_intelligence import CanonicalSkill
        from app.people.skill_engine import skill_engine

        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        skill = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == org_id,
                    CanonicalSkill.canonical_name == "PostgreSQL",
                )
            )
        ).scalar_one_or_none()
        assert skill is not None, "starter taxonomy must include PostgreSQL"
        db.add(CapabilityProjectLink(
            organization_id=org_id, project_id=project["id"],
            project_name="DX Initiative", skill_id=skill.id,
            skill_name="PostgreSQL",
            source_event_id="4f6-seed-link", status="active",
        ))
        await db.commit()

    async with db_session_factory() as db:
        from app.events.event_bus import event_bus

        await event_bus.publish(
            db, name="skill.updated", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"skill_id": skill.id}, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    capability = await _capability(client, headers, "PostgreSQL")
    assert capability["expert_count"] == 0
    assert capability["demand_count"] == 1

    signals = (
        await client.get(f"{BRAIN}/capabilities/signals", headers=headers)
    ).json()
    assert signals["total"] >= 1
    match = next(
        (s for s in signals["signals"] if s["kind"] == "capacity_without_expertise"),
        None,
    )
    assert match is not None, signals["signals"]

    # analysis changed NOTHING in the organization: no tasks were created and
    # no ownership row was authored by the capability pipeline — the only
    # ownership row is the platform's DECLARED project ownership (published
    # by the project API itself, before any capability work ran)
    async with db_session_factory() as db:
        from app.models.ownership_intelligence import OwnershipRelationship
        from app.models.project import Project

        tasks = (
            await db.execute(
                select(TaskState.id).where(TaskState.organization_id == org_id)
            )
        ).scalars().all()
        owners = list(
            (
                await db.execute(
                    select(OwnershipRelationship).where(
                        OwnershipRelationship.organization_id == org_id,
                    )
                )
            ).scalars().all()
        )
        ownership_objects = (
            await db.execute(
                select(OwnershipRelationship.object_type).where(
                    OwnershipRelationship.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert len(tasks) == 0, "analysis must never create tasks"
    assert tuple(ownership_objects) == ("project",), ownership_objects
    assert all(o.source == "declared" for o in owners), [o.source for o in owners]