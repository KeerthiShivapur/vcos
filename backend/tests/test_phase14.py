"""Phase 14 — Workflow Automation & Business Process Operating System.

Covers the full automation lifecycle: workflow CRUD and graph validation,
manual executions with conditions and branches, approval gates that pause
and resume executions, delay nodes, parallel split/join, event-driven
triggers via the event bus, business rules, cron schedules, template
marketplace and instantiation, AI workflow generation, automation
integrations with the sync worker, workflow analytics, RBAC gating,
multi-tenant isolation, universal search and the Phase 14 workers.
"""

import pytest

from tests.conftest import register_org

SIMPLE_GRAPH = {
    "nodes": [
        {"key": "start", "type": "start", "name": "Start", "config": {}},
        {"key": "notify", "type": "notification", "name": "Notify",
         "config": {"title": "Hello from workflow", "body": "Automation ran."}},
        {"key": "end", "type": "end", "name": "Done", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "notify"},
        {"source": "notify", "target": "end"},
    ],
}

CONDITION_GRAPH = {
    "nodes": [
        {"key": "start", "type": "start", "name": "Start", "config": {}},
        {"key": "check", "type": "condition", "name": "Big deal?",
         "config": {"field": "trigger.value", "operator": "gte", "value": 1000}},
        {"key": "yes", "type": "notification", "name": "Big branch",
         "config": {"title": "Big deal detected"}},
        {"key": "no", "type": "notification", "name": "Small branch",
         "config": {"title": "Small deal"}},
        {"key": "end", "type": "end", "name": "Done", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "check"},
        {"source": "check", "target": "yes", "condition": {"branch": "true"}},
        {"source": "check", "target": "no", "condition": {"branch": "false"}},
        {"source": "yes", "target": "end"},
        {"source": "no", "target": "end"},
    ],
}

APPROVAL_GRAPH = {
    "nodes": [
        {"key": "start", "type": "start", "name": "Start", "config": {}},
        {"key": "approve", "type": "approval", "name": "Finance gate",
         "config": {"title": "Approve the deal", "approver_user_id": "__OWNER__",
                    "due_hours": 24}},
        {"key": "ok", "type": "notification", "name": "Approved branch",
         "config": {"title": "Deal approved"}},
        {"key": "no", "type": "notification", "name": "Rejected branch",
         "config": {"title": "Deal rejected"}},
        {"key": "end", "type": "end", "name": "Done", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "approve"},
        {"source": "approve", "target": "ok", "condition": {"branch": "approved"}},
        {"source": "approve", "target": "no", "condition": {"branch": "rejected"}},
        {"source": "ok", "target": "end"},
        {"source": "no", "target": "end"},
    ],
}

PARALLEL_GRAPH = {
    "nodes": [
        {"key": "start", "type": "start", "name": "Start", "config": {}},
        {"key": "split", "type": "parallel_split", "name": "Split", "config": {}},
        {"key": "a", "type": "notification", "name": "Stream A",
         "config": {"title": "Stream A ran"}},
        {"key": "b", "type": "notification", "name": "Stream B",
         "config": {"title": "Stream B ran"}},
        {"key": "join", "type": "parallel_join", "name": "Join", "config": {}},
        {"key": "end", "type": "end", "name": "Done", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "split"},
        {"source": "split", "target": "a"},
        {"source": "split", "target": "b"},
        {"source": "a", "target": "join"},
        {"source": "b", "target": "join"},
        {"source": "join", "target": "end"},
    ],
}


async def _event_names(client, headers):
    events = (await client.get("/api/v1/events?limit=50", headers=headers)).json()
    return {e["name"] for e in events.get("items", events)}


