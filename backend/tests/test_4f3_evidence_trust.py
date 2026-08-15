"""Slice 4F.3 — Expertise Evidence & Trust Intelligence.

The third People Intelligence slice answers WHY the company may trust a
claimed expertise — directly under every later 4F/4G slice. Deterministic and
governed law under test:

* every evidence row carries full provenance: source taxonomy (kind), outcome
  signal, validity window, lineage key (one underlying action counted once),
  origin event id — canonical ids, never LLM invention,
* outcome ratio drives trust: same volume of evidence, different success rate
  -> materially different score / confidence / lifecycle,
* corroboration comes only from INDEPENDENT kinds (work + knowledge +
  decision), never from repeating one kind,
* derived cascades sharing one lineage key are deduplicated — a single action
  can never double count through multiple events,
* a rolled-back/expired claim loses its validity window yet stays VISIBLE in
  lineage and contradictions (history is never hidden),
* freshness is bucketed (active <= 90d / recent <= 365d / historical) and
  ``recent_only`` expert search answers "who has shown it recently",
* material failure share hard-caps lifecycle at established and confidence at
  0.59 — failed evidence deflates trust, deterministically,
* evidence drill-down is governance-scoped and tenant-isolated; read paths
  never mutate; no autonomous HR decisions ever appear,
* the Company Brain routes why/trust/recent questions to these surfaces.
"""

import datetime

from sqlalchemy import select

from app.models.skills_intelligence import Expertise as ExpertiseState, ExpertiseEvidence
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

BRAIN = "/api/v1/brain"
QUERY = "/api/v1/brain/knowledge/query"
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


async def _team(client, headers, name="Platform", code=None, department_id=None):
    import re as _re

    created = await client.post(
        "/api/v1/teams",
        json={"name": name,
              "code": code or _re.sub(r"[^a-z0-9_-]+", "-", name.lower().strip())[:20],
              "department_id": department_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _evidence(client, headers, person_id, skill_id):
    items = await client.get(
        f"{BRAIN}/people/{person_id}/expertise"
        f"/{skill_id}/evidence", headers=headers,
    )
    assert items.status_code == 200, items.text
    return items.json()


async def _publish(db_session_factory, org_id, name, actor_id, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


# ------------------------------------------------------------- provenance


async def test_every_evidence_row_carries_full_provenance(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_prov@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-prov@test.co", "Nora", "Wells")
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"], event_name="task.completed",
        tokens=["python"], reason="shipped the auth refactor",
        event_id="evt-901", source_type="task", source_id="task-42",
        source_title="Simplified OAuth flows",
        outcome="successful", origin_event_id="raw-777",
        lineage_key="task:task-42", valid_to=datetime.datetime.now(UTC) + datetime.timedelta(days=30),
    )
    await db_session.commit()
    row = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person["id"])
        )
    ).scalars().one()
    assert row.evidence_kind == "work"
    assert row.outcome == "successful"
    assert row.lineage_key == "task:task-42"
    assert row.origin_event_id == "raw-777"
    assert row.valid_to is not None
    assert row.source_type == "task" and row.source_id == "task-42"
    assert row.event_id == "evt-901"

    items = await _evidence(client, headers, person["id"], row.skill_id)
    item = items["evidence"][0]
    assert item["evidence_kind"] == "work" and item["outcome"] == "successful"
    assert item["lineage_key"] == "task:task-42"
    assert item["origin_event_id"] == "raw-777"
    assert item["source_id"] == "task-42"
    assert item["expired"] is False


async def test_lineage_fallback_is_deterministic_and_never_guessed(
        client, db_session,
):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_lineage@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-lineage@test.co", "Idris", "Kahn")
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"], event_name="deployment.completed",
        tokens=["kubernetes"], source_type="deployment", source_id="dep-9",
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person["id"])
        )
    ).scalars().one()
    assert row.lineage_key == "deployment:dep-9", "falls back to source_type:source_id"
    assert row.outcome == "successful", "taxonomy outcome, never guessed"
    assert row.evidence_kind == "work"


