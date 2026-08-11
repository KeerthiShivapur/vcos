"""Slice 4D.1 — permission-filtered universal search.

Search results that reference protected company evidence are filtered by the
caller's authorization: conversation/message results are membership-gated for
every caller, and cross-tenant results never leak.
"""

from tests.conftest import register_org


async def _invite(client, headers, email, role="employee"):
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Slice 4D Search", "role": role},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    response = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Slice 4D Search", "password": "S4DPass123!"},
    )
    assert response.status_code == 201, response.text
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"},
            "user": response.json()["user"]}


async def _search(client, headers, query):
    response = await client.get("/api/v1/search", params={"q": query}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _conversation_messages(db_session_factory, conversation_id):
    from sqlalchemy import select

    from app.models.communication import Message

    async with db_session_factory() as db:
        return list(
            (await db.execute(
                select(Message.id).where(Message.conversation_id == conversation_id)
            )).scalars().all()
        )


async def test_search_messaging_membership_filtered(client, db_session_factory):
    org = await register_org(client, email="s4d_search_msg@test.co")
    headers = org["headers"]
    outsider = await _invite(client, headers, "s4d_search_out@test.co", role="employee")

    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    conversation = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "aurora-launch-room", "member_ids": [me]},
            headers=headers,
        )
    ).json()
    sent = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "Aurora goes GA next Friday"},
        headers=headers,
    )
    assert sent.status_code == 201, sent.text
    message_ids = await _conversation_messages(db_session_factory, conversation["id"])
    assert message_ids

    owner_results = (await _search(client, headers, "Aurora"))["results"]
    assert any(
        r["type"] == "conversation" and r["id"] == conversation["id"] for r in owner_results
    )
    assert any(r["type"] == "message" and r["id"] in message_ids for r in owner_results)

    outside_results = (await _search(client, outsider["headers"], "Aurora"))["results"]
    assert not any(r["id"] == conversation["id"] and r["type"] == "conversation"
                   for r in outside_results)
    assert not any(r["type"] == "message" and r["id"] in message_ids for r in outside_results)


async def test_search_tenant_isolation(client):
    org_a = await register_org(client, email="s4d_search_orga@test.co")
    org_b = await register_org(client, email="s4d_search_orgb@test.co")

    await client.post(
        "/api/v1/projects",
        json={"name": "Vela Hidden", "description": "tenant A only", "status": "active"},
        headers=org_a["headers"],
    )

    results_b = (await _search(client, org_b["headers"], "Vela"))["results"]
    assert all(r["id"] is not None for r in results_b)
    assert not any("Vela Hidden" in (r["title"] or "") for r in results_b)

    results_a = (await _search(client, org_a["headers"], "Vela"))["results"]
    assert any("Vela Hidden" in (r["title"] or "") for r in results_a)


async def test_search_still_works_for_org_wide(client):
    org = await register_org(client, email="s4d_search_ok@test.co")
    headers = org["headers"]
    await client.post(
        "/api/v1/projects",
        json={"name": "Orion Search", "description": "indexed", "status": "active"},
        headers=headers,
    )
    results = (await _search(client, headers, "Orion"))["results"]
    assert any(r["type"] == "project" for r in results)
    assert results[0]["url"] if results else True