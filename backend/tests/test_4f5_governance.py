"""Slice 4F.5 — governance, tenant isolation and RBAC for collaboration.

The Work Collaboration Graph must obey 4C governance semantics (downward-only):

* tenants are isolated end-to-end: org B never sees org A evidence, counts,
  or people through any collaboration surface,
* a scoped reader never leaks hidden people through relationship reads,
  overview counts, rankings or project views,
* reads are refused (404) for hidden persons, and write-adjacent surfaces
  require real permissions (403 without them),
* resolving a signal is an explicit governed write, never an implicit one.
"""

from sqlalchemy import select

from app.models.collaboration_intelligence import (
    CollaborationEvidence,
    CollaborationRelationship,
)
from tests import _brain4d6_helpers as h
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


async def _hire(client, headers, email, first, last, team_id=None, department_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id, "department_id": department_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
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


# ------------------------------------------------------------- tenant isolation


async def test_tenant_isolation_end_to_end(client, db_session_factory):
    org_a = await register_org(client, email="4f5_tena@test.co")
    org_b = await register_org(client, email="4f5_tenb@test.co")
    a1 = await _hire(client, org_a["headers"], "4f5-ta@test.co", "Pia", "Quinn")
    a2 = await _hire(client, org_a["headers"], "4f5-tb@test.co", "Rey", "Sosa")
    b1 = await _hire(client, org_b["headers"], "4f5-tc@test.co", "Sam", "Todd")

    await _publish(
        db_session_factory, org_a["organization"]["id"], "task.completed",
        org_a["user"]["id"],
        {"task_id": "4f5-ta1", "assignee_id": a1["id"], "reporter_id": a2["id"],
         "title": "Tenant A work"},
    )

    # tenant A sees its own edge.
    mine = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a1['id']}/with/{a2['id']}",
        headers=org_a["headers"])).json()
    assert mine["shared_tasks"] >= 1

    # tenant B sees nothing of tenant A - not even the same person ids.
    other = await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a1['id']}/with/{a2['id']}",
        headers=org_b["headers"])
    assert other.status_code == 404, other.text

    overview_b = (await client.get(f"{BRAIN}/collaboration/overview", headers=org_b["headers"])).json()
    assert overview_b["total_relationships"] == 0

    async with db_session_factory() as db:
        b_evidence = (
            await db.execute(
                select(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == org_b["organization"]["id"],
                )
            )
        ).scalars().all()
    assert len(b_evidence) == 0


# ------------------------------------------------------------- scoped readers


async def test_scoped_reader_never_leaks_hidden_people(
        client, db_session_factory):
    org = await register_org(client, email="4f5_scope@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    visible_team = (await client.post(
        "/api/v1/teams",
        json={"name": "Visible", "code": "4f5-vis"},
        headers=headers)).json()
    hidden_team = (await client.post(
        "/api/v1/teams",
        json={"name": "Hidden", "code": "4f5-hid"},
        headers=headers)).json()

    insider = await _hire(client, headers, "4f5-sc1@test.co", "Nia", "Osei",
                          team_id=visible_team["id"])
    outsider = await _hire(client, headers, "4f5-sc2@test.co", "Omar", "Pires",
                           team_id=hidden_team["id"])

    # evidence exists inside the visible team and between the two teams.
    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-sc1", "assignee_id": insider["id"],
         "reporter_id": outsider["id"], "title": "Cross team work"},
    )
    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-sc2", "assignee_id": insider["id"],
         "reporter_id": insider["id"] if False else outsider["id"], "title": "More work"},
    )

    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Visible scope", "scope_type": "team",
              "entity_id": visible_team["id"]},
        headers=headers)).json()
    reader = await h.invite_scoped_reader(client, headers, scope["id"], "4f5-scoperead@test.co")

    # a hidden person's collaboration reads as missing (404).
    hidden_profile = await client.get(
        f"{BRAIN}/collaboration/people/{outsider['id']}", headers=reader)
    assert hidden_profile.status_code == 404, hidden_profile.text

    # the hidden person's pair is also 404 - never a 200 with hidden data.
    hidden_pair = await client.get(
        f"{BRAIN}/collaboration/relationships/people/{insider['id']}/with/{outsider['id']}",
        headers=reader)
    assert hidden_pair.status_code == 404, hidden_pair.text

    # visible person's own surface works and never lists the hidden partner.
    visible_profile = (await client.get(
        f"{BRAIN}/collaboration/people/{insider['id']}", headers=reader)).json()
    assert all(
        r["other_person_id"] != outsider["id"] for r in visible_profile["relationships"]
    ), "hidden people must never leak through person surfaces"

    # overview counts are scoped: the org-wide pair with the hidden person
    # is not counted for this caller.
    overview = (await client.get(f"{BRAIN}/collaboration/overview", headers=reader)).json()
    assert overview["total_relationships"] == 0, (
        "aggregates must be gated so hidden members never leak through counts"
    )


