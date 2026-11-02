"""Slice 4H.5 — Strategic Decision-to-Action & Execution Intelligence.

Under test (contract §12, engine-level core):

1. plan derivation on an approved decision with canonical anchors: bounded
   ≤5 steps, sanctioned types, existing targets, basis on every step,
   honesty flags, derivation_status "ok".
2. dry-run writes nothing and emits zero events.
3. pre-approval decisions are rejected (advisory-before-action).
4. non-invention: rich free-text + zero canonical anchors -> empty plan
   with derivation_status "insufficient_canonical_basis" (L18).
5. authorization via action_ops_engine.propose stores the lineage columns;
   4E.6 fingerprint exact-once still holds (replay, no dup row).
6. lineage validation: unknown decision / pre-approval decision / unknown
   scenario are all rejected before any row is written.
7. execution chain stitches decision -> actions -> evidence -> artifacts ->
   outcomes; every node cites ids; bounds respected.
8. tenant isolation: a sibling org gets None (404 at the API layer).
9. byte-identical plan replay (L19 plan side — no generated_at).
10. brain intents resolve; 4E.6 + 4G.7 collision guards hold.
11. L16 origin compatibility: direct-propose actions without lineage stay
    fully valid and never appear in another decision's chain.
12. no LLM client is imported on the plan/chain path (Amendment 10).
"""

import inspect
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.company_actions import CompanyAction, CompanyActionEvent
from app.models.company_operating import (
    CompanyCausalEdge,
    CompanyDecision,
    CompanyScenarioRun,
)
from app.models.notification import Event as EventRow
from app.models.project import Project
from app.models.approval import Risk
from tests.conftest import register_org

BRAIN_QUERY = "/api/v1/brain/knowledge/query"

_SANCTIONED_TYPES = {"task", "decision", "communication", "knowledge", "meeting", "project"}


class _User:
    """Minimal actor for engine calls (only `.id` is read)."""

    def __init__(self, org):
        self.id = (org.get("user") or {}).get("id", "tester")


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


async def _plan(db_session_factory, org_id, decision_id):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.derive_action_plan(
            db, organization_id=org_id, decision_id=decision_id,
        )
        await db.commit()
        return result


async def _chain(db_session_factory, org_id, decision_id):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.execution_chain(
            db, organization_id=org_id, decision_id=decision_id,
        )
        await db.commit()
        return result


async def _propose(db_session_factory, org_id, user, **kw):
    from app.knowledge.action_ops_engine import action_ops_engine

    async with db_session_factory() as db:
        result = await action_ops_engine.propose(
            db, organization_id=org_id, user=user, **kw,
        )
        await db.commit()
        return result


async def _count(db_session_factory, org_id, model, column=None, value=None):
    async with db_session_factory() as db:
        stmt = select(func.count()).select_from(model).where(
            model.organization_id == org_id
        )
        if column is not None:
            stmt = stmt.where(column == value)
        return int((await db.execute(stmt)).scalar_one() or 0)


