"""Slice 4 — Governed AI Worker tests.

Hermetic (SQLite in-memory, AI_PROVIDER=none). The model-invocation seam is
the only mocked boundary; everything else (operation spine, approvals,
decisions, tasks, tenant scoping) runs against real services.
"""

import json

import pytest

from tests.conftest import register_org
from app.services import governed_worker_service as gws_module
from app.services.governed_worker_service import governed_worker_service

VALID_MODEL_JSON = json.dumps(
    {
        "summary": "The project is active with manageable risk.",
        "observed_facts": ["There are open tasks."],
        "evidence": [
            {"claim": "Open tasks exist", "source": "tasks", "source_ref": "t-1"}
        ],
        "inferences": ["Delivery may slip if the top risk materializes."],
        "uncertainties": ["No capacity data in context."],
        "recommendations": ["Review the top risk this week."],
        "proposed_actions": [
            {
                "action_type": "create_task",
                "title": "Mitigate top risk",
                "description": "Run a mitigation session.",
                "requires_approval": True,
            }
        ],
    }
)


def _patch_model(monkeypatch, *, content=VALID_MODEL_JSON, available=True, boom=None):
    async def fake_invoke(*, instruction, task_kind, context):
        if boom is not None:
            raise boom
        return {
            "provider": "fake-provider",
            "model": "fake-model-1",
            "available": available,
            "content": content if available else "",
            "usage": {"total_tokens": 42},
        }

    monkeypatch.setattr(
        governed_worker_service, "_invoke_model", fake_invoke
    )


def _patch_company_state(monkeypatch):
    async def fake_state(db, *, organization_id):
        return {
            "advisory_only": True,
            "organization_id": organization_id,
            "dimensions": {
                "strategy": {
                    "label": "Strategy",
                    "state": "healthy",
                    "headline": "All goals on track",
                }
            },
            "attention": [{"title": "Review Q4 plan", "kind": "strategy", "severity": "medium"}],
            "generated_at": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        gws_module.company_operating_engine, "company_state", fake_state
    )


