"""Slice 4D.1 — canonical /brain/answer contract.

Proves the answer contract shape, tenant isolation, the "answer differs by
authorization" core contract (membership-gated messaging evidence + scoped-only
callers cannot reach the org-wide brain surface), and that evidence is never
fabricated (every cited id exists in the caller's own org).
"""

from sqlalchemy import select

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Slice 4D Answer", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Slice 4D Answer", "password": "S4DPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _seed_project(client, headers, name):
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": name, "description": "Slice 4D evidence", "status": "active"},
            headers=headers,
        )
    ).json()
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": f"Cutover phase for {name}",
                  "status": "in_progress"},
            headers=headers,
        )
    ).json()
    return project, task


async def _answer(client, headers, question):
    response = await client.post(
        "/api/v1/brain/answer", json={"question": question}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _cited_ids_of_kind(answer, kind):
    return {e["id"] for c in answer["claims"] for e in c["evidence"] if e["type"] == kind}


async def test_brain_answer_contract(client):
    org = await register_org(client, email="s4d_answer_contract@test.co")
    headers = org["headers"]
    project, task = await _seed_project(client, headers, "Cloud Migration")

    answer = await _answer(
        client, headers, "What is the status of the Cloud Migration project and its tasks?"
    )
    assert answer["question"]
    assert answer["scope_ids"] is not None
    assert "answered_at" in answer
    assert answer["claims"], answer
    for claim in answer["claims"]:
        assert claim["claim"]
        assert 0.0 <= claim["confidence"] <= 1.0
        assert "auth_scope" in claim and "scope_ids" in claim["auth_scope"]
        assert "timestamp" in claim
        for evidence in claim["evidence"]:
            assert {"type", "id", "title", "url"} <= set(evidence)
            assert evidence["url"].startswith("/")
    cited_ids = {e["id"] for c in answer["claims"] for e in c["evidence"]}
    assert project["id"] in cited_ids or task["id"] in cited_ids


async def test_brain_answer_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="s4d_answer_orga@test.co")
    org_b = await register_org(client, email="s4d_answer_orgb@test.co")
    await _seed_project(client, org_a["headers"], "Nebula Project")

    answer_b = await _answer(
        client, org_b["headers"], "What is the status of the Nebula Project?"
    )
    from app.models.project import Project

    async with db_session_factory() as db:
        projects_a = set(
            (await db.execute(
                select(Project.id).where(Project.organization_id == org_a["organization"]["id"])
            )).scalars().all()
        )
    cited = _cited_ids_of_kind(answer_b, "project")
    assert not (cited & projects_a)  # org B's answer never cites org A evidence


async def test_brain_answer_differs_by_authorization(client):
    org = await register_org(client, email="s4d_answer_authz@test.co")
    headers = org["headers"]
    outsider = await _invite(client, headers, "s4d_answer_out@test.co", role="employee")

    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    conversation = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "launch-room", "member_ids": [me]},
            headers=headers,
        )
    ).json()
    sent = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "Next week we go live with the Aurora platform"},
        headers=headers,
    )
    assert sent.status_code == 201, sent.text

    owner_answer = await _answer(client, headers, "What was decided and discussed about the Aurora platform?")
    owner_message_claims = [
        c for c in owner_answer["claims"]
        if any(e["type"] == "message" for e in c["evidence"])
    ]
    assert owner_message_claims  # member sees messaging evidence

    outsider_answer = await _answer(
        client, outsider["headers"], "What was decided and discussed about the Aurora platform?"
    )
    outsider_message_claims = [
        c for c in outsider_answer["claims"]
        if any(e["type"] == "message" for e in c["evidence"])
    ]
    assert outsider_message_claims == []  # non-member gets no messaging evidence


async def test_brain_answer_evidence_not_fabricated(client, db_session_factory):
    org = await register_org(client, email="s4d_answer_real@test.co")
    headers = org["headers"]
    await _seed_project(client, headers, "Real Evidence Project")

    answer = await _answer(
        client, headers, "Explain the status of the Real Evidence Project to me please?"
    )
    assert answer["claims"]
    kinds = {e["type"] for c in answer["claims"] for e in c["evidence"]}
    model_map = {
        "project": ("app.models.project", "Project"),
        "task": ("app.models.task", "Task"),
        "decision": ("app.models.knowledge", "Decision"),
        "conversation": ("app.models.communication", "Conversation"),
        "message": ("app.models.communication", "Message"),
        "scope": ("app.models.governance", "GovernanceScope"),
        "goal": ("app.models.goal", "Goal"),
        "budget": ("app.models.finance", "Budget"),
        "employee": ("app.models.employee", "Employee"),
    }
    async with db_session_factory() as db:
        for kind in kinds:
            module_name, cls_name = model_map[kind]
            model = getattr(__import__(module_name, fromlist=[cls_name]), cls_name)
            real = set(
                (await db.execute(
                    select(model.id).where(model.organization_id == org["organization"]["id"])
                )).scalars().all()
            )
            assert _cited_ids_of_kind(answer, kind) <= real, kind


async def test_scoped_only_caller_cannot_reach_brain(client):
    org = await register_org(client, email="s4d_answer_scoped@test.co")
    headers = org["headers"]
    scoped = await _invite(client, headers, "s4d_answer_scoped_u@test.co", role="employee")

    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Scoped Project", "description": "scope anchor", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Scoped Project", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")
    await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": scoped["user"]["id"], "role_id": manager_role["id"],
              "scope_id": scope["id"]},
        headers=headers,
    )
    assignments = (
        await client.get(
            "/api/v1/governance/assignments",
            params={"user_id": scoped["user"]["id"]},
            headers=headers,
        )
    ).json()
    org_wide_assignment = next(a for a in assignments if a["scope_id"] is None)
    removed = await client.delete(
        f"/api/v1/governance/assignments/{org_wide_assignment['id']}", headers=headers
    )
    assert removed.status_code == 200, removed.text

    denied = await client.post(
        "/api/v1/brain/answer", json={"question": "How is the company doing?"},
        headers=scoped["headers"],
    )
    assert denied.status_code == 403  # scoped-only authority cannot use org-wide brain