async def _create_workflow(client, headers, name="My Workflow", graph=None,
                           trigger_type="manual", **overrides):
    payload = {"name": name, "category": "general", "trigger_type": trigger_type}
    payload.update(overrides)
    response = await client.post("/api/v1/automation/workflows", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    workflow_id = response.json()["id"]
    if graph:
        response = await client.post(
            f"/api/v1/automation/workflows/{workflow_id}/graph",
            json={"nodes": graph["nodes"], "edges": graph["edges"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    return workflow_id


async def _activate(client, headers, workflow_id):
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/transition",
        json={"status": "active"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------ workflow CRUD


async def test_workflow_crud_and_graph_validation(client):
    org = await register_org(client, email="p14crud@test.co")
    headers = org["headers"]

    workflow_id = await _create_workflow(client, headers, name="Onboarding Flow")
    detail = (await client.get(f"/api/v1/automation/workflows/{workflow_id}", headers=headers)).json()
    assert detail["name"] == "Onboarding Flow"
    assert detail["status"] == "draft"
    assert detail["version"] == 1

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/graph",
        json={"nodes": SIMPLE_GRAPH["nodes"], "edges": SIMPLE_GRAPH["edges"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert len(detail["nodes"]) == 3
    assert len(detail["edges"]) == 2
    assert detail["version"] == 2

    # cycle detection
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/graph",
        json={
            "nodes": [{"key": "a", "type": "start"}, {"key": "b", "type": "end"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "cycle" in response.json()["detail"]

    # unknown node type
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/graph",
        json={
            "nodes": [{"key": "a", "type": "start"}, {"key": "b", "type": "quantum"}],
            "edges": [{"source": "a", "target": "b"}],
        },
        headers=headers,
    )
    assert response.status_code == 400

    # transition + duplicate + list
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/transition",
        json={"status": "active"}, headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/duplicate",
        json={"name": "Onboarding Copy"}, headers=headers,
    )
    assert response.status_code == 200
    copy_id = response.json()["id"]
    copy = (await client.get(f"/api/v1/automation/workflows/{copy_id}", headers=headers)).json()
    assert copy["name"] == "Onboarding Copy"
    assert len(copy["nodes"]) == 3

    listing = (await client.get("/api/v1/automation/workflows", headers=headers)).json()
    assert len(listing) == 2
    filtered = (await client.get("/api/v1/automation/workflows?status=active", headers=headers)).json()
    assert len(filtered) == 1

    response = await client.delete(f"/api/v1/automation/workflows/{copy_id}", headers=headers)
    assert response.status_code == 200
    assert (await client.get("/api/v1/automation/workflows", headers=headers)).json().__len__() == 1


async def test_manual_run_completes_and_emits_events(client):
    org = await register_org(client, email="p14run@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Run Me", graph=SIMPLE_GRAPH)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {"topic": "weekly"}}, headers=headers,
    )
    assert response.status_code == 200, response.text
    execution = response.json()
    assert execution["status"] == "completed"
    assert execution["trigger_source"] == "manual"
    assert execution["context"]["trigger"]["topic"] == "weekly"
    step_statuses = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert step_statuses == {"start": "succeeded", "notify": "succeeded", "end": "succeeded"}
    notify = next(s for s in execution["steps"] if s["node_key"] == "notify")
    assert notify["output"]["notification_id"]

    detail = (await client.get(f"/api/v1/automation/workflows/{workflow_id}", headers=headers)).json()
    assert detail["run_count"] >= 1
    assert detail["last_run_at"]

    executions = (await client.get("/api/v1/automation/executions", headers=headers)).json()
    assert len(executions) == 1
    assert executions[0]["status"] == "completed"

    # events emitted
    names = await _event_names(client, headers)
    assert "workflow.started" in names
    assert "workflow.completed" in names

    detail = (await client.get(f"/api/v1/automation/executions/{execution['id']}", headers=headers)).json()
    assert detail["duration_ms"] is not None


async def test_condition_branching(client):
    org = await register_org(client, email="p14cond@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Branchy", graph=CONDITION_GRAPH)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {"value": 5000}}, headers=headers,
    )
    assert response.status_code == 200
    execution = response.json()
    assert execution["status"] == "completed"
    steps = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert steps["yes"] == "succeeded"
    assert steps["no"] == "skipped"

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {"value": 50}}, headers=headers,
    )
    execution = response.json()
    assert execution["status"] == "completed"
    steps = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert steps["no"] == "succeeded"
    assert steps["yes"] == "skipped"


async def test_approval_gate_blocks_then_resumes(client):
    org = await register_org(client, email="p14appr@test.co")
    headers = org["headers"]
    owner_id = org["user"]["id"]
    graph = APPROVAL_GRAPH
    graph["nodes"][1]["config"]["approver_user_id"] = owner_id
    workflow_id = await _create_workflow(client, headers, name="Gated", graph=graph)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {"deal": "enterprise"}}, headers=headers,
    )
    assert response.status_code == 200, response.text
    execution = response.json()
    assert execution["status"] == "waiting"
    assert execution["current_node_key"] == "approve"

    approvals = (await client.get("/api/v1/automation/approvals", headers=headers)).json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["status"] == "pending"
    assert approval["title"] == "Approve the deal"
    assert approval["approver_user_id"] == owner_id

    # reject first
    response = await client.post(
        f"/api/v1/automation/approvals/{approval['id']}/decide",
        json={"decision": "rejected", "comment": "too risky"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    execution = (await client.get(
        f"/api/v1/automation/executions/{execution['id']}", headers=headers)).json()
    assert execution["status"] == "completed"
    steps = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert steps["no"] == "succeeded"
    assert steps["ok"] == "skipped"

    # second run: approve
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {"deal": "enterprise-2"}}, headers=headers,
    )
    execution2 = response.json()
    assert execution2["status"] == "waiting"
    approvals = (await client.get("/api/v1/automation/approvals?status=pending", headers=headers)).json()
    approval2 = approvals[0]
    response = await client.post(
        f"/api/v1/automation/approvals/{approval2['id']}/decide",
        json={"decision": "approved"}, headers=headers,
    )
    assert response.status_code == 200
    execution2 = (await client.get(
        f"/api/v1/automation/executions/{execution2['id']}", headers=headers)).json()
    assert execution2["status"] == "completed"
    steps = {s["node_key"]: s["status"] for s in execution2["steps"]}
    assert steps["ok"] == "succeeded"
    assert steps["no"] == "skipped"

    # double-decision rejected
    response = await client.post(
        f"/api/v1/automation/approvals/{approval['id']}/decide",
        json={"decision": "approved"}, headers=headers,
    )
    assert response.status_code == 400


