"""Slice 4D.1 — connected relationships: org graph edges & bounded traversal.

Covers the new structural edges (task → project, decision → scope, conversation
→ message), the bounded BFS traversal, both graph APIs, and RBAC gating of the
sync (brain:manage) vs traverse (brain:read) surfaces.
"""

from sqlalchemy import select

from app.intelligence.graph_engine import graph_engine
from app.models.intelligence import OrgGraphEdge
from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Slice 4D Graph", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Slice 4D Graph", "password": "S4DPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _edge_rows(db, org_id, source_type=None):
    stmt = select(OrgGraphEdge).where(OrgGraphEdge.organization_id == org_id)
    if source_type:
        stmt = stmt.where(OrgGraphEdge.source_type == source_type)
    return (await db.execute(stmt)).scalars().all()


async def test_sync_task_project_edge(client, db_session_factory):
    org = await register_org(client, email="s4d_graph_task@test.co")
    headers = org["headers"]
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Orbit", "description": "render", "status": "active"},
            headers=headers,
        )
    ).json()
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Launch orbital module", "status": "todo"},
            headers=headers,
        )
    ).json()

    async with db_session_factory() as db:
        ok = await graph_engine.sync_entity_edges(
            db, organization_id=org["organization"]["id"],
            entity_type="task", entity_id=task["id"],
        )
        assert ok >= 1
        edge = (
            await db.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == org["organization"]["id"],
                    OrgGraphEdge.source_type == "task",
                    OrgGraphEdge.source_id == task["id"],
                )
            )
        ).scalar_one_or_none()
        assert edge is not None
        assert edge.target_type == "project" and edge.target_id == project["id"]
        assert edge.relation == "belongs_to"

        again = await graph_engine.sync_entity_edges(
            db, organization_id=org["organization"]["id"],
            entity_type="task", entity_id=task["id"],
        )
        assert again >= 1
        assert len(await _edge_rows(db, org["organization"]["id"], "task")) == 1  # idempotent


async def test_sync_decision_scope_edge(client, db_session_factory):
    org = await register_org(client, email="s4d_graph_decision@test.co")
    headers = org["headers"]
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Comet", "description": "governed", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Comet", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()

    async with db_session_factory() as db:
        from app.models.knowledge import Decision

        decision = Decision(
            organization_id=org["organization"]["id"],
            title="Adopt the comet runway",
            slug="adopt-comet-runway",
            description="Governance routing test",
            status="approved",
            project_id=project["id"],
        )
        db.add(decision)
        await db.flush()

        ok = await graph_engine.sync_entity_edges(
            db, organization_id=org["organization"]["id"],
            entity_type="decision", entity_id=decision.id,
        )
        assert ok >= 1
        edge = (
            await db.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == org["organization"]["id"],
                    OrgGraphEdge.source_type == "decision",
                    OrgGraphEdge.source_id == decision.id,
                )
            )
        ).scalar_one_or_none()
        assert edge is not None
        assert edge.target_type == "scope" and edge.target_id == scope["id"]
        assert edge.relation == "governed_by"


async def test_sync_conversation_message_edges(client, db_session_factory):
    org = await register_org(client, email="s4d_graph_conv@test.co")
    headers = org["headers"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    conversation = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "war-room", "member_ids": [me]},
            headers=headers,
        )
    ).json()
    message = (
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "Systems nominal"},
            headers=headers,
        )
    ).json()

    async with db_session_factory() as db:
        ok = await graph_engine.sync_entity_edges(
            db, organization_id=org["organization"]["id"],
            entity_type="conversation", entity_id=conversation["id"],
        )
        assert ok >= 1
        edges = await _edge_rows(db, org["organization"]["id"], "conversation")
        assert any(
            e.relation == "contains" and e.target_type == "message" and e.target_id == message["id"]
            for e in edges
        )


async def test_traverse_bounded_and_connected(client, db_session_factory):
    org = await register_org(client, email="s4d_graph_traverse@test.co")
    headers = org["headers"]
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Voyager", "description": "traversal", "status": "active"},
            headers=headers,
        )
    ).json()
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Plot the course", "status": "todo"},
            headers=headers,
        )
    ).json()

    async with db_session_factory() as db:
        await graph_engine.sync_entity_edges(
            db, organization_id=org["organization"]["id"],
            entity_type="task", entity_id=task["id"],
        )
        await db.commit()

        result = await graph_engine.traverse(
            db, organization_id=org["organization"]["id"],
            start_type="task", start_id=task["id"], max_depth=3,
        )
        node_keys = {(n["type"], n["id"]) for n in result["nodes"]}
        assert ("task", task["id"]) in node_keys
        assert ("project", project["id"]) in node_keys
        assert result["truncated"] in (True, False)
        assert result["limits"]["max_depth"] == 3
        assert result["limits"]["max_nodes"] == 64
        assert result["limits"]["max_edges"] == 128
        assert len(result["nodes"]) <= 64 and len(result["edges"]) <= 128


async def test_relationship_apis_and_rbac(client):
    org = await register_org(client, email="s4d_graph_api@test.co")
    headers = org["headers"]
    employee = await _invite(client, headers, "s4d_graph_api_emp@test.co", role="employee")

    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Pulsar", "description": "api", "status": "active"},
            headers=headers,
        )
    ).json()
    task = (
        await client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Beam the signal", "status": "todo"},
            headers=headers,
        )
    ).json()

    synced = (
        await client.post(
            "/api/v1/brain/graph/relationships/sync",
            json={"entity_type": "task", "entity_id": task["id"]},
            headers=headers,
        )
    ).json()
    assert synced["synced"] >= 1
    assert synced["mode"] == "entity"

    denied_sync = await client.post(
        "/api/v1/brain/graph/relationships/sync",
        json={"entity_type": "task", "entity_id": task["id"]},
        headers=employee["headers"],
    )
    assert denied_sync.status_code == 403  # sync is brain:manage

    traversed = (
        await client.get(
            "/api/v1/brain/graph/relationships/traverse",
            params={"node_type": "task", "node_id": task["id"], "max_depth": 2},
            headers=headers,
        )
    ).json()
    assert any(n["type"] == "project" and n["id"] == project["id"] for n in traversed["nodes"])

    read_ok = (
        await client.get(
            "/api/v1/brain/graph/relationships/traverse",
            params={"node_type": "task", "node_id": task["id"]},
            headers=employee["headers"],
        )
    )
    assert read_ok.status_code == 200  # traverse is brain:read

    capped = (
        await client.get(
            "/api/v1/brain/graph/relationships/traverse",
            params={"node_type": "task", "node_id": task["id"], "max_depth": 9},
            headers=headers,
        )
    )
    assert capped.status_code == 422  # max_depth capped at 8