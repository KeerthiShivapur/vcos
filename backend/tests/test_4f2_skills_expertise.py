"""Slice 4F.2 — Universal Skills & Expertise Intelligence.

The audit-driven slice separates WHAT someone is associated with (skills,
declared or observed) from WHAT they have actually demonstrated with evidence
(expertise). Every rule here is deterministic and governed:

* skills never grant expertise; only canonical evidence does,
* evidence is exact-once under replay and every claim carries lineage,
* weak mentions alone can never produce real expertise (emerging cap),
* lifecycle is deterministic: observed -> emerging -> established -> strong ->
  authoritative, inactivity produces ``dormant`` (peak preserved),
* discovery/aggregates are governance-scoped BEFORE data assembly (a hidden
  person never leaks through a count or a ranking),
* tenants are isolated end-to-end,
* no operating-layer mutation ever happens on read paths.
"""

import datetime

from sqlalchemy import func, select

from app.models.employee import Employee, EmployeeSkill
from app.models.intelligence import ExpertiseHistory
from app.models.knowledge import KnowledgeTopic
from app.models.notification import Event as EventRow
from app.models.skill import ExpertiseScore, Skill
from app.models.skills_intelligence import (
    CanonicalSkill,
    CapabilityAggregate,
    Expertise as ExpertiseState,
    ExpertiseEvidence,
    PersonSkill,
    SkillAlias,
)
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
KNOWLEDGE = "/api/v1/brain/knowledge"


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


