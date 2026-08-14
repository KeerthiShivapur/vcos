"""Slice 4E.6 — Universal Company Actions (knowledge-to-action governed layer).

4E.5 turns intelligence into operations (recommendations). 4E.6 makes those
operations governed and universal:

* propose: an action carries full lineage (why / insight / claims / event),
  a deterministic risk policy (low risk auto-approves and routes into the
  existing operating services; medium/high wait for explicit approval;
  project type is role-gated), and an exact-once fingerprint,
* governed state machine: proposed -> validating -> awaiting_approval /
  approved -> ready -> in_progress -> (blocked) -> completed -> verified,
  with terminal reject / cancel / expire / fail / supersede and a
  transition that is never deleted, only audited,
* routing: approval materializes the action through the SAME governed
  services the company already trusts (tasks, decisions, meetings,
  announcements, documents, projects) — never a parallel universe,
* operations under test: assign / start (dependency-gated) / block /
  unblock / complete / verify / fail / cancel, an idempotent evaluate pass
  (expire stale approvals, escalate overdue & long-blocked, reflect routed
  artifact completion), outcomes + outcome intelligence,
* the action center: one bounded, tenant-isolated surface with state/type/
  scope filtered views and NL intents (actions / attention / blocked /
  overdue / escalation) dispatched through the universal query.
"""

import json

from sqlalchemy import select, update

from app.models.company_actions import CompanyAction
from app.models.knowledge import KnowledgeRecommendation
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

API = "/api/v1/brain/knowledge/actions"


