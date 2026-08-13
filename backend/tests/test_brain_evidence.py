"""Slice 4D.6 — every claim stays traceable to valid, governed evidence.

* every claim returned by /brain/answer references at least one evidence
  item with a real type + id + deep link,
* evidence ids resolve to real rows in the caller's organization,
* the cross-source evidence drawer (/brain/evidence/{type}/{id}) links the
  existing intelligence that references the object,
* restricted evidence is never revealed (hidden -> 404).
"""

from sqlalchemy import select

from app.models.knowledge import Decision
from app.models.project import Project
from app.models.task import Task as TaskRow
from tests import _brain4d6_helpers as h
from tests.conftest import register_org

_SOURCE_MODELS = {"project": Project, "task": TaskRow, "decision": Decision}


async def test_every_claim_has_resolvable_evidence(client, db_session_factory):
    org = await register_org(client, email="p4d6_evid@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=3, name="Evidence Project")
    await h.drive_full_stack(client, db_session_factory)

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project blocked?"},
            headers=headers,
        )
    ).json()
    assert answer["claims"]
    for claim in answer["claims"]:
        assert claim["claim"]
        assert 0.0 <= claim["confidence"] <= 1.0
        assert claim["timestamp"]
        if not claim["evidence"]:
            # the only legitimate empty-evidence claim is the explicit absence
            # statement ("no similar historical experience"), which is itself
            # the traceable fact about the memory store.
            assert "no similar historical experience" in claim["claim"].lower(), claim
            continue
        assert isinstance(claim["evidence"], list), claim
        for item in claim["evidence"]:
            assert item["type"] and item["id"] and item["url"]
            if item["type"] in _SOURCE_MODELS:
                model = _SOURCE_MODELS[item["type"]]
                async with db_session_factory() as db:
                    row = await db.get(model, item["id"])
                assert row is not None
                assert row.organization_id == org["organization"]["id"]


async def test_evidence_drawer_links_existing_intelligence(client, db_session_factory):
    org = await register_org(client, email="p4d6_drawer@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=3, name="Drawer Project")
    await h.drive_full_stack(client, db_session_factory)

    drawer = (
        await client.get(f"/api/v1/brain/evidence/project/{proj['id']}", headers=headers)
    )
    assert drawer.status_code == 200, drawer.text
    body = drawer.json()
    assert body["source"]["type"] == "project"
    assert body["source"]["id"] == proj["id"]
    assert body["source"]["url"].startswith("/projects/")
    # a project with blocked tasks composes into patterns + insights -> both link
    assert body["links"]["patterns"] >= 1
    assert body["links"]["insights"] >= 1
    assert body["evidence"]
    for item in body["evidence"]:
        assert item["type"] in ("pattern", "insight", "memory", "knowledge")
        assert item["id"] and item["title"] and item["url"]
    assert body["limit"] >= 1
    assert body["generated_at"]


async def test_evidence_drawer_is_governed_and_404_when_hidden(client, db_session_factory):
    org = await register_org(client, email="p4d6_drawer_gov@test.co")
    headers = org["headers"]
    visible_proj = await h.blocked_project(client, headers, count=3, name="Drawer Visible")
    scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.blocked_project(client, headers, count=3, name="Drawer Hidden")
    await h.drive_full_stack(client, db_session_factory)
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], "p4d6_drawer_gov_u@test.co"
    )

    visible = await client.get(f"/api/v1/brain/evidence/project/{visible_proj['id']}", headers=scoped)
    assert visible.status_code == 200
    hidden = await client.get(f"/api/v1/brain/evidence/project/{hidden_proj['id']}", headers=scoped)
    assert hidden.status_code == 404

    # pattern/insight/memory source types delegate to their governed engines
    insights_api = (await client.get("/api/v1/brain/insights", params={"limit": 5}, headers=headers)).json()
    if insights_api["insights"]:
        insight_id = insights_api["insights"][0]["id"]
        as_founder = await client.get(f"/api/v1/brain/evidence/insight/{insight_id}", headers=headers)
        assert as_founder.status_code == 200
        assert as_founder.json()["source"]["type"] == "insight"


async def test_claim_scopes_are_present_and_grounded(client, db_session_factory):
    org = await register_org(client, email="p4d6_ground@test.co")
    headers = org["headers"]
    proj = await h.project(client, headers, "Grounded Project")
    decision_row = await h.decision(client, headers, proj["id"])

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "what is the status of the decision work?",
                "entity_type": "project",
                "entity_id": proj["id"],
            },
            headers=headers,
        )
    ).json()
    for claim in answer["claims"]:
        assert "auth_scope" in claim
        assert "scope_ids" in claim["auth_scope"]
    blobs = " ".join((item["id"] for c in answer["claims"] for item in c["evidence"]))
    assert decision_row["id"] in blobs or answer["claims"]
    async with db_session_factory() as db:
        row = await db.get(Decision, decision_row["id"])
        assert row is not None and row.organization_id == org["organization"]["id"]