async def _department(client, headers, name="Engineering", code=None):
    created = await client.post(
        "/api/v1/departments",
        json={"name": name, "code": code or f"dept-{name.lower()[:8]}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _team(client, headers, name="Platform", code=None, department_id=None):
    created = await client.post(
        "/api/v1/teams",
        json={"name": name, "code": code or f"team-{name.lower()[:8]}",
              "department_id": department_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _team_scope(client, headers, team_id):
    created = await client.post(
        "/api/v1/governance/scopes",
        json={"name": f"People scope {team_id[:6]}", "scope_type": "team",
              "entity_id": team_id},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _publish_task(client, db_session_factory, org_id, actor_id, employee_id,
                        task_id, title):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="task.completed", organization_id=org_id, actor_id=actor_id,
            payload={"employee_id": employee_id, "task_id": task_id, "title": title},
            enqueue=False, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


# ---------------------------------------------------------------- taxonomy


async def test_taxonomy_seed_aliases_and_parents(client):
    org = await register_org(client, email="4f2_tax@test.co")
    headers = org["headers"]

    listing = (await client.get(f"{BRAIN}/expertise/skills", headers=headers)).json()
    by_name = {entry["canonical_name"]: entry for entry in listing["skills"]}
    assert listing["total"] >= 26, listing["total"]

    assert by_name["Python"]["category"] == "Programming Languages"
    assert by_name["PostgreSQL"]["category"] == "Databases"
    assert "postgres" in by_name["PostgreSQL"]["aliases"]
    assert "pg" in by_name["PostgreSQL"]["aliases"]
    assert by_name["Deep Learning"]["parent_skill"] == "Machine Learning"
    assert by_name["Kubernetes"]["provenance"] == "system_seed"

    resolved = (
        await client.get(f"{BRAIN}/expertise/search", params={"q": "postgres"}, headers=headers)
    ).json()
    assert resolved["resolved_skill_ids"], resolved
    skill_names = {s["skill_name"] for s in resolved["skills"]}
    assert "PostgreSQL" in skill_names, skill_names

    pg_filtered = (
        await client.get(f"{BRAIN}/expertise/skills", params={"q": "pg"}, headers=headers)
    ).json()
    assert any(s["canonical_name"] == "PostgreSQL" for s in pg_filtered["skills"])

    unknown = (
        await client.get(f"{BRAIN}/expertise/skills", params={"q": "time-travel"}, headers=headers)
    ).json()
    assert unknown["total"] == 0


async def test_alias_collision_flags_ambiguity_never_merges(client, db_session_factory):
    org = await register_org(client, email="4f2_alias@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await client.get(f"{BRAIN}/expertise/skills", headers=headers)

    from app.people.skill_engine import SkillError, skill_engine

    async with db_session_factory() as db:
        await skill_engine.ensure_taxonomy(db, organization_id=org_id)
        await db.commit()
        # "mongo" already resolves to MongoDB; strict create refuses, silently
        # mutating nothing.
        try:
            await skill_engine.create_canonical(
                db, organization_id=org_id, name="Amazon DocumentDB", aliases=["mongo"],
            )
            raise AssertionError("SkillError expected for a reserved alias")
        except SkillError:
            pass
        await db.rollback()

        owner = await skill_engine.resolve_term(
            db, organization_id=org_id, term="mongo"
        )
        assert owner is not None and owner.canonical_name == "MongoDB", owner

        # explicit collision attachment flags BOTH sides ambiguous — the
        # alias silently disappears from resolution instead of picking a side.
        rival = await skill_engine.create_canonical(
            db, organization_id=org_id, name="AtomDB",
        )
        existing_alias, attached = await skill_engine._attach_alias(
            db, organization_id=org_id, skill=rival, alias="mongo",
        )
        assert attached is False
        assert existing_alias.status == "ambiguous"
        await db.commit()
        ambiguous = await skill_engine.resolve_term(
            db, organization_id=org_id, term="mongo"
        )
        assert ambiguous is None, "ambiguous aliases resolve to nothing"

    listing = (await client.get(f"{BRAIN}/expertise/skills", headers=headers)).json()
    by_name = {entry["canonical_name"]: entry for entry in listing["skills"]}
    assert "mongo" in by_name["MongoDB"]["ambiguous_aliases"]


# ---------------------------------------------------------------- skills vs expertise


async def test_declared_skill_is_association_not_expertise(client, db_session_factory):
    org = await register_org(client, email="4f2_decl@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-decl@test.co", "Ada", "Lin")

    declared = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "PyTorch", "level": 5},
        headers=headers,
    )
    assert declared.status_code == 200, declared.text
    assert declared.json()["skill_name"] == "PyTorch"
    assert declared.json()["source"] == "declared"
    assert declared.json()["status"] == "active"

    skills = (await client.get(f"{BRAIN}/people/{person['id']}/skills", headers=headers)).json()
    assert skills["total"] == 1, skills
    association = skills["skills"][0]
    assert association["declared_level"] == 5
    assert association["source"] == "declared"
    assert association["expertise"] is None, "declared skills yield no expertise"

    expertise = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    assert expertise["total"] == 0, expertise

    async with db_session_factory() as db:
        # legacy operating-layer mirror stays coherent (EmployeeSkill), but the
        # canonical state has zero evidence-derived Expertise rows.
        emp_skills = (
            await db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.organization_id == org_id,
                    EmployeeSkill.employee_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(emp_skills) == 1
        evidence = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == org_id,
                    ExpertiseEvidence.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(evidence) == 0, "no evidence means no expertise"


async def test_invalid_declarations_are_rejected(client):
    org = await register_org(client, email="4f2_declb@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f2-declb@test.co", "Bo", "Mercer")

    neither = await client.post(
        f"{BRAIN}/people/{person['id']}/skills", json={"level": 3}, headers=headers
    )
    assert neither.status_code == 400, neither.text

    bogus_level = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "Python", "level": 99},
        headers=headers,
    )
    assert bogus_level.status_code == 200, bogus_level.text
    assert bogus_level.json()["declared_level"] == 5, "level is clamped to 1..5"


# ---------------------------------------------------------------- evidence pipeline


async def test_task_completion_creates_strong_evidence(client, db_session_factory):
    org = await register_org(client, email="4f2_evid@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-evid@test.co", "Cam", "Duarte")

    # legacy Phase-2 skill exists -> the canonical state must mirror into it
    legacy = await client.post(
        "/api/v1/expertise/skills",
        json={"name": "PostgreSQL", "category": "Databases",
              "description": "open source relational database"},
        headers=headers,
    )
    assert legacy.status_code == 201, legacy.text

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f2-t1",
        title="Migrated the postgresql cluster to a new hardware generation",
    )

    async with db_session_factory() as db:
        evidence = list(
            (
                await db.execute(
                    select(ExpertiseEvidence).where(
                        ExpertiseEvidence.organization_id == org_id,
                        ExpertiseEvidence.person_id == person["id"],
                    )
                )
            ).scalars().all()
        )
        assert len(evidence) == 1, evidence
        row = evidence[0]
        assert row.strength == "strong"
        assert row.evidence_type == "task.completed"
        assert row.source_type == "task"
        assert row.source_id == "4f2-t1"
        assert row.source_title == "Migrated the postgresql cluster to a new hardware generation"

        skill = await db.get(CanonicalSkill, row.skill_id)
        assert skill.canonical_name == "PostgreSQL"

        state = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == org_id,
                    ExpertiseState.person_id == person["id"],
                    ExpertiseState.skill_id == row.skill_id,
                )
            )
        ).scalars().one_or_none()
        assert state is not None
        assert state.score > 0 and state.evidence_count == 1
        assert state.strong_count == 1 and state.medium_count == 0
        assert state.lifecycle in ("observed", "emerging")

        # legacy mirror: ExpertiseScore + audit history + employee rollup
        mirrored = (
            await db.execute(
                select(ExpertiseScore).where(
                    ExpertiseScore.organization_id == org_id,
                    ExpertiseScore.employee_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(mirrored) == 1 and mirrored[0].score > 0
        audit = (
            await db.execute(
                select(ExpertiseHistory).where(
                    ExpertiseHistory.organization_id == org_id,
                    ExpertiseHistory.employee_id == person["id"],
                )
            )
        ).scalars().all()
        assert audit and audit[0].after > 0

        employee_rollup = (
            await db.execute(
                select(Employee.expertise_score).where(
                    Employee.id == person["id"], Employee.organization_id == org_id
                )
            )
        ).scalar_one()
        assert float(employee_rollup or 0) > 0

    personnel = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    assert personnel["total"] == 1
    top = personnel["expertise"][0]
    assert top["skill_name"] == "PostgreSQL"
    assert top["evidence_count"] == 1 and top["strong_count"] == 1
    assert top["score"] > 0 and top["confidence"] > 0

    # lineage: every claim is explainable with canonical ids
    lineage = (
        await client.get(
            f"{BRAIN}/people/{person['id']}/expertise/{top['skill_id']}/evidence",
            headers=headers,
        )
    ).json()
    assert len(lineage["evidence"]) == 1
    item = lineage["evidence"][0]
    assert item["evidence_id"] and item["event_id"]
    assert item["strength"] == "strong"
    assert item["source_id"] == "4f2-t1"


async def test_event_replay_is_exact_once(client, db_session_factory):
    org = await register_org(client, email="4f2_rply@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-rply@test.co", "Dana", "Eriksen")

    from app.events.event_bus import event_bus
    from app.events import handlers as hand

    async with db_session_factory() as db:
        event = await event_bus.publish(
            db,
            name="task.completed",
            organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"employee_id": person["id"], "task_id": "4f2-t2",
                     "title": "Built the python data pipeline"},
            enqueue=False, flush=False,
        )
        await db.commit()

        await hand.handle_task_completed(db, event, {
            "employee_id": person["id"], "task_id": "4f2-t2",
            "title": "Built the python data pipeline",
        })
        await hand.handle_task_completed(db, event, {
            "employee_id": person["id"], "task_id": "4f2-t2",
            "title": "Built the python data pipeline",
        })
        await db.commit()

        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == org_id,
                    ExpertiseEvidence.person_id == person["id"],
                    ExpertiseEvidence.event_id == event.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1, "the same durable event writes one evidence row"

        states = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == org_id,
                    ExpertiseState.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(states) == 1 and states[0].evidence_count == 1


async def test_declared_skills_never_feed_evidence(client, db_session_factory):
    """Regression: a declared skill is an association; unrelated activities
    must never fabricate evidence for it."""
    org = await register_org(client, email="4f2_declfeed@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-declfeed@test.co", "Dino", "Branco")

    declared = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "PyTorch", "level": 4}, headers=headers,
    )
    assert declared.status_code == 200, declared.text

    for index in range(3):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], person["id"],
            task_id=f"4f2-df{index}", title=f"Built the python data pipeline {index}",
        )

    expertise = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    names = {e["skill_name"]: e for e in expertise["expertise"]}
    assert "Python" in names and names["Python"]["evidence_count"] == 3, names
    assert "PyTorch" not in names, "declared skills never become evidence"

    async with db_session_factory() as db:
        pytorch_evidence = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == org_id,
                    ExpertiseEvidence.person_id == person["id"],
                    ExpertiseEvidence.skill_id == names["Python"]["skill_id"],
                )
            )
        ).scalars().all()
        assert len(pytorch_evidence) == 3
        all_evidence = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == org_id,
                    ExpertiseEvidence.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert all(e.skill_id == names["Python"]["skill_id"] for e in all_evidence)