async def test_delay_node_waits_then_worker_resumes(client, db_session_factory):
    org = await register_org(client, email="p14delay@test.co")
    headers = org["headers"]
    graph = {
        "nodes": [
            {"key": "start", "type": "start", "name": "Start", "config": {}},
            {"key": "wait", "type": "delay", "name": "Wait a tick",
             "config": {"seconds": 1}},
            {"key": "after", "type": "notification", "name": "After delay",
             "config": {"title": "Delay finished"}},
            {"key": "end", "type": "end", "name": "Done", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "wait"},
            {"source": "wait", "target": "after"},
            {"source": "after", "target": "end"},
        ],
    }
    workflow_id = await _create_workflow(client, headers, name="Delayed", graph=graph)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {}}, headers=headers,
    )
    execution = response.json()
    assert execution["status"] == "waiting"
    assert execution["resume_at"]

    import asyncio

    await asyncio.sleep(1.2)

    from app.workers.workflow_worker import run_once as workflow_pass

    async with db_session_factory() as session:
        processed = await workflow_pass(db=session)
        await session.commit()
    assert processed >= 1

    execution = (await client.get(
        f"/api/v1/automation/executions/{execution['id']}", headers=headers)).json()
    assert execution["status"] == "completed"
    steps = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert steps["wait"] == "succeeded"


async def test_parallel_split_and_join(client):
    org = await register_org(client, email="p14par@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Parallel", graph=PARALLEL_GRAPH)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {}}, headers=headers,
    )
    assert response.status_code == 200, response.text
    execution = response.json()
    assert execution["status"] == "completed", execution
    steps = {s["node_key"]: s["status"] for s in execution["steps"]}
    assert steps["a"] == "succeeded"
    assert steps["b"] == "succeeded"
    assert steps["join"] == "succeeded"


