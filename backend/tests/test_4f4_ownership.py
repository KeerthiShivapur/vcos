"""Slice 4F.4 — Ownership & Responsibility Intelligence.

The fourth People Intelligence slice answers "who is actually responsible for
this" as a canonical, temporal, evidence-backed governed record. Deterministic
law under test:

* ownership is a relationship window (owner, object, type, scope, start/end,
  source, evidence, confidence, backup) · history is never destroyed — a
  transfer closes the old window and opens a new one,
* responsibility types are distinct and stack (primary/operational/technical/
  ...) while exactly one primary exists per object at any moment,
* as_of reconstructs "who owned X when the incident happened",
* declared-vs-observed mismatch is ONLY surfaced (signal, "was NOT changed") —
  analysis NEVER auto-fixes ownership,
* responsibilities left by an inactive owner become gap signals with read-only
  candidates — never auto-assigned,
* an owner holding many active responsibilities without backups is flagged as
  a single-person dependency risk,
* change-driven reconcile is exact-once (replays produce no duplicates),
* continuity shows backup and governed 4C delegations (read-only),
* analysis is batch-bounded,
* the Company Brain routes /brain/ownership/* surfaces.
"""

import datetime

from sqlalchemy import select

from app.models.ownership_intelligence import (
    OwnershipChange,
    OwnershipRelationship,
)
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
UTC = datetime.timezone.utc


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