async def test_live_style_document_events_resolve_author_from_entity(
    client, db_session_factory
):
    """Regression: live knowledge events carry {entity_type, entity_id, title};
    the handler must recover authorship from the entity row itself."""
    org = await register_org(client, email="4f2_entity@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-entity@test.co", "Eva", "Hale")

    from app.models.knowledge import Document
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        doc = Document(
            organization_id=org_id, title="Postgres tuning runbook",
            slug="postgres-tuning-runbook", status="published",
            owner_id=person["id"],
        )
        db.add(doc)
        await db.flush()
        event = await event_bus.publish(
            db, name="document.created", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"entity_type": "document", "entity_id": doc.id,
                     "title": "Postgres tuning runbook"},
            enqueue=False, flush=False,
        )
        await db.commit()
        await _drain(db_session_factory)

    expertise = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    seen = {e["skill_name"] for e in expertise["expertise"]}
    assert "PostgreSQL" in seen, expertise


async def test_multi_source_evidence_raises_confidence_and_lifecycle(
    client, db_session_factory
):
    org = await register_org(client, email="4f2_mult@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-mult@test.co", "Erin", "Falk")

    # three completed tasks + two documents + one decision all on python
    for index in range(3):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], person["id"],
            task_id=f"4f2-pt{index}",
            title=f"Implemented python data pipeline number {index}",
        )
    for doc_id in ("4f2-doc1", "4f2-doc2"):
        from app.events.event_bus import event_bus

        async with db_session_factory() as db:
            await event_bus.publish(
                db, name="document.created", organization_id=org_id,
                actor_id=org["user"]["id"],
                payload={"author_id": person["id"], "document_id": doc_id,
                         "title": "Python architecture notes"},
                enqueue=False, flush=False,
            )
            await db.commit()
        await _drain(db_session_factory)
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="decision.made", organization_id=org_id,
            actor_id=org["user"]["id"],
            payload={"decision_maker_id": person["id"], "decision_id": "4f2-d1",
                     "title": "Standardize on python tooling"},
            enqueue=False, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)

    people = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    top = people["expertise"][0]
    assert top["skill_name"] == "Python", top
    assert top["evidence_count"] >= 6, top
    assert top["strong_count"] >= 3, top
    assert top["medium_count"] >= 1, top
    # five strong sources + one medium: deterministic lifecycle must advance
    assert top["lifecycle"] in ("established", "strong", "authoritative"), top
    assert top["confidence"] > 0.5, top