async def _make_project(client, headers, name="Worker Project"):
    resp = await client.post(
        "/api/v1/projects", headers=headers, json={"name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_task(client, headers, *, kind="research", project_id=None, idem=None, title="Weekly research brief"):
    body = {
        "title": title,
        "instruction": "Summarize the current state and what deserves attention.",
        "task_kind": kind,
        "scope_type": "project" if project_id else "company",
    }
    if project_id:
        body["scope_id"] = project_id
    if idem:
        body["idempotency_key"] = idem
    return await client.post("/api/v1/governed-worker/tasks", headers=headers, json=body)


@pytest.mark.asyncio
async def test_research_task_completes_with_model_assistance(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(client, headers, kind="research", project_id=project_id)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["phase"] == "queued"

    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert run.status_code == 200, run.text
    detail = run.json()
    assert detail["phase"] == "completed"
    assert detail["model"]["assisted"] is True
    assert detail["model"]["provider"] == "fake-provider"
    result = detail["result"]
    assert result["summary"] == "The project is active with manageable risk."
    assert result["inferences"]
    assert result["observed_facts"]
    assert any("Project" in fact for fact in result["observed_facts"])
    assert result["approval"] is None
    assert detail["approval"] is None


@pytest.mark.asyncio
async def test_research_task_without_model_degrades_honestly(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch, available=False)

    created = await _create_task(client, headers, kind="research", project_id=project_id)
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert run.status_code == 200, run.text
    detail = run.json()
    assert detail["phase"] == "completed"
    assert detail["model"]["available"] is False
    assert detail["model"]["assisted"] is False
    result = detail["result"]
    assert result["summary"] is None
    assert result["recommendations"] == []
    assert any(
        "unavailable" in u for u in result["uncertainties"]
    )


@pytest.mark.asyncio
async def test_company_scope_task_completes(client, monkeypatch):
    org = await register_org(client)
    _patch_company_state(monkeypatch)
    _patch_model(monkeypatch)

    created = await _create_task(client, headers=org["headers"], kind="research")
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=org["headers"]
    )
    assert run.status_code == 200, run.text
    detail = run.json()
    assert detail["phase"] == "completed"
    assert any("Strategy" in fact for fact in detail["result"]["observed_facts"])


@pytest.mark.asyncio
async def test_malformed_model_output_fails_task(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch, content="this is not json at all")

    created = await _create_task(client, headers, project_id=project_id)
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    detail = run.json()
    assert detail["phase"] == "failed"
    assert detail["result"] is None
    assert "model_output_invalid" in (detail["error"] or "")


@pytest.mark.asyncio
async def test_incomplete_model_output_fails_task(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch, content=json.dumps({"observed_facts": ["x"]}))

    created = await _create_task(client, headers, project_id=project_id)
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    detail = run.json()
    assert detail["phase"] == "failed"
    assert "model_output_invalid" in (detail["error"] or "")


@pytest.mark.asyncio
async def test_model_timeout_fails_task(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch, boom=TimeoutError("provider timed out"))

    created = await _create_task(client, headers, project_id=project_id)
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    detail = run.json()
    assert detail["phase"] == "failed"
    assert "model_invocation_failed" in (detail["error"] or "")


@pytest.mark.asyncio
async def test_recommendation_creates_proposed_decision_and_pending_approval(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(
        client, headers, kind="recommendation", project_id=project_id
    )
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert run.status_code == 200, run.text
    detail = run.json()
    assert detail["phase"] == "awaiting_approval"
    assert detail["approval"]["status"] == "pending"
    assert detail["proposal_decision"]["status"] == "proposed"
    assert detail["action_operation"]["state"] == "queued"
    assert detail["result"]["approval"]["id"] == detail["approval"]["id"]

    decisions = await client.get("/api/v1/decisions", headers=headers)
    assert decisions.status_code == 200
    titles = [d["title"] for d in decisions.json()]
    assert any(t.startswith("Recommendation:") for t in titles)


@pytest.mark.asyncio
async def test_action_blocked_before_approval(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(
        client, headers, kind="recommendation", project_id=project_id
    )
    task_id = created.json()["id"]
    detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
        )
    ).json()
    action_id = detail["action_operation"]["id"]

    resp = await client.post(
        f"/api/v1/governed-worker/actions/{action_id}/execute", headers=headers
    )
    assert resp.status_code == 400
    assert "not approved" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_action_executes_after_approval_and_creates_real_task(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(
        client, headers, kind="recommendation", project_id=project_id
    )
    task_id = created.json()["id"]
    detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
        )
    ).json()
    approval_id = detail["approval"]["id"]
    action_id = detail["action_operation"]["id"]

    decided = await client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=headers,
        json={"decision": "approved", "note": "go ahead"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    after_approval = await client.get(
        f"/api/v1/governed-worker/tasks/{task_id}", headers=headers
    )
    assert after_approval.json()["phase"] == "ready_to_execute"

    executed = await client.post(
        f"/api/v1/governed-worker/actions/{action_id}/execute", headers=headers
    )
    assert executed.status_code == 200, executed.text
    final = executed.json()
    assert final["phase"] == "executed"
    new_task_id = final["action_result"]["task_id"]

    task_resp = await client.get(f"/api/v1/tasks/{new_task_id}", headers=headers)
    assert task_resp.status_code == 200
    assert "governed-worker" in (task_resp.json().get("tags") or [])


@pytest.mark.asyncio
async def test_rejected_approval_blocks_execution(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(
        client, headers, kind="recommendation", project_id=project_id
    )
    task_id = created.json()["id"]
    detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
        )
    ).json()
    approval_id = detail["approval"]["id"]
    action_id = detail["action_operation"]["id"]

    decided = await client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=headers,
        json={"decision": "rejected", "note": "not now"},
    )
    assert decided.status_code == 200, decided.text

    resp = await client.post(
        f"/api/v1/governed-worker/actions/{action_id}/execute", headers=headers
    )
    assert resp.status_code == 400

    detail_after = await client.get(
        f"/api/v1/governed-worker/tasks/{task_id}", headers=headers
    )
    assert detail_after.json()["phase"] == "action_rejected"


