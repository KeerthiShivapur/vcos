"""Slice 4F.7 — the BOUNDED "what if?" simulation.

Under test:

* deltas are computed against the decision's own context (required
  capabilities -> availability, concentration, workload, ownership) —
  this is NOT the prediction engine,
* every run is persisted on the decision and bounded (20 runs cap),
* the primary themselves cannot be simulated against ("what if Ada" when
  Ada IS the recommendation is a no-op),
* the brain's dry-run what-if answers the same model without persisting.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.skills_intelligence import CanonicalSkill, Expertise
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
    created = await client.post(
        "/api/v1/employees",
        json={"first_name": first, "last_name": last, "email": email},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _seed_expertise(db, org_id, person_id, skill_name, evidence=8):
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
        score=82.0, evidence_count=evidence, lifecycle="strong",
        successful_count=evidence,
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


async def _create_decision(client, headers, org_id, ada_id, bob_id, actor_id,
                           db_session_factory):
    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada_id, "Kubernetes", evidence=12)
        await _seed_expertise(db, org_id, bob_id, "Kubernetes", evidence=5)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, actor_id, kube_id)
    res = await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should staff the kubernetes delivery?",
            "requirements": ["kubernetes"],
            "context_type": "org",
        },
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


# ------------------------------------------------------------ bounded what-if


async def test_what_if_is_bounded_to_the_decision_context(client, db_session_factory):
    org = await register_org(client, email="4f7_s1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-s1a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-s1b@test.co", "Bob", "Nystrom")
    view = await _create_decision(
        client, headers, org_id, ada["id"], bob["id"], org["user"]["id"],
        db_session_factory,
    )
    decision_id = view["id"]
    assert view["recommendation"]["person_id"] == ada["id"]

    res = await client.post(
        f"{BRAIN}/decisions/{decision_id}/what-if",
        json={"person_id": bob["id"]}, headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    assert body["person"]["name"] == "Bob Nystrom"
    assert "Assigning Bob Nystrom" in body["verdict"]
    assert "Bounded to this decision's context" in body["verdict"]
    assert "not a prediction" in body["verdict"].lower()

    deltas = body["deltas"]
    assert "expertise" in deltas and "capacity" in deltas
    assert "workload" in deltas and "ownership" in deltas
    assert "concentration" in deltas

    # the run is persisted on the decision (bounded list, newest first)
    detail = (await client.get(
        f"{BRAIN}/decisions/{decision_id}", headers=headers,
    )).json()
    assert len(detail["simulations"]) == 1
    assert detail["simulations"][0]["verdict"] == body["verdict"]


async def test_what_if_refuses_the_primary_itself(client, db_session_factory):
    org = await register_org(client, email="4f7_s2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-s2a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-s2b@test.co", "Bob", "Nystrom")
    view = await _create_decision(
        client, headers, org_id, ada["id"], bob["id"], org["user"]["id"],
        db_session_factory,
    )
    res = await client.post(
        f"{BRAIN}/decisions/{view['id']}/what-if",
        json={"person_id": ada["id"]}, headers=headers,
    )
    assert res.status_code == 400, res.text
    assert "simulated against" in res.json()["detail"]


async def test_what_if_runs_are_bounded_per_decision(client, db_session_factory):
    org = await register_org(client, email="4f7_s3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-s3a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-s3b@test.co", "Bob", "Nystrom")
    carol = await _hire(client, headers, "4f7-s3c@test.co", "Carol", "Shaw")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes", evidence=12)
        await _seed_expertise(db, org_id, bob["id"], "Kubernetes", evidence=5)
        await _seed_expertise(db, org_id, carol["id"], "Kubernetes", evidence=5)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)
    view = (await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should staff delivery?",
            "requirements": ["kubernetes"],
            "context_type": "org",
        },
        headers=headers,
    )).json()

    from app.intelligence.people_decision_engine import MAX_SIMS_PER_DECISION

    for i in range(MAX_SIMS_PER_DECISION + 4):
        target = bob["id"] if i % 2 else carol["id"]
        res = await client.post(
            f"{BRAIN}/decisions/{view['id']}/what-if",
            json={"person_id": target}, headers=headers,
        )
        assert res.status_code in (200, 201), res.text

    detail = (await client.get(
        f"{BRAIN}/decisions/{view['id']}", headers=headers,
    )).json()
    assert len(detail["simulations"]) <= MAX_SIMS_PER_DECISION


async def test_dry_what_if_answers_without_persisting(client, db_session_factory):
    from app.intelligence.people_decision_engine import people_decision_engine

    org = await register_org(client, email="4f7_s4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-s4a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-s4b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes", evidence=12)
        await _seed_expertise(db, org_id, bob["id"], "Kubernetes", evidence=5)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    async with db_session_factory() as db:
        view = await people_decision_engine.dry_run(
            db, organization_id=org_id,
            decision_type="staffing",
            objective="Who should staff the kubernetes delivery?",
            requirements=["kubernetes"],
            context_type="org",
        )
        assert view["persisted"] is False
        assert view["recommendation"]["person_id"] == ada["id"]
        skill_ids = [s["id"] for s in view["requirements"]]
        sim = await people_decision_engine.dry_what_if(
            db, organization_id=org_id,
            primary_person_id=ada["id"], primary_label=ada["full_name"] or "Ada Lovelace",
            person_id=bob["id"], skill_ids=skill_ids,
        )
        assert "Assigning Bob Nystrom" in sim["verdict"]
        assert sim["deltas"]["workload"] >= 0