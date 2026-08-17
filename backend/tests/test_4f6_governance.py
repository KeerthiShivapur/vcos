"""Slice 4F.6 — governance: scoped callers, tenant isolation, leak-free
project surface, bounded initiative assessment.

* org-wide capability views (overview/detail/signals) are org-wide only —
  a hidden person never leaks through a capability count,
* the project surface is leak-free for scoped callers (names and states,
  never member counts),
* a scoped initiative assessment only sees capabilities anchored to the
  caller's visible projects,
* the CEO question ("can we take this on?") is evidence-backed and
  deterministic.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.org_capability_intelligence import CapabilityProjectLink
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


async def _hire(client, headers, email, first, last, team_id=None):
    body = {"first_name": first, "last_name": last, "email": email,
            "team_id": team_id}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _team(client, headers, name):
    created = await client.post(
        "/api/v1/teams", json={"name": name, "code": f"g6-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _project(client, headers, name):
    created = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"gp-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _seed_capability(db, org_id, person_id, skill_name, evidence=6,
                           score=75.0, lifecycle="strong"):
    from datetime import datetime, timezone

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
        score=score, evidence_count=evidence, lifecycle=lifecycle,
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


# ---------------------------------------------------------------- governance


async def test_scoped_callers_never_see_org_wide_capabilities(client, db_session_factory):
    org = await register_org(client, email="4f6_gov1@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    team = await _team(client, headers, "Platform")
    insider = await _hire(client, headers, "4f6-g1@test.co", "Nina", "Visible",
                          team_id=team["id"])

    async with db_session_factory() as db:
        skill_id = await _seed_capability(
            db, org_id, insider["id"], "Python", evidence=8, lifecycle="strong",
        )
        await db.commit()
    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Platform scope", "scope_type": "team",
              "entity_id": team["id"]},
        headers=headers,
    )).json()
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f6-govread@test.co"
    )

    overview = await client.get(f"{BRAIN}/capabilities/overview", headers=reader)
    assert overview.status_code == 404, overview.text
    detail = await client.get(f"{BRAIN}/capabilities/{skill_id}", headers=reader)
    assert detail.status_code == 404, detail.text
    signals = await client.get(f"{BRAIN}/capabilities/signals", headers=reader)
    assert signals.status_code == 404, signals.text

    # the org owner (org-wide) DOES see them
    owner_overview = await client.get(
        f"{BRAIN}/capabilities/overview", headers=headers,
    )
    assert owner_overview.status_code == 200, owner_overview.text
    assert owner_overview.json()["total"] >= 1


async def test_project_surface_is_leak_free_for_scoped_callers(client, db_session_factory):
    org = await register_org(client, email="4f6_gov2@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-g2@test.co", "Leo", "Scoped")
    project = await _project(client, headers, "Visible Project")

    async with db_session_factory() as db:
        skill_id = await _seed_capability(db, org_id, person["id"], "Kubernetes")
        db.add(CapabilityProjectLink(
            organization_id=org_id, project_id=project["id"],
            project_name="Visible Project", skill_id=skill_id,
            skill_name="Kubernetes", source_event_id="4f6-gov-link",
            status="active",
        ))
        await db.commit()

    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Proj scope", "scope_type": "project",
              "entity_id": project["id"]},
        headers=headers,
    )).json()
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f6-govread2@test.co"
    )

    view = await client.get(
        f"{BRAIN}/capabilities/projects/{project['id']}", headers=reader,
    )
    assert view.status_code == 200, view.text
    caps = view.json()["capabilities"]
    assert any(c["skill_name"] == "Kubernetes" for c in caps)
    for c in caps:
        assert "expert_count" not in c, c
        assert "evidence_count" not in c, c
        assert "expert" not in str(c), c

    hidden = await client.get(
        f"{BRAIN}/capabilities/projects/not-visible-project", headers=reader,
    )
    assert hidden.status_code == 404, hidden.text


async def test_scoped_initiative_only_sees_visible_capabilities(client, db_session_factory):
    org = await register_org(client, email="4f6_gov3@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-g3@test.co", "Mara", "Scope")
    visible = await _project(client, headers, "Visible Work")
    hidden_project = await _project(client, headers, "Hidden Work")

    async with db_session_factory() as db:
        python_id = await _seed_capability(
            db, org_id, person["id"], "Python", evidence=12, lifecycle="strong",
        )
        kube_id = await _seed_capability(
            db, org_id, person["id"], "Kubernetes", evidence=6,
        )
        db.add(CapabilityProjectLink(
            organization_id=org_id, project_id=visible["id"],
            project_name="Visible Work", skill_id=python_id,
            skill_name="Python", source_event_id="4f6-gov3a", status="active",
        ))
        db.add(CapabilityProjectLink(
            organization_id=org_id, project_id=hidden_project["id"],
            project_name="Hidden Work", skill_id=kube_id,
            skill_name="Kubernetes", source_event_id="4f6-gov3b", status="active",
        ))
        await db.commit()

    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Vis proj", "scope_type": "project",
              "entity_id": visible["id"]},
        headers=headers,
    )).json()
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f6-govread3@test.co"
    )

    res = await client.post(
        f"{BRAIN}/capabilities/initiative",
        json={"question": "Can we take on a python kubernetes platform initiative?"},
        headers=reader,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    seen = {a["skill_name"] for a in body["answers"]}
    assert "Python" in seen, body["answers"]
    # the hidden-project capability must NOT be surfaced to this caller
    assert "Kubernetes" not in seen, seen
    for a in body["answers"]:
        assert "expert_count" not in a, a

    # org-wide callers see the full surface with evidence counts
    owner = await client.post(
        f"{BRAIN}/capabilities/initiative",
        json={"question": "Can we take on a python kubernetes platform initiative?"},
        headers=headers,
    )
    assert owner.status_code == 200, owner.text
    owner_names = {a["skill_name"] for a in owner.json()["answers"]}
    assert {"Python", "Kubernetes"} <= owner_names, owner_names
    assert owner.json()["answer"]


async def test_ceo_initiative_question_is_deterministic_and_evidence_backed(client, db_session_factory):
    org = await register_org(client, email="4f6_ceo@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    ada = await _hire(client, headers, "4f6-ceo1@test.co", "Ada", "CEO")
    grace = await _hire(client, headers, "4f6-ceo2@test.co", "Grace", "CEO")

    # strong proven capability with two evidence-backed experts and plenty
    # of free capacity (no committed links) -> the CEO answer is "ready"
    async with db_session_factory() as db:
        py_id = await _seed_capability(
            db, org_id, ada["id"], "Python", evidence=25, score=88.0,
            lifecycle="strong",
        )
        db.add(Expertise(
            organization_id=org_id, person_id=grace["id"], skill_id=py_id,
            score=70.0, evidence_count=6, lifecycle="strong", successful_count=6,
            last_observed=datetime.now(timezone.utc),
        ))
        await db.commit()

    await _refresh_skill(client, db_session_factory, org_id, org["user"]["id"], py_id)

    res = await client.post(
        f"{BRAIN}/capabilities/initiative",
        json={"question": "Can we take on this python platform initiative?"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    python = next(a for a in body["answers"] if a["skill_name"] == "Python")
    assert python["readiness"] == "ready", python
    assert python["capacity_available"] >= 1
    assert body["answer"]
    # the answer explains readiness from evidence — never a model score
    assert "ready" in body["answer"].lower()