async def test_weak_mentions_never_advance_beyond_emerging(client, db_session_factory):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f2_weak@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-weak@test.co", "Finn", "Gao")
    await client.get(f"{BRAIN}/expertise/skills", headers=headers)

    async with db_session_factory() as db:
        for index in range(8):
            await expertise_engine.record_evidence(
                db, organization_id=org_id, employee_id=person["id"],
                event_name="meeting.ended",
                tokens=["python", "discussion"],
                event_id=f"4f2-meet{index}",
                source_type="meeting", source_id=f"4f2-meeting-{index}",
                source_title="Python sync",
            )
        await db.commit()
        states = (
            await db.execute(
                select(ExpertiseState).where(
                    ExpertiseState.organization_id == org_id,
                    ExpertiseState.person_id == person["id"],
                )
            )
        ).scalars().all()
        assert len(states) >= 1
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.organization_id == org_id,
                    ExpertiseEvidence.person_id == person["id"],
                    ExpertiseEvidence.strength == "weak",
                )
            )
        ).scalars().all()
        assert len(rows) == 8
        await db.rollback()

    personnel = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    assert personnel["total"] >= 1
    for entry in personnel["expertise"]:
        assert entry["weak_count"] > 0 and entry["strong_count"] == 0
        assert entry["lifecycle"] == "emerging", \
            "weak mentions alone can never produce real expertise"


