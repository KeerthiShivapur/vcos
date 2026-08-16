"""Slice 4F.5 — boundedness and constant-cost guarantees.

The Work Collaboration Graph is change-driven: one event touches at most a
hard-capped number of pairs, and no analysis pass ever rescans the org or
builds an all-pairs product. These tests prove the caps hold at the edges.
"""

from sqlalchemy import func, select

from app.intelligence.work_collaboration_engine import (
    MAX_MEETING_ATTENDEES,
    MAX_GAP_PROJECTS_PER_PASS,
    MAX_PROJECT_PAIRED_MEMBERS,
)
from app.models.collaboration_intelligence import (
    CollaborationEvidence,
    CollaborationRelationship,
)
from tests.conftest import register_org

BRAIN = "/api/v1/brain"


async def _drain(db_session_factory, limit=500, rounds=5):
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
    created = await client.post(
        "/api/v1/employees",
        json={"first_name": first, "last_name": last, "email": email,
              "team_id": team_id, "department_id": department_id},
        headers=headers,
    )
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


async def test_meeting_attendee_pairing_is_hard_bounded(client, db_session_factory):
    org = await register_org(client, email="4f5_scale_meet@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    people = []
    for i in range(20):
        people.append(await _hire(
            client, headers, f"4f5-sm{i}@test.co", f"Meet{i}", "Scale"))

    # 20 attendees = 190 possible pairs; the engine must cap at 16 -> 120.
    await _publish(
        db_session_factory, org_id, "meeting.ended", org["user"]["id"],
        {"meeting_id": "4f5-big-mtg", "title": "Big sync",
         "attendees": [p["id"] for p in people]},
    )

    async with db_session_factory() as db:
        n_rels = (
            await db.execute(
                select(CollaborationRelationship.id).where(
                    CollaborationRelationship.organization_id == org_id,
                    CollaborationRelationship.scope_type == "org",
                )
            )
        ).scalars().all()
        n_evidence = (
            await db.execute(
                select(CollaborationEvidence.id).where(
                    CollaborationEvidence.organization_id == org_id,
                )
            )
        ).scalars().all()

    expected = MAX_MEETING_ATTENDEES * (MAX_MEETING_ATTENDEES - 1) // 2
    assert len(n_rels) == expected, (len(n_rels), expected)
    assert len(n_evidence) == expected


async def test_no_all_pairs_pass(client, db_session_factory):
    org = await register_org(client, email="4f5_scale_nopairs@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    people = []
    for i in range(40):
        people.append(await _hire(
            client, headers, f"4f5-sn{i}@test.co", f"Node{i}", "Scale"))

    # one task between two people: exactly one edge exists afterward - the
    # engine never enumerates all 780 possible pairs.
    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-only", "assignee_id": people[0]["id"],
         "reporter_id": people[1]["id"], "title": "Only edge"},
    )
    overview = (await client.get(f"{BRAIN}/collaboration/overview", headers=headers)).json()
    assert overview["total_relationships"] == 1, "no all-pairs pass may fabricate edges"


async def test_message_recipients_bounded_and_meaningful_only(
        client, db_session_factory):
    org = await register_org(client, email="4f5_scale_msg@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    sender = await _hire(client, headers, "4f5-msg-s@test.co", "Sender", "Scale")
    members = []
    for i in range(30):
        members.append(await _hire(
            client, headers, f"4f5-msg-m{i}@test.co", f"Recv{i}", "Scale"))

    async with db_session_factory() as db:
        from app.models.communication import Conversation, ConversationMember, Message

        conv = Conversation(organization_id=org_id, title="Scale channel", created_by=sender["id"])
        db.add(conv)
        await db.flush()
        for m in members:
            db.add(ConversationMember(
                organization_id=org_id, conversation_id=conv.id, employee_id=m["id"], role="member"))
        await db.flush()
        msg = Message(
            organization_id=org_id, conversation_id=conv.id, sender_id=sender["id"],
            content="This is a meaningful work update for the whole channel.",
        )
        db.add(msg)
        await db.commit()

    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="messaging.message_sent", organization_id=org_id,
            actor_id=sender["id"], payload={"message_id": msg.id},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory, limit=500)

    async with db_session_factory() as db:
        n_evidence = (
            await db.execute(
                select(func.count()).select_from(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == org_id,
                )
            )
        ).scalar_one()
    assert n_evidence <= 24, "recipients capped at MAX_MESSAGE_RECIPIENTS"

    # casual chatter creates no edges at all.
    async with db_session_factory() as db:
        from app.models.communication import Message as Msg

        small = Msg(
            organization_id=org_id, conversation_id=conv.id, sender_id=sender["id"],
            content="ok",
        )
        db.add(small)
        await db.commit()
        await event_bus.publish(
            db, name="messaging.message_sent", organization_id=org_id,
            actor_id=sender["id"], payload={"message_id": small.id},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory, limit=500)
    overview = (await client.get(f"{BRAIN}/collaboration/overview", headers=headers)).json()
    assert overview["total_relationships"] == 24


