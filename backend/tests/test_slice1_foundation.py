"""Slice 1 - Company Foundation: invitation lifecycle, RBAC policy, permissions payload, events, tenancy."""

import pytest

from tests.conftest import register_org


async def invite(client, headers, email, role="employee", full_name="Invitee"):
    return await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": full_name, "role": role},
        headers=headers,
    )


async def accept(client, token, email, full_name="Invitee", password="InviteePass123!"):
    return await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "email": email, "full_name": full_name, "password": password},
    )


async def register_roles(client, org, *codes):
    """Accept an invite for each role code and return {code: headers}."""
    result = {}
    for code in codes:
        r = await invite(client, org["headers"], f"{code}@slice1.test.co", role=code, full_name=code.title())
        assert r.status_code == 201, r.text
        r = await accept(client, r.json()["token"], f"{code}@slice1.test.co")
        assert r.status_code == 201, r.text
        result[code] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return result


@pytest.mark.asyncio
async def test_me_returns_effective_permissions(client):
    org = await register_org(client, email="perms@slice1.test.co")
    me = await client.get("/api/v1/auth/me", headers=org["headers"])
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == "ceo"
    assert len(body["permissions"]) > 50
    assert "users:invite" in body["permissions"]
    assert "roles:manage" in body["permissions"]
    assert "invitations:manage" in body["permissions"]


@pytest.mark.asyncio
async def test_permission_hierarchy_employee_subset_of_hr_subset_of_ceo(client):
    org = await register_org(client, email="hier@slice1.test.co")
    users = await register_roles(client, org, "hr", "employee")
    perms = {}
    for code, headers in users.items():
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        perms[code] = set(me.json()["permissions"])
    ceo_perms = set((await client.get("/api/v1/auth/me", headers=org["headers"])).json()["permissions"])
    assert perms["employee"].issubset(perms["hr"]), "employee role must not exceed hr role"
    assert perms["hr"].issubset(ceo_perms), "hr role must not exceed ceo role"
    assert "users:invite" in perms["hr"]
    assert "roles:manage" not in perms["hr"]
    assert "invitations:manage" in perms["hr"]


@pytest.mark.asyncio
async def test_register_emits_single_user_created_event(client):
    org = await register_org(client, email="events@slice1.test.co")
    events = await client.get("/api/v1/events", headers=org["headers"])
    names = [e["name"] for e in events.json()["items"]]
    assert names.count("user.created") == 1, "user.created must be emitted exactly once at registration"
    assert "user.registered" not in names, "legacy user.registered event must not be emitted"


@pytest.mark.asyncio
async def test_invite_flow_audit_notification_events(client):
    org = await register_org(client, email="trace@slice1.test.co")
    r = await invite(client, org["headers"], "tracee@slice1.test.co")
    assert r.status_code == 201
    token = r.json()["token"]
    r = await accept(client, token, "tracee@slice1.test.co")
    assert r.status_code == 201

    audit = await client.get("/api/v1/audit", headers=org["headers"])
    actions = {e["action"] for e in audit.json()["items"]}
    assert "organization.created" in actions
    assert "auth.login" in actions
    assert "user.invited" in actions
    assert "invitation.accepted" in actions

    events = await client.get("/api/v1/events", headers=org["headers"])
    names = {e["name"] for e in events.json()["items"]}
    assert "user.created" in names
    assert "user.invited" in names
    assert "user.login" in names