@pytest.mark.asyncio
async def test_cancelled_approval_blocks_execution(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(
        client, headers, kind="recommendation", project_id=project_id
    )
    task_id = created.json()["id"]
    detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
        )
    ).json()
    approval_id = detail["approval"]["id"]
    action_id = detail["action_operation"]["id"]

    cancelled = await client.post(
        f"/api/v1/approvals/{approval_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200, cancelled.text

    resp = await client.post(
        f"/api/v1/governed-worker/actions/{action_id}/execute", headers=headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_idempotent_creation_with_same_key(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    _patch_model(monkeypatch)

    first = await _create_task(client, headers, idem="key-123", title="Idem task")
    second = await _create_task(client, headers, idem="key-123", title="Idem task")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    listing = await client.get("/api/v1/governed-worker/tasks", headers=headers)
    matching = [t for t in listing.json() if t["title"] == "Idem task"]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_cancel_queued_task_then_run_is_rejected(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    _patch_model(monkeypatch)

    created = await _create_task(client, headers, title="Cancel me")
    task_id = created.json()["id"]

    cancelled = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["phase"] == "cancelled"

    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert run.status_code == 400


@pytest.mark.asyncio
async def test_invalid_transitions(client, monkeypatch):
    org = await register_org(client)
    headers = org["headers"]
    project_id = await _make_project(client, headers)
    _patch_model(monkeypatch)

    created = await _create_task(client, headers, project_id=project_id)
    task_id = created.json()["id"]
    run = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert run.status_code == 200

    rerun = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/run", headers=headers
    )
    assert rerun.status_code == 400

    recancel = await client.post(
        f"/api/v1/governed-worker/tasks/{task_id}/cancel", headers=headers
    )
    assert recancel.status_code == 400


@pytest.mark.asyncio
async def test_project_scope_requires_valid_project(client):
    org = await register_org(client)
    headers = org["headers"]

    missing = await client.post(
        "/api/v1/governed-worker/tasks",
        headers=headers,
        json={
            "title": "Bad scope",
            "instruction": "Do research on nothing.",
            "task_kind": "research",
            "scope_type": "project",
        },
    )
    assert missing.status_code == 400

    bogus = await client.post(
        "/api/v1/governed-worker/tasks",
        headers=headers,
        json={
            "title": "Bad scope id",
            "instruction": "Do research on nothing.",
            "task_kind": "research",
            "scope_type": "project",
            "scope_id": "does-not-exist",
        },
    )
    assert bogus.status_code == 400


@pytest.mark.asyncio
async def test_tenant_isolation(client, monkeypatch):
    org_a = await register_org(client, name="Alpha Co")
    org_b = await register_org(client, name="Beta Co")
    project_a = await _make_project(client, org_a["headers"], name="Alpha Project")
    _patch_model(monkeypatch)

    created = await _create_task(
        client, org_a["headers"], project_id=project_a, title="Alpha research"
    )
    task_id = created.json()["id"]
    detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{task_id}/run", headers=org_a["headers"]
        )
    ).json()

    listing_b = await client.get(
        "/api/v1/governed-worker/tasks", headers=org_b["headers"]
    )
    assert listing_b.status_code == 200
    assert listing_b.json() == []

    cross_get = await client.get(
        f"/api/v1/governed-worker/tasks/{task_id}", headers=org_b["headers"]
    )
    assert cross_get.status_code == 404

    with_action = await _create_task(
        client, org_a["headers"], kind="recommendation",
        project_id=project_a, title="Alpha recommendation",
    )
    action_detail = (
        await client.post(
            f"/api/v1/governed-worker/tasks/{with_action.json()['id']}/run",
            headers=org_a["headers"],
        )
    ).json()
    action_id = action_detail["action_operation"]["id"]

    cross_execute = await client.post(
        f"/api/v1/governed-worker/actions/{action_id}/execute",
        headers=org_b["headers"],
    )
    assert cross_execute.status_code == 404

    assert detail["phase"] == "completed"
