"""Slice 4F.5 — evidence lineage, provenance, replay convergence.

Every collaboration claim must trace back to named evidence: which event
created it, when, and with what outcome. The ledger is append-only (events
are applied exactly once) so replays converge; nothing in the graph is ever
auto-corrected by the analysis itself.
"""

import math

from sqlalchemy import func, select

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


async def _hire(client, headers, email, first, last, team_id=None):
    created = await client.post(
        "/api/v1/employees",
        json={"first_name": first, "last_name": last, "email": email,
              "team_id": team_id},
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


async def test_evidence_provenance_is_traceable(client, db_session_factory):
    org = await register_org(client, email="4f5_lineage@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-lin1@test.co", "Ali", "Castro")
    b = await _hire(client, headers, "4f5-lin2@test.co", "Bella", "Diaz")

    await _publish(
        db_session_factory, org_id, "task.completed",
        org["user"]["id"],
        {"task_id": "4f5-l1", "project_id": "prj-4f5-l1",
         "assignee_id": a["id"], "reporter_id": b["id"], "title": "Ship docs"},
    )
    detail = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        headers=headers)).json()

    ev = detail["evidence"]
    assert len(ev) == 1
    row = ev[0]
    assert row["event_name"] == "task.completed"
    assert row["outcome"] == "success"
    assert row["points"] > 0
    assert row["source_type"] == "task"
    assert row["source_id"] == "4f5-l1"
    assert row["source_title"] == "Ship docs"
    assert row["project_id"] == "prj-4f5-l1"
    assert row["occurred_at"]
    assert row["id"]

    # the relationship carries the same provenance pointers.
    assert detail["source_type"] == "task"
    assert detail["last_source_id"] == "4f5-l1"


async def test_strength_explanation_traces_to_counters(client, db_session_factory):
    org = await register_org(client, email="4f5_explain@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-ex1@test.co", "Carmen", "Elias")
    b = await _hire(client, headers, "4f5-ex2@test.co", "Dmitri", "Farah")

    for i in range(3):
        await _publish(
            db_session_factory, org_id, "task.completed",
            org["user"]["id"],
            {"task_id": f"4f5-ex{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": f"Task {i}"},
        )
    detail = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        headers=headers)).json()

    assert detail["shared_tasks"] == 3
    assert detail["successful_interactions"] == 3
    explain = detail["explain"]
    assert "formula" in explain
    assert explain["evidence_count"] == 3
    assert explain["failure_ratio"] == 0.0

    # the formula input equals exactly the counters from the graph.
    wp = explain["weighted_positive"]
    assert wp > 0
    assert round(detail["strength"], 4) == round(1 - math.exp(-wp / 10.0), 4)


async def test_replay_converges_exactly_once(client, db_session_factory):
    org = await register_org(client, email="4f5_replay@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-rp1@test.co", "Emeka", "Gates")
    b = await _hire(client, headers, "4f5-rp2@test.co", "Fiona", "Hart")

    class FakeEvent:
        id = "replay-1"
        name = "task.completed"
        organization_id = org_id
        actor_id = org["user"]["id"]

    from app.intelligence.work_collaboration_engine import work_collaboration_engine

    payload = {"task_id": "4f5-rp1", "assignee_id": a["id"],
               "reporter_id": b["id"], "title": "Replay me"}
    # the same durable event (same id) is delivered three times: a producer
    # retry / bus re-delivery. It must apply exactly once.
    for _ in range(3):
        async with db_session_factory() as session:
            await work_collaboration_engine.record_event(
                session, organization_id=org_id, event=FakeEvent(), payload=payload,
            )
            await session.commit()

    detail = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        headers=headers)).json()
    assert detail["shared_tasks"] == 1, "replayed events must apply exactly once"
    assert detail["evidence_count"] == 1
    assert len(detail["evidence"]) == 1

    async with db_session_factory() as db:
        n_evidence = (
            await db.execute(
                select(func.count()).select_from(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == org_id,
                )
            )
        ).scalar_one()
    assert n_evidence == 1


async def test_ledger_is_append_only(client, db_session_factory):
    org = await register_org(client, email="4f5_append@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-ap1@test.co", "Grace", "Ines")
    b = await _hire(client, headers, "4f5-ap2@test.co", "Hugo", "Jiang")

    await _publish(
        db_session_factory, org_id, "task.created", org["user"]["id"],
        {"task_id": "4f5-ap1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "First"},
    )
    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-ap1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "First"},
    )

    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(CollaborationEvidence).where(
                    CollaborationEvidence.organization_id == org_id,
                ).order_by(CollaborationEvidence.created_at)
            )
        ).scalars().all()
        # two distinct events -> two evidence rows; the first is never edited.
        assert len(rows) == 2
        assert rows[0].event_name == "task.created"
        assert rows[1].event_name == "task.completed"
        assert rows[0].outcome == "neutral"
        assert rows[1].outcome == "success"