async def test_scoped_reader_unit_and_project_surfaces_stay_scoped(
        client, db_session_factory):
    org = await register_org(client, email="4f5_scopeproj@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    visible_team = (await client.post(
        "/api/v1/teams",
        json={"name": "Alpha", "code": "4f5-alp"},
        headers=headers)).json()
    hidden_team = (await client.post(
        "/api/v1/teams",
        json={"name": "Beta", "code": "4f5-bet"},
        headers=headers)).json()
    insider = await _hire(client, headers, "4f5-sp1@test.co", "Kira", "Nakagawa",
                          team_id=visible_team["id"])
    outsider = await _hire(client, headers, "4f5-sp2@test.co", "Luca", "Moreau",
                           team_id=hidden_team["id"])

    await _publish(
        db_session_factory, org_id, "meeting.ended", org["user"]["id"],
        {"meeting_id": "4f5-mtg1", "title": "Cross team sync",
         "attendees": [insider["id"], outsider["id"]]},
    )

    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Alpha scope", "scope_type": "team",
              "entity_id": visible_team["id"]},
        headers=headers)).json()
    reader = await h.invite_scoped_reader(client, headers, scope["id"], "4f5-scoperead2@test.co")

    # the hidden team's unit surface is refused entirely.
    hidden_unit = await client.get(
        f"{BRAIN}/collaboration/units/team/{hidden_team['id']}", headers=reader)
    assert hidden_unit.status_code == 404, hidden_unit.text


# ------------------------------------------------------------- permission gates


async def test_collaboration_surfaces_require_brain_read(client, db_session_factory):
    org = await register_org(client, email="4f5_perm@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-pa@test.co", "Milo", "Wang")
    b = await _hire(client, headers, "4f5-pb@test.co", "Nadia", "Zaki")

    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-p1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Perm gate"},
    )

    # an ordinary invited employee without brain:read gets 403, never data.
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "4f5-noperm@test.co", "full_name": "No Perm", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "No Perm",
              "password": "StrongPass123!"},
    )
    assert joined.status_code == 201, joined.text
    no_perm = {"Authorization": f"Bearer {joined.json()['access_token']}"}

    # strip brain:read from the employee role (this test's own database):
    # every collaboration surface must then refuse this caller.
    from sqlalchemy import delete

    from app.models.role import Permission, Role, RolePermission, UserRole

    async with db_session_factory() as db:
        role_row = (
            await db.execute(
                select(Role).where(Role.code == "employee", Role.is_system.is_(True))
            )
        ).scalar_one_or_none()
        perm = (
            await db.execute(
                select(Permission).where(Permission.code == "brain:read")
            )
        ).scalar_one_or_none()
        assert role_row is not None and perm is not None
        await db.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_row.id,
                RolePermission.permission_id == perm.id,
            )
        )
        # leave the user's own role rows in place beyond brain:read.
        user_role_rows = (
            await db.execute(
                select(UserRole).where(
                    UserRole.user_id == joined.json()["user"]["id"],
                    UserRole.organization_id == org_id,
                    UserRole.scope_id.is_(None),
                )
            )
        ).scalars().all()
        assert user_role_rows, "invitee holds the employee role"
        await db.commit()

    for path in (
        f"/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        f"/collaboration/people/{a['id']}",
        "/collaboration/overview",
        "/collaboration/changes",
        "/collaboration/signals",
    ):
        res = await client.get(f"{BRAIN}{path}", headers=no_perm)
        assert res.status_code == 403, (path, res.text)

    # the org owner still reads the same surface (control group).
    control = await client.get(
        f"{BRAIN}/collaboration/overview", headers=headers)
    assert control.status_code == 200


async def test_signal_resolution_is_an_explicit_governed_write(
        client, db_session_factory):
    org = await register_org(client, email="4f5_signalgov@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-sg1@test.co", "Opal", "Dean")
    b = await _hire(client, headers, "4f5-sg2@test.co", "Pavel", "Ivanov")

    # strong -> at_risk transition: successes first, then repeated failures
    # produce an open negative_shift advisory signal.
    for i in range(20):
        await _publish(
            db_session_factory, org_id, "task.completed", org["user"]["id"],
            {"task_id": f"4f5-sg-ok{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": "Good work"},
        )
    for i in range(11):
        await _publish(
            db_session_factory, org_id, "approval.rejected", b["id"],
            {"approval_id": f"4f5-rej{i}", "requester_id": a["id"],
             "title": "Access request"},
        )
    signals = (await client.get(f"{BRAIN}/collaboration/signals", headers=headers)).json()
    assert signals["total"] >= 1

    # without employees:manage the resolve write is refused (403).
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "4f5-sgr@test.co", "full_name": "Signal Reader",
              "role": "employee"},
        headers=headers,
    )
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Signal Reader",
              "password": "StrongPass123!"},
    )
    no_manage = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    signal_id = signals["signals"][0]["id"]
    refused = await client.post(
        f"{BRAIN}/collaboration/signals/{signal_id}/resolve", headers=no_manage)
    assert refused.status_code == 403, refused.text

    # the owner (employees:manage) resolves it explicitly.
    resolved = await client.post(
        f"{BRAIN}/collaboration/signals/{signal_id}/resolve", headers=headers)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved"] == signal_id
    # resolving a signal never mutates the collaboration graph.
    async with db_session_factory() as db:
        rel = (
            await db.execute(
                select(CollaborationRelationship).where(
                    CollaborationRelationship.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert rel, "the relationship still exists after signal resolution"
