"""Slice 4F.7 — governance: the LOCKED privacy pipeline.

Under test:

* pipeline order: Identity -> Authorization -> Governance scope ->
  Accessible evidence -> Decision reasoning -> Answer (reasoning never
  runs before the permission check),
* scoped callers may create decisions ONLY on projects they can see;
  org-wide decisions are org-wide only,
* scoped callers never see decisions on other projects (detail, list,
  what-if all leak-free),
* the what-if surface respects the same scope as the decision itself,
* tenant isolation: another organization's decision is invisible.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models.skills_intelligence import CanonicalSkill, Expertise
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
        json={"name": name, "code": f"f7g-{name.lower()[:8]}"},
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


async def _scope(client, headers, project_id):
    return (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "P scope", "scope_type": "project",
              "entity_id": project_id},
        headers=headers,
    )).json()


# --------------------------------------------------------------- governance


async def test_scoped_callers_create_only_on_visible_projects(client, db_session_factory):
    org = await register_org(client, email="4f7_g1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-g1a@test.co", "Ada", "Lovelace")
    visible = await _project(client, headers, "Visible Proj")
    hidden = await _project(client, headers, "Hidden Proj")
    scope = await _scope(client, headers, visible["id"])
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f7-g1read@test.co"
    )

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    # on their own project: 200 and a real recommendation
    res = await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should own the visible project?",
            "requirements": ["kubernetes"],
            "context_type": "project",
            "context_id": visible["id"],
        },
        headers=reader,
    )
    assert res.status_code in (200, 201), res.text
    assert res.json()["recommendation"]["person_id"] == ada["id"]

    # org-wide / other-project contexts are refused BEFORE any reasoning
    res = await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should own the whole company?",
            "requirements": ["kubernetes"],
            "context_type": "org",
        },
        headers=reader,
    )
    assert res.status_code == 404, res.text
    res = await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should own the hidden project?",
            "requirements": ["kubernetes"],
            "context_type": "project",
            "context_id": hidden["id"],
        },
        headers=reader,
    )
    assert res.status_code == 404, res.text


async def test_scoped_callers_never_see_other_projects_decisions(
    client, db_session_factory,
):
    org = await register_org(client, email="4f7_g2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f7-g2a@test.co", "Ada", "Lovelace")
    mine = await _project(client, headers, "Mine Proj")
    other = await _project(client, headers, "Other Proj")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_id, ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], kube_id)

    # org owner creates decisions on both projects
    for project, tag in ((mine, "mine"), (other, "other")):
        res = await client.post(
            f"{BRAIN}/decisions",
            json={
                "decision_type": "staffing",
                "objective": f"Who should own the {tag} project?",
                "requirements": ["kubernetes"],
                "context_type": "project", "context_id": project["id"],
            },
            headers=headers,
        )
        assert res.status_code in (200, 201), res.text

    scope = await _scope(client, headers, mine["id"])
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f7-g2read@test.co"
    )

    # list: the hidden project's decision never appears
    lst = (await client.get(f"{BRAIN}/decisions", headers=reader)).json()
    assert len(lst["decisions"]) == 1, lst["decisions"]
    assert lst["decisions"][0]["context"]["context_id"] == mine["id"]

    # detail of a decision on their project: 200; on the other: 404
    mine_dec, other_dec = lst["decisions"][0], None
    other_dec = (await client.get(
        f"{BRAIN}/decisions", headers=headers,
    )).json()
    other_id = next(
        d["id"] for d in other_dec["decisions"]
        if d["context"]["context_id"] == other["id"]
    )
    assert (await client.get(
        f"{BRAIN}/decisions/{mine_dec['id']}", headers=reader,
    )).status_code == 200
    assert (await client.get(
        f"{BRAIN}/decisions/{other_id}", headers=reader,
    )).status_code == 404

    # what-if on the other project's decision: 404 too
    ada2 = await _hire(client, headers, "4f7-g2b@test.co", "Bob", "Nystrom")
    res = await client.post(
        f"{BRAIN}/decisions/{other_id}/what-if",
        json={"person_id": ada2["id"]}, headers=reader,
    )
    assert res.status_code == 404, res.text


async def test_decisions_are_tenant_isolated(client, db_session_factory):
    org_a = await register_org(client, email="4f7_g3a@test.co")
    org_b = await register_org(client, email="4f7_g3b@test.co")
    ada = await _hire(client, headers=org_a["headers"], email="4f7-g3@test.co",
                      first="Ada", last="Lovelace")

    async with db_session_factory() as db:
        kube_id = await _seed_expertise(db, org_a["organization"]["id"],
                                        ada["id"], "Kubernetes")
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_a["organization"]["id"],
                         org_a["user"]["id"], kube_id)

    a_view = (await client.post(
        f"{BRAIN}/decisions",
        json={
            "decision_type": "staffing",
            "objective": "Who should staff delivery?",
            "requirements": ["kubernetes"],
            "context_type": "org",
        },
        headers=org_a["headers"],
    )).json()
    assert a_view["recommendation"]["person_id"] == ada["id"]

    # organization B cannot see or act on A's decision (and vice versa)
    assert (await client.get(
        f"{BRAIN}/decisions/{a_view['id']}", headers=org_b["headers"],
    )).status_code == 404
    res = await client.post(
        f"{BRAIN}/decisions/{a_view['id']}/lifecycle",
        json={"action": "review"}, headers=org_b["headers"],
    )
    assert res.status_code == 404, res.text
    lst_b = (await client.get(f"{BRAIN}/decisions", headers=org_b["headers"])).json()
    assert lst_b["decisions"] == []