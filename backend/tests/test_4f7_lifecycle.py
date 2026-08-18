"""Slice 4F.7 — the human-governed decision lifecycle.

Under test:

* the state machine detected -> evaluated -> recommended -> reviewed ->
  approved | rejected -> executed -> verified -> outcome,
* every transition is audit-logged with its actor,
* invalid transitions are refused with the allowed moves,
* HIGH-tier people decisions (hiring, promotion, termination,
  compensation, disciplinary) are REFUSED by design — they stay entirely
  under human governance,
* the recorded outcome (success AND failure) becomes evidence for the
  NEXT evaluation — Decision -> Outcome -> Learning,
* lifecycle/outcome writes require employees:manage (humans decide).
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.people_decision import DecisionAudit
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
    existing = (
        await db.execute(
            select(Expertise).where(
                Expertise.organization_id == org_id,
                Expertise.person_id == person_id,
                Expertise.skill_id == skill.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.score = 82.0
        existing.evidence_count = evidence
        existing.lifecycle = "strong"
        existing.successful_count = evidence
        existing.last_observed = datetime.now(timezone.utc)
        return skill.id
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


async def _create_decision(client, headers, organization_id, person_id, actor_id,
                           db_session_factory, evidence: int = 8):
    async with db_session_factory() as db:
        skill_id = await _seed_expertise(
            db, organization_id, person_id, "Kubernetes",
            evidence=evidence,
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, organization_id, actor_id, skill_id)
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


async def _act(client, headers, decision_id, action, expect=200):
    res = await client.post(
        f"{BRAIN}/decisions/{decision_id}/lifecycle",
        json={"action": action}, headers=headers,
    )
    assert res.status_code == expect, res.text
    return res.json() if res.status_code in (200, 201) else None


# ----------------------------------------------------------------- lifecycle


async def test_full_human_governed_lifecycle_with_audit(client, db_session_factory):
    org = await register_org(client, email="4f7_l1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-l1a@test.co", "Ada", "Lovelace")
    view = await _create_decision(
        client, headers, org_id, ada["id"], org["user"]["id"], db_session_factory,
    )
    decision_id = view["id"]
    assert view["lifecycle"] == "recommended"

    reviewed = await _act(client, headers, decision_id, "review")
    assert reviewed["lifecycle"] == "reviewed"
    approved = await _act(client, headers, decision_id, "approve")
    assert approved["lifecycle"] == "approved"
    assert approved["outcome"]["status"] is None
    executed = await _act(client, headers, decision_id, "execute")
    assert executed["lifecycle"] == "executed"
    verified = await _act(client, headers, decision_id, "verify")
    assert verified["lifecycle"] == "verified"

    res = await client.post(
        f"{BRAIN}/decisions/{decision_id}/outcome",
        json={"status": "successful",
              "note": "delivery landed on time and stayed stable"},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    final = res.json()
    assert final["lifecycle"] == "outcome"
    assert final["outcome"]["status"] == "successful"
    assert final["outcome"]["note"]
    assert final["outcome"]["recorded_by"] == org["user"]["id"]

    # the append-only human governance trail names every transition
    actions = [a["action"] for a in final["audit"]]
    assert actions == [
        "detected", "evaluated", "recommended",
        "review", "approve", "execute", "verify", "outcome",
    ], actions
    assert all(a["actor_id"] for a in final["audit"] if a["action"] != "detected")


async def test_invalid_transitions_are_refused_with_the_allowed_moves(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_l2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-l2@test.co", "Ada", "Lovelace")
    view = await _create_decision(
        client, headers, org_id, ada["id"], org["user"]["id"], db_session_factory,
    )
    decision_id = view["id"]

    # cannot approve straight from 'recommended' (the human must review first)
    res = await client.post(
        f"{BRAIN}/decisions/{decision_id}/lifecycle",
        json={"action": "approve"}, headers=headers,
    )
    assert res.status_code == 400, res.text
    assert "cannot approve from lifecycle 'recommended'" in res.json()["detail"]

    await _act(client, headers, decision_id, "review")
    await _act(client, headers, decision_id, "reject")
    rejected = (await client.get(
        f"{BRAIN}/decisions/{decision_id}", headers=headers,
    )).json()
    assert rejected["lifecycle"] == "rejected"
    assert rejected["outcome"]["status"] is None

    # outcome is recordable on a rejected decision (the honest learning path)
    res = await client.post(
        f"{BRAIN}/decisions/{decision_id}/outcome",
        json={"status": "unsuccessful", "note": "the alternative failed too"},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text
    assert res.json()["outcome"]["status"] == "unsuccessful"


async def test_high_tier_people_decisions_are_refused(client, db_session_factory):
    """Constitution: hiring/promotion/termination stay under human governance."""
    org = await register_org(client, email="4f7_l3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-l3@test.co", "Ada", "Lovelace")

    async with db_session_factory() as db:
        skill_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], skill_id)

    for objective in (
        "Should we promote Ada to director?",
        "Should we hire a new platform lead?",
        "Should we terminate Bob's contract?",
        "Should we raise Daisy's compensation?",
        "Should we start disciplinary proceedings?",
    ):
        res = await client.post(
            f"{BRAIN}/decisions",
            json={
                "decision_type": "succession",
                "objective": objective,
                "requirements": ["kubernetes"],
                "risk_tier": "high",
            },
            headers=headers,
        )
        assert res.status_code == 400, res.text
        assert "human governance" in res.json()["detail"].lower(), res.text


async def test_the_outcome_feeds_the_next_evaluation(client, db_session_factory):
    """Decision -> Outcome -> Learning: the recorded outcome becomes
    evidence for the next recommendation."""
    org = await register_org(client, email="4f7_l4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-l4a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-l4b@test.co", "Bob", "Nystrom")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await _seed_expertise(db, org_id, bob["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    first = await _create_decision(
        client, headers, org_id, ada["id"], org["user"]["id"], db_session_factory,
        evidence=14,
    )
    assert first["recommendation"]["person_id"] == ada["id"]
    await _act(client, headers, first["id"], "review")
    await _act(client, headers, first["id"], "approve")
    res = await client.post(
        f"{BRAIN}/decisions/{first['id']}/outcome",
        json={"status": "successful", "note": "delivered"},
        headers=headers,
    )
    assert res.status_code in (200, 201), res.text

    second = await _create_decision(
        client, headers, org_id, bob["id"], org["user"]["id"], db_session_factory,
    )
    second_detail = (await client.get(
        f"{BRAIN}/decisions/{second['id']}", headers=headers,
    )).json()
    combined = " ".join(
        (c["rationale"] or "") + " " + (c["trade_off"] or "") + " "
        + (c["why_not"] or "")
        for c in second_detail["candidates"]
    )
    assert "prior recommendation outcomes" in combined, combined


async def test_lifecycle_and_outcome_require_employees_manage(client, db_session_factory):
    from tests import _brain4d6_helpers as h

    org = await register_org(client, email="4f7_l5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-l5a@test.co", "Ada", "Lovelace")
    project = (await client.post(
        "/api/v1/projects",
        json={"name": "Visible P", "code": "f7l5-1"}, headers=headers,
    )).json()

    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "P scope", "scope_type": "project",
              "entity_id": project["id"]},
        headers=headers,
    )).json()
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f7-l5read@test.co"
    )

    async with db_session_factory() as db:
        skill_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], skill_id)

    view = await _create_decision(
        client, headers, org_id, ada["id"], org["user"]["id"], db_session_factory,
    )
    res = await client.post(
        f"{BRAIN}/decisions/{view['id']}/lifecycle",
        json={"action": "review"}, headers=reader,
    )
    assert res.status_code == 403, res.text
    res = await client.post(
        f"{BRAIN}/decisions/{view['id']}/outcome",
        json={"status": "successful"}, headers=reader,
    )
    assert res.status_code == 403, res.text

    async with db_session_factory() as db:
        audits = (
            await db.execute(
                select(DecisionAudit).where(
                    DecisionAudit.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert len(audits) == 3  # detected + evaluated + recommended only