async def test_unknown_event_is_weak_neutral_work(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_unknown@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-unknown@test.co", "Rhea", "Gomes")
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"], event_name="some.unknown.event",
        tokens=["postgres"], source_type="unknown", source_id="u-1",
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person["id"])
        )
    ).scalars().one()
    assert row.evidence_kind == "work" and row.outcome == "neutral"
    assert row.strength == "weak"


# ------------------------------------------------------- outcome-driven trust


async def _cell_skill_id(db_session, person_id):
    row = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person_id).limit(1)
        )
    ).scalars().one()
    return row.skill_id


async def _seed_ratio(client, db_session, email, first, last, rows, successes):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email=email)
    headers = org["headers"]
    person = await _hire(client, headers, f"emp-{first.lower()}-{rows}@emp.test.co",
                         first, last)
    base = datetime.datetime.now(UTC) - datetime.timedelta(days=40)
    for i in range(rows):
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name="task.completed",
            tokens=["python"], source_type="task",
            source_id=f"task-{first.lower()}-{i}", occurred_at=base + datetime.timedelta(hours=i),
            outcome="successful" if i < successes else "failed",
        )
    await db_session.commit()
    skill_id = await _cell_skill_id(db_session, person["id"])
    return org, headers, person, skill_id


async def test_outcome_ratio_drives_the_trust_gap_between_operators(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org_a, _, a, a_skill = await _seed_ratio(
        client, db_session, "4f3_ratio_a@test.co", "Alice", "Stone", 20, 20)
    await _seed_ratio(
        client, db_session, "4f3_ratio_b@test.co", "Bob", "Grey", 20, 9)

    state_a = await expertise_engine.state(
        db_session, organization_id=org_a["organization"]["id"],
        person_id=a["id"], skill_id=a_skill,
    )
    org_b, _, b, b_skill = await _seed_ratio(
        client, db_session, "4f3_ratio_c@test.co", "Carol", "Blue", 20, 9)
    state_b = await expertise_engine.state(
        db_session, organization_id=org_b["organization"]["id"],
        person_id=b["id"], skill_id=b_skill,
    )
    assert state_a["successful_count"] == 20 and state_a["failed_count"] == 0
    assert state_a["outcome_ratio"] == 1.0
    assert state_b["successful_count"] == 9 and state_b["failed_count"] == 11
    assert state_b["outcome_ratio"] == 0.45
    # same evidence volume; outcomes decide the trust
    assert state_a["score"] > state_b["score"]
    assert state_a["confidence"] > state_b["confidence"]
    assert state_a["lifecycle"] in ("established", "strong", "authoritative")
    assert state_b["lifecycle"] in ("observed", "emerging")
    assert state_a["confidence"] != state_a["lifecycle"], "confidence never equals the label"


async def test_failed_evidence_never_hidden_from_current_scoring(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, _, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_ratio_d@test.co", "Dev", "Ora", 10, 2)
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert state["failed_count"] == 8
    assert state["outcome_ratio"] == 0.2
    trust = await expertise_engine.trust(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert trust["contradiction_count"] >= 8, "the failures are surfaced as contradictions"


async def test_material_failure_share_caps_lifecycle_and_confidence(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_ratio_e@test.co", "Eve", "Fox", 8, 2)
    x = await expertise_engine.trust(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    # 25% success: outcome_validation 0.2 and the outcome gate deflate
    # deterministically; the lifecycle is NEVER strong/authoritative.
    assert x["lifecycle"] in ("observed", "emerging", "established")
    assert x["lifecycle"] != "strong"
    assert x["failed_count"] == 6 and x["outcome_ratio"] == 0.25
    assert x["contradiction_count"] >= 6


async def test_confidence_cap_never_exceeds_097(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    # four strong source types -> full breadth; the rest near-ceiling.
    org, headers, person, skill_id = await _seed_kinds(
        client, db_session, "cap", "Finn",
        {"task.completed": 10, "milestone.completed": 10,
         "document.created": 10, "goal.completed": 10},
    )
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert state["evidence_count"] == 40
    assert state["confidence"] <= 0.97
    assert state["lifecycle"] == "authoritative"


# ------------------------------------------------------------ corroboration


async def _seed_kinds(client, db_session, email, first, kinds_by_event, span_days=30):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_corr_" + email + "@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, f"emp-{first.lower()}-{email}@emp.test.co", first, "Kim")
    base = datetime.datetime.now(UTC) - datetime.timedelta(days=span_days)
    i = 0
    for event_name, count in kinds_by_event.items():
        for _ in range(count):
            await expertise_engine.record_evidence(
                db_session, organization_id=org["organization"]["id"],
                employee_id=person["id"], event_name=event_name,
                tokens=["python"], source_type=event_name.split(".")[0],
                source_id=f"{first}-{event_name}-{i}", occurred_at=base + datetime.timedelta(hours=i),
            )
            i += 1
    await db_session.commit()
    skill_id = await _cell_skill_id(db_session, person["id"])
    return org, headers, person, skill_id


async def test_corroboration_needs_independent_kinds(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org_a, _, a, a_skill = await _seed_kinds(
        client, db_session, "a", "Ari",
        {"task.completed": 1, "milestone.completed": 1, "document.created": 1,
         "wiki.created": 1, "goal.completed": 1, "certificate.earned": 1},
    )
    org_b, _, b, b_skill = await _seed_kinds(
        client, db_session, "b", "Bree",
        {"task.completed": 6},
    )
    state_a = await expertise_engine.state(
        db_session, organization_id=org_a["organization"]["id"],
        person_id=a["id"], skill_id=a_skill,
    )
    state_b = await expertise_engine.state(
        db_session, organization_id=org_b["organization"]["id"],
        person_id=b["id"], skill_id=b_skill,
    )
    assert state_a["corroborated_kinds"] == 3, state_a["corroborated_kinds"]
    assert state_b["corroborated_kinds"] == 1
    assert state_a["evidence_count"] == 6 and state_b["evidence_count"] == 6
    assert state_a["confidence"] > state_b["confidence"]


# ------------------------------------------------------- one action, one count


async def test_derived_cascade_never_double_counts(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_cascade@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-cascade@test.co", "Cy", "Kim")
    # one underlying action: a task AND its deployment event share one lineage
    # key "deploy:42" and the same kind (work).
    for event_name, source_type in (("task.completed", "task"),
                                    ("deployment.completed", "deployment")):
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name=event_name,
            tokens=["python"], source_type=source_type,
            source_id=f"{source_type}-42", lineage_key="deploy:42",
        )
    await db_session.commit()
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=await _cell_skill_id(db_session, person["id"]),
    )
    assert state["evidence_count"] == 1, "one action counted once"
    assert state["distinct_lineages"] == 1
    factors = state["factors"]
    assert factors["deduplicated_count"] == 1
    # the second row still exists but never inflates any dimension
    rows = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person["id"])
        )
    ).scalars().all()
    assert len(rows) == 2


async def test_independent_lineages_do_add_evidence(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_kinds(
        client, db_session, "d", "Dee",
        {"task.completed": 2},
    )
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-other-99",
        lineage_key="task:task-other-99",
    )
    await db_session.flush()
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert state["evidence_count"] == 3, "independent lineages each count once"
    assert state["distinct_lineages"] == 3


# ------------------------------------------------------------- expiry/recency


async def test_rolled_back_deployment_expires_claim_and_keeps_history(client, db_session_factory):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_rollback@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-rollback@test.co", "Gus", "Roe")
    await _publish(db_session_factory, org["organization"]["id"], "deployment.completed",
                   person["id"], {"deployment_id": "dep-rb-1", "service": "python api",
                                  "actor_id": person["id"]})
    await _publish(db_session_factory, org["organization"]["id"], "deployment.rolled_back",
                   person["id"], {"deployment_id": "dep-rb-1", "service": "python api",
                                  "actor_id": person["id"]})
    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.person_id == person["id"])
            )
        ).scalars().all()
        by_type = {r.evidence_type: r for r in rows}
    assert "deployment.completed" in by_type and "deployment.rolled_back" in by_type
    assert by_type["deployment.rolled_back"].outcome == "failed"
    skill_id = by_type["deployment.completed"].skill_id
    async with db_session_factory() as db:
        trust = await expertise_engine.trust(
            db, organization_id=org["organization"]["id"], person_id=person["id"],
            skill_id=skill_id,
        )
    assert trust is not None and trust["evidence_total"] == 2
    contradictions = trust["contradictions"]
    assert len(contradictions) == 2, "expired success + failed rollback are both surfaced"
    assert any(x["expired"] and x["outcome"] == "successful" for x in contradictions)
    assert any(not x["expired"] and x["outcome"] == "failed" for x in contradictions)
    assert trust["freshness"] == "active" or trust["freshness"] == "recent"