@pytest.mark.asyncio
async def test_resend_rotates_token_and_resets_expiry(client):
    org = await register_org(client, email="resend@slice1.test.co")
    r = await invite(client, org["headers"], "resendee@slice1.test.co")
    assert r.status_code == 201
    old_token = r.json()["token"]
    inv_id = r.json()["invitation"]["id"]
    old_expiry = r.json()["invitation"]["expires_at"]

    r = await client.post(f"/api/v1/users/invitations/{inv_id}/resend", headers=org["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    new_token = body["token"]
    assert new_token != old_token
    assert body["invitation"]["status"] == "pending"
    assert body["invitation"]["expires_at"] != old_expiry

    accepted = await accept(client, new_token, "resendee@slice1.test.co")
    assert accepted.status_code == 201
    rejected = await accept(client, old_token, "resendee@slice1.test.co")
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_resend_accepted_invitation_rejected(client):
    org = await register_org(client, email="resend2@slice1.test.co")
    r = await invite(client, org["headers"], "resendee2@slice1.test.co")
    token = r.json()["token"]
    inv_id = r.json()["invitation"]["id"]
    assert (await accept(client, token, "resendee2@slice1.test.co")).status_code == 201
    r = await client.post(f"/api/v1/users/invitations/{inv_id}/resend", headers=org["headers"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_resend_cross_organization_404(client):
    org_a = await register_org(client, email="crossa@slice1.test.co")
    org_b = await register_org(client, email="crossb@slice1.test.co", name="Other Corp", slug="other-corpx")
    r = await invite(client, org_a["headers"], "cross@slice1.test.co")
    inv_id = r.json()["invitation"]["id"]
    r = await client.post(f"/api/v1/users/invitations/{inv_id}/resend", headers=org_b["headers"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_resend_requires_permission(client):
    org = await register_org(client, email="resend3@slice1.test.co")
    r = await invite(client, org["headers"], "resendee3@slice1.test.co")
    inv_id = r.json()["invitation"]["id"]
    users = await register_roles(client, org, "employee")
    r = await client.post(f"/api/v1/users/invitations/{inv_id}/resend", headers=users["employee"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invite_role_assignment_policy(client):
    org = await register_org(client, email="policy@slice1.test.co")
    users = await register_roles(client, org, "hr")

    r = await invite(client, users["hr"], "ok@slice1.test.co", role="employee")
    assert r.status_code == 201, r.text

    for code in ("admin", "ceo", "manager"):
        r = await invite(client, users["hr"], f"{code}@slice1.test.co", role=code)
        assert r.status_code == 403, f"hr must not invite {code}: {r.status_code}"


@pytest.mark.asyncio
async def test_role_assignment_policy_on_direct_assign(client):
    org = await register_org(client, email="assign@slice1.test.co")
    users = await register_roles(client, org, "hr", "employee")
    target = (await client.get("/api/v1/users", headers=org["headers"]))
    target_id = next(u["id"] for u in target.json()["items"] if u["email"] == "employee@slice1.test.co")
    roles = await client.get("/api/v1/roles", headers=org["headers"])
    roles_by_code = {r["code"]: r["id"] for r in roles.json()}

    r = await client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_id": roles_by_code["admin"], "replace_all": True},
        headers=users["hr"],
    )
    assert r.status_code == 403, "hr must not assign admin"

    r = await client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_id": roles_by_code["employee"], "replace_all": True},
        headers=users["hr"],
    )
    assert r.status_code == 200

    r = await client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_id": roles_by_code["ceo"], "replace_all": True},
        headers=org["headers"],
    )
    assert r.status_code == 200, "ceo may assign ceo"


@pytest.mark.asyncio
async def test_duplicate_invite_and_existing_member(client):
    org = await register_org(client, email="dup@slice1.test.co")
    r = await invite(client, org["headers"], "duppee@slice1.test.co")
    assert r.status_code == 201, r.text
    r = await invite(client, org["headers"], "duppee@slice1.test.co")
    assert r.status_code == 409, r.text

    r = await invite(client, org["headers"], "alreadyee@slice1.test.co")
    token = r.json()["token"]
    assert (await accept(client, token, "alreadyee@slice1.test.co")).status_code == 201
    r = await invite(client, org["headers"], "alreadyee@slice1.test.co")
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_invitation_list_omits_tokens(client):
    org = await register_org(client, email="list@slice1.test.co")
    await invite(client, org["headers"], "listee@slice1.test.co")
    listing = await client.get("/api/v1/users/invitations", headers=org["headers"])
    assert listing.status_code == 200
    assert all("token" not in item for item in listing.json())


@pytest.mark.asyncio
async def test_tenant_isolation_invitations(client):
    org_a = await register_org(client, email="isoa@slice1.test.co")
    org_b = await register_org(client, email="isob@slice1.test.co", name="Iso B", slug="iso-bb")
    await invite(client, org_a["headers"], "iso@slice1.test.co")
    listing_b = await client.get("/api/v1/users/invitations", headers=org_b["headers"])
    assert listing_b.json() == []


@pytest.mark.asyncio
async def test_manager_cannot_invite(client):
    org = await register_org(client, email="mgr@slice1.test.co")
    users = await register_roles(client, org, "manager")
    r = await invite(client, users["manager"], "mgree@slice1.test.co")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_suspended_user_cannot_login(client):
    import uuid

    org = await register_org(client, email="suspend@slice1.test.co")
    email = f"employee-{uuid.uuid4().hex[:8]}@slice1.test.co"
    r = await invite(client, org["headers"], email, role="employee", full_name="Susp Employee")
    assert r.status_code == 201, r.text
    r = await accept(client, r.json()["token"], email, full_name="Susp Employee")
    assert r.status_code == 201, r.text
    listing = await client.get("/api/v1/users", headers=org["headers"])
    target = next(u for u in listing.json()["items"] if u["email"] == email)
    r = await client.patch(
        f"/api/v1/users/{target['id']}/status",
        json={"status": "suspended"},
        headers=org["headers"],
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "InviteePass123!"},
    )
    assert r.status_code == 403
