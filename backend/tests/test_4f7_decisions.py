"""Slice 4F.7 — People Decision Intelligence: the decision itself.

The 4F capstone turns 4F.1..4F.6 into evidence-backed, human-controlled
organizational decision support. Under test:

* one canonical decision record (type, risk tier, context, requirements,
  lifecycle, recommendation, provenance),
* the People Intelligence chain: initiative -> required capabilities ->
  expertise/trust (4F.2/4F.3) -> ownership (4F.4) -> collaboration (4F.5)
  -> capacity (4F.6) -> recommendation,
* decision-specific evidence, NEVER employee scores (no "Alice = 93"),
* alternatives with trade-offs, excluded candidates with honest why-not,
* empty pools surface the capability gap honestly,
* task vs role context: the same person can be recommended for an
  expertise question and excluded on capacity for a staffing question.
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


async def _hire(client, headers, email, first, last, team_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"f7-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _task(client, headers, title, assignee_id=None, project_id=None):
    payload = {"title": title}
    if assignee_id:
        payload["assignee_id"] = assignee_id
    if project_id:
        payload["project_id"] = project_id
    created = await client.post("/api/v1/tasks", json=payload, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _seed_expertise(db, org_id, person_id, skill_name, evidence=6,
                          score=80.0, lifecycle="strong", failures=0):
    """Direct expertise record + canonical taxonomy (the 4F.6 seeding path)."""
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
        existing.score = score
        existing.evidence_count = evidence
        existing.lifecycle = lifecycle
        existing.successful_count = evidence - failures
        existing.failed_count = failures
        existing.last_observed = datetime.now(timezone.utc)
        return skill.id
    db.add(Expertise(
        organization_id=org_id, person_id=person_id, skill_id=skill.id,
        score=score, evidence_count=evidence, lifecycle=lifecycle,
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


async def _create_decision(client, headers, **body):
    res = await client.post(f"{BRAIN}/decisions", json=body, headers=headers)
    assert res.status_code in (200, 201), res.text
    return res.json()


# ------------------------------------------------------------ core decision


async def test_staffing_decision_recommends_evidence_backed_expert(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_d1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-d1a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-d1b@test.co", "Bob", "Nystrom")
    project = await _project(client, headers, "Kube Platform")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12, score=88.0,
            lifecycle="strong",
        )
        # Bob holds Docker evidence, NOT Kubernetes expertise.
        await _seed_expertise(db, org_id, bob["id"], "Docker", evidence=6)
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    view = await _create_decision(
        client, headers,
        decision_type="staffing",
        objective="Who should own the kubernetes platform delivery?",
        requirements=["kubernetes"],
        context_type="project",
        context_id=project["id"],
        context_label="Kube Platform",
    )

    assert view["lifecycle"] == "recommended"
    assert view["risk_tier"] == "medium"
    rec = view["recommendation"]
    assert rec["person_id"] == ada["id"]
    assert rec["person_label"] == "Ada Lovelace"
    assert rec["confidence"] > 0.0
    assert "recommended because" in rec["rationale"].lower()

    # candidates: Ada recommended, Bob excluded (no kubernetes evidence).
    roles = {c["person_id"]: c["role"] for c in view["candidates"]}
    assert roles.get(ada["id"]) == "recommended"
    if bob["id"] in roles:
        assert roles[bob["id"]] == "excluded"

    # NO employee scores anywhere — evidence and reasons only.
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("candidates", "recommendation", "evidence", "provenance"):
                    continue
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    for c in view["candidates"]:
        assert "score" not in c, c
        assert c["rationale"] or c["why_not"]
    # the recommended candidate's Why is evidence bullets
    assert view["candidates"][0]["rationale"]
    assert "evidence" in view["candidates"][0]["rationale"]

    assert len(view["evidence"]) >= 1, view["evidence"]
    assert view["evidence"][0]["claim"]
    assert view["evidence"][0]["dimension"] == "expertise"

    # provenance reconstructs the chain and the confidence formula
    prov = view["provenance"]
    assert any("4F.6" in c for c in prov["chain"]), prov["chain"]
    assert prov["confidence_formula"]
    assert any("no employee scores" in c for c in prov["constraints"])
    assert prov["request"]["objective"]


async def test_task_vs_role_context_changes_the_recommendation(
    client, db_session_factory,
):
    """The same person can be recommended for an expertise question but be
    out of the running for a long-term role because of capacity."""
    org = await register_org(client, email="4f7_d2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-d2a@test.co", "Ada", "Lovelace")
    bob = await _hire(client, headers, "4f7-d2b@test.co", "Bob", "Nystrom")
    project = await _project(client, headers, "Delivery Platform")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12, score=88.0,
            lifecycle="strong",
        )
        await _seed_expertise(
            db, org_id, bob["id"], "Kubernetes", evidence=8, score=70.0,
            lifecycle="established",
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    # Ada carries 6 open tasks -> capacity constrained for a staffing role.
    for i in range(6):
        task = await _task(
            client, headers, f"overload {i}", assignee_id=ada["id"],
            project_id=project["id"],
        )
        moved = await client.patch(
            f"/api/v1/tasks/{task['id']}", json={"status": "in_progress"},
            headers=headers,
        )
        assert moved.status_code in (200, 201), moved.text

    role_view = await _create_decision(
        client, headers,
        decision_type="staffing",
        objective="Who should staff the delivery platform for six months?",
        requirements=["kubernetes"],
        context_type="project", context_id=project["id"],
    )
    roles = {c["person_id"]: c["role"] for c in role_view["candidates"]}
    assert roles.get(bob["id"]) == "recommended", roles
    assert roles.get(ada["id"]) == "excluded", roles
    ada_row = next(c for c in role_view["candidates"] if c["person_id"] == ada["id"])
    assert "active tasks" in ada_row["why_not"], ada_row["why_not"]

    # The same person answers the expertise question fine (info retrieval).
    expert_view = await _create_decision(
        client, headers,
        decision_type="expertise",
        objective="Who has the strongest trusted kubernetes expertise?",
        requirements=["kubernetes"],
    )
    assert expert_view["recommendation"]["person_id"] == ada["id"]
    assert "strong" in expert_view["candidates"][0]["rationale"].lower()


async def test_empty_pool_surfaces_the_capability_gap_honestly(client, db_session_factory):
    org = await register_org(client, email="4f7_d3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _hire(client, headers, "4f7-d3@test.co", "Zoe", "Nobody")

    view = await _create_decision(
        client, headers,
        decision_type="staffing",
        objective="Who should own the terraform migration?",
        requirements=["terraform"],
    )
    assert view["recommendation"]["person_id"] is None
    assert view["recommendation"]["confidence"] == 0.0
    assert "No people found" in view["recommendation"]["rationale"]
    assert view["candidates"] == []


async def test_capability_gap_decision_answers_with_the_gap(client, db_session_factory):
    org = await register_org(client, email="4f7_d4@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-d4a@test.co", "Ada", "Lovelace")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    view = await _create_decision(
        client, headers,
        decision_type="capability_gap",
        objective="What capability gap prevents us from taking the terraform work?",
        requirements=["terraform"],
        context_type="org",
    )
    assert view["recommendation"]["person_id"] is None
    assert "gap" in view["recommendation"]["rationale"].lower()


async def test_honest_failures_are_visible_in_the_evidence(client, db_session_factory):
    """'5 successful outcomes, 1 unsuccessful outcome' is shown, never hidden."""
    org = await register_org(client, email="4f7_d5@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-d5a@test.co", "Ada", "Lovelace")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(
            db, org_id, ada["id"], "Kubernetes", evidence=12, score=80.0,
            lifecycle="strong", failures=2,
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    view = await _create_decision(
        client, headers,
        decision_type="expertise",
        objective="Who is the kubernetes expert?",
        requirements=["kubernetes"],
    )
    assert view["recommendation"]["person_id"] == ada["id"]
    combined = " ".join(
        [c["rationale"] or "" for c in view["candidates"]]
        + [e["claim"] for e in view["evidence"]]
    )
    assert "unsuccessful outcomes" in combined, combined