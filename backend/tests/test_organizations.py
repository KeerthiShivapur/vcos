"""Organization profile, settings, branding, stats."""

import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_get_organization(client):
    org = await register_org(client, slug="profile-org", email="org@profile.test.co")
    response = await client.get("/api/v1/organizations/me", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["slug"] == "profile-org"
    assert response.json()["industry"] == "Software"


@pytest.mark.asyncio
async def test_update_organization(client):
    org = await register_org(client, email="updateorg@test.test.co")
    response = await client.patch(
        "/api/v1/organizations/me",
        json={"name": "Acme Corp 2.0", "description": "A better company", "country": "Germany"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Corp 2.0"
    assert response.json()["description"] == "A better company"
    assert response.json()["country"] == "Germany"


@pytest.mark.asyncio
async def test_organization_settings(client):
    org = await register_org(client, email="orgsettings@test.test.co")
    fetched = await client.get("/api/v1/organizations/me/settings", headers=org["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["default_theme"] == "system"

    updated = await client.patch(
        "/api/v1/organizations/me/settings",
        json={"default_theme": "dark", "weekly_digest": False},
        headers=org["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["default_theme"] == "dark"
    assert updated.json()["weekly_digest"] is False


@pytest.mark.asyncio
async def test_organization_branding(client):
    org = await register_org(client, email="branding@test.test.co")
    response = await client.post(
        "/api/v1/organizations/me/branding",
        json={"brand_primary_color": "#0EA5E9", "logo_url": "https://cdn.example.com/logo.png"},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["brand_primary_color"] == "#0EA5E9"


@pytest.mark.asyncio
async def test_organization_stats(client):
    org = await register_org(client, email="stats@test.test.co")
    response = await client.get("/api/v1/organizations/me/stats", headers=org["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["total_users"] == 1
    assert data["roles_count"] == 6
    assert data["active_users"] == 1
    assert data["audit_entries"] >= 1