async def test_signal_lineage_and_resolution(client, db_session_factory):
    org = await register_org(client, email="4f5_sigin@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-si1@test.co", "Idris", "Khan")
    b = await _hire(client, headers, "4f5-si2@test.co", "Jana", "Lopez")

    for i in range(20):
        await _publish(
            db_session_factory, org_id, "task.completed", org["user"]["id"],
            {"task_id": f"4f5-si-ok{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": f"Good {i}"},
        )
    for i in range(11):
        await _publish(
            db_session_factory, org_id, "approval.rejected", b["id"],
            {"approval_id": f"4f5-si-rej{i}", "requester_id": a["id"],
             "title": f"Request {i}"},
        )
    await _drain(db_session_factory)
    signals = (await client.get(
        f"{BRAIN}/collaboration/signals", headers=headers)).json()
    assert signals["total"] >= 1
    sig = signals["signals"][0]
    # the signal explains its own basis (advisory, with kind and detail).
    assert sig["kind"] in ("negative_shift", "slowdown", "concentration", "gap")
    assert sig["status"] == "open"
    assert sig["detail"]
    assert sig["evidence"]

    resolved = await client.post(
        f"{BRAIN}/collaboration/signals/{sig['id']}/resolve", headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] == sig["id"]

    after = (await client.get(
        f"{BRAIN}/collaboration/signals", headers=headers)).json()
    assert after["total"] == 0, "resolved signals leave the open list"

    resolved_list = (await client.get(
        f"{BRAIN}/collaboration/signals?status=resolved", headers=headers)).json()
    assert any(s["id"] == sig["id"] for s in resolved_list["signals"])

    # the relation itself is untouched by lifecycle writes on signals.
    detail = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        headers=headers)).json()
    assert detail["failed_interactions"] == 11


async def test_changes_surface_lists_recent_evolution(client, db_session_factory):
    org = await register_org(client, email="4f5_changes@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-ch1@test.co", "Kofi", "Martins")
    b = await _hire(client, headers, "4f5-ch2@test.co", "Lena", "Novak")

    for i in range(5):
        await _publish(
            db_session_factory, org_id, "meeting.ended", org["user"]["id"],
            {"meeting_id": f"4f5-mtg{i}", "title": "Weekly",
             "attendees": [a["id"], b["id"]]},
        )
    await _drain(db_session_factory)
    changes = (await client.get(
        f"{BRAIN}/collaboration/changes", headers=headers)).json()
    assert changes["total"] >= 1
    # the graph is undirected: the pair may be stored in either order.
    assert any({c["person_a_id"], c["person_b_id"]} == {a["id"], b["id"]}
               for c in changes["changes"])
    # a fresh pair with real evidence reads as emerging.
    row = next(c for c in changes["changes"]
               if {c["person_a_id"], c["person_b_id"]} == {a["id"], b["id"]})
    assert row["change"] == "emerging"


async def test_relationship_carries_monthly_evolution_markers(client, db_session_factory):
    org = await register_org(client, email="4f5_month@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-mo1@test.co", "Marco", "Ott")
    b = await _hire(client, headers, "4f5-mo2@test.co", "Nina", "Pal")

    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-mo1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Month work"},
    )
    detail = (await client.get(
        f"{BRAIN}/collaboration/relationships/people/{a['id']}/with/{b['id']}",
        headers=headers)).json()
    assert detail["month_key"]
    assert detail["points_cur_month"] > 0
    assert detail["points_prev_month"] == 0

    # the org rollup accumulates the same totals - consistent, explainable.
    overview = (await client.get(f"{BRAIN}/collaboration/overview", headers=headers)).json()
    assert overview["total_relationships"] == 1
    assert overview["org_rollup"]["total_strength"] > 0
    assert overview["org_rollup"]["total_evidence"] == 1


async def test_person_ranking_uses_evidence_share(client, db_session_factory):
    org = await register_org(client, email="4f5_rank@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    hub = await _hire(client, headers, "4f5-rk1@test.co", "Obi", "Quartz")
    p1 = await _hire(client, headers, "4f5-rk2@test.co", "Pearl", "Reyes")
    p2 = await _hire(client, headers, "4f5-rk3@test.co", "Queen", "Silva")
    p3 = await _hire(client, headers, "4f5-rk4@test.co", "Ravi", "Tan")

    for i, other in enumerate((p1, p2, p3)):
        for j in range(i + 1):
            await _publish(
                db_session_factory, org_id, "task.completed", org["user"]["id"],
                {"task_id": f"4f5-rk{other['id']}{j}", "assignee_id": hub["id"],
                 "reporter_id": other["id"], "title": f"Work {i}"},
            )

    page = (await client.get(
        f"{BRAIN}/collaboration/people/{hub['id']}", headers=headers)).json()
    rels = page["relationships"]
    assert len(rels) == 3
    # ranked strongest first.
    assert rels[0]["other_person_id"] == p3["id"]
    assert rels[1]["other_person_id"] == p2["id"]
    assert rels[2]["other_person_id"] == p1["id"]
    # the person's share of total org strength is present (advisory context).
    assert page["rollup"]["share_of_org_strength"] == 1.0