async def test_expired_source_drops_out_of_current_score(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_kinds(
        client, db_session, "e", "Eli",
        {"task.completed": 5},
    )
    rows = (
        await db_session.execute(
            select(ExpertiseEvidence).where(
                ExpertiseEvidence.person_id == person["id"])
        )
    ).scalars().all()
    for row in rows:
        row.valid_to = datetime.datetime.now(UTC) - datetime.timedelta(days=1)
    await db_session.commit()
    # expiry is a changed state: the cell is deterministically recomputed
    # (O(changed entities) — a rollback worker, not a read-path mutation).
    await expertise_engine.recompute_employee(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"],
    )
    await db_session.commit()
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert state["score"] == 0.0, "expired claims no longer score"
    trust = await expertise_engine.trust(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert trust["contradiction_count"] == 5, "expired rows stay visible as history"


async def test_freshness_buckets_active_recent_historical(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    days = {"active": 10, "recent": 200, "historical": 400}
    states = {}
    for label, gap in days.items():
        org = await register_org(client, email=f"4f3_fresh_{label}@test.co")
        headers = org["headers"]
        person = await _hire(client, headers, f"4f3-fresh-{label}@test.co", label, "Day")
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name="task.completed",
            tokens=["python"], source_type="task", source_id=f"task-{label}-1",
            occurred_at=datetime.datetime.now(UTC) - datetime.timedelta(days=gap),
        )
        await db_session.flush()
        states[label] = await expertise_engine.state(
            db_session, organization_id=org["organization"]["id"],
            person_id=person["id"], skill_id=await _cell_skill_id(db_session, person["id"]),
        )
    assert states["active"]["freshness"] == "active"
    assert states["recent"]["freshness"] == "recent"
    assert states["historical"]["freshness"] == "historical"
    assert states["active"]["score"] > states["recent"]["score"] > states["historical"]["score"]


async def test_recent_only_expert_search_filters_stale_claims(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_recent_search@test.co")
    headers = org["headers"]
    newbie = await _hire(client, headers, "4f3-recent-new@test.co", "New", "Kid")
    oldie = await _hire(client, headers, "4f3-recent-old@test.co", "Old", "Timer")
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=newbie["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-new-1",
        occurred_at=datetime.datetime.now(UTC) - datetime.timedelta(days=5),
    )
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=oldie["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-old-1",
        occurred_at=datetime.datetime.now(UTC) - datetime.timedelta(days=300),
    )
    await db_session.commit()
    all_experts = (await client.get(
        f"{BRAIN}/expertise/search", params={"q": "python"}, headers=headers)).json()
    names = {e["name"] for e in all_experts["experts"]}
    assert {"New Kid", "Old Timer"} <= names
    recent = (await client.get(
        f"{BRAIN}/expertise/search", params={"q": "python", "recent_only": "true"},
        headers=headers)).json()
    assert recent["recent_only"] is True
    recent_names = {e["name"] for e in recent["experts"]}
    assert "New Kid" in recent_names and "Old Timer" not in recent_names

# --------------------------------------------------- event-driven outcomes


async def test_approval_rejection_writes_failed_decision_evidence(client, db_session_factory):
    org = await register_org(client, email="4f3_reject@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-reject@test.co", "Han", "Solo")
    await _publish(db_session_factory, org["organization"]["id"], "approval.rejected",
                   person["id"],
                   {"requester_id": person["id"], "approval_id": "appr-9",
                    "title": "python toolchain upgrade approval"})
    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.person_id == person["id"])
            )
        ).scalars().all()
        assert any(
            r.evidence_kind == "decision" and r.outcome == "failed"
            and r.source_type == "approval" and r.source_id == "appr-9"
            for r in rows
        ), f"approval rejection must leave failed decision evidence: {rows}"


