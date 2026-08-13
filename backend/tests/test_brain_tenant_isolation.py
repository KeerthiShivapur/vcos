"""Slice 4D.6 — tenant isolation: Org A must never see Org B evidence.

The unified brain (answer, overview, evidence, related) is fully
tenant-scoped; cross-tenant lookups behave as missing (404) so nothing can
leak names, ids or existence.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def test_cross_tenant_brain_surfaces_leak_nothing(client, db_session_factory):
    org_a = await register_org(client, email="p4d6_iso_a@test.co")
    org_b = await register_org(client, email="p4d6_iso_b@test.co")
    proj_a = await h.blocked_project(
        client, org_a["headers"], count=3, name="Isolated A Secret Project"
    )
    await h.seed_memory(client, org_a["headers"], proj_a["id"], "A secret memory")
    await h.drive_full_stack(client, db_session_factory)

    answer_b = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind?",
                  "entity_type": "project", "entity_id": proj_a["id"]},
            headers=org_b["headers"],
        )
    ).json()
    assert not answer_b["insights"]
    blobs = " ".join(c["claim"] for c in answer_b["claims"]).lower()
    assert "secret" not in blobs and "isolated a" not in blobs

    evidence_b = await client.get(
        f"/api/v1/brain/evidence/project/{proj_a['id']}", headers=org_b["headers"]
    )
    assert evidence_b.status_code == 404
    related_b = await client.get(
        f"/api/v1/brain/related/project/{proj_a['id']}", headers=org_b["headers"]
    )
    assert related_b.status_code == 404

    overview_b = (await client.get("/api/v1/brain/overview", headers=org_b["headers"])).json()
    assert overview_b["attention"] == []
    assert overview_b["recent_intelligence"]["insights"]["count"] == 0

    # Org A still sees everything (sanity)
    evidence_a = await client.get(
        f"/api/v1/brain/evidence/project/{proj_a['id']}", headers=org_a["headers"]
    )
    assert evidence_a.status_code == 200


async def test_insight_claims_never_cross_tenants(client, db_session_factory):
    org_a = await register_org(client, email="p4d6_iso_claim@test.co")
    org_b = await register_org(client, email="p4d6_iso_claim2@test.co")
    await h.blocked_project(client, org_a["headers"], count=3, name="Claim Org A Project")
    await h.drive_full_stack(client, db_session_factory)

    answer_a = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "what is happening in the company?"},
            headers=org_a["headers"],
        )
    ).json()
    assert answer_a["insights"]
    answer_b = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "what is happening in the company?"},
            headers=org_b["headers"],
        )
    ).json()
    assert not answer_b["insights"]
    assert not answer_b["patterns"]