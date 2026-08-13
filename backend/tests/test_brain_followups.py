"""Slice 4D.7 — conversational continuity.

A follow-up question that does not name an entity inherits the conversation's
anchor: "Has this happened before?" after asking about a project answers
about that project — without the user repeating it and without the frontend
re-sending it. Conversations are owner-scoped and tenant-isolated.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def test_followup_inherits_anchor_without_repeating_entity(client, db_session_factory):
    org = await register_org(client, email="p4d7_follow1@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=2, name="Followup Alpha")
    await h.seed_memory(client, headers, proj["id"], "Followup Alpha delay precedent")
    await h.drive_full_stack(client, db_session_factory)

    conversation = (
        await client.post("/api/v1/brain/conversations", json={}, headers=headers)
    ).json()

    first = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": proj["id"],
                "conversation_id": conversation["id"],
            },
            headers=headers,
        )
    ).json()
    assert first["conversation"]["id"] == conversation["id"]
    assert first["conversation"]["turn"] == 1
    first_claim_entities = {
        (e["type"], e["id"]) for c in first["claims"] for e in c["evidence"]
    }
    assert ("project", proj["id"]) in first_claim_entities

    # Follow-up WITHOUT entity: the anchor is inherited server-side.
    followup = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "has this happened before?",
                "conversation_id": conversation["id"],
            },
            headers=headers,
        )
    ).json()
    assert followup["conversation"]["turn"] == 2
    followup_entities = {
        (e["type"], e["id"]) for c in followup["claims"] for e in c["evidence"]
    }
    assert ("project", proj["id"]) in followup_entities, followup_entities

    # The conversation records both turns with the inherited anchor.
    detail = (
        await client.get(f"/api/v1/brain/conversations/{conversation['id']}", headers=headers)
    ).json()
    assert detail["turn_count"] == 2
    assert detail["last_anchor_id"] == proj["id"]
    assert [t["question"] for t in detail["turns"]] == [
        "why is this project delayed?", "has this happened before?",
    ]


async def test_conversation_is_owner_scoped(client, db_session_factory):
    org = await register_org(client, email="p4d7_owner@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=1, name="Owner Scope 4D7")
    conversation = (
        await client.post("/api/v1/brain/conversations", json={}, headers=headers)
    ).json()

    scoped = await h.invite_scoped_reader(client, headers, (await h.scope_for_project(client, headers, proj["id"]))["id"], f"reader{org['organization']['id'][:6]}@test.co")

    # Another (scoped) caller cannot read the CEO's conversation.
    other = await client.get(f"/api/v1/brain/conversations/{conversation['id']}", headers=scoped)
    assert other.status_code == 404
    # Nor list it.
    listed = (await client.get("/api/v1/brain/conversations", headers=scoped)).json()
    assert all(c["id"] != conversation["id"] for c in listed["conversations"])
    # Nor answer into it.
    forbidden = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "who owns this?", "conversation_id": conversation["id"]},
            headers=scoped,
        )
    )
    assert forbidden.status_code == 404
    # The owner can: the orphan question inherits the anchor.
    followup = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "who owns this?", "conversation_id": conversation["id"]},
            headers=headers,
        )
    )
    assert followup.status_code == 200
    assert followup.json()["conversation"]["turn"] == 1


async def test_conversations_are_tenant_isolated(client, db_session_factory):
    org_a = await register_org(client, email="p4d7_tenanta@test.co")
    org_b = await register_org(client, email="p4d7_tenantb@test.co")
    conv_a = (
        await client.post("/api/v1/brain/conversations", json={}, headers=org_a["headers"])
    ).json()

    # Org B cannot see or use Org A's conversation.
    assert (await client.get(f"/api/v1/brain/conversations/{conv_a['id']}", headers=org_b["headers"])).status_code == 404
    assert (await client.post(
        "/api/v1/brain/answer",
        json={"question": "what changed this week?", "conversation_id": conv_a["id"]},
        headers=org_b["headers"],
    )).status_code == 404
    # Each user lists only their own conversations.
    own = (await client.get("/api/v1/brain/conversations", headers=org_b["headers"])).json()
    assert own["count"] == 0


async def test_conversation_turn_count_is_bounded(client, db_session_factory):
    org = await register_org(client, email="p4d7_bounded@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=1, name="Bounded Turns 4D7")
    conversation = (
        await client.post("/api/v1/brain/conversations", json={}, headers=headers)
    ).json()
    for i in range(6):
        answer = (
            await client.post(
                "/api/v1/brain/answer",
                json={"question": f"status question number {i}?", "conversation_id": conversation["id"]},
                headers=headers,
            )
        ).json()
        assert answer["conversation"]["turn"] == i + 1
    detail = (
        await client.get(f"/api/v1/brain/conversations/{conversation['id']}", headers=headers)
    ).json()
    assert detail["turn_count"] == 6
    # Turns are retained in order, no duplicates, all anchored to the project.
    assert len(detail["turns"]) == 6
    assert {t["question"] for t in detail["turns"]} == {f"status question number {i}?" for i in range(6)}
    assert all(t["anchor_id"] == proj["id"] for t in detail["turns"] if t["anchor_id"])


async def test_answer_without_conversation_works_as_before(client, db_session_factory):
    org = await register_org(client, email="p4d7_noconv@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=2, name="No Conv 4D7")
    await h.seed_memory(client, headers, proj["id"], "No Conv precedent")
    await h.drive_full_stack(client, db_session_factory)
    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "has this happened before?", "entity_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
    ).json()
    assert "conversation" not in answer
    assert answer["claims"]