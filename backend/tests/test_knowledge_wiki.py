"""Phase 4 — Wiki: hierarchy, tree, move, publish, tenancy."""

import pytest

from tests.conftest import register_org


async def _page(client, headers, title, **overrides):
    payload = {"title": title, "space": "organization", "content": f"Content for {title}"}
    payload.update(overrides)
    resp = await client.post("/api/v1/wiki", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_wiki_hierarchy_and_tree(client):
    org = await register_org(client, email="wiki@phase4.test.co")
    headers = org["headers"]

    root = await _page(client, headers, "Engineering Handbook")
    root_id = root["id"]
    child = await _page(client, headers, "Coding Standards", parent_id=root_id)
    child_id = child["id"]
    await _page(client, headers, "Review Process", parent_id=child_id)
    await _page(client, headers, "Unrelated Page")

    tree = await client.get("/api/v1/wiki/tree", headers=headers)
    assert tree.status_code == 200, tree.text
    root_node = next((n for n in tree.json() if n["id"] == root_id), None)
    assert root_node is not None
    assert len(root_node["children"]) == 1
    assert root_node["children"][0]["id"] == child_id
    assert len(root_node["children"][0]["children"]) == 1

    children = await client.get(f"/api/v1/wiki/{root_id}/children", headers=headers)
    assert children.status_code == 200
    assert len(children.json()) == 1

    got = await client.get(f"/api/v1/wiki/{root_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["child_count"] == 1


@pytest.mark.asyncio
async def test_wiki_publish_and_move(client):
    org = await register_org(client, email="wikimove@phase4.test.co")
    headers = org["headers"]

    page = await _page(client, headers, "Runbook")
    page_id = page["id"]
    target = await _page(client, headers, "Ops")
    target_id = target["id"]

    published = await client.post(f"/api/v1/wiki/{page_id}/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    moved = await client.post(f"/api/v1/wiki/{page_id}/move", json={"parent_id": target_id}, headers=headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] == target_id

    cyc = await client.post(f"/api/v1/wiki/{target_id}/move", json={"parent_id": page_id}, headers=headers)
    assert cyc.status_code == 400, cyc.text
    tree = await client.get("/api/v1/wiki/tree", headers=headers)
    assert tree.status_code == 200

    deleted = await client.delete(f"/api/v1/wiki/{page_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    missing = await client.get(f"/api/v1/wiki/{page_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_wiki_tenancy(client):
    org_a = await register_org(client, email="wikit@phase4.test.co")
    org_b = await register_org(client, email="wikib@phase4.test.co")
    page = await _page(client, org_a["headers"], "Secret Notes")
    got = await client.get(f"/api/v1/wiki/{page['id']}", headers=org_b["headers"])
    assert got.status_code == 404
