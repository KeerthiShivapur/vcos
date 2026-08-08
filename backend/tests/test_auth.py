import pytest

from tests.conftest import register_org


@pytest.mark.asyncio
async def test_register_creates_org_and_logs_in(client):
    session = await register_org(client)
    assert session["user"]["role"] == "ceo"
    assert session["user"]["status"] == "active"
    assert session["organization"]["name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_login_and_me(client):
    session = await register_org(client, email="login@acme.test.co")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@acme.test.co", "password": "StrongPass123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["user"]["email"] == "login@acme.test.co"

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "login@acme.test.co"


@pytest.mark.asyncio
async def test_invalid_credentials_rejected(client):
    await register_org(client, email="badpass@acme.test.co")
    response = await client.post(
        "/api/v1/auth/login", json={"email": "badpass@acme.test.co", "password": "WrongPass123!"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cycle(client):
    session = await register_org(client, email="refresh@acme.test.co")
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session["refresh"]}
    )
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_session(client):
    session = await register_org(client, email="logout@acme.test.co")
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": session["refresh"]},
        headers=session["headers"],
    )
    assert response.status_code == 200
    # Refresh with the revoked token must fail
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session["refresh"]}
    )
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_change_password_and_login_again(client):
    session = await register_org(client, email="changepass@acme.test.co")
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "StrongPass123!", "new_password": "NewStrongPass456!"},
        headers=session["headers"],
    )
    assert response.status_code == 200
    old_login = await client.post(
        "/api/v1/auth/login", json={"email": "changepass@acme.test.co", "password": "StrongPass123!"}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/api/v1/auth/login", json={"email": "changepass@acme.test.co", "password": "NewStrongPass456!"}
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_forgot_and_reset_password(client):
    await register_org(client, email="resetpw@acme.test.co")
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "resetpw@acme.test.co"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sessions_listed_and_revoked(client):
    session = await register_org(client, email="sessions@acme.test.co")
    sessions = await client.get("/api/v1/auth/sessions", headers=session["headers"])
    assert sessions.status_code == 200
    assert len(sessions.json()) >= 1
    session_id = sessions.json()[0]["id"]
    revoked = await client.delete(f"/api/v1/auth/sessions/{session_id}", headers=session["headers"])
    assert revoked.status_code == 200
    remaining = await client.get("/api/v1/auth/sessions", headers=session["headers"])
    assert session_id not in [s["id"] for s in remaining.json()]
