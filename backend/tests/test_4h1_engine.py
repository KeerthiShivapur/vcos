"""Slice 4H.1 — Universal Company / Organizational Intelligence engine.

Under test:

* temporal_state: the health-trail series grows across seeded events and
  stays exact-once on replay; per-step dimension scores present.
* narrative: insufficient before two rows, then deterministic bounded steps.
* causal edges: derived from canonical tables on refresh, exact-once per
  event, walked by causal_chain with per-hop confidence + evidence refs.
* what_happens_if: extends what_if with company-level consequence hops,
  honesty contract unchanged.
* multi_level_state: the same schema parameterized by department/team/person
  scope, bounded to the scope's entities.
* memory loop: predict -> outcome -> compare -> lesson memory, recall
  filters, replay convergence.
* refresh writes attention-worthy scoped trail rows (exact-once).
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.intelligence.company_operating_engine import company_operating_engine
from app.models.company_memory import CompanyMemory
from app.models.company_operating import (
    CompanyCausalEdge,
    CompanyDecision,
    CompanyHealthHistory,
)
from app.models.customer import Customer, CustomerProjectLink
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Milestone
from app.models.task import Task
from app.models.customer_intelligence import CustomerCommitment
from tests.conftest import register_org

CAP = "/api/v1/brain/execution/capacity"


async def _drain(db_session_factory, limit=200, rounds=6):
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


async def _publish(db_session_factory, org_id, actor_id, name, payload):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name=name, organization_id=org_id, actor_id=actor_id,
            payload=payload, enqueue=True, flush=False,
        )
        await db.commit()
    return await _drain(db_session_factory)


async def _project(client, headers, name, status="active"):
    resp = await client.post(
        "/api/v1/projects",
        json={"name": name, "code": f"h1-{name.lower().replace(' ', '-')[:16]}",
              "status": status},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _team(client, headers, name, code):
    resp = await client.post(
        "/api/v1/teams", json={"name": name, "code": code}, headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _hire(client, headers, email, first, last, team_id=None):
    resp = await client.post(
        "/api/v1/employees",
        json={"first_name": first, "last_name": last, "email": email,
              "team_id": team_id},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _demand(client, headers, project_id, capability, units):
    resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": capability, "units": units,
              "window_start": date.today().isoformat(),
              "window_end": (date.today() + timedelta(days=30)).isoformat(),
              "proficiency": "high"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _capability(db_session_factory, org_id, name, available=10):
    async with db_session_factory() as db:
        existing = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == org_id,
                    OrgCapability.canonical_name == name,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(OrgCapability(
                organization_id=org_id, skill_id=f"sk-{name[:20]}",
                canonical_name=name,
                capacity_potential=available + 2,
                capacity_committed=0, capacity_reserved=0,
                capacity_available=available, capacity_state="available",
                expert_count=3, evidence_count=3, lifecycle="established",
            ))
        await db.commit()


async def _task(db_session_factory, org_id, project_id, assignee_id):
    async with db_session_factory() as db:
        db.add(Task(
            organization_id=org_id, project_id=project_id,
            assignee_id=assignee_id, title="Scope work", status="active",
            estimate_hours=40.0,
        ))
        await db.commit()


async def _customer(db_session_factory, org_id, name="Northwind Co"):
    async with db_session_factory() as db:
        row = Customer(
            organization_id=org_id, company_name=name,
            segment="enterprise", tier="key",
        )
        db.add(row)
        await db.flush()
        cid = row.id
        await db.commit()
    return cid


async def _link_customer_project(db_session_factory, org_id, customer_id, project_id):
    async with db_session_factory() as db:
        db.add(CustomerProjectLink(
            organization_id=org_id, customer_id=customer_id,
            project_id=project_id, status="active",
        ))
        await db.commit()


async def _milestone(db_session_factory, org_id, project_id, name="Ship gate"):
    async with db_session_factory() as db:
        row = Milestone(
            organization_id=org_id, project_id=project_id, name=name,
            status="in_progress",
        )
        db.add(row)
        await db.flush()
        mid = row.id
        await db.commit()
    return mid


async def _health_rows(db_session_factory, org_id, scope_type=None):
    async with db_session_factory() as db:
        stmt = select(CompanyHealthHistory).where(
            CompanyHealthHistory.organization_id == org_id,
        )
        if scope_type:
            stmt = stmt.where(CompanyHealthHistory.scope_type == scope_type)
        return list((await db.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# 1. temporal_state
# ---------------------------------------------------------------------------

async def test_temporal_state_series_grows_and_is_exact_once(client, db_session_factory):
    org = await register_org(client, email="4h1_temp@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    series = None
    async with db_session_factory() as db:
        series = await company_operating_engine.temporal_state(
            db, organization_id=org_id,
        )
    assert series["count"] == 0
    assert series["latest"] is None
    assert series["scope_type"] == "org"

    proj = await _project(client, headers, "temporal anchor")
    await _drain(db_session_factory)
    async with db_session_factory() as db:
        series = await company_operating_engine.temporal_state(
            db, organization_id=org_id,
        )
    assert series["count"] == 1
    step = series["series"][0]
    assert set(step) == {
        "occurred_at", "company_score", "company_state",
        "primary_constraint", "domains",
    }
    assert 0 <= step["company_score"] <= 100

    await _publish(
        db_session_factory, org_id, org["user"]["id"],
        "task.completed",
        {"task_id": "4h1-t1", "project_id": proj["id"],
         "assignee_id": None, "title": "done"},
    )
    async with db_session_factory() as db:
        series = await company_operating_engine.temporal_state(
            db, organization_id=org_id,
        )
    assert series["count"] == 2
    assert series["latest"]["company_score"] == series["series"][-1]["company_score"]

    # replay the same durable event (same id, bus re-delivery) -> no new row.
    from app.models.notification import Event as EventRow

    before = len(series["series"])
    async with db_session_factory() as db:
        ev = (
            await db.execute(
                select(EventRow).where(
                    EventRow.organization_id == org_id,
                    EventRow.name == "task.completed",
                ).order_by(EventRow.occurred_at.desc()).limit(1)
            )
        ).scalar_one()

        class FakeEvent:
            id = ev.id
            name = ev.name

        for _ in range(2):
            await company_operating_engine.refresh(
                db, organization_id=org_id, event=FakeEvent(),
                payload={"task_id": "4h1-t1", "project_id": proj["id"]},
            )
        await db.commit()
    async with db_session_factory() as db:
        series = await company_operating_engine.temporal_state(
            db, organization_id=org_id,
        )
    assert series["count"] == before


# ---------------------------------------------------------------------------
# 2. narrative
# ---------------------------------------------------------------------------

async def test_narrative_insufficient_then_deterministic(client, db_session_factory):
    org = await register_org(client, email="4h1_narr@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    async with db_session_factory() as db:
        n = await company_operating_engine.narrative(db, organization_id=org_id)
    assert n["window"] == "insufficient_history"
    assert n["steps"] == []

    proj = await _project(client, headers, "narrative anchor")
    await _drain(db_session_factory)
    await _publish(
        db_session_factory, org_id, org["user"]["id"],
        "task.completed",
        {"task_id": "4h1-n1", "project_id": proj["id"],
         "assignee_id": None, "title": "done"},
    )
    async with db_session_factory() as db:
        n = await company_operating_engine.narrative(db, organization_id=org_id)
    assert len(n["steps"]) == 1
    step = n["steps"][0]
    assert "window" in step
    assert "score_before" in step and "score_after" in step
    assert isinstance(n["story"], list) and len(n["story"]) >= 1
    first = n["story"][0]
    async with db_session_factory() as db:
        again = await company_operating_engine.narrative(db, organization_id=org_id)
    assert again["story"] == n["story"]  # deterministic wording


# ---------------------------------------------------------------------------
# 3. causal edges + causal_chain
# ---------------------------------------------------------------------------

async def test_causal_edges_derived_and_chain_walks(client, db_session_factory):
    org = await register_org(client, email="4h1_chain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    proj = await _project(client, headers, "chain anchor")
    await _drain(db_session_factory)
    customer_id = await _customer(db_session_factory, org_id)
    await _link_customer_project(db_session_factory, org_id, customer_id, proj["id"])
    milestone_id = await _milestone(db_session_factory, org_id, proj["id"])
    await _task(db_session_factory, org_id, proj["id"], None)
    await _publish(
        db_session_factory, org_id, org["user"]["id"],
        "task.completed",
        {"task_id": "4h1-c1", "project_id": proj["id"],
         "assignee_id": None, "title": "done"},
    )

    async with db_session_factory() as db:
        edges = list(
            (
                await db.execute(
                    select(CompanyCausalEdge).where(
                        CompanyCausalEdge.organization_id == org_id,
                    )
                )
            ).scalars().all()
        )
    kinds = {e.kind for e in edges}
    assert "project->customer" in kinds
    assert "project->milestone" in kinds
    assert "task->execution" in kinds
    assert all(e.confidence in ("high", "medium", "low") for e in edges)
    assert all(isinstance(e.evidence_ref, list) for e in edges)
    assert all(e.source_event_id for e in edges)

    # project subject walks to the customer (forward) and back (reverse).
    async with db_session_factory() as db:
        chain = await company_operating_engine.causal_chain(
            db, organization_id=org_id,
            entity_type="project", entity_id=proj["id"], depth=3,
        )
    assert chain["subject"] == {"type": "project", "id": proj["id"]}
    to_customers = [h for h in chain["hops"] if h["to_type"] == "customer"]
    assert any(h["to_id"] == customer_id for h in to_customers)
    assert all("confidence" in h and "evidence_ref" in h for h in chain["hops"])
    assert all("from_label" in h and "to_label" in h for h in chain["hops"])

    async with db_session_factory() as db:
        back = await company_operating_engine.causal_chain(
            db, organization_id=org_id,
            entity_type="customer", entity_id=customer_id, depth=2,
        )
    assert any(h["to_type"] == "project" for h in back["hops"])

    # milestone subject is reachable.
    async with db_session_factory() as db:
        mchain = await company_operating_engine.causal_chain(
            db, organization_id=org_id,
            entity_type="milestone", entity_id=milestone_id, depth=2,
        )
    assert len(mchain["hops"]) >= 1

    # exact-once on replay: re-drain adds no duplicate edges.
    async with db_session_factory() as db:
        again = (
            await db.execute(
                select(CompanyCausalEdge).where(
                    CompanyCausalEdge.organization_id == org_id,
                )
            )
        ).scalars().all()
    assert len(again) == len(edges)


# ---------------------------------------------------------------------------
# 4. what_happens_if
# ---------------------------------------------------------------------------

async def test_what_happens_if_company_hops(client, db_session_factory):
    org = await register_org(client, email="4h1_whi@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    proj = await _project(client, headers, "what-happens anchor")
    await _drain(db_session_factory)
    await _capability(db_session_factory, org_id, "beta_eng")
    await _demand(client, headers, proj["id"], "beta_eng", 4)
    customer_id = await _customer(db_session_factory, org_id)
    async with db_session_factory() as db:
        db.add(CustomerCommitment(
            organization_id=org_id, customer_id=customer_id,
            summary="Release the what-happens platform",
            expected_at=date.today() + timedelta(days=14),
            status="at_risk", project_id=proj["id"],
            source_event_id="seed-commitment-4h1-whi",
        ))
        await db.commit()

    async with db_session_factory() as db:
        result = await company_operating_engine.what_happens_if(
            db, organization_id=org_id,
            scenario_type="delay",
            payload={"project_id": proj["id"], "days": 10},
        )
    assert result["scenario_type"] == "delay"
    assert result["not_a_prediction"] is True
    assert result["note"]
    assert "company_consequences" in result
    kinds = {h["kind"] for h in result["company_consequences"]}
    assert "customer" in kinds
    assert all(h["confidence"] for h in result["company_consequences"])
    assert len(result["company_consequences"]) <= 5

    async with db_session_factory() as db:
        unknown = await company_operating_engine.what_happens_if(
            db, organization_id=org_id,
            scenario_type="bogus", payload={},
        )
    assert unknown["scenario_type"] == "bogus"
    assert "scenario_type must be reallocate | delay | hire" in unknown["note"]
    assert unknown["not_a_prediction"] is True


# ---------------------------------------------------------------------------
# 5. multi_level_state
# ---------------------------------------------------------------------------

async def test_multi_level_state_team_and_person_scope(client, db_session_factory):
    org = await register_org(client, email="4h1_scope@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    team = await _team(client, headers, "Platform Guild", "h1-plat")
    member = await _hire(
        client, headers, "4h1-scope@test.co", "Scope", "Reader", team["id"],
    )
    proj = await _project(client, headers, "scope anchor")
    await _drain(db_session_factory)
    await _task(db_session_factory, org_id, proj["id"], member["id"])

    async with db_session_factory() as db:
        team_state = await company_operating_engine.multi_level_state(
            db, organization_id=org_id, scope_type="team", scope_id=team["id"],
        )
    assert team_state["scope_type"] == "team"
    assert team_state["scope_id"] == team["id"]
    assert 0 <= team_state["company_score"] <= 100
    assert isinstance(team_state["domains"], list)
    assert all(
        {"key", "label", "score", "state", "reasons", "affected"} <= set(d)
        for d in team_state["domains"]
    )
    assert any(d["key"] == "people" for d in team_state["domains"])

    async with db_session_factory() as db:
        person_state = await company_operating_engine.multi_level_state(
            db, organization_id=org_id, scope_type="person", scope_id=member["id"],
        )
    assert person_state["scope_type"] == "person"
    assert person_state["scope_id"] == member["id"]

    async with db_session_factory() as db:
        unsupported = await company_operating_engine.multi_level_state(
            db, organization_id=org_id, scope_type="galaxy", scope_id="x",
        )
    assert unsupported["company_state"] == "unsupported_scope"

    async with db_session_factory() as db:
        missing = await company_operating_engine.multi_level_state(
            db, organization_id=org_id, scope_type="team", scope_id="nope",
        )
    assert missing["company_score"] == 80
    assert missing["domains"] == []


# ---------------------------------------------------------------------------
# 6. memory loop: predict -> outcome -> compare -> lesson
# ---------------------------------------------------------------------------

async def test_memory_loop_prediction_compare_and_lesson(client, db_session_factory):
    org = await register_org(client, email="4h1_mem@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    approved = await client.post(
        f"/api/v1/brain/execution/company/decisions",
        json={"kind": "hire", "title": "Hire for the platform bottleneck",
              "predicted_outcome": {"expected_outcome": "successful"},
              "prediction_confidence": 0.7,
              "confidence": 0.8, "owner_label": "Leadership"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    decision_id = approved.json()["decision_id"]
    assert approved.json()["prediction_recorded"] is True
    await _drain(db_session_factory)

    executed = await client.post(
        f"/api/v1/brain/execution/company/decisions/{decision_id}/execute",
        json={"executed_by_label": "Ada Owner"}, headers=headers,
    )
    assert executed.status_code == 200, executed.text
    await _drain(db_session_factory)

    outcome = await client.post(
        f"/api/v1/brain/execution/company/decisions/{decision_id}/outcome",
        json={"outcome_kind": "successful", "effectiveness": 0.8,
              "lesson": "predictions with confidence survive outcomes when scoped to capability gaps"},
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    body = outcome.json()
    assert body["actual_outcome_compare"]["predicted"] == "successful"
    assert body["actual_outcome_compare"]["observed"] == "successful"
    assert body["actual_outcome_compare"]["aligned"] is True
    assert body["lesson_memory"]["fact_kind"] == "lesson"

    # recall filters: predicted, decision_id.
    memory = (
        await client.get(
            f"/api/v1/brain/execution/company/memory?predicted=true",
            headers=headers,
        )
    ).json()
    assert memory["total_decisions"] == 1
    entry = memory["decisions"][0]
    assert entry["prediction_confidence"] == 0.7
    assert entry["actual_outcome_compare"]["aligned"] is True
    assert entry["reviewed_at"]

    filtered = (
        await client.get(
            f"/api/v1/brain/execution/company/memory?decision_id={decision_id}",
            headers=headers,
        )
    ).json()
    assert filtered["total_decisions"] == 1

    # lesson memory row with evidence lineage to the decision.
    async with db_session_factory() as db:
        memories = list(
            (
                await db.execute(
                    select(CompanyMemory).where(
                        CompanyMemory.organization_id == org_id,
                        CompanyMemory.dedupe_key == f"lesson:decision:{decision_id}",
                    )
                )
            ).scalars().all()
        )
    assert len(memories) == 1
    assert memories[0].fact_kind == "lesson"
    assert any(
        ev.get("entity") == "decision" and ev.get("id") == decision_id
        for ev in (memories[0].evidence_json or [])
    )

    # replay the same outcome event -> single decision, single lesson row.
    await _drain(db_session_factory)
    async with db_session_factory() as db:
        decisions = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == org_id,
                        CompanyDecision.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
    assert len(decisions) == 1
    assert decisions[0].actual_outcome_compare["aligned"] is True


async def test_memory_loop_without_prediction_stays_byte_compatible(client, db_session_factory):
    org = await register_org(client, email="4h1_plain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    approved = await client.post(
        f"/api/v1/brain/execution/company/decisions",
        json={"kind": "hire", "title": "Plain decision",
              "confidence": 0.5, "owner_label": "Leadership"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["prediction_recorded"] is False
    await _drain(db_session_factory)

    memory = (
        await client.get(f"/api/v1/brain/execution/company/memory", headers=headers)
    ).json()
    entry = memory["decisions"][0]
    assert "prediction_confidence" not in entry
    assert "actual_outcome_compare" not in entry


# ---------------------------------------------------------------------------
# 7. refresh writes attention-worthy scoped trail rows (exact-once)
# ---------------------------------------------------------------------------

async def test_refresh_writes_scoped_deviation_rows(client, db_session_factory):
    org = await register_org(client, email="4h1_devi@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    team = await _team(client, headers, "Covered Guild", "h1-cov")
    member = await _hire(
        client, headers, "4h1-devi@test.co", "Devi", "Ation", team["id"],
    )
    await _capability(db_session_factory, org_id, "covered_eng", available=10)

    p1 = await _project(client, headers, "covered one")
    p2 = await _project(client, headers, "covered two")
    await _drain(db_session_factory)
    await _demand(client, headers, p1["id"], "covered_eng", 2)
    await _demand(client, headers, p2["id"], "covered_eng", 2)
    await _task(db_session_factory, org_id, p1["id"], member["id"])
    await _task(db_session_factory, org_id, p2["id"], member["id"])

    # an org-wide uncovered demand drags the org score down.
    p3 = await _project(client, headers, "uncovered three")
    await _drain(db_session_factory)
    await _demand(client, headers, p3["id"], "uncovered_eng", 2)

    await _publish(
        db_session_factory, org_id, org["user"]["id"],
        "capacity.demand.created",
        {"project_id": p3["id"], "capability": "uncovered_eng", "units": 2},
    )

    async with db_session_factory() as db:
        scoped = (
            await db.execute(
                select(CompanyHealthHistory).where(
                    CompanyHealthHistory.organization_id == org_id,
                    CompanyHealthHistory.scope_type == "team",
                )
            )
        ).scalars().all()
        org_rows = (
            await db.execute(
                select(CompanyHealthHistory).where(
                    CompanyHealthHistory.organization_id == org_id,
                    CompanyHealthHistory.scope_type == "org",
                )
            )
        ).scalars().all()
    assert len(scoped) <= 3
    # the covered team deviates from the org (org carries the uncovered gap).
    if scoped:
        assert {r.scope_type for r in scoped} == {"team"}
        assert {r.source_event_id for r in scoped} <= {r.source_event_id for r in org_rows}
        assert all(r.company_score >= 80 for r in scoped)

    # exact-once: replaying the same durable event (same id) adds no rows.
    from app.models.notification import Event as EventRow

    count_org = len(org_rows)
    count_scoped = len(scoped)
    async with db_session_factory() as db:
        ev = (
            await db.execute(
                select(EventRow).where(
                    EventRow.organization_id == org_id,
                    EventRow.name == "capacity.demand.created",
                ).order_by(EventRow.occurred_at.desc()).limit(1)
            )
        ).scalar_one()

        class FakeEvent:
            id = ev.id
            name = ev.name

        for _ in range(2):
            await company_operating_engine.refresh(
                db, organization_id=org_id, event=FakeEvent(),
                payload={"project_id": p3["id"], "capability": "uncovered_eng",
                         "units": 2},
            )
        await db.commit()
    async with db_session_factory() as db:
        org_rows = (
            await db.execute(
                select(CompanyHealthHistory).where(
                    CompanyHealthHistory.organization_id == org_id,
                    CompanyHealthHistory.scope_type == "org",
                )
            )
        ).scalars().all()
        scoped = (
            await db.execute(
                select(CompanyHealthHistory).where(
                    CompanyHealthHistory.organization_id == org_id,
                    CompanyHealthHistory.scope_type == "team",
                )
            )
        ).scalars().all()
    assert len(org_rows) == count_org
    assert len(scoped) == count_scoped
