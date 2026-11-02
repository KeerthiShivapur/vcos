"""Slice 4H.1 — governance for Universal Company / Organizational
Intelligence: org-wide surfaces 404 for scoped readers; multi-level
membership; write permissions."""

from tests._brain4d6_helpers import invite_scoped_reader
from tests.conftest import register_org

COMPANY = "/api/v1/brain/execution/company"


async def _scoped_reader(client, headers, scope_id, email):
    return await invite_scoped_reader(client, headers, scope_id, email)


async def test_scoped_reader_404s_on_org_wide_universal_surfaces(client, db_session_factory):
    org = await register_org(client, email="4h1_gov@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4h1 scope", "scope_type": "organization", "entity_id": org_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped = await _scoped_reader(client, headers, scope.json()["id"], "4h1-reader@test.co")

    for path in (
        f"{COMPANY}/narrative",
        f"{COMPANY}/causal-chain?subject_type=project&subject_id=x",
        f"{COMPANY}/state?from=2026-01-01&to=2030-01-01",
    ):
        resp = await client.get(path, headers=scoped)
        assert resp.status_code == 404, (path, resp.text)

    resp = await client.post(
        f"{COMPANY}/what-happens-if",
        json={"scenario_type": "delay", "payload": {"project_id": "x", "days": 1}},
        headers=scoped,
    )
    assert resp.status_code == 404, resp.text

    # org-level state stays 404 for the scoped caller (no scope params).
    resp = await client.get(f"{COMPANY}/state", headers=scoped)
    assert resp.status_code == 404, resp.text


async def test_scope_membership_for_multi_level(client, db_session_factory):
    org = await register_org(client, email="4h1_member@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    visible = await client.post(
        "/api/v1/teams", json={"name": "Visible", "code": "h1-vis"},
        headers=headers,
    )
    visible = visible.json()
    hidden = await client.post(
        "/api/v1/teams", json={"name": "Hidden", "code": "h1-hid"},
        headers=headers,
    )
    hidden = hidden.json()

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "Visible team scope", "scope_type": "team",
              "entity_id": visible["id"]},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped = await _scoped_reader(client, headers, scope.json()["id"], "4h1-mem@test.co")

    # member scope: the team the caller's governance covers -> 200.
    resp = await client.get(
        f"{COMPANY}/state?scope_type=team&scope_id={visible['id']}",
        headers=scoped,
    )
    assert resp.status_code == 200, resp.text

    # non-member scope: 404 — never a 200 with hidden data.
    resp = await client.get(
        f"{COMPANY}/state?scope_type=team&scope_id={hidden['id']}",
        headers=scoped,
    )
    assert resp.status_code == 404, resp.text

    resp = await client.get(
        f"{COMPANY}/narrative?scope_type=team&scope_id={hidden['id']}",
        headers=scoped,
    )
    assert resp.status_code == 404, resp.text


async def test_writes_require_projects_manage(client, db_session_factory):
    org = await register_org(client, email="4h1_writep@test.co")
    headers, org_id = org["headers"], org["organization"]["id"]

    scope = await client.post(
        "/api/v1/governance/scopes",
        json={"name": "4h1 write scope", "scope_type": "organization",
              "entity_id": org_id},
        headers=headers,
    )
    assert scope.status_code in (200, 201), scope.text
    scoped = await _scoped_reader(client, headers, scope.json()["id"], "4h1-writer@test.co")

    # a scoped caller without the write grant is denied at the permission gate.
    resp = await client.post(
        f"{COMPANY}/decisions",
        json={"kind": "hire", "title": "x",
              "predicted_outcome": {"expected_outcome": "successful"}},
        headers=scoped,
    )
    assert resp.status_code == 403, resp.text