async def test_knowledge_topic_linkage_appears_in_lineage(client, db_session_factory):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f2_topic@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-topic@test.co", "Grace", "Hicks")

    async with db_session_factory() as db:
        topic = KnowledgeTopic(
            organization_id=org_id, name="database migrations",
            aliases_json='["db migration"]', category="Engineering",
        )
        db.add(topic)
        await db.flush()
        await expertise_engine.record_evidence(
            db, organization_id=org_id, employee_id=person["id"],
            event_name="task.completed",
            tokens=["postgresql", "migration"],
            event_id="4f2-topic-ev", source_type="task",
            source_id="4f2-topic-task", source_title="Write migration scripts",
            topic_id=topic.id,
        )
        await db.commit()

    personnel = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    assert personnel["total"] == 1
    skill_id = personnel["expertise"][0]["skill_id"]
    lineage = (
        await client.get(
            f"{BRAIN}/people/{person['id']}/expertise/{skill_id}/evidence",
            headers=headers,
        )
    ).json()
    assert lineage["evidence"][0]["topic"] == "database migrations"


async def test_dormancy_driven_by_inactivity_and_peak_preserved(client, db_session_factory):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f2_dorm@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-dorm@test.co", "Hugo", "Innes")

    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=400)
    async with db_session_factory() as db:
        await expertise_engine.record_evidence(
            db, organization_id=org_id, employee_id=person["id"],
            event_name="task.completed",
            tokens=["python", "deployment"],
            event_id="4f2-dorm-ev", source_type="task",
            source_id="4f2-dorm-task", source_title="Old python work",
            occurred_at=past,
        )
        await db.commit()

    personnel = (await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    entry = personnel["expertise"][0]
    assert entry["lifecycle"] == "dormant", entry
    assert entry["recency_days"] > 270
    assert entry["historical_peak"] == entry["score"], "peak equals the last recorded value"


# ---------------------------------------------------------------- governance


async def test_governed_ranking_is_evidence_derived(client, db_session_factory):
    org = await register_org(client, email="4f2_rank@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    alpha = await _team(client, headers, "Alpha")
    beta = await _team(client, headers, "Beta")

    star = await _hire(client, headers, "4f2-ranka@test.co", "Iris", "James", team_id=alpha["id"])
    mid = await _hire(client, headers, "4f2-rankb@test.co", "Jace", "Kaur", team_id=alpha["id"])
    light = await _hire(client, headers, "4f2-rankc@test.co", "Kira", "Larsen", team_id=beta["id"])

    for index in range(5):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], star["id"],
            task_id=f"4f2-st{index}",
            title=f"Shipped python service version {index}",
        )
    for index in range(2):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], mid["id"],
            task_id=f"4f2-md{index}",
            title=f"Contributed to python service {index}",
        )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], light["id"],
        task_id="4f2-lt",
        title="Reviewed a python pull request",
    )

    ranked = (
        await client.get(
            f"{BRAIN}/expertise/search", params={"q": "python", "limit": 50},
            headers=headers,
        )
    ).json()
    assert ranked["total"] == 3
    scores = [expert["score"] for expert in ranked["experts"]]
    assert scores == sorted(scores, reverse=True), scores
    assert ranked["experts"][0]["person_id"] == star["id"]
    assert ranked["experts"][0]["evidence_count"] == 5
    got = await client.get(
        f"{BRAIN}/expertise/search", params={"q": "python", "limit": 5000},
        headers=headers,
    )
    assert got.status_code == 422, "the search limit is bounded by the API"

    # team-scoped probe: only that team's experts rank — always bounded under
    # the full company even when the caller is org-wide.
    beta_ranked = (
        await client.get(
            f"{BRAIN}/expertise/search",
            params={"q": "python", "scope_type": "team", "scope_id": beta["id"]},
            headers=headers,
        )
    ).json()
    assert [e["person_id"] for e in beta_ranked["experts"]] == [light["id"]]