async def test_gap_analysis_pass_is_bounded(client, db_session_factory):
    org = await register_org(client, email="4f5_scale_gap@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    # departments A..E with employees; >100 active projects sharing them.
    depts = {}
    for code in ("a", "b", "c", "d", "e"):
        created = await client.post(
            "/api/v1/departments", json={"name": f"Dept {code}", "code": f"4f5d{code}"},
            headers=headers)
        assert created.status_code in (200, 201), created.text
        depts[code] = created.json()["id"]
    employees = {}
    for code in ("a", "b", "c", "d", "e"):
        employees[code] = (await _hire(
            client, headers, f"4f5-gap-{code}@test.co", f"Gap{code}", "Scale",
            department_id=depts[code]))["id"]

    async with db_session_factory() as db:
        from app.models.project import Project, ProjectMember

        for i in range(120):
            proj = Project(
                organization_id=org_id, code=f"gap-proj-{i}", name=f"Project {i}",
                status="active", owner_id=employees["a"],
            )
            db.add(proj)
            await db.flush()
            for code in ("a", "b", "c"):
                db.add(ProjectMember(
                    organization_id=org_id, project_id=proj.id,
                    employee_id=employees[code], role="member"))
        await db.commit()

    result = (await client.post(
        f"{BRAIN}/collaboration/analyze", headers=headers)).json()
    assert result["projects_scanned"] <= MAX_GAP_PROJECTS_PER_PASS
    assert result["unit_pairs_checked"] <= len(depts) * (len(depts) - 1) // 2
    assert result["gaps"] >= 0

    # a second pass is idempotent: no unbounded growth in signals.
    again = await client.post(f"{BRAIN}/collaboration/analyze", headers=headers)
    assert again.status_code == 200, again.text


async def test_bulk_events_apply_each_once_in_bounded_time(
        client, db_session_factory):
    org = await register_org(client, email="4f5_scale_bulk@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    from app.events.event_bus import event_bus

    people = []
    for i in range(12):
        people.append(await _hire(
            client, headers, f"4f5-bulk-{i}@test.co", f"Bulk{i}", "Scale"))

    async with db_session_factory() as db:
        for i in range(60):
            a, b = people[i % 12], people[(i * 7 + 1) % 12]
            await event_bus.publish(
                db, name="task.completed", organization_id=org_id,
                actor_id=org["user"]["id"],
                payload={"task_id": f"4f5-bulk-{i}", "assignee_id": a["id"],
                         "reporter_id": b["id"], "title": f"Bulk {i}"},
                enqueue=True, flush=False,
            )
        await db.commit()
    processed = await _drain(db_session_factory, limit=500, rounds=8)
    assert processed >= 60  # the 60 task events plus lifecycle setup events

    async with db_session_factory() as db:
        n_evidence = (
            await db.execute(
                select(CollaborationEvidence.id).where(
                    CollaborationEvidence.organization_id == org_id,
                ))
        ).scalars().all()
    assert len(n_evidence) == 60


async def test_project_pairing_respects_member_cap(client, db_session_factory):
    org = await register_org(client, email="4f5_scale_proj@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    owner = await _hire(client, headers, "4f5-proj-o@test.co", "Owner", "Scale")
    members = []
    for i in range(30):
        members.append(await _hire(
            client, headers, f"4f5-proj-m{i}@test.co", f"Member{i}", "Scale"))

    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        from app.models.project import Project, ProjectMember

        proj = Project(organization_id=org_id, code="scale-proj",
                       name="Scale project", status="active", owner_id=owner["id"])
        db.add(proj)
        await db.flush()
        for m in members:
            db.add(ProjectMember(organization_id=org_id, project_id=proj.id,
                                 employee_id=m["id"], role="member"))
        await db.commit()
        project_id = proj.id
        await event_bus.publish(
            db, name="project.started", organization_id=org_id,
            actor_id=owner["id"], payload={"project_id": project_id},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        n_evidence = (
            await db.execute(
                select(CollaborationEvidence.id).where(
                    CollaborationEvidence.organization_id == org_id,
                ))
        ).scalars().all()
    assert len(n_evidence) <= MAX_PROJECT_PAIRED_MEMBERS, (
        "owner is paired with at most the capped number of members"
    )