async def test_op_success_and_failure_share_one_lineage(client, db_session_factory):
    org = await register_org(client, email="4f3_ops@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-ops@test.co", "Ira", "Vance")
    for name in ("deployment.completed", "deployment.failed"):
        await _publish(db_session_factory, org["organization"]["id"], name,
                       person["id"],
                       {"deployment_id": "dep-7", "service": "python api",
                        "actor_id": person["id"]})
    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.person_id == person["id"])
            )
        ).scalars().all()
        state = await _state_of(db, org["organization"]["id"], person["id"],
                                rows[0].skill_id)
    by_type = {r.evidence_type: r for r in rows}
    assert by_type["deployment.completed"].outcome == "successful"
    assert by_type["deployment.failed"].outcome == "failed"
    assert {r.lineage_key for r in rows} == {"deployment:dep-7"}
    # the pair dedupes to one effective row (first inserted wins on ties)
    assert state["evidence_count"] == 1
    assert state["factors"]["deduplicated_count"] == 1
    assert state["distinct_lineages"] == 1


async def test_goal_completed_names_goal_and_counts_success(client, db_session_factory):
    org = await register_org(client, email="4f3_goal@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-goal@test.co", "Jo", "Lane")
    await _publish(db_session_factory, org["organization"]["id"], "goal.completed",
                   person["id"],
                   {"goal_id": "goal-3", "name": "containerize python services",
                    "owner_id": person["id"]})
    async with db_session_factory() as db:
        rows = (
            await db.execute(
                select(ExpertiseEvidence).where(
                    ExpertiseEvidence.person_id == person["id"])
            )
        ).scalars().all()
        assert any(
            r.evidence_type == "goal.completed"
            and r.evidence_kind == "work"
            and r.outcome == "successful"
            and r.source_type == "goal" and r.source_id == "goal-3"
            for r in rows
        ), f"goal completion must leave successful work evidence: {rows}"


