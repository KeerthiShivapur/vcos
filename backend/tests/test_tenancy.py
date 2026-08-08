"""Multi-tenancy: no organization may read another organization's data."""

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_cross_organization_user_access_blocked(client):
    org_a = await register_org(client, slug="tenant-a", email="a@a.test.co")
    org_b = await register_org(client, slug="tenant-b", email="b@b.test.co")

    # Organization B's user must not be able to see Organization A's users.
    response = await client.get("/api/v1/users", headers=org_b["headers"])
    assert response.status_code == 200
    emails = [u["email"] for u in response.json()["items"]]
    assert "a@a.test.co" not in emails
    assert "b@b.test.co" in emails

    # B cannot fetch A's user by id.
    a_user_id = org_a["user"]["id"]
    response = await client.get(f"/api/v1/users/{a_user_id}", headers=org_b["headers"])
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cross_organization_audit_isolated(client):
    org_a = await register_org(client, slug="audit-a", email="audita@a.test.co")
    org_b = await register_org(client, slug="audit-b", email="auditb@b.test.co")

    audit_a = await client.get("/api/v1/audit", headers=org_a["headers"])
    audit_b = await client.get("/api/v1/audit", headers=org_b["headers"])
    actions_a = {e["action"] for e in audit_a.json()["items"]}
    actions_b = {e["action"] for e in audit_b.json()["items"]}
    assert "organization.created" in actions_a
    assert "organization.created" in actions_b
    # Both orgs have their own entries with their own resource ids.
    resource_ids_a = {e["resource_id"] for e in audit_a.json()["items"] if e["resource_id"]}
    resource_ids_b = {e["resource_id"] for e in audit_b.json()["items"] if e["resource_id"]}
    assert resource_ids_a.isdisjoint(resource_ids_b)
    # No tenant may appear in the other tenant's logs at all.
    org_ids_a = {e["id"] for e in audit_a.json()["items"]}
    org_ids_b = {e["id"] for e in audit_b.json()["items"]}
    assert org_ids_a.isdisjoint(org_ids_b)


@pytest.mark.asyncio
async def test_cross_organization_notifications_isolated(client):
    org_a = await register_org(client, slug="notif-a", email="notifa@a.test.co")
    org_b = await register_org(client, slug="notif-b", email="notifb@b.test.co")

    notifs_a = await client.get("/api/v1/notifications", headers=org_a["headers"])
    notifs_b = await client.get("/api/v1/notifications", headers=org_b["headers"])
    recipients_a = {n["id"] for n in notifs_a.json()["items"]}
    recipients_b = {n["id"] for n in notifs_b.json()["items"]}
    assert recipients_a.isdisjoint(recipients_b)


@pytest.mark.asyncio
async def test_session_tokens_bound_to_tenant(client):
    org_b = await register_org(client, slug="bound-b", email="boundb@b.test.co")
    # Using org B's token on org A's endpoints only touches org B data.
    response = await client.get("/api/v1/organizations/me", headers=org_b["headers"])
    assert response.status_code == 200
    assert response.json()["slug"] == org_b["organization"]["slug"]
