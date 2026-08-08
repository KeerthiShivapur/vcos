"""RBAC: permissions enforced on protected endpoints."""

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_employee_cannot_invite_or_manage_roles(client):
    org = await register_org(client, email="owner@rbac.test.co")

    # Owner (CEO) invites an employee.
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "emp@rbac.test.co", "full_name": "Emp Worker", "role": "employee"},
        headers=org["headers"],
    )
    assert invite.status_code == 201
    invite_token = invite.json()["token"]

    # Employee registers through the invitation.
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite_token, "full_name": "Emp Worker", "password": "EmpPass123!"},
    )
    assert emp.status_code == 201
    emp_headers = {"Authorization": f"Bearer {emp.json()['access_token']}"}

    # Employee cannot invite others (users:invite is manager+).
    blocked = await client.post(
        "/api/v1/users/invite",
        json={"email": "blocked@rbac.test.co", "role": "employee"},
        headers=emp_headers,
    )
    assert blocked.status_code == 403

    # Employee cannot read the audit log.
    blocked_audit = await client.get("/api/v1/audit", headers=emp_headers)
    assert blocked_audit.status_code == 403

    # Employee cannot manage roles.
    blocked_roles = await client.get("/api/v1/roles", headers=emp_headers)
    assert blocked_roles.status_code == 403

    # Employee cannot update organization settings.
    blocked_org = await client.patch(
        "/api/v1/organizations/me", json={"name": "Hijacked"}, headers=emp_headers
    )
    assert blocked_org.status_code == 403

    # Employee CAN use their own workspace.
    ws = await client.get("/api/v1/workspace", headers=emp_headers)
    assert ws.status_code == 200

    # Employee CAN read own profile.
    me = await client.get("/api/v1/auth/me", headers=emp_headers)
    assert me.status_code == 200

    # Employee CAN update own profile (users:profile is on all default roles).
    updated = await client.patch(
        "/api/v1/users/me",
        json={"full_name": "Emp Updated", "job_title": "Engineer", "timezone": "UTC"},
        headers=emp_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Emp Updated"
    assert updated.json()["job_title"] == "Engineer"

    # Employee CANNOT assign roles to anyone (users:manage is manager+).
    blocked_role = await client.post(
        "/api/v1/users/{}/roles".format(org["user"]["id"]),
        json={"role_id": "x"},
        headers=emp_headers,
    )
    assert blocked_role.status_code in (403, 404)


@pytest.mark.asyncio
async def test_ceo_can_manage_everything(client):
    org = await register_org(client, email="ceo@rbac.test.co")
    roles = await client.get("/api/v1/roles", headers=org["headers"])
    assert roles.status_code == 200
    audit = await client.get("/api/v1/audit", headers=org["headers"])
    assert audit.status_code == 200
    assert len(audit.json()["items"]) > 0
    permissions = await client.get("/api/v1/roles/permissions", headers=org["headers"])
    assert permissions.status_code == 200
    assert len(permissions.json()) > 0


@pytest.mark.asyncio
async def test_role_assignment_changes_effective_permissions(client):
    org = await register_org(client, email="assign@rbac.test.co")

    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "assignee@rbac.test.co", "full_name": "Assignee", "role": "employee"},
        headers=org["headers"],
    )
    emp = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Assignee", "password": "EmpPass123!"},
    )
    emp_id = emp.json()["user"]["id"]
    emp_headers = {"Authorization": f"Bearer {emp.json()['access_token']}"}

    # Before: audit access denied.
    assert (await client.get("/api/v1/audit", headers=emp_headers)).status_code == 403

    # Find the admin role id.
    roles = (await client.get("/api/v1/roles", headers=org["headers"])).json()
    admin_role = next(r for r in roles if r["code"] == "admin")

    # Owner assigns the admin role.
    assigned = await client.post(
        f"/api/v1/users/{emp_id}/roles",
        json={"role_id": admin_role["id"], "replace_all": True},
        headers=org["headers"],
    )
    assert assigned.status_code == 200
    assert assigned.json()["role"] == "admin"

    # After: audit access granted through the new role.
    assert (await client.get("/api/v1/audit", headers=emp_headers)).status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401