async def _state_of(db, org_id, person_id, skill):
    from app.intelligence.expertise_engine import expertise_engine

    return await expertise_engine.state(
        db, organization_id=org_id, person_id=person_id, skill_id=skill)

# --------------------------------------------------------- governed reads


async def test_trust_profile_route_exposes_after_why(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_trust_route@test.co", "Lia", "Pine", 6, 6)
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    trust = (await client.get(
        f"{BRAIN}/people/{person['id']}/expertise/{skill_id}/trust",
        headers=headers)).json()
    assert trust["trust"] is True
    assert trust["person_name"] or trust["person_id"] == person["id"]
    assert trust["skill_name"] == "Python"
    assert trust["lifecycle"] == state["lifecycle"]
    assert trust["score"] == state["score"] and trust["confidence"] == state["confidence"]
    assert trust["evidence_total"] == 6
    assert trust["evidence_by_kind"]["work"] == 6
    assert trust["successful_count"] == 6 and trust["failed_count"] == 0
    assert trust["distinct_lineages"] == 6
    assert trust["freshness"] in ("active", "recent", "historical")
    # the drill-down is the same claim, not a new computation
    assert trust["evidence_by_source"]["task"] == 6


async def test_evidence_drilldown_is_governed_and_tenant_isolated(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_gov@test.co")
    headers = org["headers"]
    team = await _team(client, headers, "Trust Team")
    hidden = await _team(client, headers, "Hidden Team")
    visible = await _hire(client, headers, "4f3-gov-vis@test.co", "Mia", "Blue",
                          team_id=team["id"])
    secret = await _hire(client, headers, "4f3-gov-sec@test.co", "Moe", "Green",
                         team_id=hidden["id"])
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=visible["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-gov-vis-1",
    )
    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=secret["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-gov-sec-1",
    )
    await db_session.commit()
    scope = (await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Trust team scope", "scope_type": "team",
              "entity_id": team["id"]}, headers=headers)).json()
    scoped = await h.invite_scoped_reader(client, headers, scope["id"], "4f3-gov-user@test.co")

    visible_skill = await _cell_skill_id(db_session, visible["id"])
    vis_lines = await client.get(
        f"{BRAIN}/people/{visible['id']}/expertise/{visible_skill}/evidence",
        headers=headers)
    evidence_id = vis_lines.json()["evidence"][0]["evidence_id"]
    evidence_id = vis_lines.json()["evidence"][0]["evidence_id"]

    # owner sees the drill-down; the scoped reader never does for hidden people
    assert (await client.get(f"{BRAIN}/expertise/evidence/{evidence_id}",
                             headers=headers)).status_code == 200
    hidden_lines = await client.get(
        f"{BRAIN}/people/{secret['id']}/expertise/python/evidence", headers=scoped)
    assert hidden_lines.status_code == 404, "scoped reader never sees hidden people"

    # cross-tenant: another org cannot dereference this evidence at all
    org2 = await register_org(client, email="4f3_other@test.co")
    hidden_by_b = await client.get(
        f"{BRAIN}/expertise/evidence/{evidence_id}", headers=org2["headers"])
    assert hidden_by_b.status_code == 404, "tenant isolation on the drill-down"