async def _project(client, headers, name, owner_id=None, code=None):
    payload = {"name": name}
    if code:
        payload["code"] = code
    if owner_id:
        payload["owner_id"] = owner_id
    created = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _publish(db_session_factory, org_id, name, actor_id, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _assign(client, headers, project_id, owner_id, responsibility_type="primary", **extra):
    res = await client.post(
        f"{BRAIN}/ownership/assign",
        json={"object_type": "project", "object_id": project_id,
              "responsibility_type": responsibility_type,
              "owner_id": owner_id, **extra},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _object(client, headers, project_id):
    res = await client.get(f"{BRAIN}/ownership/objects/project/{project_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------- core record


async def test_assignment_creates_canonical_window_with_types_stacked(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_assign@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    alma = await _hire(client, headers, "4f4-a@test.co", "Alma", "Nova")
    project = await _project(client, headers, "Payments Platform", owner_id=alma["id"])
    await _drain(db_session_factory)

    # the project.created handler reconciled the declared owner.
    current = await _object(client, headers, project["id"])
    assert current["primary"] is not None
    assert current["primary"]["owner_id"] == alma["id"]
    assert current["primary"]["source"] == "declared"
    assert current["primary"]["confidence"] == 1.0
    assert current["primary"]["object_name"] == "Payments Platform"

    # a technical responsibility stacks on top of the primary.
    await _assign(client, headers, project["id"], alma["id"], responsibility_type="technical")
    current = await _object(client, headers, project["id"])
    types = {r["responsibility_type"] for r in current["relationships"]}
    assert types == {"primary", "technical"}
    assert current["primary"]["responsibility_type"] == "primary"

    row = (
        await db_session.execute(
            select(OwnershipRelationship).where(
                OwnershipRelationship.object_id == project["id"],
                OwnershipRelationship.responsibility_type == "primary",
            )
        )
    ).scalars().one()
    assert row.status == "active"
    assert row.declared_start is not None


async def test_transfer_preserves_history_and_as_of_reconstructs(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_transfer@test.co")
    headers = org["headers"]
    alice = await _hire(client, headers, "4f4-t1@test.co", "Alice", "One")
    bob = await _hire(client, headers, "4f4-t2@test.co", "Bob", "Two")
    project = await _project(client, headers, "Checkout", owner_id=alice["id"])
    await _drain(db_session_factory)

    res = await client.post(
        f"{BRAIN}/ownership/transfer",
        json={"object_type": "project", "object_id": project["id"],
              "to_owner_id": bob["id"]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["transferred"] is True

    current = await _object(client, headers, project["id"])
    assert current["primary"]["owner_id"] == bob["id"]

    history = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/history",
        headers=headers)).json()
    assert any(e.get("action") == "transferred" for e in history["events"])

    # who owned it at 2020 (before any window)?
    early = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/as-of",
        params={"at": "2020-01-01T00:00:00Z"}, headers=headers)).json()
    assert early["primary"] is None

    # bob's active window at its declared start.
    row = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.object_id == project["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().one()
    later = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/as-of",
        params={"at": row.declared_start.isoformat()}, headers=headers)).json()
    assert later["primary"]["owner_id"] == bob["id"]


async def test_reconcile_is_exact_once_no_duplicate_windows(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_once@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    kai = await _hire(client, headers, "4f4-once@test.co", "Kai", "Reyes")
    project = await _project(client, headers, "Exact Once", owner_id=None)
    await _drain(db_session_factory)

    from app.intelligence.ownership_engine import ownership_engine

    for _ in range(3):
        await ownership_engine.reconcile(
            db_session, organization_id=org_id,
            object_type="project", object_id=project["id"],
            object_name="Exact Once", owner_id=kai["id"],
            source="declared", evidence={"event": "project.created"},
        )
        await db_session.commit()
    active = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.object_id == project["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().all()
    assert len(active) == 1
    assigned = (await db_session.execute(
        select(OwnershipChange).where(
            OwnershipChange.object_id == project["id"],
            OwnershipChange.action == "assigned",
        )
    )).scalars().all()
    assert len(assigned) == 1

    # a changed declared owner lands as ONE transfer, still one active window.
    other = await _hire(client, headers, "4f4-once2@test.co", "Mina", "Reyes")
    await ownership_engine.reconcile(
        db_session, organization_id=org_id,
        object_type="project", object_id=project["id"],
        object_name="Exact Once", owner_id=other["id"], source="declared",
    )
    await db_session.commit()
    active = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.object_id == project["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().all()
    assert len(active) == 1
    assert active[0].owner_id == other["id"]


async def test_unknown_owner_or_missing_object_type_is_rejected(client, db_session):
    org = await register_org(client, email="4f4_refuse@test.co")
    headers = org["headers"]
    res = await client.post(
        f"{BRAIN}/ownership/assign",
        json={"object_type": "project", "object_id": "nope",
              "owner_id": "ghost"},
        headers=headers,
    )
    assert res.status_code == 404
    res2 = await client.post(
        f"{BRAIN}/ownership/assign",
        json={"object_type": "custom", "object_id": "kpi-1",
              "object_name": "NPS Dashboard", "owner_id": "ghost"},
        headers=headers,
    )
    assert res2.status_code == 404


# ------------------------------------------------------------- close


async def test_close_keeps_history(client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_close@test.co")
    headers = org["headers"]
    sam = await _hire(client, headers, "4f4-close@test.co", "Sam", "Yu")
    project = await _project(client, headers, "Legacy", owner_id=sam["id"])
    await _drain(db_session_factory)
    res = await client.post(
        f"{BRAIN}/ownership/close",
        json={"object_type": "project", "object_id": project["id"],
              "reason": "sunset"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    current = await _object(client, headers, project["id"])
    assert current["primary"] is None
    history = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/history",
        headers=headers)).json()
    assert any(e.get("action") == "closed" for e in history["events"])


# ------------------------------------------------------------- backup + 4C


async def test_backup_and_continuity_with_4c_delegation_read(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_backup@test.co")
    headers = org["headers"]
    owner = await _hire(client, headers, "4f4-bk1@test.co", "Omar", "Iqbal")
    backup = await _hire(client, headers, "4f4-bk2@test.co", "Bina", "Iqbal")
    project = await _project(client, headers, "Billing", owner_id=owner["id"])
    await _drain(db_session_factory)

    res = await client.post(
        f"{BRAIN}/ownership/backup",
        json={"object_type": "project", "object_id": project["id"],
              "backup_owner_id": backup["id"]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    continuity = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/continuity",
        headers=headers)).json()
    assert continuity["primary"]["owner_id"] == owner["id"]
    assert continuity["backup"]["owner_id"] == backup["id"]

    # a person holding only a backup role is surfaced by their own surface.
    mine = (await client.get(
        f"{BRAIN}/ownership/people/{backup['id']}/responsibilities",
        headers=headers)).json()
    assert mine["backup_roles"] == 1
    assert mine["active"] == []

    # an owner can never be their own fallback.
    bad = await client.post(
        f"{BRAIN}/ownership/backup",
        json={"object_type": "project", "object_id": project["id"],
              "backup_owner_id": owner["id"]},
        headers=headers,
    )
    assert bad.status_code == 400

    # 4C delegation anchored at the responsibility's scope shows in continuity.
    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Billing Unit", "scope_type": "department"},
        headers=headers)).json()
    from app.models.enterprise import AccessGrant

    db_session.add(AccessGrant(
        organization_id=org["organization"]["id"],
        granted_by=org["user"]["id"], granted_to_user=org["user"]["id"],
        permission_code="brain:read",
        resource_type="scope", resource_id=scope["id"],
        reason="continuity read test", status="active",
    ))
    await db_session.commit()
    await _assign(client, headers, project["id"], owner["id"], scope_id=scope["id"])
    continuity = (await client.get(
        f"{BRAIN}/ownership/objects/project/{project['id']}/continuity",
        headers=headers)).json()
    assert continuity["delegation"] is not None
    assert continuity["delegation"]["scope_id"] == scope["id"]
    assert any(
        g["permission_code"] == "brain:read"
        for g in continuity["delegation"]["grants"]
    )


# ------------------------------------------------------------- analysis


async def test_inactive_owner_gap_signal_never_auto_assigns(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_gap@test.co")
    headers = org["headers"]
    leo = await _hire(client, headers, "4f4-gap@test.co", "Leo", "Marsh")
    project = await _project(client, headers, "Legacy Core", owner_id=leo["id"])
    await _drain(db_session_factory)

    from app.models.employee import Employee

    emp = await db_session.get(Employee, leo["id"])
    emp.status = "inactive"
    await db_session.commit()

    analyze = (await client.post(f"{BRAIN}/ownership/analyze", headers=headers)).json()
    assert analyze["gap"] == 1
    assert analyze["mismatch"] == 0

    signals = (await client.get(f"{BRAIN}/ownership/signals", headers=headers)).json()
    gaps = [s for s in signals["signals"] if s["kind"] == "gap"]
    assert len(gaps) == 1
    assert gaps[0]["severity"] == "critical"
    assert "no longer an active employee" in gaps[0]["detail"]

    # the ownership record was NOT changed by analysis - only a signal exists.
    current = await _object(client, headers, project["id"])
    assert current["primary"]["owner_id"] == leo["id"]
    # gap re-scan is deduplicated (idempotent signals).
    await client.post(f"{BRAIN}/ownership/analyze", headers=headers)
    signals = (await client.get(
        f"{BRAIN}/ownership/signals", params={"kind": "gap"}, headers=headers)).json()
    assert signals["total"] == 1

    # resolving a signal is explicit and governed.
    res = await client.post(
        f"{BRAIN}/ownership/signals/{gaps[0]['id']}/resolve", headers=headers)
    assert res.status_code == 200, res.text
    signals = (await client.get(
        f"{BRAIN}/ownership/signals", params={"status": "resolved"},
        headers=headers)).json()
    assert signals["total"] == 1


async def test_observed_mismatch_is_surfaced_never_auto_changed(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_mis@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    declared = await _hire(client, headers, "4f4-mis1@test.co", "Dora", "Lane")
    practice = await _hire(client, headers, "4f4-mis2@test.co", "Pax", "Lane")
    project = await _project(client, headers, "Inventory", owner_id=declared["id"])
    await _drain(db_session_factory)

    from app.intelligence.expertise_engine import expertise_engine

    now = datetime.datetime.now(UTC)
    for i in range(4):
        await expertise_engine.record_evidence(
            db_session, organization_id=org_id,
            employee_id=practice["id"], event_name="task.completed",
            tokens=["python"], reason="runs the inventory system",
            event_id=f"evt-mis-{i}", source_type="project",
            source_id=project["id"], source_title="Inventory",
            outcome="successful", origin_event_id=f"raw-mis-{i}",
            lineage_key=f"task:t-{i}",
            valid_to=now + datetime.timedelta(days=30),
        )
    await db_session.commit()

    analyze = (await client.post(f"{BRAIN}/ownership/analyze", headers=headers)).json()
    assert analyze["mismatch"] == 1
    assert analyze["gap"] == 0

    signals = (await client.get(
        f"{BRAIN}/ownership/signals", params={"kind": "mismatch"},
        headers=headers)).json()
    assert signals["total"] == 1
    sig = signals["signals"][0]
    assert "Potential responsibility mismatch" in sig["detail"]
    assert "was NOT changed" in sig["detail"]

    # declared owner still owns it - analysis NEVER auto-fixes.
    current = await _object(client, headers, project["id"])
    assert current["primary"]["owner_id"] == declared["id"]


async def test_single_point_dependency_flagged_without_auto_fix(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_spof@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    solo = await _hire(client, headers, "4f4-spof@test.co", "Solo", "Vega")
    for i in range(3):
        await _project(client, headers, f"Critical {i}", owner_id=solo["id"])
    await _drain(db_session_factory)

    analyze = (await client.post(f"{BRAIN}/ownership/analyze", headers=headers)).json()
    assert analyze["single_point"] == 3
    signals = (await client.get(
        f"{BRAIN}/ownership/signals", params={"kind": "single_point"},
        headers=headers)).json()
    assert signals["total"] == 3
    assert all("no backup" in s["detail"] for s in signals["signals"])

    # backing up one object removes one dependency risk.
    rescue = await _hire(client, headers, "4f4-spof2@test.co", "Nia", "Vega")
    one = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.organization_id == org_id,
            OwnershipRelationship.responsibility_type == "primary",
            OwnershipRelationship.status == "active",
            OwnershipRelationship.owner_id == solo["id"],
        ).order_by(OwnershipRelationship.created_at.asc()).limit(1)
    )).scalars().first()
    await client.post(
        f"{BRAIN}/ownership/backup",
        json={"object_type": "project", "object_id": one.object_id,
              "backup_owner_id": rescue["id"]},
        headers=headers,
    )
    analyze = (await client.post(f"{BRAIN}/ownership/analyze", headers=headers)).json()
    assert analyze["single_point"] == 2


async def test_analysis_is_bounded_batched(client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_bound@test.co")
    headers = org["headers"]
    a = await _hire(client, headers, "4f4-bd-a@test.co", "Ava", "Bond")
    for i in range(5):
        await _project(client, headers, f"Batch {i}", owner_id=a["id"])
    await _drain(db_session_factory)
    analyze = (await client.post(
        f"{BRAIN}/ownership/analyze", params={"limit": 2, "offset": 0},
        headers=headers)).json()
    assert analyze["scanned"] == 2
    assert analyze["next_offset"] == 2
    summary = (await client.get(f"{BRAIN}/ownership/summary", headers=headers)).json()
    assert summary["active_relationships"] == 5


# ------------------------------------------------------------- events bridge


async def test_project_events_reconcile_ownership_and_replay_is_safe(
        client, db_session, db_session_factory):
    org = await register_org(client, email="4f4_evt@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f4-evt@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f4-evt2@test.co", "Bob", "Builder")
    project = await _project(client, headers, "Replay", owner_id=ada["id"])
    await _drain(db_session_factory)

    # the project.created handler created the declared window.
    rows = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.organization_id == org_id,
            OwnershipRelationship.object_id == project["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().all()
    assert len(rows) == 1 and rows[0].owner_id == ada["id"]

    # an owner change lands as a transfer; replaying the event is a no-op.
    from app.models.project import Project

    project_row = await db_session.get(Project, project["id"])
    project_row.owner_id = bob["id"]
    await db_session.commit()
    for _ in range(2):
        await _publish(db_session_factory, org_id, "project.updated",
                       actor_id=org["user"]["id"],
                       payload={"project_id": project["id"], "name": "Replay"})
    rows = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.organization_id == org_id,
            OwnershipRelationship.object_id == project["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().all()
    assert len(rows) == 1 and rows[0].owner_id == bob["id"]

    # offboarding closes every window of a person and never reassigns.
    await _project(client, headers, "Second", owner_id=ada["id"])
    await _drain(db_session_factory)
    await _publish(db_session_factory, org_id, "employee.offboarded",
                   actor_id=org["user"]["id"],
                   payload={"employee_id": ada["id"]})
    left = (await db_session.execute(
        select(OwnershipRelationship).where(
            OwnershipRelationship.organization_id == org_id,
            OwnershipRelationship.owner_id == ada["id"],
            OwnershipRelationship.status == "active",
        )
    )).scalars().all()
    assert left == []


async def test_uninvited_caller_cannot_write_ownership(client):
    await register_org(client, email="4f4_perm@test.co")
    res = await client.post(
        f"{BRAIN}/ownership/assign",
        json={"object_type": "custom", "object_id": "kpi-2",
              "object_name": "Support", "owner_id": "x"},
    )
    assert res.status_code in (401, 403)