async def _drain_events(db_session_factory, limit=400):
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _create_conversation(client, headers, title="ops-room"):
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    created = await client.post(
        "/api/v1/conversations",
        json={"type": "channel", "title": title, "member_ids": [me]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _send_message(client, headers, conversation_id, content):
    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=headers,
    )
    assert sent.status_code in (200, 201), sent.text


async def _seed_conflict(client, headers):
    conv = await _create_conversation(client, headers, "budget")
    await _send_message(client, headers, conv["id"], "The migration budget is 5 lakh.")
    await _send_message(client, headers, conv["id"], "The migration budget is 10 lakh.")


async def _propose(client, headers, action_type="task", title="Act on the conflict",
                   risk="medium", **extra):
    body = {"action_type": action_type, "title": title, "risk": risk, **extra}
    return await client.post(API, json=body, headers=headers)


async def _conflict_recommendation(client, headers):
    recs = (
        await client.get("/api/v1/brain/knowledge/recommendations", headers=headers)
    ).json()
    return next(r for r in recs["recommendations"] if r["kind"] == "conflict")


async def _transition(client, headers, action_id, transition, **extra):
    return await client.post(
        f"{API}/{action_id}/transition",
        json={"transition": transition, **extra}, headers=headers,
    )


# ------------------------------------------------------------ propose & policy


async def test_propose_applies_policy_and_dedups(client, db_session_factory):
    org = await register_org(client, email="4e6_prop@test.co")
    headers = org["headers"]
    await _seed_conflict(client, headers)
    await _drain_events(db_session_factory)
    rec = await _conflict_recommendation(client, headers)

    # medium risk -> awaiting_approval with approval required
    r = await _propose(client, headers, source_recommendation_id=rec["id"])
    assert r.status_code == 201, r.text
    action = r.json()
    assert action["state"] == "awaiting_approval"
    assert action["approval_required"] is True
    assert action["policy"] == "approval"
    assert action["source_recommendation_id"] == rec["id"], "lineage is recorded"
    assert action["fingerprint"], "exact-once fingerprint present"

    # exact-once: same proposal is a dedup replay, same id, never duplicated
    r2 = await _propose(client, headers, source_recommendation_id=rec["id"])
    assert r2.status_code == 201, r2.text
    assert r2.json()["deduplicated"] is True
    assert r2.json()["id"] == action["id"]
    async with db_session_factory() as session:
        n = (
            await session.execute(
                select(CompanyAction)
                .where(CompanyAction.organization_id == org["organization"]["id"])
            )
        ).scalars().all()
        assert len(n) == 1, "dedup never creates a second row"


async def test_low_risk_auto_routes_into_operating_system(client, db_session_factory):
    """Low-risk actions skip approval and materialize through a real service."""
    org = await register_org(client, email="4e6_low@test.co")
    headers = org["headers"]

    r = await _propose(client, headers, action_type="task", risk="low",
                       title="Write the known-good pricing doc",
                       source_problem="capture the settled pricing policy")
    assert r.status_code == 201, r.text
    action = r.json()
    assert action["state"] == "ready"
    assert action["approval_required"] is False
    assert action["policy"] == "auto"
    assert action["target_type"] == "task"
    assert action["target_id"], "a real task artifact is routed"

    # the routed artifact truly exists in the operating layer
    task = (
        await client.get(f"/api/v1/tasks/{action['target_id']}", headers=headers)
    ).json()
    assert "[Action]" in task["title"]

    # a project-type action is always restricted,
    # even at low risk (role-gated + approval-mandatory)
    rp = await _propose(client, headers, action_type="project", risk="low",
                        title="Open the pricing program")
    assert rp.status_code == 201, rp.text
    assert rp.json()["policy"] == "restricted"
    assert rp.json()["approval_required"] is True


async def test_propose_requires_real_lineage(client):
    org = await register_org(client, email="4e6_lineage@test.co")
    headers = org["headers"]
    r = await _propose(
        client, headers,
        source_recommendation_id="does-not-exist",
    )
    assert r.status_code == 400, "a fake source recommendation must be rejected"


async def test_all_six_action_types_route_into_their_operating_system(client, db_session_factory):
    """The universal action contract routes every type into the REAL governed
    service — never a parallel universe: task, decision, communication,
    knowledge, meeting and project all materialize an existing artifact."""
    org = await register_org(client, email="4e6_types@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    cases = [
        ("task", "/api/v1/tasks/{id}", "title"),
        ("decision", "/api/v1/decisions/{id}", "title"),
        ("communication", None, None),  # the hermetic test app mounts no announcements router
        ("knowledge", "/api/v1/documents/{id}", "title"),
        ("meeting", "/api/v1/meetings/{id}", "title"),
        ("project", "/api/v1/projects/{id}", "name"),  # projects expose name, not title
    ]
    for action_type, artifact_path, name_key in cases:
        r = await _propose(
            client, headers, action_type=action_type, risk="low",
            title=f"Route the {action_type} action", source_problem=f"{action_type} routing smoke",
        )
        assert r.status_code == 201, r.text
        action = r.json()
        if action_type == "project":
            # project is restricted: approval-mandatory, routed only on approval
            assert action["policy"] == "restricted"
            assert action["approval_required"] is True
            assert action["target_type"] is None
            r2 = await _transition(client, headers, action["id"], "approve", note="ok")
            assert r2.json()["state"] == "ready"
            assert r2.json()["target_type"] == "project", "project routes on approval"
            action = r2.json()
        else:
            assert action["state"] == "ready", f"{action_type} auto-routes to ready"
        assert action["target_type"] == action_type
        assert action["target_id"], f"{action_type} materializes a real artifact"
        if artifact_path:
            detail = await client.get(artifact_path.format(id=action["target_id"]), headers=headers)
            assert detail.status_code == 200, f"{action_type} artifact exists: {detail.text[:200]}"
            assert "[Action]" in detail.json()[name_key], f"{action_type} artifact carries the action lineage"
        else:
            from app.communication.announcement_service import announcement_service

            async with db_session_factory() as session:
                row = await announcement_service.get(
                    session, organization_id=org_id,
                    announcement_id=action["target_id"],
                )
                assert row is not None, "the routed announcement exists in the operating layer"
                assert "[Action]" in row.title


# ------------------------------------------------- state machine & transitions


async def test_approval_lifecycle_with_audit_and_invalid_guards(client, db_session_factory):
    org = await register_org(client, email="4e6_life@test.co")
    headers = org["headers"]
    await _seed_conflict(client, headers)
    await _drain_events(db_session_factory)
    rec = await _conflict_recommendation(client, headers)
    action = (
        await _propose(client, headers, source_recommendation_id=rec["id"])
    ).json()

    # approve -> ready and the task is routed
    r = await _transition(client, headers, action["id"], "approve",
                          note="approved by lead")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "ready"
    assert r.json()["target_type"] == "task"
    assert r.json()["approved_at"], "approval is timestampted"

    r = await _transition(client, headers, action["id"], "assign", assignee_id="opsteam")
    assert r.json()["assignee_id"] == "opsteam"

    for tr in ("start", "complete"):
        r = await _transition(client, headers, action["id"], tr,
                              note=f"smoke {tr}")
        assert r.status_code == 200, r.text
    r = await _transition(client, headers, action["id"], "verify", note="verified")
    assert r.json()["state"] == "verified"

    # invalid transition from a terminal-ish state is a clean 400
    bad = await _transition(client, headers, action["id"], "start")
    assert bad.status_code == 400

    detail = (
        await client.get(f"{API}/{action['id']}", headers=headers)
    ).json()
    trail = [e["event"] for e in detail["events"]]
    assert trail[0] == "action.verified"
    assert "action.approved" in trail
    assert "action.created" in trail  # nothing is deleted — immutable trail


async def test_terminal_escapes_reject_fail_cancel(client):
    org = await register_org(client, email="4e6_term@test.co")
    headers = org["headers"]

    # reject from awaiting approval
    a1 = (await _propose(client, headers, title="Reject this action")).json()
    r = await _transition(client, headers, a1["id"], "reject", note="no need")
    assert r.json()["state"] == "rejected"
    assert r.json()["rejected_reason"]

    # fail is a legal terminal escape from a pending state
    a2 = (await _propose(client, headers, title="Fail this action")).json()
    r = await _transition(client, headers, a2["id"], "fail", note="cannot proceed")
    assert r.json()["state"] == "failed"
    assert r.json()["fail_reason"]

    # cancel any non-terminal state
    a3 = (await _propose(client, headers, title="Cancel this action")).json()
    r = await _transition(client, headers, a3["id"], "cancel", note="abandoned")
    assert r.json()["state"] == "cancelled"


async def test_start_requires_dependencies_complete(client, db_session_factory):
    org = await register_org(client, email="4e6_dep@test.co")
    headers = org["headers"]

    dep = (await _propose(client, headers, title="Prepare the prerequisite")).json()
    # dep is awaiting_approval; approve+ready to make it completable
    await _transition(client, headers, dep["id"], "approve", note="ok")
    await _transition(client, headers, dep["id"], "assign", assignee_id="me")
    await _transition(client, headers, dep["id"], "start", note="go")
    await _transition(client, headers, dep["id"], "complete", note="done")

    main = (
        await _propose(client, headers, title="Ship the dependent thing",
                       depends_on=[dep["id"]])
    ).json()
    await _transition(client, headers, main["id"], "approve", note="ok")
    # dependency is complete, so we may start
    r = await _transition(client, headers, main["id"], "assign", assignee_id="me")
    r = await _transition(client, headers, main["id"], "start", note="go")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "in_progress"


async def test_start_blocked_by_incomplete_dependency(client, db_session_factory):
    org = await register_org(client, email="4e6_depb@test.co")
    headers = org["headers"]

    dep = (await _propose(client, headers, title="Unfinished prerequisite")).json()
    await _transition(client, headers, dep["id"], "approve", note="ok")

    main = (
        await _propose(client, headers, title="Depends on unfinished",
                       depends_on=[dep["id"]])
    ).json()
    await _transition(client, headers, main["id"], "approve", note="ok")
    await _transition(client, headers, main["id"], "assign", assignee_id="me")
    r = await _transition(client, headers, main["id"], "start", note="go")
    assert r.status_code == 400, "start must be refused while a dependency is open"
    assert "not completed" in r.text

    # finish the dependency and the same action may now start
    await _transition(client, headers, dep["id"], "assign", assignee_id="me")
    await _transition(client, headers, dep["id"], "start", note="go")
    await _transition(client, headers, dep["id"], "complete", note="done")
    r = await _transition(client, headers, main["id"], "start", note="go")
    assert r.status_code == 200
    assert r.json()["state"] == "in_progress"


# ------------------------------------------------------------ evaluate & ops


async def test_evaluate_expires_stale_approvals(client, db_session_factory):
    org = await register_org(client, email="4e6_exp@test.co")
    headers = org["headers"]
    action = (await _propose(client, headers, title="Sitting approval")).json()
    assert action["state"] == "awaiting_approval"

    # backdate the row so the policy horizon has lapsed
    import datetime

    async with db_session_factory() as session:
        await session.execute(
            update(CompanyAction)
            .where(CompanyAction.id == action["id"])
            .values(updated_at=datetime.datetime.utcnow() - datetime.timedelta(days=21))
        )
        await session.commit()

    r = (await client.post(f"{API}/evaluate", headers=headers)).json()
    assert r["expired"] >= 1, r
    detail = (await client.get(f"{API}/{action['id']}", headers=headers)).json()
    assert detail["state"] == "expired"


async def test_evaluate_escalates_overdue(client, db_session_factory):
    org = await register_org(client, email="4e6_esc@test.co")
    headers = org["headers"]
    action = (await _propose(client, headers, title="Overdue rollout",
                             risk="low")).json()  # auto -> ready
    # ready + overdue (due in the past)
    r = await _transition(client, headers, action["id"], "start", note="go",
                          due_at="2000-01-01T00:00:00Z")
    result = (await client.post(f"{API}/evaluate", headers=headers)).json()
    assert result["escalated"] >= 1
    detail = (await client.get(f"{API}/{action['id']}", headers=headers)).json()
    assert detail["escalation_level"] >= 1
    assert "action.escalated" in [e["event"] for e in detail["events"]]


async def test_evaluate_reflects_completed_routed_task(client, db_session_factory):
    """When the routed operating artifact is completed, evaluate folds it back
    into the action — action and source of truth never diverge."""
    from app.work.task_service import task_service

    org = await register_org(client, email="4e6_refl@test.co")
    headers = org["headers"]
    action = (await _propose(
        client, headers, title="Ship the migration runbook", risk="low"
    )).json()  # ready, routed to a real task
    assert action["state"] == "ready"
    await _transition(client, headers, action["id"], "assign", assignee_id="me")
    await _transition(client, headers, action["id"], "start", note="go")

    # mark the routed task done in the operating layer
    async with db_session_factory() as session:
        task = await task_service.get(
            session, organization_id=org["organization"]["id"],
            task_id=action["target_id"],
        )
        assert task is not None, "the routed task exists"
        await task_service.update(
            session, organization_id=org["organization"]["id"],
            task=task, data={"status": "completed"}, actor=None, ip_address="test",
        )
        await session.commit()

    r = (await client.post(f"{API}/evaluate", headers=headers)).json()
    assert r["auto_completed"] >= 1, r
    detail = (await client.get(f"{API}/{action['id']}", headers=headers)).json()
    assert detail["state"] == "completed", "reflected from the routed task"
    assert "reflected from routed" in detail["events"][0]["note"]


async def test_evaluate_idempotent_second_pass_is_stable(client, db_session_factory):
    org = await register_org(client, email="4e6_idem@test.co")
    headers = org["headers"]
    await _propose(client, headers, title="One normal action")
    r1 = (await client.post(f"{API}/evaluate", headers=headers)).json()
    r2 = (await client.post(f"{API}/evaluate", headers=headers)).json()
    # no outcomes mutate across replays once stable
    assert r2["expired"] == 0
    assert r2["escalated"] == 0


# --------------------------------------------------------------- outcomes


async def test_outcome_and_outcome_intelligence(client):
    org = await register_org(client, email="4e6_out@test.co")
    headers = org["headers"]

    a = (await _propose(client, headers, title="Landing the rollout", risk="low")).json()
    for tr in ("assign", "start", "complete", "verify"):
        await _transition(client, headers, a["id"], tr,
                          note="x" if tr != "assign" else None,
                          assignee_id="me" if tr == "assign" else None)
    o = await client.post(
        f"{API}/{a['id']}/outcome",
        json={"outcome_type": "success", "verdict": "done", "effectiveness": 0.9},
        headers=headers,
    )
    assert o.status_code == 200, o.text
    assert o.json()["outcome"]["outcome_type"] == "success"

    b = (await _propose(client, headers, title="Rollout that missed", risk="low")).json()
    for tr in ("assign", "start", "complete", "verify"):
        await _transition(client, headers, b["id"], tr,
                          note="x" if tr != "assign" else None,
                          assignee_id="me" if tr == "assign" else None)
    await client.post(
        f"{API}/{b['id']}/outcome",
        json={"outcome_type": "failed", "verdict": "partial", "effectiveness": 0.2},
        headers=headers,
    )

    intel = (
        await client.get(f"{API}/outcome-intelligence", headers=headers)
    ).json()
    assert intel["total"] == 2
    assert intel["success_rate"] == 0.5, intel
    # granularity by outcome type exists
    by_type = {row["key"]: row for row in intel["by_outcome_type"]}
    assert by_type["success"]["avg_effectiveness"] == 0.9


# ------------------------------------------- center, isolation & NL intents


async def test_center_filters_and_state_stats(client):
    org = await register_org(client, email="4e6_center@test.co")
    headers = org["headers"]
    await _propose(client, headers, title="Awaiting approval item")
    low = (await _propose(client, headers, title="auto routed item",
                          risk="low")).json()  # -> ready

    c = (await client.get(API, headers=headers)).json()
    assert c["items"], "center lists the actions"
    assert c["stats"]["by_state"]["ready"] >= 1
    assert c["stats"]["open"] >= 1

    only_ready = (await client.get(API, params={"state": "ready"}, headers=headers)).json()
    assert all(i["state"] == "ready" for i in only_ready["items"])

    only_type = (await client.get(API, params={"action_type": "task"}, headers=headers)).json()
    assert all(i["action_type"] == "task" for i in only_type["items"])

    mine = (await client.get(API, params={"mine": True}, headers=headers)).json()
    assert mine["total"] >= 0  # callable and bounded


async def test_governance_never_crosses_tenants(client, db_session_factory):
    org_a = await register_org(client, email="4e6_iso_a@test.co")
    ha = org_a["headers"]
    await _seed_conflict(client, ha)
    await _drain_events(db_session_factory)
    action = (await _propose(client, ha, title="Tenant A action")).json()

    org_b = await register_org(client, email="4e6_iso_b@test.co")
    hb = org_b["headers"]

    assert (await client.get(API, headers=hb)).json()["total"] == 0
    assert (await client.get(f"{API}/{action['id']}", headers=hb)).status_code == 404
    assert (
        await _transition(client, hb, action["id"], "cancel", note="x")
    ).status_code == 404
    assert (
        await client.post(
            f"{API}/{action['id']}/outcome",
            json={"outcome_type": "success", "effectiveness": 0.5},
            headers=hb,
        )
    ).status_code == 404


async def test_universal_query_routes_action_intents(client, db_session_factory):
    org = await register_org(client, email="4e6_qint@test.co")
    headers = org["headers"]
    await _propose(client, headers, title="Attention-worthy pending item")
    await _transition(client, headers, (await _propose(
        client, headers, title="Blocked thing")).json()["id"], "reject", note="nope")

    for question, intent in (
        ("what needs my attention", "attention"),
        ("what is blocked", "blocked"),
        ("which actions are overdue", "overdue"),
        ("show my actions", "actions"),
        ("what needs to be escalated", "escalation"),
    ):
        resp = (
            await client.post(
                "/api/v1/brain/knowledge/query",
                json={"question": question}, headers=headers,
            )
        ).json()
        assert resp["intent"] == intent, f"{question!r} -> {resp['intent']} != {intent}"
        assert "items" in resp, "the action routing returns the center view"


# SQL helper: a timestamp 21 days in the past (matches _EXPIRE_AFTER_DAYS=14)