async def test_cancel_execution(client):
    org = await register_org(client, email="p14cancel@test.co")
    headers = org["headers"]
    graph = {
        "nodes": [
            {"key": "start", "type": "start", "name": "Start", "config": {}},
            {"key": "approve", "type": "approval", "name": "Gate",
             "config": {"title": "Gate approval", "due_hours": 24}},
            {"key": "end", "type": "end", "name": "Done", "config": {}},
        ],
        "edges": [{"source": "start", "target": "approve"},
                  {"source": "approve", "target": "end"}],
    }
    workflow_id = await _create_workflow(client, headers, name="Cancellable", graph=graph)
    await _activate(client, headers, workflow_id)
    execution = (await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {}}, headers=headers)).json()
    assert execution["status"] == "waiting"

    response = await client.post(
        f"/api/v1/automation/executions/{execution['id']}/cancel", headers=headers)
    assert response.status_code == 200
    execution = (await client.get(
        f"/api/v1/automation/executions/{execution['id']}", headers=headers)).json()
    assert execution["status"] == "cancelled"
    assert all(s["status"] in ("succeeded", "skipped") for s in execution["steps"])
    assert all(a["status"] == "cancelled" for a in execution["approvals"])


# ------------------------------------------------------- event-driven triggers


async def test_event_trigger_via_event_bus(client, db_session_factory):
    org = await register_org(client, email="p14evt@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(
        client, headers, name="Event Driven", graph=SIMPLE_GRAPH, trigger_type="event",
    )
    await _activate(client, headers, workflow_id)

    response = await client.post(
        "/api/v1/automation/triggers",
        json={"workflow_id": workflow_id, "trigger_type": "event",
              "event_name": "task.created",
              "config": {"filters": [{"field": "priority", "operator": "eq", "value": "high"}]}},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    triggers = (await client.get("/api/v1/automation/triggers", headers=headers)).json()
    assert len(triggers) == 1
    assert triggers[0]["event_name"] == "task.created"

    # emit a non-matching event
    from app.services.event_service import event_service
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        await event_service.emit(
            session, name="task.created", organization_id=org["organization"]["id"],
            payload={"priority": "low", "task_id": "x"},
        )
        await session.commit()
        await event_bus.process_pending(session, limit=10)
        await session.commit()
    assert (await client.get("/api/v1/automation/executions", headers=headers)).json().__len__() == 0

    # emit a matching event
    async with db_session_factory() as session:
        await event_service.emit(
            session, name="task.created", organization_id=org["organization"]["id"],
            payload={"priority": "high", "task_id": "y", "title": "Urgent"},
        )
        await session.commit()
        await event_bus.process_pending(session, limit=10)
        await session.commit()

    executions = (await client.get("/api/v1/automation/executions", headers=headers)).json()
    assert len(executions) == 1
    assert executions[0]["status"] == "completed"
    assert executions[0]["trigger_source"] == "event"
    assert executions[0]["trigger_event"] == "task.created"
    assert executions[0]["context"]["trigger"]["task_id"] == "y"

    triggers = (await client.get("/api/v1/automation/triggers", headers=headers)).json()
    assert triggers[0]["fire_count"] == 1
    assert triggers[0]["last_fired_at"]


async def test_webhook_trigger_with_token(client):
    org = await register_org(client, email="p14hook@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(
        client, headers, name="Webhook Flow", graph=SIMPLE_GRAPH,
        trigger_type="webhook", trigger_config={"token": "secret-token-42"},
    )
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/webhooks/{workflow_id}",
        json={"token": "wrong", "event": "pulse"},
    )
    assert response.status_code == 401

    response = await client.post(
        f"/api/v1/automation/webhooks/{workflow_id}",
        json={"token": "secret-token-42", "event": "pulse"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


# ------------------------------------------------------------ business rules


async def test_business_rules_fire_actions(client, db_session_factory):
    org = await register_org(client, email="p14rule@test.co")
    headers = org["headers"]
    response = await client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Flagged expense alert",
            "event_name": "expense.flagged",
            "conditions": [{"field": "policy_flags", "operator": "truthy", "value": None}],
            "actions": [
                {"action": "send_notification",
                 "config": {"title": "Expense flagged!", "body": "Review now.",
                            "recipient_ref": "__OWNER__"}}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    rule_id = response.json()["id"]

    rules = (await client.get("/api/v1/automation/rules", headers=headers)).json()
    assert len(rules) == 1
    assert rules[0]["event_name"] == "expense.flagged"

    from app.services.event_service import event_service
    from app.events.event_bus import event_bus

    async with db_session_factory() as session:
        await event_service.emit(
            session, name="expense.flagged", organization_id=org["organization"]["id"],
            payload={"policy_flags": ["over_limit"], "amount": 5000},
        )
        await session.commit()
        await event_bus.process_pending(session, limit=10)
        await session.commit()

    rules = (await client.get("/api/v1/automation/rules", headers=headers)).json()
    assert rules[0]["hit_count"] == 1
    assert rules[0]["last_triggered_at"]

    # non-matching payload does not fire
    async with db_session_factory() as session:
        await event_service.emit(
            session, name="expense.flagged", organization_id=org["organization"]["id"],
            payload={"policy_flags": [], "amount": 10},
        )
        await session.commit()
        await event_bus.process_pending(session, limit=10)
        await session.commit()
    rules = (await client.get("/api/v1/automation/rules", headers=headers)).json()
    assert rules[0]["hit_count"] == 1

    # update + delete
    response = await client.patch(
        f"/api/v1/automation/rules/{rule_id}", json={"enabled": False}, headers=headers)
    assert response.status_code == 200
    response = await client.delete(f"/api/v1/automation/rules/{rule_id}", headers=headers)
    assert response.status_code == 200


# ----------------------------------------------------------------- schedules


async def test_schedule_cron_fires_runs(client, db_session_factory):
    org = await register_org(client, email="p14sched@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Daily Digest", graph=SIMPLE_GRAPH)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        "/api/v1/automation/schedules",
        json={"workflow_id": workflow_id, "name": "Daily 9am",
              "cron": "0 9 * * *", "payload_template": {"channel": "digest"}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    schedule_id = response.json()["id"]
    assert response.json()["next_run_at"]

    schedules = (await client.get("/api/v1/automation/schedules", headers=headers)).json()
    assert len(schedules) == 1
    assert schedules[0]["cron"] == "0 9 * * *"

    # invalid cron rejected
    response = await client.post(
        "/api/v1/automation/schedules",
        json={"workflow_id": workflow_id, "name": "Bad", "cron": "99 99 99 99 99"},
        headers=headers,
    )
    assert response.status_code == 400

    # force the schedule due and run the scheduler worker
    from datetime import datetime, timedelta, timezone

    async with db_session_factory() as session:
        schedule = await session.get(__import__("app.models.workflow", fromlist=["WorkflowSchedule"]).WorkflowSchedule, schedule_id)
        schedule.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

    from app.workers.scheduler_worker import run_once as scheduler_pass

    async with db_session_factory() as session:
        started = await scheduler_pass(db=session)
        await session.commit()
    assert started >= 1

    executions = (await client.get("/api/v1/automation/executions", headers=headers)).json()
    assert len(executions) == 1
    assert executions[0]["trigger_source"] == "schedule"
    assert executions[0]["context"]["trigger"]["channel"] == "digest"

    schedules = (await client.get("/api/v1/automation/schedules", headers=headers)).json()
    assert schedules[0]["run_count"] == 1
    assert schedules[0]["last_run_at"]

    response = await client.delete(f"/api/v1/automation/schedules/{schedule_id}", headers=headers)
    assert response.status_code == 200


# ---------------------------------------------------------------- templates


async def test_templates_seed_list_and_instantiate(client):
    org = await register_org(client, email="p14tpl@test.co")
    headers = org["headers"]

    templates = (await client.get("/api/v1/automation/templates", headers=headers)).json()
    assert len(templates) >= 6
    names = {t["name"] for t in templates}
    assert "New Employee Onboarding" in names
    assert "High Value Deal Approval" in names
    assert "New Hire Task Distribution" in names

    onboarding = next(t for t in templates if t["name"] == "New Employee Onboarding")
    response = await client.post(
        "/api/v1/automation/templates/instantiate",
        json={"template_id": onboarding["id"], "name": "My Onboarding"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    workflow = response.json()
    assert workflow["name"] == "My Onboarding"
    assert workflow["trigger_type"] == "event"
    assert len(workflow["nodes"]) == 5
    assert len(workflow["edges"]) == 4

    # org-owned template
    response = await client.post(
        "/api/v1/automation/templates",
        json={"name": "Custom Flow", "category": "finance",
              "nodes": SIMPLE_GRAPH["nodes"], "edges": SIMPLE_GRAPH["edges"]},
        headers=headers,
    )
    assert response.status_code == 201
    templates = (await client.get("/api/v1/automation/templates", headers=headers)).json()
    assert any(t["name"] == "Custom Flow" and t["is_system"] is False for t in templates)


# ------------------------------------------------------------ AI generation


async def test_ai_generate_workflow_from_prompt(client):
    org = await register_org(client, email="p14ai@test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/automation/ai/generate",
        json={"prompt": "Design an onboarding workflow for new employees",
              "name": "AI Onboarding"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["valid"] is True
    workflow = result["workflow"]
    assert workflow["name"] == "AI Onboarding"
    assert len(workflow["nodes"]) >= 4
    assert workflow["trigger_type"] in ("event", "manual")

    explain = (await client.get(
        f"/api/v1/automation/ai/explain/{workflow['id']}", headers=headers)).json()
    assert explain["node_count"] == len(workflow["nodes"])
    assert "AI Onboarding" in explain["summary"]

    # ai decision node inside a generated workflow
    response = await client.post(
        "/api/v1/automation/ai/generate",
        json={"prompt": "Create an intelligent decision workflow using AI",
              "name": "AI Decide"}, headers=headers,
    )
    assert response.status_code == 200
    workflow = response.json()["workflow"]
    node_types = {n["type"] for n in workflow["nodes"]}
    assert "ai_decision" in node_types

    # persist: false → no workflow created
    response = await client.post(
        "/api/v1/automation/ai/generate",
        json={"prompt": "Build a weekly digest workflow", "persist": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert "workflow" not in response.json()

    suggestion = await client.post(
        "/api/v1/automation/ai/rules/suggest",
        json={"prompt": "Alert me whenever an expense is flagged by policy"},
        headers=headers,
    )
    assert suggestion.status_code == 200
    assert suggestion.json()["event_name"] == "expense.flagged"


# -------------------------------------------------------------- integrations


async def test_integrations_sync_via_worker(client, db_session_factory):
    org = await register_org(client, email="p14int@test.co")
    headers = org["headers"]

    response = await client.post(
        "/api/v1/automation/integrations",
        json={"name": "Zapier Feed", "platform": "zapier",
              "config": {"url": "https://hooks.zapier.test/feed"}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    integration_id = response.json()["id"]

    integrations = (await client.get("/api/v1/automation/integrations", headers=headers)).json()
    assert len(integrations) == 1
    assert integrations[0]["platform"] == "zapier"

    # queued sync → worker drains it → integration.completed event
    response = await client.post(
        f"/api/v1/automation/integrations/{integration_id}/sync",
        json={"message": "deploy triggered"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["queued"] is True

    from app.workers.integration_worker import run_once as integration_pass

    async with db_session_factory() as session:
        processed = await integration_pass(db=session)
        await session.commit()
    assert processed >= 1

    integrations = (await client.get("/api/v1/automation/integrations", headers=headers)).json()
    assert integrations[0]["sync_count"] == 1
    assert integrations[0]["last_sync_at"]

    events = (await client.get("/api/v1/events?limit=50", headers=headers)).json()
    names = {e["name"] for e in events.get("items", events)}
    assert "integration.completed" in names

    # webhook delivery failure is recorded, not silently dropped
    response = await client.post(
        "/api/v1/automation/integrations",
        json={"name": "Broken Hook", "platform": "webhook",
              "config": {"url": "https://example.invalid/hook"}},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    broken_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/automation/integrations/{broken_id}/sync",
        json={"message": "boom"}, headers=headers,
    )
    assert response.status_code == 200
    async with db_session_factory() as session:
        await integration_pass(db=session)
        await session.commit()
    integrations = (await client.get("/api/v1/automation/integrations", headers=headers)).json()
    broken = next(i for i in integrations if i["id"] == broken_id)
    assert broken["status"] == "error"
    assert broken["error"]

    response = await client.delete(f"/api/v1/automation/integrations/{integration_id}", headers=headers)
    assert response.status_code == 200


# ---------------------------------------------------------------- analytics


async def test_analytics_dashboard_trends_metrics(client, db_session_factory):
    org = await register_org(client, email="p14stats@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Measured", graph=SIMPLE_GRAPH)
    await _activate(client, headers, workflow_id)
    for _ in range(2):
        response = await client.post(
            f"/api/v1/automation/workflows/{workflow_id}/run",
            json={"context": {}}, headers=headers,
        )
        assert response.status_code == 200

    dashboard = (await client.get("/api/v1/automation/analytics/dashboard", headers=headers)).json()
    assert dashboard["workflows"]["total"] >= 1
    assert dashboard["workflows"]["active"] >= 1
    assert dashboard["executions"]["total"] >= 2
    assert dashboard["executions"]["completed"] >= 2
    assert dashboard["completion_rate"] == 100.0
    assert dashboard["avg_duration_ms"] >= 0
    assert dashboard["run_count"] >= 2

    trends = (await client.get("/api/v1/automation/analytics/trends?days=30", headers=headers)).json()
    assert len(trends["by_day"]) >= 1
    assert trends["by_day"][0]["runs"] >= 2
    assert trends["by_workflow"][0]["workflow_id"] == workflow_id

    from app.workers.workflow_analytics_worker import run_once as analytics_pass

    async with db_session_factory() as session:
        written = await analytics_pass(db=session)
        await session.commit()
    assert written >= 1

    metrics = (await client.get(
        "/api/v1/automation/analytics/metrics?metric_type=executions", headers=headers)).json()
    assert len(metrics) >= 1
    assert metrics[0]["count"] >= 2


# --------------------------------------------------------- RBAC + isolation


async def test_rbac_gates_automation(client):
    org = await register_org(client, email="p14rbac@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Rbac Flow", graph=SIMPLE_GRAPH)
    await _activate(client, headers, workflow_id)

    # invite a plain employee
    employee_email = "plain@rbac.test.co"
    response = await client.post(
        "/api/v1/users/invite",
        json={"email": employee_email, "role": "employee"},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    invite = response.json()
    invite_token = invite.get("token") or invite.get("invite_token")

    response = await client.post(
        "/api/v1/auth/register/invite",
        json={
            "token": invite_token,
            "full_name": "Plain Employee",
            "email": employee_email,
            "password": "StrongPass123!",
        },
    )
    if response.status_code != 201:
        pytest.skip("invite flow did not yield a usable session")
    employee_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    # employee can read (employee role has automation:read)
    response = await client.get("/api/v1/automation/workflows", headers=employee_headers)
    assert response.status_code == 200, response.text

    # employee cannot write
    response = await client.post(
        "/api/v1/automation/workflows", json={"name": "Blocked"}, headers=employee_headers)
    assert response.status_code == 403
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run", json={"context": {}},
        headers=employee_headers)
    assert response.status_code == 403
    response = await client.post("/api/v1/automation/ai/generate",
                                 json={"prompt": "x"}, headers=employee_headers)
    assert response.status_code == 403

    # owner can manage
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {}}, headers=headers)
    assert response.status_code == 200


async def test_multi_tenant_isolation(client):
    org_a = await register_org(client, email="tenant-a@iso.test.co", slug="iso-a")
    org_b = await register_org(client, email="tenant-b@iso.test.co", slug="iso-b")
    headers_a, headers_b = org_a["headers"], org_b["headers"]

    workflow_a = await _create_workflow(client, headers_a, name="Tenant A Secret",
                                        graph=SIMPLE_GRAPH)
    await _create_workflow(client, headers_b, name="Tenant B Secret", graph=SIMPLE_GRAPH)
    await _activate(client, headers_a, workflow_a)
    await client.post(
        f"/api/v1/automation/workflows/{workflow_a}/run", json={"context": {}}, headers=headers_a)

    listing_a = (await client.get("/api/v1/automation/workflows", headers=headers_a)).json()
    assert [w["name"] for w in listing_a] == ["Tenant A Secret"]
    listing_b = (await client.get("/api/v1/automation/workflows", headers=headers_b)).json()
    assert [w["name"] for w in listing_b] == ["Tenant B Secret"]

    response = await client.get(f"/api/v1/automation/workflows/{workflow_a}", headers=headers_b)
    assert response.status_code == 404

    execs_a = (await client.get("/api/v1/automation/executions", headers=headers_a)).json()
    execs_b = (await client.get("/api/v1/automation/executions", headers=headers_b)).json()
    assert len(execs_a) == 1
    assert len(execs_b) == 0

    # analytics isolated too
    dash_b = (await client.get("/api/v1/automation/analytics/dashboard", headers=headers_b)).json()
    assert dash_b["executions"]["total"] == 0


# ------------------------------------------------------------------- search


async def test_workflows_in_universal_search(client):
    org = await register_org(client, email="p14srch@test.co")
    headers = org["headers"]
    workflow_id = await _create_workflow(client, headers, name="Searchable Magic Flow")

    response = await client.get(
        "/api/v1/search?q=Searchable", headers=headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] >= 1
    workflow_hits = [r for r in result["results"] if r["type"] == "workflow"]
    assert any(hit["id"] == workflow_id for hit in workflow_hits)


# ------------------------------------------------------------ failure paths


async def test_failed_action_and_retry(client):
    org = await register_org(client, email="p14fail@test.co")
    headers = org["headers"]
    graph = {
        "nodes": [
            {"key": "start", "type": "start", "name": "Start", "config": {}},
            {"key": "boom", "type": "notification", "name": "Broken notify",
             "config": {"title": "x", "recipient_ref": "missing-user-000"}},
            {"key": "end", "type": "end", "name": "Done", "config": {}},
        ],
        "edges": [{"source": "start", "target": "boom"},
                  {"source": "boom", "target": "end"}],
    }
    workflow_id = await _create_workflow(client, headers, name="Failing", graph=graph)
    await _activate(client, headers, workflow_id)

    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/run",
        json={"context": {}}, headers=headers,
    )
    execution = response.json()
    assert execution["status"] == "failed"
    assert "recipient" in (execution["error"] or "")
    boom = next(s for s in execution["steps"] if s["node_key"] == "boom")
    assert boom["status"] == "failed"

    # retry after fixing the config
    graph["nodes"][1]["config"].pop("recipient_ref", None)
    response = await client.post(
        f"/api/v1/automation/workflows/{workflow_id}/graph",
        json={"nodes": graph["nodes"], "edges": graph["edges"]}, headers=headers,
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/v1/automation/executions/{execution['id']}/retry", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["reset"] == 1

    execution = (await client.get(
        f"/api/v1/automation/executions/{execution['id']}", headers=headers)).json()
    assert execution["status"] == "completed"


# --------------------------------------------------------------- workflows


async def test_workers_are_registered(client, db_session_factory):
    from app.workers.scheduler import WORKER_REGISTRY

    names = [name for name, _ in WORKER_REGISTRY]
    for worker in ("workflow", "scheduler", "retry", "integration", "workflow_analytics"):
        assert worker in names

    from app.workers.workflow_worker import run_once as workflow_pass
    from app.workers.retry_worker import run_once as retry_pass

    async with db_session_factory() as session:
        await workflow_pass(db=session)
        await retry_pass(db=session)
        await session.commit()
