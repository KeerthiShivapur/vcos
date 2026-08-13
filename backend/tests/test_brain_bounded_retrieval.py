"""Slice 4D.6 — bounded retrieval: brain never scans the org, every
response surface is capped, and over/under-sized client limits are clamped.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org

ANSWER_SECTION_LIMIT = 3
ANSWER_RELATED_LIMIT = 8
OVERVIEW_ATTENTION_LIMIT = 3
OVERVIEW_RECENT_LIMIT = 3
OVERVIEW_COUNT_LIMIT = 200


async def _rich_org(client, db_session_factory):
    """A few stalled projects -> patterns, insights, memories anchored to them."""
    org = await register_org(client, email="p4d6_bounded@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    proj = await h.blocked_project(client, headers, count=3, name="Bounded Brain Project A")
    for title in ("First approval delay", "Second approval delay", "Third approval delay"):
        await h.seed_memory(client, headers, proj["id"], title=title)
    await h.drive_full_stack(client, db_session_factory)
    await h.seed_knowledge(client, db_session_factory, headers, org_id, project_id=proj["id"])
    return org, headers, org_id, proj


async def test_answers_are_section_capped_and_deterministic(client, db_session_factory):
    org, headers, org_id, proj = await _rich_org(client, db_session_factory)
    response = await client.post(
        "/api/v1/brain/answer",
        json={"question": "how is this project doing overall?",
              "entity_type": "project", "entity_id": proj["id"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    for section in ("patterns", "memories", "insights", "knowledge"):
        assert len(payload.get(section, [])) <= ANSWER_SECTION_LIMIT, section
    assert len(payload.get("related_entities", [])) <= ANSWER_RELATED_LIMIT
    assert 0 <= payload["confidence"] <= 1
    again = (await client.post(
        "/api/v1/brain/answer",
        json={"question": "how is this project doing overall?",
              "entity_type": "project", "entity_id": proj["id"]},
        headers=headers,
    )).json()
    assert payload["summary"] == again["summary"]
    assert payload["confidence"] == again["confidence"]


async def test_overview_attention_and_recent_are_bounded(client, db_session_factory):
    org, headers, org_id, proj = await _rich_org(client, db_session_factory)
    overview = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    attention = overview["attention"]
    assert len(attention) <= OVERVIEW_ATTENTION_LIMIT * 3
    by_source = [item for item in attention if item["source"] == "memory"]
    assert len(by_source) <= OVERVIEW_ATTENTION_LIMIT
    for key in ("insights", "patterns", "memories"):
        bucket = overview["recent_intelligence"][key]
        assert bucket["count"] <= OVERVIEW_COUNT_LIMIT
        assert len(bucket["latest"]) <= OVERVIEW_RECENT_LIMIT
        assert "truncated" in bucket
    assert overview["scope"] == {"org_wide": True}


async def test_evidence_drawer_limits_are_obeyed(client, db_session_factory):
    org, headers, org_id, proj = await _rich_org(client, db_session_factory)

    small = (await client.get(
        f"/api/v1/brain/evidence/project/{proj['id']}", params={"link_limit": 2}, headers=headers
    )).json()
    assert small["limit"] == 2
    for key, value in small["links"].items():
        assert value <= 2, key
    assert len(small["evidence"]) <= 2 * 4
    assert len(small["related_entities"]) <= 2

    large = (await client.get(
        f"/api/v1/brain/evidence/project/{proj['id']}", params={"link_limit": 9}, headers=headers
    )).json()
    assert large["limit"] == 9
    for key, value in large["links"].items():
        assert value <= 9, key


async def test_related_is_bounded_and_rejects_invalid_limits(client, db_session_factory):
    org, headers, org_id, proj = await _rich_org(client, db_session_factory)

    capped = (await client.get(
        f"/api/v1/brain/related/project/{proj['id']}", params={"limit": 3}, headers=headers
    )).json()
    assert len(capped["related"]) <= 3
    assert "truncated" in capped

    large = (await client.get(
        f"/api/v1/brain/related/project/{proj['id']}", params={"limit": 20}, headers=headers
    )).json()
    assert len(large["related"]) <= 20
    assert "truncated" in large

    oversized = await client.get(
        f"/api/v1/brain/related/project/{proj['id']}", params={"limit": 50}, headers=headers
    )
    assert oversized.status_code == 422  # edge rejects before any retrieval

    undersized = await client.get(
        f"/api/v1/brain/related/project/{proj['id']}", params={"limit": 0}, headers=headers
    )
    assert undersized.status_code == 422


async def test_evidence_rejects_out_of_range_link_limit(client, db_session_factory):
    org, headers, org_id, proj = await _rich_org(client, db_session_factory)
    maxed = await client.get(
        f"/api/v1/brain/evidence/project/{proj['id']}", params={"link_limit": 10}, headers=headers
    )
    assert maxed.status_code == 200, maxed.text
    assert maxed.json()["limit"] == 10
    oversized = await client.get(
        f"/api/v1/brain/evidence/project/{proj['id']}", params={"link_limit": 50}, headers=headers
    )
    assert oversized.status_code == 422  # bounded at the edge, never silently scanned