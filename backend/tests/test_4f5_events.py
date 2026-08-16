"""Slice 4F.5 — event-driven collaboration feeding.

The Work Collaboration Graph is fed from the SAME durable events the
platform already emits. Under test:

* task.* events pair assignee<->reporter and count shared tasks,
* project lifecycle events pair the owner with bounded members,
* decision.made pairs maker<->participants (bounded),
* meeting.ended/completed pair attendees (bounded),
* messaging.message_sent pairs sender<->members ONLY for meaningful content,
* approval.approved/rejected pair requester<->approver and flip the sign,
* every replay is exact-once (no double counting through the event bus),
* an event with no meaningful pair never fabricates an edge.
"""

from sqlalchemy import select

from app.models.collaboration_intelligence import (
    CollaborationEvidence,
    CollaborationRelationship,
)
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


async def _hire(client, headers, email, first, last, department_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "department_id": department_id}
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


async def _pair(client, headers, person_a, person_b):
    res = await client.get(
        f"{BRAIN}/collaboration/relationships/people/{person_a}/with/{person_b}",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------- task events


async def test_task_events_pair_assignee_and_reporter(client, db_session_factory):
    org = await register_org(client, email="4f5_evtask@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-et@test.co", "Eli", "Nakamura")
    b = await _hire(client, headers, "4f5-ef@test.co", "Farah", "Hussain")

    await _publish(
        db_session_factory, org_id, "task.created", org["user"]["id"],
        {"task_id": "4f5-ev1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Create handoff"},
    )
    rel = await _pair(client, headers, a["id"], b["id"])
    assert rel["shared_tasks"] == 1
    assert rel["points_cur_month"] > 0

    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-ev1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Create handoff"},
    )
    rel = await _pair(client, headers, a["id"], b["id"])
    assert rel["successful_interactions"] == 1
    # each task event is one evidence item for the pair: created + completed
    # materialize as two task-anchored items for the same task.
    assert rel["shared_tasks"] == 2
    assert rel["evidence_count"] == 2

    await _publish(
        db_session_factory, org_id, "task.blocked", org["user"]["id"],
        {"task_id": "4f5-ev2", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Blocked work"},
    )
    rel = await _pair(client, headers, a["id"], b["id"])
    assert rel["failed_interactions"] == 1
    assert rel["health_state"] in ("at_risk", "blocked", "healthy", "low_evidence")


async def test_events_without_pairs_never_fabricate_edges(client, db_session_factory):
    org = await register_org(client, email="4f5_evnone@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-en@test.co", "Nora", "Fields")

    # a task with no assignee cannot evidence a pair.
    await _publish(
        db_session_factory, org_id, "task.created", org["user"]["id"],
        {"task_id": "4f5-en1", "assignee_id": None, "reporter_id": a["id"],
         "title": "No assignee"},
    )
    async with db_session_factory() as db:
        count = (
            await db.execute(
                select(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert count == [], "an event without a valid pair must not fabricate edges"


# ------------------------------------------------------------- project events


async def test_project_lifecycle_pairs_owner_with_members(client, db_session_factory):
    org = await register_org(client, email="4f5_evproj@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    owner = await _hire(client, headers, "4f5-eq@test.co", "Quinn", "Ford")
    m1 = await _hire(client, headers, "4f5-er@test.co", "Rhea", "Sawyer")
    m2 = await _hire(client, headers, "4f5-es@test.co", "Seth", "Walsh")

    from app.models.project import ProjectMember

    async with db_session_factory() as db:
        project_id = "4f5-proj1"
        from app.models.project import Project

        db.add(Project(
            id=project_id, organization_id=org_id, name="Orion",
            code="orion", owner_id=owner["id"], status="draft",
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=project_id, employee_id=m1["id"],
        ))
        db.add(ProjectMember(
            organization_id=org_id, project_id=project_id, employee_id=m2["id"],
        ))
        await db.commit()

    await _publish(
        db_session_factory, org_id, "project.started", org["user"]["id"],
        {"project_id": "4f5-proj1", "name": "Orion", "status": "active"},
    )
    rel_om1 = await _pair(client, headers, owner["id"], m1["id"])
    rel_om2 = await _pair(client, headers, owner["id"], m2["id"])
    assert rel_om1["shared_tasks"] >= 1
    assert rel_om2["shared_tasks"] >= 1
    # the project-scoped view sees the evidence too.
    view = (await client.get(
        f"{BRAIN}/collaboration/projects/4f5-proj1", headers=headers)).json()
    assert view["total_evidence"] >= 2


# ------------------------------------------------------------- decision events


async def test_decision_events_pair_maker_with_participants(client, db_session_factory):
    org = await register_org(client, email="4f5_evdec@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    maker = await _hire(client, headers, "4f5-ed@test.co", "Devi", "Nair")
    p1 = await _hire(client, headers, "4f5-ee@test.co", "Ethan", "Brooks")
    p2 = await _hire(client, headers, "4f5-ef2@test.co", "Fiona", "Clay")

    from app.models.knowledge import Decision, DecisionParticipant

    async with db_session_factory() as db:
        db.add(Decision(
            id="4f5-dec1", organization_id=org_id, title="Cloud migration",
            slug="cloud-migration-4f5", decision_maker_id=maker["id"], status="made",
        ))
        db.add(DecisionParticipant(
            organization_id=org_id, decision_id="4f5-dec1", employee_id=p1["id"],
        ))
        db.add(DecisionParticipant(
            organization_id=org_id, decision_id="4f5-dec1", employee_id=p2["id"],
        ))
        await db.commit()

    await _publish(
        db_session_factory, org_id, "decision.made", org["user"]["id"],
        {"decision_id": "4f5-dec1", "title": "Cloud migration"},
    )
    rel1 = await _pair(client, headers, maker["id"], p1["id"])
    rel2 = await _pair(client, headers, maker["id"], p2["id"])
    assert rel1["shared_decisions"] == 1
    assert rel2["shared_decisions"] == 1

    await _publish(
        db_session_factory, org_id, "decision.implemented", org["user"]["id"],
        {"decision_id": "4f5-dec1", "title": "Cloud migration"},
    )
    rel1 = await _pair(client, headers, maker["id"], p1["id"])
    assert rel1["successful_interactions"] >= 1


# ------------------------------------------------------------- meeting events


async def test_meeting_events_pair_attendees(client, db_session_factory):
    org = await register_org(client, email="4f5_evmeet@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-ma@test.co", "Mina", "Sharma")
    b = await _hire(client, headers, "4f5-mb@test.co", "Noah", "Bell")
    c = await _hire(client, headers, "4f5-mc@test.co", "Olga", "Tate")

    await _publish(
        db_session_factory, org_id, "meeting.ended", org["user"]["id"],
        {"meeting_id": "4f5-mtg1", "title": "Sprint review",
         "attendees": [a["id"], b["id"], c["id"]]},
    )
    rel_ab = await _pair(client, headers, a["id"], b["id"])
    rel_ac = await _pair(client, headers, a["id"], c["id"])
    rel_bc = await _pair(client, headers, b["id"], c["id"])
    assert rel_ab["shared_meetings"] == 1
    assert rel_ac["shared_meetings"] == 1
    assert rel_bc["shared_meetings"] == 1


# ------------------------------------------------------------- message events


async def test_message_events_count_only_meaningful_communication(
        client, db_session_factory):
    org = await register_org(client, email="4f5_evmsg@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    sender = await _hire(client, headers, "4f5-ms@test.co", "Sam", "Iyer")
    recipient = await _hire(client, headers, "4f5-mr@test.co", "Tara", "Vance")

    from app.models.communication import Conversation, ConversationMember, Message

    async with db_session_factory() as db:
        db.add(Conversation(
            id="4f5-conv1", organization_id=org_id, type="dm",
            created_by=sender["id"],
        ))
        db.add(ConversationMember(
            organization_id=org_id, conversation_id="4f5-conv1",
            employee_id=sender["id"],
        ))
        db.add(ConversationMember(
            organization_id=org_id, conversation_id="4f5-conv1",
            employee_id=recipient["id"],
        ))
        db.add(Message(
            id="4f5-msg1", organization_id=org_id, conversation_id="4f5-conv1",
            sender_id=sender["id"], content="ok",  # casual -> NOT meaningful
        ))
        db.add(Message(
            id="4f5-msg2", organization_id=org_id, conversation_id="4f5-conv1",
            sender_id=sender["id"],
            content="The deployment plan is ready and the rollout window is confirmed.",
        ))
        await db.commit()

    await _publish(
        db_session_factory, org_id, "messaging.message_sent", sender["id"],
        {"conversation_id": "4f5-conv1", "message_id": "4f5-msg1"},
    )
    missing = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{sender['id']}/with/{recipient['id']}",
        headers=headers))
    assert missing.status_code == 404, "casual chatter must not create edges"

    await _publish(
        db_session_factory, org_id, "messaging.message_sent", sender["id"],
        {"conversation_id": "4f5-conv1", "message_id": "4f5-msg2"},
    )
    rel = await _pair(client, headers, sender["id"], recipient["id"])
    assert rel["meaningful_messages"] == 1
    assert rel["shared_meetings"] == 0


# ------------------------------------------------------------- approval events


async def test_approval_events_pair_requester_with_approver_and_flip_sign(
        client, db_session_factory):
    org = await register_org(client, email="4f5_evappr@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    requester = await _hire(client, headers, "4f5-qa@test.co", "Ravi", "Gupta")
    approver = await _hire(client, headers, "4f5-qb@test.co", "Wendy", "Moore")

    for i in range(3):
        await _publish(
            db_session_factory, org_id, "approval.approved", approver["id"],
            {"approval_id": f"4f5-appr{i}", "requester_id": requester["id"],
             "title": "Budget approval"},
        )
    rel = await _pair(client, headers, requester["id"], approver["id"])
    assert rel["successful_interactions"] == 3
    strong = rel["strength"]

    for i in range(3):
        await _publish(
            db_session_factory, org_id, "approval.rejected", approver["id"],
            {"approval_id": f"4f5-rej{i}", "requester_id": requester["id"],
             "title": "Budget approval"},
        )
    rel = await _pair(client, headers, requester["id"], approver["id"])
    assert rel["failed_interactions"] == 3
    assert rel["strength"] < strong, "rejections must deflate strength"
    assert rel["health_state"] in ("blocked", "at_risk")


# ------------------------------------------------------------- exact-once


async def test_replays_through_the_bus_are_exact_once(client, db_session_factory):
    org = await register_org(client, email="4f5_evonce@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-oa@test.co", "Aria", "Stone")
    b = await _hire(client, headers, "4f5-ob2@test.co", "Blake", "Reed")

    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.created", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"task_id": "4f5-rc", "assignee_id": a["id"],
                     "reporter_id": b["id"], "title": "Replay safe"},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)
    await _drain(db_session_factory)

    rel = await _pair(client, headers, a["id"], b["id"])
    assert rel["shared_tasks"] == 1
    async with db_session_factory() as db:
        count = (
            await db.execute(
                select(CollaborationEvidence.id).where(
                    CollaborationEvidence.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert len(count) == 1
