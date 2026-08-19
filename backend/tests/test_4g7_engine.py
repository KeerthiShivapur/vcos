"""Slice 4G.7 — Universal Company Operating Intelligence engine.

Under test:

* company_state: one composed picture of the company — the eight dimensions
  always appear and the attention list is bounded and deterministic,
* health: the eight explainable domains computed over the canonical
  surfaces; the company score is the weighted composition; exact-once
  CompanyHealthHistory trail (replays converge, one row per event),
* primary constraint: the weakest domain carries the constraint, its root
  cause and interventions,
* root_cause: business target -> metric -> driver -> customer impact ->
  project -> task/dependency -> capacity -> people/capability chains, with
  project and capability matching,
* impact: propagation across people/project/capability/customer/goal,
* recommendations: the universal queue is composed, bounded, deterministic,
  every item evidence-carrying and advisory-only,
* what_if: bounded consequences for reallocate / delay / hire — never a
  prediction,
* changes: "what changed" windowing (insufficient before two assessments,
  realistic deltas after),
* the governed memory loop: approve -> execute -> outcome -> learning with
  exact-once decision records,
* governance: org-wide surfaces 404 for scoped readers; enums 400-validated.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.intelligence.company_operating_engine import company_operating_engine
from app.models.company_operating import (
    CompanyDecision,
    CompanyHealthHistory,
)
from app.models.customer import Customer
from app.models.customer import CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment
from app.models.employee import Employee
from app.models.notification import Event
from app.models.org_capability_intelligence import OrgCapability
from app.models.project import Project
from app.models.task import Task
from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

COMPANY = "/api/v1/brain/execution/company"
CAP = "/api/v1/brain/execution/capacity"
BUS = "/api/v1/brain/execution/business"


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
    await _drain(db_session_factory)


async def _project(db_session_factory, org_id, name, status="active"):
    async with db_session_factory() as db:
        project = Project(
            organization_id=org_id, name=name,
            code=f"c7-{name.lower().replace(' ', '-')[:16]}", status=status,
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


async def _capability(db_session_factory, org_id, name, available=8):
    async with db_session_factory() as db:
        existing = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == org_id,
                    OrgCapability.canonical_name == name,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.capacity_available = available
            existing.capacity_committed = 0
            existing.capacity_reserved = 0
            existing.capacity_potential = available + 2
            existing.capacity_state = "available"
        else:
            db.add(OrgCapability(
                organization_id=org_id, skill_id=f"sk-{name[:20]}",
                canonical_name=name,
                capacity_potential=available + 2,
                capacity_committed=0, capacity_reserved=0,
                capacity_available=available, capacity_state="available",
                expert_count=3, evidence_count=3, lifecycle="established",
            ))
        await db.commit()


async def _demand(client, headers, project_id, capability, units,
                  window_start, window_end):
    resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": capability, "units": units,
              "window_start": window_start.isoformat(),
              "window_end": window_end.isoformat(), "proficiency": "high"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _window(days=30, offset=0):
    today = date.today()
    return today + timedelta(days=offset), today + timedelta(days=offset + days)


async def _business_target(client, headers, org_id, key, target_value,
                           end_days=60, db_session_factory=None):
    resp = await client.post(
        f"{BUS}/metrics",
        json={"key": key, "kind": "revenue", "direction": "up_is_good",
              "unit": "usd"},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    await _drain(db_session_factory)
    resp = await client.post(
        f"{BUS}/outcomes",
        json={"metric_key": key, "value": target_value * 0.5,
              "observed_at": (datetime.now().astimezone() - timedelta(days=10))
              .isoformat(), "source": "financial"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    if db_session_factory is not None:
        await _drain(db_session_factory)
    resp = await client.post(
        f"{BUS}/targets",
        json={"metric_key": key, "target_value": target_value,
              "end_date": (date.today() + timedelta(days=end_days)).isoformat()},
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    await _drain(db_session_factory)


async def _commitment(db_session_factory, org_id, customer_id, project_id,
                      summary="Ship the Q3 release", status="at_risk"):
    async with db_session_factory() as db:
        db.add(CustomerCommitment(
            organization_id=org_id, customer_id=customer_id,
            summary=summary,
            expected_at=date.today() + timedelta(days=14),
            status=status, project_id=project_id,
            source_event_id=f"seed-commitment-{abs(hash(summary + project_id)) % 10**12}",
        ))
        await db.commit()


async def _customer(db_session_factory, org_id, name="Enterprise North"):
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


async def _task(db_session_factory, org_id, project_id, assignee_id,
                status="active", hours=45):
    async with db_session_factory() as db:
        db.add(Task(
            organization_id=org_id, project_id=project_id,
            assignee_id=assignee_id, title="Heavy task", status=status,
            estimate_hours=float(hours),
        ))
        await db.commit()


async def _employee(db_session_factory, org_id, email="worker@acme.test.co",
                    name="Work"):
    async with db_session_factory() as db:
        row = Employee(
            organization_id=org_id, employee_number=f"emp-{email[:8]}",
            first_name=name, last_name="Er", display_name=name,
            email=email,
        )
        db.add(row)
        await db.flush()
        eid = row.id
        await db.commit()
    return eid


async def _health_rows(db_session_factory, org_id):
    async with db_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(CompanyHealthHistory).where(
                        CompanyHealthHistory.organization_id == org_id,
                    ).order_by(CompanyHealthHistory.occurred_at.asc())
                )
            ).scalars().all()
        )


async def _company_health(db_session_factory, org_id):
    async with db_session_factory() as db:
        return await company_operating_engine.health(
            db, organization_id=org_id,
        )


# ---------------------------------------------------------------------------
# 1. Universal company state
# ---------------------------------------------------------------------------

async def test_company_state_composes_all_dimensions(client, db_session_factory):
    org = await register_org(client, email="4g7_state@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    project = await _project(db_session_factory, org_id, "Flagship")
    ws, we = _window()
    await _capability(db_session_factory, org_id, "backend_eng", available=4)
    created = await client.post(
        "/api/v1/brain/execution/strategy/goals",
        json={"title": "Grow ARR", "kind": "revenue", "priority": 1,
              "metric_kind": "revenue", "metric_unit": "usd",
              "target_value": 1000, "current_value": 100, "timeline_label": "FY2026"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    await _demand(client, headers, project, "backend_eng", 6, ws, we)
    await _capability(db_session_factory, org_id, "design", available=2)
    other = await _project(db_session_factory, org_id, "Design Work")
    await _demand(client, headers, other, "design", 3, ws, we)
    await _drain(db_session_factory)

    response = await client.get(f"{COMPANY}/state", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["advisory_only"] is True
    assert set(body["dimensions"].keys()) == {
        "strategy", "execution", "coordination", "capacity",
        "people", "customers", "financial", "knowledge",
    }
    assert len(body["attention"]) <= 5
    assert body["generated_at"]


async def test_company_state_is_bounded_and_attention_prioritized(
    client, db_session_factory,
):
    org = await register_org(client, email="4g7_st2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    for i in range(6):
        await _project(db_session_factory, org_id, f"Proj {i}")
    ws, we = _window()
    await _capability(db_session_factory, org_id, "scarce", available=1)
    for i in range(4):
        p = await _project(db_session_factory, org_id, f"Scarce {i}")
        await _demand(client, headers, p, "scarce", 3, ws, we)
    await _drain(db_session_factory)

    response = await client.get(f"{COMPANY}/state", headers=headers)
    body = response.json()
    attention = body["attention"]
    assert len(attention) <= 5
    assert attention[0]["kind"] == "capacity_constraint"
    assert attention[0]["priority"] == 1


# ---------------------------------------------------------------------------
# 2. Company health: exact-once trail, eight domains, primary constraint
# ---------------------------------------------------------------------------

async def test_health_exact_once_trail_and_eight_domains(
    client, db_session_factory,
):
    org = await register_org(client, email="4g7_hlth@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    actor = org["user"]["id"]

    project = await _project(db_session_factory, org_id, "Health Project")
    ws, we = _window()
    await _capability(db_session_factory, org_id, "nlp_eng", available=1)
    await _demand(client, headers, project, "nlp_eng", 4, ws, we)
    await _publish(db_session_factory, org_id, actor, "task.completed", {
        "organization_id": org_id, "task_id": "task-health-1",
        "project_id": project, "title": "Ship module",
    })
    await _publish(db_session_factory, org_id, actor, "milestone.completed", {
        "organization_id": org_id, "project_id": project,
        "milestone_id": "ms-health-1", "title": "M1",
    })

    rows = await _health_rows(db_session_factory, org_id)
    assert len(rows) == 3  # demand.created + task.completed + milestone.completed

    async with db_session_factory() as db:
        for row in rows:
            before = len(list(
                (await db.execute(
                    select(CompanyHealthHistory).where(
                        CompanyHealthHistory.organization_id == org_id,
                        CompanyHealthHistory.source_event_id == row.source_event_id,
                    )
                )).scalars().all()
            ))
            await company_operating_engine.refresh(
                db, organization_id=org_id,
                event=SimpleNamespace(name=row.event_name, id=row.source_event_id),
                payload={},
            )
            await db.commit()
            after = len(list(
                (await db.execute(
                    select(CompanyHealthHistory).where(
                        CompanyHealthHistory.organization_id == org_id,
                        CompanyHealthHistory.source_event_id == row.source_event_id,
                    )
                )).scalars().all()
            ))
            assert before == 1 and after == 1, "replay converges"

    health = await _company_health(db_session_factory, org_id)
    assert health["advisory_only"] is True
    assert [d["key"] for d in health["domains"]] == [
        "strategy", "execution", "people", "capacity", "customers",
        "financial", "coordination", "knowledge",
    ]
    for d in health["domains"]:
        assert 0 <= d["score"] <= 100
        assert d["state"] in ("healthy", "concerned", "at_risk", "critical")
        assert isinstance(d["evidence_count"], int)
    assert health["history"], "the trail is served"
    # the capacity bottleneck dominates: the primary constraint names it
    constraint = health["primary_constraint"]
    assert constraint is not None
    assert constraint["domain"] == "capacity"
    assert "nlp_eng" in str(constraint["label"])


async def test_health_live_compute_before_any_event(client, db_session_factory):
    org = await register_org(client, email="4g7_hln@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    health = await _company_health(db_session_factory, org_id)
    assert health["history"] == []
    assert health["company_state"] in ("healthy", "concerned")
    assert len(health["domains"]) == 8
    assert health["generated_at"]


async def test_primary_constraint_drives_company_state(client, db_session_factory):
    org = await register_org(client, email="4g7_cst@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "leadership", available=0)
    for i in range(3):
        p = await _project(db_session_factory, org_id, f"P{i}")
        await _demand(client, headers, p, "leadership", 2, ws, we)
    await _drain(db_session_factory)

    health = await _company_health(db_session_factory, org_id)
    capacity_domain = next(d for d in health["domains"] if d["key"] == "capacity")
    assert capacity_domain["state"] in ("at_risk", "critical")
    constraint = health["primary_constraint"]
    assert constraint["domain"] == "capacity"
    assert constraint["interventions"], "interventions always ride along"
    assert health["company_state"] in ("concerned", "at_risk", "critical")
    assert "capacity" in health["summary"]


# ---------------------------------------------------------------------------
# 3. Root-cause chains
# ---------------------------------------------------------------------------

async def test_root_cause_from_business_target(client, db_session_factory):
    org = await register_org(client, email="4g7_rc1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _business_target(client, headers, org_id, "recurring_revenue", 500,
                           db_session_factory=db_session_factory)
    await client.post(
        f"{BUS}/drivers",
        json={"key": "d_sales", "title": "Sales pipeline conversion",
              "driver_type": "customer", "strength": "strong",
              "direction": "toward", "impact_shape": "attribute",
              "metric_keys": ["recurring_revenue"]},
        headers=headers,
    )
    project = await _project(db_session_factory, org_id, "Deliver Growth")
    await _drain(db_session_factory)

    result = await _root_cause(db_session_factory, org_id, "recurring_revenue")
    assert result["matched_on"] == "business_target"
    layers = [s["layer"] for s in result["chain"]]
    assert layers[0] == "business_problem"
    assert "metric" in layers
    assert "driver" in layers
    assert layers[-1] == "people_capability"
    assert result["resolution_hint"]


async def _root_cause(db_session_factory, org_id, problem):
    async with db_session_factory() as db:
        return await company_operating_engine.root_cause(
            db, organization_id=org_id, problem=problem,
        )


async def test_root_cause_from_project_and_capability(client, db_session_factory):
    org = await register_org(client, email="4g7_rc2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    customer = await _customer(db_session_factory, org_id)
    project = await _project(db_session_factory, org_id, "Build Portal")
    await _commitment(db_session_factory, org_id, customer, project)

    result = await _root_cause(db_session_factory, org_id, "Build Portal")
    assert result["matched_on"] == "project"
    layers = [s["layer"] for s in result["chain"]]
    assert layers[0] == "business_problem"
    assert "capacity_constraint" in layers or "people_capability" in layers
    assert "customer_impact" in layers

    ws, we = _window()
    await _capability(db_session_factory, org_id, "data_eng", available=1)
    await _demand(client, headers, project, "data_eng", 4, ws, we)
    await _drain(db_session_factory)

    result = await _root_cause(db_session_factory, org_id, "data_eng")
    assert result["matched_on"] == "capability"
    layers = [s["layer"] for s in result["chain"]]
    assert layers[-1] == "people_capability"
    assert "capacity_constraint" in layers


async def test_root_cause_unmatched_is_declared(client, db_session_factory):
    org = await register_org(client, email="4g7_rc3@test.co")

    result = await _root_cause(db_session_factory, org["organization"]["id"], "nothing matches this")
    assert result["matched_on"] == "none"
    assert result["chain"] == []


# ---------------------------------------------------------------------------
# 4. Impact propagation
# ---------------------------------------------------------------------------

async def _impact(db_session_factory, org_id, subject_type, subject_id):
    async with db_session_factory() as db:
        return await company_operating_engine.impact(
            db, organization_id=org_id,
            subject_type=subject_type, subject_id=subject_id,
        )


async def test_impact_project_and_customer_and_goal(client, db_session_factory):
    org = await register_org(client, email="4g7_imp1@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    customer = await _customer(db_session_factory, org_id)
    project = await _project(db_session_factory, org_id, "Portal")
    await _commitment(db_session_factory, org_id, customer, project)

    result = await _impact(db_session_factory, org_id, "project", project)
    assert result["subject_type"] == "project"
    assert result["label"] == "Portal"
    steps = [s["step"] for s in result["chain"]]
    assert steps[0] == "execution"
    assert "customers" in steps
    assert result["consequence_summary"]

    result = await _impact(db_session_factory, org_id, "customer", customer)
    assert result["subject_type"] == "customer"
    steps = [s["step"] for s in result["chain"]]
    assert steps[0] == "customers"
    assert "execution" in steps

    result = await _impact(db_session_factory, org_id, "goal", "no-such-goal")
    assert result["consequence_summary"] == "goal not found"


async def test_impact_person_and_capability(client, db_session_factory):
    org = await register_org(client, email="4g7_imp2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    worker = await _employee(db_session_factory, org_id)
    project = await _project(db_session_factory, org_id, "Heavy Lift")
    await _task(db_session_factory, org_id, project, worker, hours=45)

    result = await _impact(db_session_factory, org_id, "person", worker)
    assert result["subject_type"] == "person"
    steps = [s["step"] for s in result["chain"]]
    assert steps[0] == "people"
    assert "execution" in steps

    ws, we = _window()
    await _capability(db_session_factory, org_id, "ml_eng", available=2)
    await _demand(client, headers, project, "ml_eng", 5, ws, we)
    await _drain(db_session_factory)

    customer_id = await _customer(db_session_factory, org_id)
    async with db_session_factory() as db:
        db.add(CustomerProjectLink(
            organization_id=org_id, customer_id=customer_id,
            project_id=project, status="active",
        ))
        await db.commit()

    result = await _impact(db_session_factory, org_id, "capability", "ml_eng")
    assert result["subject_type"] == "capability"
    steps = [s["step"] for s in result["chain"]]
    assert steps[0] == "capacity"
    assert "execution" in steps
    assert "strategy" in steps or "customers" in steps


async def test_impact_unknown_subject_type(client, db_session_factory):
    org = await register_org(client, email="4g7_imp3@test.co")
    result = await _impact(
        db_session_factory, org["organization"]["id"], "rocket", "x",
    )
    assert "must be person | project | capability | customer | goal" in (
        result["consequence_summary"]
    )


# ---------------------------------------------------------------------------
# 5. Universal recommendation queue
# ---------------------------------------------------------------------------

async def _recommendations(db_session_factory, org_id):
    async with db_session_factory() as db:
        return await company_operating_engine.recommendations(
            db, organization_id=org_id,
        )


async def test_universal_recommendations_composed_bounded_advisory(
    client, db_session_factory,
):
    org = await register_org(client, email="4g7_rec@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _business_target(client, headers, org_id, "recurring_revenue", 500,
                           db_session_factory=db_session_factory)
    ws, we = _window()
    await _capability(db_session_factory, org_id, "security_eng", available=0)
    project = await _project(db_session_factory, org_id, "Hardened")
    await _demand(client, headers, project, "security_eng", 3, ws, we)
    await _drain(db_session_factory)

    result = await _recommendations(db_session_factory, org_id)
    assert result["advisory_only"] is True
    assert result["total"] > 0
    assert len(result["recommendations"]) <= 20
    keys = [r["key"] for r in result["recommendations"]]
    assert len(keys) == len(set(keys)), "keys are unique"
    for rec in result["recommendations"]:
        assert rec["title"]
        assert rec["why"]
        assert rec["confidence"]
        assert rec["owner_label"] is not None
        assert rec["expected_improvement"]
        assert rec["evidence_ref"]
        assert rec["source"] in (
            "strategy", "execution", "capacity", "coordination",
            "customer", "business", "knowledge",
        )


async def test_recommendations_mention_capacity_constraint_first(
    client, db_session_factory,
):
    org = await register_org(client, email="4g7_rec2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "infra_eng", available=0)
    project = await _project(db_session_factory, org_id, "Infra Push")
    await _demand(client, headers, project, "infra_eng", 3, ws, we)
    await _drain(db_session_factory)

    result = await _recommendations(db_session_factory, org_id)
    assert result["recommendations"][0]["source"] == "capacity"
    assert result["recommendations"][0]["kind"] == "capacity_constraint"
    assert "infra_eng" in result["recommendations"][0]["title"]


# ---------------------------------------------------------------------------
# 6. Bounded what-if
# ---------------------------------------------------------------------------

async def _what_if(db_session_factory, org_id, scenario_type, payload):
    async with db_session_factory() as db:
        return await company_operating_engine.what_if(
            db, organization_id=org_id,
            scenario_type=scenario_type, payload=payload,
        )


async def test_what_if_delay_scenario(client, db_session_factory):
    org = await register_org(client, email="4g7_wi1@test.co")
    org_id = org["organization"]["id"]
    project = await _project(db_session_factory, org_id, "Deliverable")

    result = await _what_if(db_session_factory, org_id, "delay", {
        "project_id": project, "days": 21,
    })
    assert result["not_a_prediction"] is True
    assert result["scenario_type"] == "delay"
    assert result["consequences"], "delay propagates consequences"
    assert any(
        "delayed 21 days" in c["label"] for c in result["consequences"]
    )
    assert "humans decide" in result["note"]


async def test_what_if_reallocate_scenario(client, db_session_factory):
    org = await register_org(client, email="4g7_wi2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "frontend_eng", available=2)
    pa = await _project(db_session_factory, org_id, "Alpha")
    pb = await _project(db_session_factory, org_id, "Beta")
    await _demand(client, headers, pa, "frontend_eng", 3, ws, we)
    await _demand(client, headers, pb, "frontend_eng", 2, ws, we)
    await _drain(db_session_factory)

    result = await _what_if(db_session_factory, org_id, "reallocate", {
        "capability": "frontend_eng", "from_project_id": pa,
        "to_project_id": pb, "units": 1,
    })
    assert result["scenario_type"] == "reallocate"
    assert result["not_a_prediction"] is True
    assert result["scenario"]["type"] == "reallocate"
    assert result["scenario"]["units"] == 1
    assert result["consequences"], "reallocation carries goal directions"


async def test_what_if_hire_scenario(client, db_session_factory):
    org = await register_org(client, email="4g7_wi3@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    await _capability(db_session_factory, org_id, "qa_eng", available=1)
    project = await _project(db_session_factory, org_id, "Quality")
    await _demand(client, headers, project, "qa_eng", 5, ws, we)
    await _drain(db_session_factory)

    result = await _what_if(db_session_factory, org_id, "hire", {
        "capability": "qa_eng", "people": 2, "ramp_days": 30,
    })
    assert result["scenario_type"] == "hire"
    assert result["scenario"]["people"] == 2
    assert any("hire 2 people" in c["label"] for c in result["consequences"])
    assert any("ramp" in c["label"] for c in result["consequences"])


async def test_what_if_unknown_scenario_is_declared(client, db_session_factory):
    org = await register_org(client, email="4g7_wi4@test.co")
    result = await _what_if(
        db_session_factory, org["organization"]["id"], "moon", {},
    )
    assert "reallocate | delay | hire" in result["note"]


# ---------------------------------------------------------------------------
# 7. What changed
# ---------------------------------------------------------------------------

async def _changes(db_session_factory, org_id):
    async with db_session_factory() as db:
        return await company_operating_engine.changes(
            db, organization_id=org_id,
        )


async def test_changes_insufficient_history_at_start(client, db_session_factory):
    org = await register_org(client, email="4g7_ch1@test.co")
    result = await _changes(db_session_factory, org["organization"]["id"])
    assert result["window"] == "insufficient_history"
    assert result["changes"][0]["kind"] == "no_window"


async def test_changes_reports_real_deltas(client, db_session_factory):
    org = await register_org(client, email="4g7_ch2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    ws, we = _window()
    # row 1: platform_eng is a critical bottleneck (1 unit available, 5 demanded)
    await _capability(db_session_factory, org_id, "platform_eng", available=1)
    project = await _project(db_session_factory, org_id, "Platform")
    await _demand(client, headers, project, "platform_eng", 5, ws, we)
    await _drain(db_session_factory)

    # row 2: the constraint is relieved (20 units available) — the company
    # health trail must report the improved capacity domain
    await _capability(db_session_factory, org_id, "platform_eng", available=20)
    await _demand_v2(client, headers, project, "platform_eng", 5, ws, we)
    await _drain(db_session_factory)

    limits = await _changes(db_session_factory, org_id)
    assert limits["window"] != "insufficient_history"
    assert limits["company_score_after"] > limits["company_score_before"]
    capacities = [c for c in limits["changes"] if c.get("domain") == "capacity"]
    assert capacities and capacities[0]["kind"] in (
        "improved", "state_shift", "resolved_constraint",
    )
    assert capacities[0]["to_score"] > capacities[0]["from_score"]


async def _demand_v2(client, headers, project_id, capability, units,
                     ws, we):
    """Re-publish demand to drive a second company health assessment."""
    resp = await client.post(
        f"{CAP}/demands",
        json={"project_id": project_id, "capability": capability, "units": units,
              "window_start": ws.isoformat(), "window_end": we.isoformat(),
              "proficiency": "high"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 8. Governed memory loop (approve -> execute -> outcome -> learning)
# ---------------------------------------------------------------------------

async def test_governed_memory_loop_closes_with_learning(
    client, db_session_factory,
):
    org = await register_org(client, email="4g7_mem@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    approved = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "Hire two platform engineers",
              "recommendation_key": "capacity:01",
              "rationale": "platform_eng is the company bottleneck",
              "impact_label": "gap 3 units",
              "expected_improvement": "clear the platform constraint",
              "confidence": 0.8, "owner_label": "Technical Leadership"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    decision_id = approved.json()["decision_id"]
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(CompanyDecision).where(
                        CompanyDecision.organization_id == org_id,
                        CompanyDecision.decision_id == decision_id,
                    )
                )
            ).scalars().all()
        )
        assert len(rows) == 1
        assert rows[0].state == "approved"
        assert rows[0].kind == "hire"
        assert rows[0].recommendation_key == "capacity:01"

    memory = await _memory(db_session_factory, org_id)
    assert memory["total_decisions"] == 1
    assert memory["decisions"][0]["decision_id"] == decision_id
    assert memory["decisions"][0]["state"] == "approved"

    executed = await client.post(
        f"{COMPANY}/decisions/{decision_id}/execute",
        json={"executed_by_label": "Ada Owner"}, headers=headers,
    )
    assert executed.status_code == 200, executed.text
    await _drain(db_session_factory)

    outcome = await client.post(
        f"{COMPANY}/decisions/{decision_id}/outcome",
        json={"outcome_kind": "successful", "effectiveness": 0.75,
              "lesson": "hiring ahead of the bottleneck clears it faster than reallocation",
              "evidence": [{"source": "capacity center", "gap_before": 3, "gap_after": 0}]},
        headers=headers,
    )
    assert outcome.status_code == 200, outcome.text
    await _drain(db_session_factory)

    memory = await _memory(db_session_factory, org_id)
    decision = memory["decisions"][0]
    assert decision["state"] == "outcome_recorded"
    assert decision["outcome_kind"] == "successful"
    assert decision["effectiveness"] == 0.75
    assert len(memory["learnings"]) == 1
    assert memory["learnings"][0]["lesson"] == (
        "hiring ahead of the bottleneck clears it faster than reallocation"
    )
    assert memory["learnings"][0]["decision_id"] == decision_id


async def _memory(db_session_factory, org_id):
    async with db_session_factory() as db:
        return await company_operating_engine.memory(
            db, organization_id=org_id,
        )


async def test_decision_exact_once_replay(client, db_session_factory):
    org = await register_org(client, email="4g7_mem2@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    approved = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "delay_project", "title": "Delay Beta by two weeks",
              "rationale": "frontend_eng scarce"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        event = (
            await db.execute(
                select(Event).where(
                    Event.organization_id == org_id,
                    Event.name == "company.decision.recorded",
                ).order_by(Event.occurred_at.desc()).limit(1)
            )
        ).scalar_one()
        await company_operating_engine.record_decision(
            db, organization_id=org_id,
            event=SimpleNamespace(name="company.decision.recorded", id=event.id),
            payload={"organization_id": org_id,
                     "decision_id": approved.json()["decision_id"],
                     "kind": "delay_project", "title": "Delay Beta by two weeks"},
        )
        await db.commit()
        count = len(list(
            (await db.execute(
                select(CompanyDecision).where(
                    CompanyDecision.organization_id == org_id,
                    CompanyDecision.decision_id == approved.json()["decision_id"],
                )
            )).scalars().all()
        ))
        assert count == 1, "decision replay converges"


async def test_decision_validation_400s(client, db_session_factory):
    org = await register_org(client, email="4g7_val@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    bad_kind = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "teleport", "title": "x"}, headers=headers,
    )
    assert bad_kind.status_code == 400
    assert "kind must be one of" in bad_kind.json()["detail"]

    notitle = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": " "}, headers=headers,
    )
    assert notitle.status_code == 400

    bad_state = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "x", "state": "flying"}, headers=headers,
    )
    assert bad_state.status_code == 400

    bad_conf = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "x", "confidence": 3}, headers=headers,
    )
    assert bad_conf.status_code == 400

    bad_whatif = await client.post(
        f"{COMPANY}/what-if",
        json={"scenario_type": "teleport"}, headers=headers,
    )
    assert bad_whatif.status_code == 200
    assert "reallocate | delay | hire" in bad_whatif.json()["note"]

    no_auth = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "x"},
    )
    assert no_auth.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 9. Governance: org-wide 404 for scoped readers; effect of being scoped
# ---------------------------------------------------------------------------

async def test_scoped_reader_404s_on_company_surfaces(client, db_session_factory):
    org = await register_org(client, email="4g7_gov@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4g7 scope", "scope_type": "organization", "entity_id": org_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped = await invite_scoped_reader(
        client, headers, scope.json()["id"], "reader4g7@test.co",
    )

    for path in (
        f"{COMPANY}/state", f"{COMPANY}/health", f"{COMPANY}/recommendations",
        f"{COMPANY}/changes", f"{COMPANY}/memory",
        f"{COMPANY}/root-cause?problem=x", f"{COMPANY}/impact?subject_type=project&subject_id=x",
    ):
        response = await client.get(path, headers=scoped)
        assert response.status_code == 404, (path, response.text)

    scoped_write = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "x"}, headers=scoped,
    )
    # governed writes require an ORG-WIDE permission grant; a scoped
    # caller is denied before the 404 scope guard can run
    assert scoped_write.status_code == 403, scoped_write.text


async def test_company_query_routes_universal_intent(client, db_session_factory):
    org = await register_org(client, email="4g7_qry@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    await _business_target(client, headers, org_id, "recurring_revenue", 500,
                           db_session_factory=db_session_factory)

    response = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "what should the company do next"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "company_operating"
    assert body["advisory_only"] is True
    assert "recommendations" in body

    response = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "what is the biggest company constraint"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "company_operating"

    response = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "what changed at the company level"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "company_operating"
    assert "window" in response.json()

    response = await client.post(
        "/api/v1/brain/knowledge/query",
        json={"question": "how is the company performing"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == "business_performance"