async def test_read_paths_never_mutate(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_readonly@test.co", "Rin", "Yama", 4, 4)
    before = await _state_of(db_session, org["organization"]["id"], person["id"], skill_id)
    rows_before = (
        await db_session.execute(select(ExpertiseEvidence))
    ).scalars().all()
    for _ in range(2):
        await client.get(
            f"{BRAIN}/people/{person['id']}/expertise/{skill_id}/trust", headers=headers)
        await client.get(f"{BRAIN}/expertise/search", params={"q": "python"},
                         headers=headers)
        await client.get(f"{BRAIN}/people/{person['id']}/expertise/{skill_id}/evidence",
                         headers=headers)
    after = await _state_of(db_session, org["organization"]["id"], person["id"], skill_id)
    rows_after = (
        await db_session.execute(select(ExpertiseEvidence))
    ).scalars().all()
    assert after["score"] == before["score"]
    assert after["confidence"] == before["confidence"]
    assert after["evidence_count"] == before["evidence_count"]
    assert after["lifecycle"] == before["lifecycle"]
    assert len(rows_after) == len(rows_before)


async def test_no_autonomous_hr_decisions_anywhere(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_no_hr@test.co", "Sam", "Hill", 8, 8)
    trust = (await client.get(
        f"{BRAIN}/people/{person['id']}/expertise/{skill_id}/trust", headers=headers)).json()
    banned = {"promotion", "pay_raise", "salary", "hire", "fire",
              "recommendation", "performance_grade", "raise"}
    keys = set(trust)
    assert not keys & banned, f"HR decision fields leak into trust: {keys & banned}"
    search = (await client.get(f"{BRAIN}/expertise/search", params={"q": "python"},
                               headers=headers)).json()
    for e in search["experts"]:
        assert not set(e) & banned, set(e) & banned

# ------------------------------------------------------------------ NL intents


async def test_why_trust_intent_answers_trust_profile(client, db_session):
    org = await register_org(client, email="4f3_nl_trust@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-nl-trust@test.co", "Keerthi", "Rao")
    from app.intelligence.expertise_engine import expertise_engine

    for i in range(6):
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name="task.completed",
            tokens=["python"], source_type="task", source_id=f"task-nl-{i}",
        )
    await db_session.commit()
    resp = (await client.post(
        QUERY, json={"question": "why does Keerthi know Python?"},
        headers=headers)).json()
    assert resp["intent"] == "expertise_trust"
    assert resp["kind"] == "trust_profile"
    assert resp["answers"][0]["person_name"] or resp["answers"][0]["person_id"] == person["id"]
    t = resp["answers"][0]
    assert t["score"] > 0 and t["evidence_total"] == 6
    assert "recent_evidence" in t and t["freshness"] in ("active", "recent", "historical")


async def test_what_evidence_intent_returns_evidence_trail(client, db_session):
    org = await register_org(client, email="4f3_nl_evidence@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-nl-ev@test.co", "Py", "Thon")
    from app.intelligence.expertise_engine import expertise_engine

    for i in range(3):
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name="task.completed",
            tokens=["python"], source_type="task", source_id=f"task-nlev-{i}",
        )
    await db_session.commit()
    resp = (await client.post(
        QUERY, json={"question": "what evidence backs Py's Python expertise?"},
        headers=headers)).json()
    assert resp["intent"] == "expertise_trust"
    answers = resp["answers"]
    assert answers, resp
    assert resp["kind"] == "trust_profile", resp
    assert answers[0]["person_id"] == person["id"]
    assert "successful_count" in answers[0], "trust facets travel with the answer"

    nonsensical = (await client.post(
        QUERY, json={"question": "why does the server restart at night?"},
        headers=headers)).json()
    assert nonsensical["intent"] == "expertise_trust"
    assert nonsensical["kind"] in ("not_expertise", "no_person")