async def _approved_decision(client, headers, title="Delay the platform migration"):
    res = await client.post(
        "/api/v1/brain/execution/company/decisions",
        json={"kind": "delay_project", "title": title,
              "rationale": "protect the customer commitment",
              "confidence": 0.8, "owner_label": "Delivery Leadership"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()["decision_id"]


async def _seed_anchors(db_session_factory, org_id, project_code="4h5-platform"):
    """One real open risk + one real project — the canonical anchors."""
    async with db_session_factory() as db:
        db.add(Risk(
            organization_id=org_id, title="Integration slip risk",
            description="vendor API may slip", probability=4, impact=4,
            risk_score=16, status="open",
        ))
        db.add(Project(
            organization_id=org_id, code=project_code, name="Platform Migration",
            description="4h5 anchor", status="active",
        ))
        await db.commit()
        risk_id = (
            await db.execute(select(Risk.id).where(Risk.organization_id == org_id))
        ).scalars().first()
        project_id = (
            await db.execute(select(Project.id).where(Project.organization_id == org_id))
        ).scalars().first()
    return risk_id, project_id


async def _attach_state_context(db_session_factory, org_id, decision_id):
    from app.intelligence.company_operating_engine import company_operating_engine

    async with db_session_factory() as db:
        result = await company_operating_engine.attach_state_context(
            db, organization_id=org_id, decision_id=decision_id,
        )
        await db.commit()
        return result


# ---------------------------------------------------------------------------
# 1 + 2. canonical plan from anchors; dry-run writes nothing
# ---------------------------------------------------------------------------

async def test_1_2_plan_from_anchors_and_dry_run_is_eventless(client, db_session_factory):
    org = await register_org(client, email="4h5_plan@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    decision_id = await _approved_decision(client, headers)
    await _drain(db_session_factory)

    risk_id, project_id = await _seed_anchors(db_session_factory, org_id)
    # a canonical edge from the decision to its anchored project — the same
    # join the 4H.3 state anchor reads, so the plan can cite the project
    async with db_session_factory() as db:
        db.add(CompanyCausalEdge(
            organization_id=org_id,
            source_type="decision", source_id=decision_id,
            target_type="project", target_id=project_id,
            kind="constraint->project", confidence="high",
            source_event_id="evt:4h5-edge",
        ))
        await db.commit()
    attached = await _attach_state_context(db_session_factory, org_id, decision_id)
    assert attached.get("accepted") is True, attached

    plan = await _plan(db_session_factory, org_id, decision_id)
    assert plan is not None
    assert plan["decision"]["decision_id"] == decision_id
    assert plan["decision"]["state"] == "approved"
    assert plan["honesty"]["advisory_only"] is True
    assert plan["honesty"]["not_a_prediction"] is True
    assert plan["honesty"]["derivation_status"] == "ok"
    steps = plan["proposed_steps"]
    assert 1 <= len(steps) <= 5
    for i, step in enumerate(steps, start=1):
        assert step["action_type"] in _SANCTIONED_TYPES
        assert step["basis"]["decision_id"] == decision_id
        assert step["basis"]["relation"]
        assert step["target"]["id"]
        assert step["step_no"] == i
        assert set(step["approval_expected"]) == {"policy", "approval_required"}
    assert any(s["basis"].get("risk_id") == risk_id for s in steps)
    assert any(s["target"]["id"] == project_id for s in steps)

    # dry-run proof: zero rows written, zero events emitted
    actions_before = await _count(db_session_factory, org_id, CompanyAction)
    events_before = await _count(db_session_factory, org_id, EventRow)
    audit_before = await _count(db_session_factory, org_id, CompanyActionEvent)
    again = await _plan(db_session_factory, org_id, decision_id)
    assert again == plan  # byte-identical replay (L19 plan side)
    actions_after = await _count(db_session_factory, org_id, CompanyAction)
    events_after = await _count(db_session_factory, org_id, EventRow)
    audit_after = await _count(db_session_factory, org_id, CompanyActionEvent)
    assert (actions_before, events_before, audit_before) == (
        actions_after, events_after, audit_after
    )


# ---------------------------------------------------------------------------
# 3. pre-approval decisions are rejected
# ---------------------------------------------------------------------------

async def test_3_pre_approval_decision_rejected(client, db_session_factory):
    org = await register_org(client, email="4h5_pre@test.co")
    _, org_id = org["headers"], org["organization"]["id"]

    async with db_session_factory() as db:
        row = CompanyDecision(
            organization_id=org_id, decision_id="dec:proposed:4h5",
            kind="hire", title="A decision nobody approved yet",
            state="proposed", source_event_id="evt:4h5-proposed",
        )
        db.add(row)
        await db.commit()

    plan = await _plan(db_session_factory, org_id, "dec:proposed:4h5")
    assert plan is not None and plan.get("rejected") is True
    assert plan["reason"] == "decision not yet approved"
    assert "proposed_steps" not in plan


# ---------------------------------------------------------------------------
# 4. non-invention: text alone cannot manufacture steps (L18)
# ---------------------------------------------------------------------------

async def test_4_non_invention_without_canonical_anchors(client, db_session_factory):
    org = await register_org(client, email="4h5_invent@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    res = await client.post(
        "/api/v1/brain/execution/company/decisions",
        json={"kind": "other", "title": "Transform our go-to-market motion",
              "rationale": "we should obviously hire ten engineers, rebuild the "
                           "website, launch in three regions and open a office "
                           "in Austin as soon as possible",
              "confidence": 0.9, "owner_label": "Leadership"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    decision_id = res.json()["decision_id"]
    await _drain(db_session_factory)

    plan = await _plan(db_session_factory, org_id, decision_id)
    assert plan is not None
    assert plan["proposed_steps"] == []
    assert plan["honesty"]["derivation_status"] == "insufficient_canonical_basis"
    assert plan["honesty"]["advisory_only"] is True


# ---------------------------------------------------------------------------
# 5. authorization stores lineage; exact-once replay holds
# ---------------------------------------------------------------------------

async def test_5_lineage_propose_and_exact_once(client, db_session_factory):
    org = await register_org(client, email="4h5_auth@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]
    decision_id = await _approved_decision(client, headers)
    await _drain(db_session_factory)

    async with db_session_factory() as db:
        scenario_row = CompanyScenarioRun(
            organization_id=org_id, scope_type="org", scope_id=None,
            scenario_kind="delay", input_hash="h4h5", snapshot_ref="st:4h5",
            source_event_id="evt:4h5-scenario",
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(scenario_row)
        await db.commit()
        scenario_id = scenario_row.id

    first = await _propose(
        db_session_factory, org_id, _User(org),
        action_type="task", title="Rehearse the migration rollback plan",
        source_problem="delay_project decision",
        source_company_decision_id=decision_id,
        source_scenario_id=scenario_id,
    )
    assert first is not None and first.get("deduplicated") is not True
    assert first["source_company_decision_id"] == decision_id
    assert first["source_scenario_id"] == scenario_id

    replay = await _propose(
        db_session_factory, org_id, _User(org),
        action_type="task", title="Rehearse the migration rollback plan",
        source_problem="delay_project decision",
        source_company_decision_id=decision_id,
        source_scenario_id=scenario_id,
    )
    assert replay is not None and replay.get("deduplicated") is True
    assert replay["id"] == first["id"]
    assert await _count(db_session_factory, org_id, CompanyAction) == 1


# ---------------------------------------------------------------------------
# 6. lineage validation rejects bad anchors before writing
# ---------------------------------------------------------------------------

async def test_6_lineage_validation(client, db_session_factory):
    org = await register_org(client, email="4h5_valid@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    decision_id = await _approved_decision(client, headers)
    proposed_id = "dec:unapproved:4h5"
    async with db_session_factory() as db:
        db.add(CompanyDecision(
            organization_id=org_id, decision_id=proposed_id,
            kind="hire", title="Not approved", state="recommended",
            source_event_id="evt:4h5-unapproved",
        ))
        await db.commit()

    from app.knowledge.action_ops_engine import action_ops_engine

    async with db_session_factory() as db:
        for bad_kwargs in (
            {"source_company_decision_id": "dec:missing:nowhere"},
            {"source_company_decision_id": proposed_id},
            {"source_scenario_id": "scn:missing"},
        ):
            try:
                await action_ops_engine.propose(
                    db, organization_id=org_id, user=_User(org),
                    action_type="task", title="Validate the lineage anchor",
                    **bad_kwargs,
                )
                raise AssertionError(f"expected ValueError for {bad_kwargs}")
            except ValueError:
                pass
        await db.rollback()
    assert await _count(db_session_factory, org_id, CompanyAction) == 0


# ---------------------------------------------------------------------------
# 7. chain stitching: decision -> actions -> evidence -> artifacts -> outcomes
# ---------------------------------------------------------------------------

async def test_7_chain_stitching_and_bounds(client, db_session_factory):
    org = await register_org(client, email="4h5_chain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    decision_id = await _approved_decision(client, headers)
    await _drain(db_session_factory)

    action = await _propose(
        db_session_factory, org_id, _User(org),
        action_type="task", title="Freeze the migration window",
        source_problem="delay_project decision",
        source_company_decision_id=decision_id,
    )
    action_id = action["id"]
    # low risk auto-approved + routed: the task artifact exists already
    assert action["state"] == "ready"
    assert action["target_type"] == "task" and action["target_id"]

    from app.knowledge.action_ops_engine import action_ops_engine

    async with db_session_factory() as db:
        await action_ops_engine.transition(
            db, organization_id=org_id, action_id=action_id, user=_User(org),
            transition="start",
        )
        await db.commit()
    async with db_session_factory() as db:
        await action_ops_engine.transition(
            db, organization_id=org_id, action_id=action_id, user=_User(org),
            transition="complete",
        )
        await db.commit()
    async with db_session_factory() as db:
        outcome = await action_ops_engine.record_outcome(
            db, organization_id=org_id, action_id=action_id, user=_User(org),
            outcome_type="success", effectiveness=0.9,
            verdict="window frozen without customer impact",
        )
        await db.commit()
    assert outcome is not None

    chain = await _chain(db_session_factory, org_id, decision_id)
    assert chain is not None
    assert chain["decision"]["decision_id"] == decision_id
    assert [a["action_id"] for a in chain["actions"]] == [action_id]
    assert len(chain["evidence"]) >= 1
    assert all(ev["action_id"] == action_id for ev in chain["evidence"])
    assert any(art["target_type"] == "task" and art["via_action_id"] == action_id
               for art in chain["artifacts"])
    assert len(chain["outcomes"]) == 1
    assert chain["outcomes"][0]["outcome_type"] == "success"
    # bounds (contract §5.5)
    assert len(chain["actions"]) <= 10
    assert len(chain["evidence"]) <= 20
    assert len(chain["artifacts"]) <= 10
    assert len(chain["outcomes"]) <= 5


# ---------------------------------------------------------------------------
# 8. tenant isolation
# ---------------------------------------------------------------------------

async def test_8_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="4h5_tena@test.co")
    org_b = await register_org(client, email="4h5_temb@test.co")
    decision_id = await _approved_decision(org_a["client"] if False else client,
                                           org_a["headers"])
    await _drain(db_session_factory)

    assert await _plan(db_session_factory, org_b["organization"]["id"], decision_id) is None
    assert await _chain(db_session_factory, org_b["organization"]["id"], decision_id) is None
    assert await _plan(db_session_factory, org_a["organization"]["id"], decision_id) is not None


# ---------------------------------------------------------------------------
# 10. brain intents + collision guards
# ---------------------------------------------------------------------------

async def test_10_brain_intents_and_collision(client, db_session_factory):
    org = await register_org(client, email="4h5_brain@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    decision_id = await _approved_decision(
        client, headers, title="Hire for the platform bottleneck"
    )
    await _drain(db_session_factory)

    plan_q = (await client.post(
        BRAIN_QUERY,
        json={"question": "what is the action plan for the hire decision?"},
        headers=headers,
    )).json()
    assert plan_q["intent"] == "company_execution_plan", plan_q.get("intent")

    chain_q = (await client.post(
        BRAIN_QUERY,
        json={"question": "did we act on the platform bottleneck decision?"},
        headers=headers,
    )).json()
    assert chain_q["intent"] == "company_execution_chain", chain_q.get("intent")

    # collision guards: 4E.6 action-center phrases and 4G.7 what-if phrases
    # never resolve to the 4H.5 intents
    for q in (
        "show me my actions",
        "open the action center",
        "what if we delay the platform project",
        "what if we reallocate capacity",
    ):
        res = (await client.post(
            BRAIN_QUERY, json={"question": q}, headers=headers,
        )).json()
        assert res.get("intent") not in (
            "company_execution_plan", "company_execution_chain"
        ), f"{q} -> {res.get('intent')}"


# ---------------------------------------------------------------------------
# 11. L16 origin compatibility: direct-propose actions stay valid
# ---------------------------------------------------------------------------

async def test_11_l16_origin_compatibility(client, db_session_factory):
    org = await register_org(client, email="4h5_origin@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    decision_id = await _approved_decision(client, headers)
    await _drain(db_session_factory)

    orphan = await _propose(
        db_session_factory, org_id, _User(org),
        action_type="communication", title="Announce the quarterly roadmap",
        source_problem="leadership offsite",
    )
    assert orphan["source_company_decision_id"] is None
    assert orphan["source_scenario_id"] is None

    linked = await _propose(
        db_session_factory, org_id, _User(org),
        action_type="task", title="Draft the migration checklist",
        source_problem="delay_project decision",
        source_company_decision_id=decision_id,
    )

    chain = await _chain(db_session_factory, org_id, decision_id)
    linked_ids = [a["action_id"] for a in chain["actions"]]
    assert linked["id"] in linked_ids
    assert orphan["id"] not in linked_ids  # scope is a filter, not a fork


# ---------------------------------------------------------------------------
# 12. no LLM on the plan/chain path (Amendment 10)
# ---------------------------------------------------------------------------

async def test_12_no_llm_on_plan_or_chain_path():
    from app.intelligence import company_operating_engine as coe

    source = inspect.getsource(coe)
    for banned in ("openai", "anthropic", "llm_client", "chat_completion",
                   "AzureOpenAI", "get_llm"):
        assert banned not in source, f"forbidden symbol on the plan path: {banned}"
    plan_src = inspect.getsource(coe.CompanyOperatingEngine.derive_action_plan)
    chain_src = inspect.getsource(coe.CompanyOperatingEngine.execution_chain)
    for src in (plan_src, chain_src):
        assert "publish_event" not in src
        assert "db.add(" not in src
        assert "httpx" not in src