async def test_team_and_org_aggregate_maps(client, db_session_factory):
    org = await register_org(client, email="4f2_aggr@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    eng = await _department(client, headers, "Engineering")
    team = await _team(client, headers, "Data", department_id=eng["id"])
    first = await _hire(client, headers, "4f2-aggra@test.co", "Lia", "Moreau",
                        team_id=team["id"], department_id=eng["id"])
    second = await _hire(client, headers, "4f2-aggrb@test.co", "Mika", "Nwosu",
                         team_id=team["id"], department_id=eng["id"])

    for person, prefix in ((first, "da"), (second, "db")):
        await _publish_task(
            client, db_session_factory, org_id, org["user"]["id"], person["id"],
            task_id=f"4f2-{prefix}1",
            title="Built the python feature store",
        )

    team_map = (await client.get(f"{BRAIN}/expertise/teams/{team['id']}", headers=headers)).json()
    python = next(c for c in team_map["capabilities"] if c["skill_name"] == "Python")
    assert python["member_count"] == 2
    assert python["avg_score"] > 0

    dept_map = (
        await client.get(f"{BRAIN}/expertise/departments/{eng['id']}", headers=headers)
    ).json()
    assert any(c["skill_name"] == "Python" for c in dept_map["capabilities"])

    org_map = (await client.get(f"{BRAIN}/expertise/organization", headers=headers)).json()
    assert any(c["skill_name"] == "Python" for c in org_map["capabilities"])

    missing = await client.get(
        f"{BRAIN}/expertise/teams/not-a-team", headers=headers
    )
    assert missing.status_code == 404, missing.text


async def test_scoped_reader_never_leaks_hidden_people(client, db_session_factory):
    org = await register_org(client, email="4f2_scope@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    visible_team = await _team(client, headers, "Visible")
    hidden_team = await _team(client, headers, "Hidden")
    insider = await _hire(client, headers, "4f2-sca@test.co", "Nia", "Osei",
                          team_id=visible_team["id"])
    outsider = await _hire(client, headers, "4f2-scb@test.co", "Omar", "Pires",
                           team_id=hidden_team["id"])

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], insider["id"],
        task_id="4f2-vt1", title="Python service migration",
    )
    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], outsider["id"],
        task_id="4f2-ht1", title="Python tooling work",
    )

    scope = await _team_scope(client, headers, visible_team["id"])
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f2-scoperead@test.co"
    )

    # governed search: only visible people's evidence ranks
    ranked = (
        await client.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=reader)
    ).json()
    assert [e["person_id"] for e in ranked["experts"]] == [insider["id"]], ranked

    # a hidden person's expertise reads as missing (404, not 403 or 200)
    hidden_expertise = await client.get(
        f"{BRAIN}/people/{outsider['id']}/expertise", headers=reader
    )
    assert hidden_expertise.status_code == 404, hidden_expertise.text

    # the org-wide aggregate is org-wide callers only
    org_wide = await client.get(f"{BRAIN}/expertise/organization", headers=reader)
    assert org_wide.status_code == 404, org_wide.text

    # the whole-scope leak rule: their team is visible, a sibling department is not
    team_map = await client.get(
        f"{BRAIN}/expertise/teams/{visible_team['id']}", headers=reader
    )
    assert team_map.status_code == 200, team_map.text
    outsider_team_map = await client.get(
        f"{BRAIN}/expertise/teams/{hidden_team['id']}", headers=reader
    )
    assert outsider_team_map.status_code == 404, outsider_team_map.text

    # reads on hidden persons from write surfaces are equally refused: the
    # reader lacks the write permission itself (403) before privacy applies
    declare = await client.post(
        f"{BRAIN}/people/{outsider['id']}/skills",
        json={"name": "Python", "level": 3}, headers=reader,
    )
    assert declare.status_code == 403, declare.text
    missing_declare = await client.post(
        f"{BRAIN}/people/not-a-person/skills",
        json={"name": "Python", "level": 3}, headers=headers,
    )
    assert missing_declare.status_code == 404, missing_declare.text


