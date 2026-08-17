"""Slice 4F.7 — the Company Brain surface: decision questions and
change-driven detection.

Under test (the directive's universal queries):

* "Who should own this?" / "who can take this on without creating a
  capacity problem?" -> evidence-backed recommendations with Why,
  alternatives, trade-offs and provenance,
* "Why is Ada recommended?" -> the recommendation's evidence bullets,
* "Why not Bob?" -> the honest disqualifying evidence,
* "What if we assign Bob?" -> the bounded decision simulation,
* "What are the alternatives?" -> alternatives with trade-offs,
* "Where are we dependent on one person?" -> concentration findings,
* project.started DETECTS a staffing decision (signal only, never an
  autonomous action; exact-once on replay),
* every brain answer is read-only: nothing is persisted by a query.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.skills_intelligence import CanonicalSkill, Expertise
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
QUERY = "/api/v1/brain/knowledge/query"


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
    created = await client.post(
        "/api/v1/employees",
        json={"first_name": first, "last_name": last, "email": email},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"f7b-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _seed_expertise(db, org_id, person_id, skill_name, evidence=8,
                          score=82.0, failures=0):
    from app.people.skill_engine import skill_engine

    await skill_engine.ensure_taxonomy(db, organization_id=org_id)
    skill = (
        await db.execute(
            select(CanonicalSkill).where(
                CanonicalSkill.organization_id == org_id,
                CanonicalSkill.canonical_name == skill_name,
            )
        )
    ).scalar_one_or_none()
    assert skill is not None
    db.add(Expertise(
        organization_id=org_id, person_id=person_id, skill_id=skill.id,
        score=score, evidence_count=evidence, lifecycle="strong",
        successful_count=evidence - failures, failed_count=failures,
        last_observed=datetime.now(timezone.utc),
    ))
    return skill.id


async def _refresh_skill(client, db_session_factory, org_id, actor_id, skill_id):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="skill.updated", organization_id=org_id, actor_id=actor_id,
            payload={"skill_id": skill_id}, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _ask(client, headers, question):
    res = await client.post(QUERY, json={"question": question}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------- brain queries


async def test_who_should_own_returns_evidence_backed_recommendation(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_b1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b1a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-b1b@test.co", "Bob", "Nystrom")
    project = await _project(client, headers, "Kube Platform")
    # both are involved in the project: Bob enters the candidate pool as a
    # member, where his lack of kubernetes evidence disqualifies him.
    for person_id, name in ((ada["id"], "Ada"), (bob["id"], "Bob")):
        res = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"employee_id": person_id}, headers=headers,
        )
        assert res.status_code in (200, 201), res.text

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12, score=88.0,
        )
        await _seed_expertise(db, org_id, bob["id"], "Docker", evidence=6)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "who should own the kubernetes platform?")
    assert body["intent"] == "people_decision", body
    assert body["kind"] == "recommendation"
    assert body["recommendation"]["person_id"] == ada["id"]
    assert "Recommended: Ada Lovelace" in body["answer"]
    assert body["candidates"], body
    roles = {c["person_id"]: c["role"] for c in body["candidates"]}
    assert roles[ada["id"]] == "recommended"
    assert roles[bob["id"]] == "excluded"
    assert "no evidence in the required capabilities" in next(
        c["why_not"] for c in body["candidates"] if c["person_id"] == bob["id"]
    )
    # context-aware: the question already knows it is about this project
    assert body["context"]["context_id"] == project["id"]
    # read-only: a Company Brain query never persists a decision
    lst = (await client.get(f"{BRAIN}/decisions", headers=headers)).json()
    assert lst["decisions"] == []


async def test_who_can_take_this_on_answers_capacity(client, db_session_factory):
    org = await register_org(client, email="4f7_b2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b2a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-b2b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=10,
        )
        await _seed_expertise(db, org_id, bob["id"], "Kubernetes", evidence=6)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(
        client, headers,
        "who can take on the kubernetes work without creating a capacity problem?",
    )
    assert body["intent"] == "people_decision"
    assert body["decision_type"] == "capacity"
    assert body["recommendation"]["person_label"] == "Ada Lovelace"


async def test_why_is_ada_recommended_explains_from_evidence(client, db_session_factory):
    org = await register_org(client, email="4f7_b3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b3@test.co", "Ada", "Lovelace")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "why is ada recommended for kubernetes?")
    assert body["intent"] == "people_decision", body
    assert body["kind"] == "why_recommended", body
    assert "Ada" in body["answer"]
    assert "evidence" in body["answer"].lower()


async def test_why_not_bob_answers_with_honest_negative_evidence(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_b4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b4a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-b4b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12,
        )
        # Bob's honest history: fewer trusted outcomes, failures recorded
        await _seed_expertise(
            db, org_id, bob["id"], "Kubernetes", evidence=3, score=40.0,
            failures=2,
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "why not bob?")
    assert body["intent"] == "people_decision"
    assert body["kind"] == "why_not"
    assert "Bob" in body["answer"]
    assert "not recommended because" in body["answer"].lower()
    assert "unsuccessful outcomes" in body["answer"]


async def test_what_if_we_assign_answers_a_bounded_delta(client, db_session_factory):
    org = await register_org(client, email="4f7_b5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b5a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-b5b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12, score=88.0,
        )
        await _seed_expertise(db, org_id, bob["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "what if we assign bob to delivery?")
    assert body["intent"] == "people_decision"
    assert body["kind"] == "what_if", body
    assert body["person"]["name"] == "Bob Nystrom"
    assert "Assigning Bob Nystrom" in body["answer"]
    assert body["simulation"]["deltas"]


async def test_alternatives_are_surfaced_with_trade_offs(client, db_session_factory):
    org = await register_org(client, email="4f7_b6@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b6a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-b6b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12,
        )
        await _seed_expertise(
            db, org_id, bob["id"], "Kubernetes", evidence=6, score=70.0,
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "what are the alternatives for kubernetes?")
    assert body["intent"] == "people_decision"
    assert body["kind"] == "alternatives"
    assert "Primary: Ada Lovelace" in body["answer"]
    assert "Alternative" in body["answer"]


async def test_single_person_dependency_is_surfaced(client, db_session_factory):
    org = await register_org(client, email="4f7_b7@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b7@test.co", "Ada", "Lovelace")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    body = await _ask(client, headers, "where are we dependent on one person?")
    assert body["intent"] == "people_decision"
    assert body["kind"] == "dependency"
    assert any(
        float(a.get("concentration_share") or 0) >= 0.6 for a in body["answers"]
    ), body["answers"]
    assert "concentrated" in body["answer"].lower()


# ---------------------------------------------------- change-driven detection


async def test_project_started_detects_a_staffing_decision_exact_once(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_b8@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-b8@test.co", "Ada", "Lovelace")
    project = await _project(client, headers, "Neo Payload")

    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="project.started", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={
                "project_id": project["id"], "name": "Neo Payload",
                "actor_id": org["user"]["id"], "owner_id": ada["id"],
            },
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    lst = (await client.get(f"{BRAIN}/decisions", headers=headers)).json()
    assert len(lst["decisions"]) == 1, lst["decisions"]
    detected = lst["decisions"][0]
    assert detected["decision_type"] == "staffing"
    assert detected["lifecycle"] == "detected"
    assert detected["context"]["context_id"] == project["id"]
    assert detected["recommended_person_label"] is None

    # detection is a signal only: no evaluation, no recommendation, no action
    detail = (await client.get(
        f"{BRAIN}/decisions/{detected['id']}", headers=headers,
    )).json()
    assert detail["recommendation"]["rationale"] is None
    assert [a["action"] for a in detail["audit"]] == ["detected"]

    # replay is exact-once: the same event id never creates a second record
    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="project.started", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={
                "project_id": project["id"], "name": "Neo Payload",
                "actor_id": org["user"]["id"], "owner_id": ada["id"],
            },
            enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)
    lst = (await client.get(f"{BRAIN}/decisions", headers=headers)).json()
    assert len(lst["decisions"]) == 1, lst["decisions"]