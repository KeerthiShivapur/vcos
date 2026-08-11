"""Slice 4D.1 — canonical company context & evidence layer (unit level).

Covers the governance-first caller access resolution, the bounded evidence
builder, and the accessible-id resolver that backs permission-filtered search.
Every assertion is multi-tenant and authorization-gated.
"""

from sqlalchemy import select

from app.intelligence.company_context import (
    classify_query,
    build_context,
    resolve_accessible_ids,
    resolve_caller_access,
)
from app.models.communication import ConversationMember
from types import SimpleNamespace

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Slice 4D Context", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Slice 4D Context", "password": "S4DPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _create_project(client, headers, name, status="active"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "Slice 4D evidence", "status": status},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _employee_id(client, headers):
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()
    return me["id"]


async def _brain_context(db_session_factory, org_id, user, question):
    user_id = user["id"] if isinstance(user, dict) else user.id
    async with db_session_factory() as db:
        return await build_context(db, SimpleNamespace(id=user_id), question, organization_id=org_id)


async def test_caller_access_org_wide_and_anchored(client, db_session_factory):
    org = await register_org(client, email="s4d_ctx_access@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "s4d_ctx_emp@test.co", role="employee")

    project = await _create_project(client, headers, "Cloud Migration")
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Cloud Migration", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")
    assigned = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": employee["user"]["id"], "role_id": manager_role["id"],
              "scope_id": scope["id"]},
        headers=headers,
    )
    assert assigned.status_code == 201, assigned.text

    owner_user = org["user"]
    async with db_session_factory() as db:
        owner_access = await resolve_caller_access(
            db, organization_id=org["organization"]["id"], user=SimpleNamespace(id=owner_user["id"])
        )
        assert owner_access.org_wide is True
        assert owner_access.visible_scope_ids  # scopes exist -> all visible to org-wide
        assert project["id"] in owner_access.project_ids

        emp_access = await resolve_caller_access(
            db, organization_id=org["organization"]["id"], user=SimpleNamespace(id=employee["user"]["id"])
        )
        assert emp_access.org_wide is True  # invited employee keeps an org-wide assignment
        assert scope["id"] in emp_access.anchored_scope_ids
        assert project["id"] in emp_access.project_ids


async def test_build_context_shape_and_scope_gating(client, db_session_factory):
    org = await register_org(client, email="s4d_ctx_build@test.co")
    headers = org["headers"]
    project = await _create_project(client, headers, "Cloud Migration")
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Cutover to the new platform",
                  "status": "in_progress"},
            headers=headers,
        )
    ).json()

    context = await _brain_context(
        db_session_factory, org["organization"]["id"], org["user"],
        "What is the status of the Cloud Migration project and its tasks?",
    )
    assert context["org_wide"] is True
    assert "scope_ids" in context
    evidence = context["evidence"]
    project_ids = {e["id"] for e in evidence if e["type"] == "project"}
    task_ids = {e["id"] for e in evidence if e["type"] == "task"}
    assert project["id"] in project_ids
    assert task["id"] in task_ids
    for item in evidence:
        assert item["type"] in ("project", "task", "decision", "conversation", "message",
                                "scope", "approval_policy", "goal", "budget", "employee")
        assert item["id"] and item["title"] and item["url"]
        assert item["relation"] in ("matched", "direct", "recent")
        assert "timestamp" in item and "source" in item


async def test_build_context_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="s4d_ctx_orga@test.co")
    org_b = await register_org(client, email="s4d_ctx_orgb@test.co")

    await _create_project(client, org_a["headers"], "Aurora Northstar")
    context_b = await _brain_context(
        db_session_factory, org_b["organization"]["id"], SimpleNamespace(id=org_b["user"]["id"]),
        "What is the status of the Aurora Northstar project?",
    )
    assert "Aurora Northstar" not in " ".join(e.get("title", "") for e in context_b["evidence"])


async def test_resolve_accessible_ids_membership(client, db_session_factory):
    org = await register_org(client, email="s4d_ctx_ids@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "s4d_ctx_ids_emp@test.co", role="employee")

    me = await _employee_id(client, headers)
    conversation = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "launch-room", "member_ids": [me]},
            headers=headers,
        )
    ).json()
    async with db_session_factory() as db:
        foreign_ids = await resolve_accessible_ids(
            db, SimpleNamespace(id=org["user"]["id"]), organization_id=org["organization"]["id"],
            kind="conversation", ids=[conversation["id"]],
        )
        assert foreign_ids == [conversation["id"]]  # owner is a member

        emp_ids = await resolve_accessible_ids(
            db, SimpleNamespace(id=employee["user"]["id"]), organization_id=org["organization"]["id"],
            kind="conversation", ids=[conversation["id"]],
        )
        assert emp_ids == []  # non-member never sees the conversation

        membership = await db.execute(
            select(ConversationMember).where(
                ConversationMember.organization_id == org["organization"]["id"]
            )
        )
        assert len(membership.scalars().all()) >= 1


async def test_classify_query_intents():
    result = classify_query("What is the status of the Cloud Migration project and its tasks?")
    assert "project" in result and "task" in result
    budget_like = classify_query("How is the engineering budget and who is the top engineer?")
    assert "budget" in budget_like or "employee" in budget_like
    unknown = classify_query("What is the meaning of life?")
    assert isinstance(unknown, dict)