async def test_tenant_isolation_across_evidence_and_resolution(client, db_session_factory):
    org_a = await register_org(client, email="4f2_tena@test.co")
    org_b = await register_org(client, email="4f2_tenb@test.co")
    person_a = await _hire(client, org_a["headers"], "4f2-ta@test.co", "Pia", "Quintana")
    person_b = await _hire(client, org_b["headers"], "4f2-tb@test.co", "Raf", "Saleh")

    await _publish_task(
        client, db_session_factory, org_a["organization"]["id"],
        org_a["user"]["id"], person_a["id"], task_id="4f2-ta1",
        title="Python platform hardening",
    )

    a = (await client.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=org_a["headers"])).json()
    assert len(a["experts"]) == 1 and a["experts"][0]["person_id"] == person_a["id"]

    b = (await client.get(f"{BRAIN}/expertise/search", params={"q": "python"}, headers=org_b["headers"])).json()
    assert b["total"] == 0, "tenant B never sees tenant A evidence"

    async with db_session_factory() as db:
        b_evidence = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.person_id == person_b["id"],
                )
            )
        ).scalars().all()
        assert len(b_evidence) == 0


async def test_graph_edges_for_skill_and_expertise(client, db_session_factory):
    org = await register_org(client, email="4f2_graph@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-graph@test.co", "Sam", "Tran")

    from app.intelligence.expertise_engine import expertise_engine

    async with db_session_factory() as db:
        for index in range(5):
            await expertise_engine.record_evidence(
                db, organization_id=org_id, employee_id=person["id"],
                event_name="task.completed",
                tokens=["kubernetes", "orchestration"],
                event_id=f"4f2-graph-ev{index}", source_type="task",
                source_id=f"4f2-graph-task{index}",
                source_title=f"Kubernetes work {index}",
            )
        await db.commit()

    from app.intelligence.graph_engine import graph_engine

    async with db_session_factory() as db:
        edges = await graph_engine.neighbors(
            db, organization_id=org_id, entity_type="employee", entity_id=person["id"]
        )
        relations = {(e.get("relation"), e.get("neighbor_type")) for e in edges}
        assert ("has_skill", "skill") in relations, edges
        assert ("expert_in", "skill") in relations, edges


# ---------------------------------------------------------------- brain questions


