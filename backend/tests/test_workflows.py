"""Invitations, registration from invite, role assignment, notifications, audit, events, workspace, search."""

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_invite_and_accept_flow(client):
    org = await register_org(client, email="inviter@flow.test.co")
    response = await client.post(
        "/api/v1/users/invite",
        json={"email": "invitee@flow.test.co", "full_name": "Invitee Person", "role": "employee"},
        headers=org["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invitation"]["status"] == "pending"
    assert body["token"], "console transport must expose the invite token"

    accepted = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": body["token"], "full_name": "Invitee Person", "password": "InviteePass123!"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["user"]["role"] == "employee"

    # User now exists in the directory.
    directory = await client.get("/api/v1/users", headers=org["headers"])
    emails = [u["email"] for u in directory.json()["items"]]
    assert "invitee@flow.test.co" in emails


@pytest.mark.asyncio
async def test_invitation_token_cannot_be_reused(client):
    org = await register_org(client, email="reuse@flow.test.co")
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "reuse2@flow.test.co", "role": "employee"},
        headers=org["headers"],
    )
    token = invite.json()["token"]
    first = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "full_name": "First", "password": "InviteePass123!"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": token, "full_name": "Second", "password": "InviteePass123!"},
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_invite_revoked(client):
    org = await register_org(client, email="revoke@flow.test.co")
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "revokee@flow.test.co", "role": "employee"},
        headers=org["headers"],
    )
    invitation_id = invite.json()["invitation"]["id"]
    revoked = await client.post(
        f"/api/v1/users/invitations/{invitation_id}/revoke", headers=org["headers"]
    )
    assert revoked.status_code == 200
    listing = await client.get("/api/v1/users/invitations", headers=org["headers"])
    entry = next(i for i in listing.json() if i["id"] == invitation_id)
    assert entry["status"] == "revoked"


@pytest.mark.asyncio
async def test_welcome_notification_and_mark_read(client):
    org = await register_org(client, email="notif@flow.test.co")
    stats = await client.get("/api/v1/notifications/stats", headers=org["headers"])
    assert stats.status_code == 200
    assert stats.json()["total_unread"] >= 1

    notifications = await client.get("/api/v1/notifications", headers=org["headers"])
    items = notifications.json()["items"]
    assert any(n["type"] == "system" for n in items)

    marked = await client.post("/api/v1/notifications/read", json={"ids": None}, headers=org["headers"])
    assert marked.status_code == 200

    stats_after = await client.get("/api/v1/notifications/stats", headers=org["headers"])
    assert stats_after.json()["total_unread"] == 0


@pytest.mark.asyncio
async def test_audit_and_events_recorded(client):
    org = await register_org(client, email="auditflow@test.test.co.co")
    audit = await client.get("/api/v1/audit", headers=org["headers"])
    actions = {e["action"] for e in audit.json()["items"]}
    assert "organization.created" in actions
    assert "auth.login" in actions

    events = await client.get("/api/v1/events", headers=org["headers"])
    names = {e["name"] for e in events.json()["items"]}
    assert "organization.created" in names
    assert "user.created" in names
    assert "user.login" in names

    actions_catalog = await client.get("/api/v1/audit/actions", headers=org["headers"])
    assert "user.invited" in actions_catalog.json()


@pytest.mark.asyncio
async def test_workspace_lifecycle(client):
    org = await register_org(client, email="ws@flow.test.co")

    settings = await client.get("/api/v1/workspace/settings", headers=org["headers"])
    assert settings.status_code == 200
    assert settings.json()["shortcuts"] == []

    updated = await client.patch(
        "/api/v1/workspace/settings",
        json={"shortcuts": [{"label": "Phase 1 notes", "href": "/projects"}]},
        headers=org["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["shortcuts"] == [{"label": "Phase 1 notes", "href": "/projects"}]

    fetched = await client.get("/api/v1/workspace/settings", headers=org["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["shortcuts"] == [{"label": "Phase 1 notes", "href": "/projects"}]


@pytest.mark.asyncio
async def test_global_search_finds_users(client):
    org = await register_org(client, email="search@flow.test.co")
    response = await client.get("/api/v1/search?q=Ada", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    types = {r["type"] for r in response.json()["results"]}
    assert "user" in types

    # Empty-ish query returns no results.
    response = await client.get("/api/v1/search?q=zzzzzzz", headers=org["headers"])
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_dashboard_summary(client):
    org = await register_org(client, email="dash@flow.test.co")
    response = await client.get("/api/v1/dashboard/summary", headers=org["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["organization_name"] == "Acme Corp"
    assert data["current_user"]["email"] == "dash@flow.test.co"
    assert data["total_users"] >= 1
    assert len(data["recent_activity"]) > 0
    assert data["workspace"] is not None


@pytest.mark.asyncio
async def test_platform_health(client):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    platform = await client.get("/api/v1/platform")
    assert platform.json()["api_version"] == "v1"
    assert platform.json()["features"]["foundation"] is True

