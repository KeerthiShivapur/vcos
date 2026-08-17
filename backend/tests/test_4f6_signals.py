"""Slice 4F.6 — advisory signals: concentration, single-person dependency,
capacity gaps. Analysis NEVER changes the organization:

* a large evidence share in one person surfaces a concentration signal,
* exactly one expert who is already committed surfaces single_point,
* demand exceeding free capacity surfaces capability_gap,
* when a finding clears, its open signal auto-resolves,
* acknowledging is the only write surface (employees:manage).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.org_capability_intelligence import CapabilityProjectLink, CapabilitySignal
from app.models.skills_intelligence import CanonicalSkill, Expertise
from app.models.project import ProjectMember
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


async def _hire(client, headers, email, first, last):
    body = {"first_name": first, "last_name": last, "email": email}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"sig-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _skill_id(db, org_id, name):
    from app.people.skill_engine import skill_engine

    await skill_engine.ensure_taxonomy(db, organization_id=org_id)
    row = (
        await db.execute(
            select(CanonicalSkill.id).where(
                CanonicalSkill.organization_id == org_id,
                CanonicalSkill.canonical_name == name,
            )
        )
    ).scalar_one_or_none()
    assert row is not None, f"starter taxonomy must include {name}"
    return row


async def _set_cell(db, org_id, person_id, skill_id, score, evidence,
                    lifecycle="established", successful=0, failed=0):
    cell = (
        await db.execute(
            select(Expertise).where(
                Expertise.organization_id == org_id,
                Expertise.person_id == person_id,
                Expertise.skill_id == skill_id,
            )
        )
    ).scalar_one_or_none()
    if cell is None:
        cell = Expertise(
            organization_id=org_id, person_id=person_id, skill_id=skill_id,
        )
        db.add(cell)
    cell.score = score
    cell.evidence_count = evidence
    cell.lifecycle = lifecycle
    cell.successful_count = successful
    cell.failed_count = failed
    cell.last_observed = datetime.now(timezone.utc)
    cell.frequency_90d = evidence
    return cell


async def _refresh(db_session_factory, org_id, actor_id, skill_id):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="skill.updated", organization_id=org_id, actor_id=actor_id,
            payload={"skill_id": skill_id}, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _signals(client, headers):
    res = await client.get(f"{BRAIN}/capabilities/signals", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _open_signals_by_kind(client, headers):
    body = await _signals(client, headers)
    by_kind: dict[str, list[dict]] = {}
    for s in body["signals"]:
        if s["status"] in ("open", "acknowledged"):
            by_kind.setdefault(s["kind"], []).append(s)
    return by_kind


# ---------------------------------------------------------------- signals


async def test_concentration_signal_when_evidence_is_lopsided(client, db_session_factory):
    org = await register_org(client, email="4f6_sig1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    star = await _hire(client, headers, "4f6-s1a@test.co", "Hero", "Expert")
    peer = await _hire(client, headers, "4f6-s1b@test.co", "Side", "Kick")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "PostgreSQL")
        # 20 of 22 evidence items belong to one person -> 91% concentration
        await _set_cell(db, org_id, star["id"], skill_id, 90.0, 20,
                        lifecycle="strong", successful=20)
        await _set_cell(db, org_id, peer["id"], skill_id, 50.0, 2,
                        lifecycle="established")
        await db.commit()
    await _refresh(db_session_factory, org_id, org["user"]["id"], skill_id)

    detail = (
        await client.get(f"{BRAIN}/capabilities/{skill_id}", headers=headers)
    ).json()
    assert detail["concentration"]["share"] >= 0.9
    assert detail["concentration"]["second_share"] <= 0.1

    by_kind = await _open_signals_by_kind(client, headers)
    conc = by_kind.get("concentration", [])
    assert len(conc) == 1, by_kind
    assert conc[0]["severity"] == "critical"
    assert "one person" in conc[0]["detail"]


async def test_single_point_dependency_and_autoresolve(client, db_session_factory):
    org = await register_org(client, email="4f6_sig2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    only = await _hire(client, headers, "4f6-s2@test.co", "Only", "One")
    project = await _project(client, headers, "Critical Path")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Kubernetes")
        await _set_cell(db, org_id, only["id"], skill_id, 85.0, 9,
                        lifecycle="strong", successful=9)
        db.add(CapabilityProjectLink(
            organization_id=org_id, project_id=project["id"],
            project_name="Critical Path", skill_id=skill_id,
            skill_name="Kubernetes", source_event_id="4f6-sig-link",
            status="active",
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=project["id"], employee_id=only["id"],
        ))
        await db.commit()
    await _refresh(db_session_factory, org_id, org["user"]["id"], skill_id)

    by_kind = await _open_signals_by_kind(client, headers)
    sp = by_kind.get("single_point_dependency", [])
    assert len(sp) == 1, by_kind
    assert sp[0]["severity"] == "critical"

    # the project completes: the expert is no longer committed -> the
    # single-point finding clears and its signal auto-resolves
    async with db_session_factory() as db:
        from app.events.event_bus import event_bus

        await event_bus.publish(
            db, name="project.completed", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"project_id": project["id"], "status": "completed"},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    by_kind = await _open_signals_by_kind(client, headers)
    assert "single_point_dependency" not in by_kind, by_kind
    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(CapabilitySignal).where(
                        CapabilitySignal.organization_id == org_id,
                        CapabilitySignal.kind == "single_point_dependency",
                    )
                )
            ).scalars().all()
        )
    assert len(rows) == 1 and rows[0].status == "resolved"


async def test_acknowledge_is_the_only_write_surface(client, db_session_factory):
    org = await register_org(client, email="4f6_sig3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    hero = await _hire(client, headers, "4f6-s3a@test.co", "Prime", "Expert")
    peer = await _hire(client, headers, "4f6-s3b@test.co", "Second", "Expert")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Machine Learning")
        await _set_cell(db, org_id, hero["id"], skill_id, 92.0, 18,
                        lifecycle="strong", successful=18)
        await _set_cell(db, org_id, peer["id"], skill_id, 55.0, 2)
        await db.commit()
    await _refresh(db_session_factory, org_id, org["user"]["id"], skill_id)

    by_kind = await _open_signals_by_kind(client, headers)
    signal = by_kind["concentration"][0]
    assert signal["status"] == "open"

    res = await client.patch(
        f"{BRAIN}/capabilities/signals/{signal['signal_id']}/acknowledge",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "acknowledged"

    missing = await client.patch(
        f"{BRAIN}/capabilities/signals/not-a-signal/acknowledge", headers=headers,
    )
    assert missing.status_code == 404, missing.text

    # acknowledging changed ONLY the signal: expertise/teams untouched
    detail = (
        await client.get(f"{BRAIN}/capabilities/{skill_id}", headers=headers)
    ).json()
    assert detail["expert_count"] == 2


async def test_capability_gap_when_demand_exceeds_capacity(client, db_session_factory):
    org = await register_org(client, email="4f6_sig4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    expert = await _hire(client, headers, "4f6-s4@test.co", "Busy", "Bee")
    p1 = await _project(client, headers, "Demand One")
    p2 = await _project(client, headers, "Demand Two")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Distributed Systems")
        await _set_cell(db, org_id, expert["id"], skill_id, 80.0, 8,
                        lifecycle="strong", successful=8)
        for pid, pname in ((p1["id"], "Demand One"), (p2["id"], "Demand Two")):
            db.add(CapabilityProjectLink(
                organization_id=org_id, project_id=pid, project_name=pname,
                skill_id=skill_id, skill_name="Distributed Systems",
                source_event_id=f"4f6-gap-{pid}", status="active",
            ))
            db.add(ProjectMember(
                organization_id=org_id, project_id=pid, employee_id=expert["id"],
            ))
        await db.commit()
    await _refresh(db_session_factory, org_id, org["user"]["id"], skill_id)

    detail = (
        await client.get(f"{BRAIN}/capabilities/{skill_id}", headers=headers)
    ).json()
    assert detail["capacity"]["committed"] >= 1
    assert detail["capacity"]["available"] == 0
    assert detail["demand"]["count"] >= 2

    by_kind = await _open_signals_by_kind(client, headers)
    assert len(by_kind.get("capacity_constraint", [])) == 1, by_kind
    assert len(by_kind.get("capability_gap", [])) == 1, by_kind