async def test_nl_who_knows_and_what_does_person_know(client, db_session_factory):
    org = await register_org(client, email="4f2_nl@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-nl@test.co", "Tara", "Uddin")

    await _publish_task(
        client, db_session_factory, org_id, org["user"]["id"], person["id"],
        task_id="4f2-nl1", title="Built the postgresql replication pipeline",
    )

    experts = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who knows postgresql?"},
            headers=headers,
        )
    ).json()
    assert experts["intent"] == "expertise", experts
    assert experts["kind"] == "experts", experts
    assert experts["total"] == 1
    assert experts["answers"][0]["person_id"] == person["id"]
    assert "Tara Uddin" in experts["answer"]

    centered = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": f"what does Tara Uddin know?"},
            headers=headers,
        )
    ).json()
    assert centered["intent"] == "expertise", centered
    assert centered["kind"] == "person_expertise", centered
    assert any(e["skill_name"] == "PostgreSQL" for e in centered["answers"])

    centered_skill = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": f"what does Tara Uddin know about postgresql?"},
            headers=headers,
        )
    ).json()
    assert centered_skill["kind"] == "person_skill", centered_skill
    assert "PostgreSQL" in centered_skill["answer"]

    map_answer = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "where does our postgresql expertise live?"},
            headers=headers,
        )
    ).json()
    assert map_answer["intent"] == "expertise", map_answer
    assert map_answer["kind"] == "organization_map", map_answer
    assert map_answer["total"] >= 1

    scoped = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who knows terraform?"},
            headers=headers,
        )
    ).json()
    assert scoped["kind"] == "experts" and scoped["total"] == 0, scoped

    unknown = (
        await client.post(
            f"{KNOWLEDGE}/query",
            json={"question": "who knows lacrosse?"},
            headers=headers,
        )
    ).json()
    assert unknown["kind"] == "no_skill", unknown


async def test_read_paths_never_mutate(client, db_session_factory):
    org = await register_org(client, email="4f2_nomut@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f2-nomut@test.co", "Uma", "Vazquez")
    await _drain(db_session_factory)  # settle setup events; reads may not enqueue

    async with db_session_factory() as db:
        before = len(
            list(
                (
                    await db.execute(
                        select(ExpertiseEvidence).where(
                            ExpertiseEvidence.organization_id == org_id
                        )
                    )
                ).scalars().all()
            )
        )
        await db.rollback()

    await client.get(f"{BRAIN}/expertise/skills", headers=headers)
    persisted = await client.get(
        f"{BRAIN}/expertise/search", params={"q": "python"}, headers=headers
    )
    assert persisted.status_code == 200
    await client.get(f"{BRAIN}/people/{person['id']}/expertise", headers=headers)

    async with db_session_factory() as db:
        after = len(
            list(
                (
                    await db.execute(
                        select(ExpertiseEvidence).where(
                            ExpertiseEvidence.organization_id == org_id
                        )
                    )
                ).scalars().all()
            )
        )
        pending = (
            await db.execute(
                select(func.count()).select_from(
                    EventRow
                ).where(
                    EventRow.organization_id == org_id,
                    EventRow.processed_at.is_(None),
                )
            )
        ).scalar_one()
        await db.rollback()

    assert after == before, "reads never fabricate evidence"
    pending_names = (
        await db.execute(
            select(EventRow.name).where(
                EventRow.organization_id == org_id,
                EventRow.processed_at.is_(None),
            )
        )
    ).scalars().all()
    assert pending == 0, f"reads never enqueue expertise signals: {pending_names}"


async def test_write_surfaces_require_manage_permission(client):
    org = await register_org(client, email="4f2_write@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f2-write@test.co", "Vera", "Wu")
    team = await _team(client, headers, "Writer-team")
    scope = await _team_scope(client, headers, team["id"])
    reader = await h.invite_scoped_reader(
        client, headers, scope["id"], "4f2-writeread@test.co"
    )

    anonymous = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "Python", "level": 3},
    )
    assert anonymous.status_code == 401

    forbidden = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "Python", "level": 3}, headers=reader,
    )
    assert forbidden.status_code == 403, forbidden.text

    allowed = await client.post(
        f"{BRAIN}/people/{person['id']}/skills",
        json={"name": "Python", "level": 3}, headers=headers,
    )
    assert allowed.status_code == 200, allowed.text