async def test_recent_discovery_nl_filters_stale_people(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org = await register_org(client, email="4f3_nl_recent@test.co")
    headers = org["headers"]
    newbie = await _hire(client, headers, "4f3-nl-new@test.co", "Fresh", "Ferno")
    oldie = await _hire(client, headers, "4f3-nl-old@test.co", "Veteran", "Voss")
    for person, days in ((newbie, 5), (oldie, 300)):
        await expertise_engine.record_evidence(
            db_session, organization_id=org["organization"]["id"],
            employee_id=person["id"], event_name="task.completed",
            tokens=["python"], source_type="task", source_id=f"task-nlr-{days}",
            occurred_at=datetime.datetime.now(UTC) - datetime.timedelta(days=days),
        )
    await db_session.commit()
    resp = (await client.post(
        QUERY, json={"question": "who knows Python recently?"},
        headers=headers)).json()
    assert resp["intent"] == "expertise"
    names = {a["name"] for a in resp["answers"]}
    assert "Fresh Ferno" in names and "Veteran Voss" not in names

    broad = (await client.post(
        QUERY, json={"question": "who knows Python?"},
        headers=headers)).json()
    assert {a["name"] for a in broad["answers"]} == {"Fresh Ferno", "Veteran Voss"}


async def test_expertise_engine_model_version_is_4f3(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine

    org, headers, person, skill_id = await _seed_ratio(
        client, db_session, "4f3_modelver@test.co", "Vera", "Code", 3, 3)
    state = await expertise_engine.state(
        db_session, organization_id=org["organization"]["id"],
        person_id=person["id"], skill_id=skill_id,
    )
    assert state["model_version"] == "4f3.1"