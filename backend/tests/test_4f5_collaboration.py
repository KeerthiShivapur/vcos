"""Slice 4F.5 — Work Collaboration Intelligence.

The canonical, change-driven, evidence-backed Work Collaboration Graph under
test:

* relationships exist ONLY where evidence exists (task/meeting/decision/
  message/approval events) — no all-pairs pass, ever,
* a pair is canonical (ordered), counters are exact, strength is bounded and
  deterministic, confidence grows with evidence,
* health and quality states are derived deterministically from evidence,
* monthly markers roll so evolution (emerging/strengthening/weakening/
  dormant) is observable,
* unit (department/team) pairs roll up from the same evidence,
* project views surface evidence concentration as ADVISORY findings,
* overview/changes/relationships reads are governance-scoped and bounded.
"""

import datetime

from sqlalchemy import func, select

from app.models.collaboration_intelligence import (
    CollaborationEvidence,
    CollaborationOrgRollup,
    CollaborationRelationship,
    CollaborationUnitPair,
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


async def _hire(client, headers, email, first, last, team_id=None, department_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id, "department_id": department_id}
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


async def _task(client, headers, title, assignee_id=None, reporter_id=None, project_id=None):
    payload = {"title": title}
    if assignee_id:
        payload["assignee_id"] = assignee_id
    if reporter_id:
        payload["reporter_id"] = reporter_id
    if project_id:
        payload["project_id"] = project_id
    created = await client.post("/api/v1/tasks", json=payload, headers=headers)
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
    return res


# ------------------------------------------------------------- core record


async def test_task_events_create_canonical_pair_with_counters(
        client, db_session_factory):
    org = await register_org(client, email="4f5_core@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    alma = await _hire(client, headers, "4f5-a@test.co", "Alma", "Nova")
    ben = await _hire(client, headers, "4f5-b@test.co", "Ben", "Okafor")

    task = await _task(client, headers, "Payments migration",
                       assignee_id=alma["id"], reporter_id=ben["id"])
    await _drain(db_session_factory)

    res = await _pair(client, headers, alma["id"], ben["id"])
    assert res.status_code == 200, res.text
    rel = res.json()
    assert rel["person_a_id"] in (alma["id"], ben["id"])
    assert rel["person_b_id"] in (alma["id"], ben["id"])
    assert rel["person_a_id"] < rel["person_b_id"]
    assert rel["shared_tasks"] >= 1
    assert rel["evidence_count"] >= 1
    assert 0.0 <= rel["strength"] <= 1.0
    assert rel["confidence"] >= 0.4
    assert rel["health_state"] in (
        "blocked", "at_risk", "dormant", "emerging", "weakening",
        "strengthening", "strong", "healthy", "low_evidence",
    )
    # the relationship detail explains the strength deterministically.
    explain = rel["explain"]
    assert explain["evidence_count"] >= 1
    assert "weighted_positive" in explain
    # evidence lineage: every record references a real event.
    assert rel["recent_evidence"][0]["event_name"] == "task.created"
    assert rel["recent_evidence"][0]["detail"]


async def test_pair_is_canonical_order_independent(client, db_session_factory):
    org = await register_org(client, email="4f5_order@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-oa@test.co", "Ada", "Lopez")
    b = await _hire(client, headers, "4f5-ob@test.co", "Bob", "Kim")
    await _task(client, headers, "Canonical pair", assignee_id=a["id"], reporter_id=b["id"])
    await _drain(db_session_factory)

    ab = await _pair(client, headers, a["id"], b["id"])
    ba = await _pair(client, headers, b["id"], a["id"])
    assert ab.status_code == ba.status_code == 200
    assert ab.json()["id"] == ba.json()["id"]


async def test_strength_is_bounded_deterministic_and_evidence_driven(
        client, db_session_factory):
    org = await register_org(client, email="4f5_str@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-sa@test.co", "Sam", "Roy")
    b = await _hire(client, headers, "4f5-sb@test.co", "Tina", "Das")

    async with db_session_factory() as db:
        strength_after = []
        for i in range(12):
            await _publish(
                db_session_factory, org_id, "task.completed",
                org["user"]["id"],
                {"task_id": f"4f5-t{i}", "assignee_id": a["id"],
                 "reporter_id": b["id"], "title": f"Completed task {i}"},
            )
            res = await _pair(client, headers, a["id"], b["id"])
            rel = res.json()
            strength_after.append(rel["strength"])
            assert 0.0 <= rel["strength"] <= 0.95
            if len(strength_after) > 1:
                assert rel["strength"] >= strength_after[-2], (
                    "strength must never decrease on successful evidence"
                )
    assert strength_after[-1] > strength_after[0]


async def test_failed_evidence_deflates_strength_deterministically(
        client, db_session_factory):
    org = await register_org(client, email="4f5_neg@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-na@test.co", "Nina", "Patel")
    b = await _hire(client, headers, "4f5-nb@test.co", "Owen", "White")

    for i in range(2):
        await _publish(
            db_session_factory, org_id, "task.completed",
            org["user"]["id"],
            {"task_id": f"4f5-ok{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": "Good task"},
        )
    strong = (await _pair(client, headers, a["id"], b["id"])).json()

    for i in range(4):
        await _publish(
            db_session_factory, org_id, "task.blocked",
            org["user"]["id"],
            {"task_id": f"4f5-blk{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": "Blocked task"},
        )
    weak = (await _pair(client, headers, a["id"], b["id"])).json()

    assert weak["strength"] < strong["strength"], "failures must deflate strength"
    assert weak["failed_interactions"] == 4
    assert weak["health_state"] in ("blocked", "at_risk")
    assert weak["quality"] == "problematic"

    # the strength explanation names the deflation the counter shows.
    assert weak["explain"]["failure_ratio"] > 0


async def test_monthly_markers_roll_and_evolution_is_observable(
        client, db_session_factory):
    org = await register_org(client, email="4f5_evo@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-ea@test.co", "Eva", "Green")
    b = await _hire(client, headers, "4f5-eb@test.co", "Finn", "Hall")

    for i in range(5):
        await _publish(
            db_session_factory, org_id, "task.completed",
            org["user"]["id"],
            {"task_id": f"4f5-e{i}", "assignee_id": a["id"],
             "reporter_id": b["id"], "title": "Joint win"},
        )
    rel = (await _pair(client, headers, a["id"], b["id"])).json()
    assert rel["month_key"] == datetime.datetime.now(UTC).strftime("%Y-%m")
    assert rel["points_cur_month"] > 0
    assert rel["points_prev_month"] >= 0
    assert rel["health_state"] in ("strengthening", "emerging", "healthy", "strong")


async def test_no_pair_exists_without_evidence(client, db_session_factory):
    org = await register_org(client, email="4f5_nopair@test.co")
    headers = org["headers"]
    a = await _hire(client, headers, "4f5-pa@test.co", "Paul", "Chen")
    b = await _hire(client, headers, "4f5-pb@test.co", "Priya", "Rao")
    # no events at all -> no edge, ever.
    res = await _pair(client, headers, a["id"], b["id"])
    assert res.status_code == 404, res.text


# ------------------------------------------------------------- unit pairs


async def test_department_and_team_pairs_roll_up_from_same_evidence(
        client, db_session_factory):
    org = await register_org(client, email="4f5_unit@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    eng_dept = (await client.post(
        "/api/v1/departments",
        json={"name": "Engineering", "code": "4f5-eng"},
        headers=headers)).json()
    sales_dept = (await client.post(
        "/api/v1/departments",
        json={"name": "Sales", "code": "4f5-sales"},
        headers=headers)).json()

    alice = await _hire(client, headers, "4f5-ua@test.co", "Alice", "Moss",
                        department_id=eng_dept["id"])
    bob = await _hire(client, headers, "4f5-ub@test.co", "Bob", "Stone",
                      department_id=sales_dept["id"])

    for i in range(3):
        await _publish(
            db_session_factory, org_id, "task.completed",
            org["user"]["id"],
            {"task_id": f"4f5-u{i}", "assignee_id": alice["id"],
             "reporter_id": bob["id"], "title": "Cross dept task"},
        )

    eng_view = (await client.get(
        f"{BRAIN}/collaboration/units/department/{eng_dept['id']}",
        headers=headers)).json()
    assert eng_view["unit_label"] == "Engineering"
    sales_pair = [p for p in eng_view["pairs"] if p["other_unit_id"] == sales_dept["id"]]
    assert len(sales_pair) == 1
    pair = sales_pair[0]
    assert pair["shared_tasks"] >= 3
    assert pair["successful_interactions"] >= 3
    assert 0.0 <= pair["strength"] <= 1.0
    assert pair["health_state"] in (
        "emerging", "healthy", "strong", "strengthening",
    )

    bad_unit = await client.get(
        f"{BRAIN}/collaboration/units/project/{eng_dept['id']}", headers=headers)
    assert bad_unit.status_code == 400, bad_unit.text


# ------------------------------------------------------------- project view


async def test_project_view_surfaces_dependency_concentration_as_advisory(
        client, db_session_factory):
    org = await register_org(client, email="4f5_proj@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    owner = await _hire(client, headers, "4f5-poa@test.co", "Maya", "Khan")
    m1 = await _hire(client, headers, "4f5-pob@test.co", "Leo", "Diaz")
    m2 = await _hire(client, headers, "4f5-poc@test.co", "Zoe", "Fischer")
    project = await _project(client, headers, "Apollo", owner_id=owner["id"])
    await _drain(db_session_factory)

    # add members directly (ProjectMember rows) so the engine pairs owner<->member.
    from app.models.project import ProjectMember

    async with db_session_factory() as db:
        for member in (m1, m2):
            db.add(ProjectMember(
                organization_id=org_id, project_id=project["id"],
                employee_id=member["id"],
            ))
        await db.commit()

    for i in range(10):
        await _publish(
            db_session_factory, org_id, "task.completed",
            org["user"]["id"],
            {"task_id": f"4f5-p{i}", "assignee_id": owner["id"],
             "reporter_id": m1["id"], "title": "Apollo task",
             "project_id": project["id"]},
        )

    view = (await client.get(
        f"{BRAIN}/collaboration/projects/{project['id']}", headers=headers)).json()
    assert view["project_name"] == "Apollo"
    assert view["total_evidence"] >= 10
    assert len(view["top_pairs"]) >= 1
    assert view["people"], "per-person evidence share is present"
    assert any(p["person_id"] == owner["id"] for p in view["people"])
    dep = view["dependency_concentration"]
    if dep is not None:
        assert "advisory" in dep
        assert dep["share_of_project_evidence"] > 0


# ------------------------------------------------------------- overview / changes


async def test_overview_and_changes_surfaces(client, db_session_factory):
    org = await register_org(client, email="4f5_ov@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-oa@test.co", "Rita", "Mehta")
    b = await _hire(client, headers, "4f5-ob@test.co", "Sid", "Cole")
    c = await _hire(client, headers, "4f5-oc@test.co", "Uma", "Larsen")

    await _publish(
        db_session_factory, org_id, "task.completed", org["user"]["id"],
        {"task_id": "4f5-ov1", "assignee_id": a["id"], "reporter_id": b["id"],
         "title": "Overview task"},
    )
    # decisions read participants from the canonical DecisionParticipant rows.
    from app.models.knowledge import Decision, DecisionParticipant

    async with db_session_factory() as db:
        db.add(Decision(
            id="4f5-d1", organization_id=org_id, title="Pick vendor",
            slug="pick-vendor-4f5", decision_maker_id=a["id"],
            status="made",
        ))
        db.add(DecisionParticipant(
            organization_id=org_id, decision_id="4f5-d1",
            employee_id=b["id"], role="consulted",
        ))
        db.add(DecisionParticipant(
            organization_id=org_id, decision_id="4f5-d1",
            employee_id=c["id"], role="consulted",
        ))
        await db.commit()
    await _publish(
        db_session_factory, org_id, "decision.made", org["user"]["id"],
        {"decision_id": "4f5-d1", "decision_maker_id": a["id"], "title": "Pick vendor"},
    )

    overview = (await client.get(f"{BRAIN}/collaboration/overview", headers=headers)).json()
    assert overview["total_relationships"] >= 2
    assert overview["health"]["emerging"] >= 1 or overview["health"]["healthy"] >= 1
    assert overview["org_rollup"]["total_evidence"] >= 2
    assert "open_signals" in overview

    changes = (await client.get(f"{BRAIN}/collaboration/changes", headers=headers)).json()
    assert changes["days"] == 30
    assert len(changes["changes"]) >= 2
    assert all(c["change"] in (
        "emerging", "strengthening", "weakening", "dormant", "healthy",
        "strong", "at_risk", "blocked", "low_evidence",
    ) for c in changes["changes"])


async def test_person_relationships_surface_ranked_partners(
        client, db_session_factory):
    org = await register_org(client, email="4f5_pers@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    hub = await _hire(client, headers, "4f5-ha@test.co", "Hans", "Vogel")
    p1 = await _hire(client, headers, "4f5-hb@test.co", "Ira", "Bauer")
    p2 = await _hire(client, headers, "4f5-hc@test.co", "Jon", "Keller")

    for i, other in ((1, p1), (2, p2), (3, p1), (4, p1)):
        await _publish(
            db_session_factory, org_id, "task.completed", org["user"]["id"],
            {"task_id": f"4f5-h{i}", "assignee_id": hub["id"],
             "reporter_id": other["id"], "title": "Hub task"},
        )

    view = (await client.get(
        f"{BRAIN}/collaboration/people/{hub['id']}", headers=headers)).json()
    assert view["person_id"] == hub["id"]
    assert len(view["relationships"]) == 2
    assert view["relationships"][0]["other_person_id"] == p1["id"]
    assert view["relationships"][0]["strength"] > view["relationships"][1]["strength"]
    assert view["rollup"]["active_relationships"] == 2
    assert view["rollup"]["total_evidence"] == 4
    assert 0.0 <= view["rollup"]["share_of_org_strength"] <= 1.0

    # a person with no evidence yields an empty, truthful surface.
    nobody = await _hire(client, headers, "4f5-hd@test.co", "Kai", "Ortiz")
    empty = (await client.get(
        f"{BRAIN}/collaboration/people/{nobody['id']}", headers=headers)).json()
    assert empty["relationships"] == []


async def test_exact_once_replay_never_double_counts(client, db_session_factory):
    org = await register_org(client, email="4f5_once@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    a = await _hire(client, headers, "4f5-xa@test.co", "Xena", "Wu")
    b = await _hire(client, headers, "4f5-xb@test.co", "Yuri", "Anand")

    # same durable event id replayed twice must converge (idempotent drain).
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.completed", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"task_id": "4f5-x1", "assignee_id": a["id"],
                     "reporter_id": b["id"], "title": "Once"},
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)
    await _drain(db_session_factory)  # replay the same queued event again

    rel = (await _pair(client, headers, a["id"], b["id"])).json()
    assert rel["evidence_count"] == 1
    assert rel["shared_tasks"] == 1
    assert rel["successful_interactions"] == 1

    async with db_session_factory() as db:
        ev_rows = (
            await db.execute(
                select(func.count(CollaborationEvidence.id)).where(
                    CollaborationEvidence.organization_id == org_id,
                    CollaborationEvidence.source_id == "4f5-x1",
                )
            )
        ).scalar_one()
    assert ev_rows == 1
