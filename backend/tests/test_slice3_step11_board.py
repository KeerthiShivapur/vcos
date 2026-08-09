"""Slice 3 Step 11: work board — list payloads carry blocker context for board cards."""

import pytest

from tests.conftest import register_org

pytestmark = pytest.mark.asyncio


async def test_task_list_blocks_and_dependencies_are_enriched(client):
    org = await register_org(client, email="b1x@acme.com")
    headers = org["headers"]
    project = (await client.post("/api/v1/projects", headers=headers, json={
        "name": "BoardProj", "code": "bp1x", "status": "active",
    })).json()
    blocked = (await client.post("/api/v1/tasks", headers=headers, json={
        "project_id": project["id"], "title": "Release", "status": "backlog",
    })).json()
    gate = (await client.post("/api/v1/tasks", headers=headers, json={
        "project_id": project["id"], "title": "Approve", "status": "todo",
    })).json()
    done = (await client.post("/api/v1/tasks", headers=headers, json={
        "project_id": project["id"], "title": "Ship docs", "status": "completed",
    })).json()
    await client.post(f"/api/v1/tasks/{blocked['id']}/dependencies", headers=headers, json={
        "depends_on_task_id": gate["id"], "kind": "finish_to_start",
    })
    await client.post(f"/api/v1/tasks/{blocked['id']}/dependencies", headers=headers, json={
        "depends_on_task_id": done["id"], "kind": "finish_to_start",
    })

    r = await client.get(f"/api/v1/tasks?project_id={project['id']}", headers=headers)
    assert r.status_code == 200, r.text
    by_title = {t["title"]: t for t in r.json()}
    assert "Release" in by_title and "Approve" in by_title and "Ship docs" in by_title

    release = by_title["Release"]
    assert len(release["dependencies"]) == 2
    # Only the still-open gate shows as a blocker; the completed dep does not.
    assert [d["title"] for d in release["blocked_by"]] == ["Approve"]
    assert release["blocked_by"][0]["status"] == "todo"
    # Board card badge relies on this shape.
    assert release["blocked_by"][0]["title"] == "Approve"

    # Detail endpoint keeps matching the list shape.
    detail = (await client.get(f"/api/v1/tasks/{blocked['id']}", headers=headers)).json()
    assert [d["title"] for d in detail["blocked_by"]] == ["Approve"]

async def test_task_list_blocks_empty_when_no_dependencies(client):
    org = await register_org(client, email="b2x@acme.com")
    headers = org["headers"]
    project = (await client.post("/api/v1/projects", headers=headers, json={
        "name": "Bare", "code": "bp2x", "status": "active",
    })).json()
    await client.post("/api/v1/tasks", headers=headers, json={
        "project_id": project["id"], "title": "Standalone",
    })
    r = await client.get("/api/v1/tasks", headers=headers)
    assert r.status_code == 200, r.text
    task = next(t for t in r.json() if t["title"] == "Standalone")
    assert task["blocked_by"] == []
    assert task["dependencies"] == []
