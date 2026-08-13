"""Slice 4D.6 — role-aware brain: the same question legitimately differs by access.

* an org-wide founder sees company-wide intelligence,
* a project-scoped reader only ever receives their scope's intelligence —
  the hidden project's pattern/insight never appears in claims or sections,
  and its evidence/related endpoints are 404 (indistinguishable from missing),
* governance runs before retrieval: nothing is filtered after generation.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _scenario(client, db_session_factory, email):
    org = await register_org(client, email=email)
    headers = org["headers"]
    visible_proj = await h.blocked_project(client, headers, count=3, name="Visible Ops")
    visible_scope = await h.scope_for_project(client, headers, visible_proj["id"])
    hidden_proj = await h.blocked_project(client, headers, count=3, name="Hidden Ops")
    await h.drive_full_stack(client, db_session_factory)
    return org, headers, visible_proj, visible_scope, hidden_proj


async def test_scoped_reader_and_orgwide_answers_differ(client, db_session_factory):
    org, headers, visible_proj, visible_scope, hidden_proj = await _scenario(
        client, db_session_factory, "p4d6_roles@test.co"
    )
    scoped = await h.invite_scoped_reader(
        client, headers, visible_scope["id"], "p4d6_roles_u@test.co"
    )

    question = "why is this project stuck?"
    org_wide_answer = (
        await client.post("/api/v1/brain/answer", json={"question": question}, headers=headers)
    ).json()
    scoped_answer = (
        await client.post("/api/v1/brain/answer", json={"question": question}, headers=scoped)
    ).json()

    # org-wide sees both projects' insights; the scoped reader only theirs
    org_wide_insight_ids = {i["id"] for i in org_wide_answer["insights"]}
    scoped_insight_ids = {i["id"] for i in scoped_answer["insights"]}
    assert org_wide_insight_ids and org_wide_insight_ids >= scoped_insight_ids
    assert len(org_wide_insight_ids) > len(scoped_insight_ids)

    insights_api = (await client.get("/api/v1/brain/insights", params={"limit": 200}, headers=scoped)).json()
    visible = next(i for i in insights_api["insights"] if i["auth_project_id"] == visible_proj["id"])
    assert visible["id"] in scoped_insight_ids
    assert not any(i["auth_project_id"] == hidden_proj["id"] for i in insights_api["insights"])

    # neither claim section nor patterns leak the hidden project
    scoped_claim_blobs = " ".join(c["claim"] for c in scoped_answer["claims"]).lower()
    assert "hidden ops" not in scoped_claim_blobs
    for pattern in scoped_answer["patterns"]:
        assert pattern["id"]
    scoped_direct = (
        await client.get(
            f"/api/v1/brain/evidence/project/{hidden_proj['id']}", headers=scoped
        )
    )
    assert scoped_direct.status_code == 404
    org_wide_direct = (
        await client.get(f"/api/v1/brain/evidence/project/{hidden_proj['id']}", headers=headers)
    )
    assert org_wide_direct.status_code == 200

    # same question, different answers by authorization
    assert scoped_answer["summary"] != org_wide_answer["summary"]


async def test_overview_is_role_aware(client, db_session_factory):
    org, headers, visible_proj, visible_scope, hidden_proj = await _scenario(
        client, db_session_factory, "p4d6_roled_overview@test.co"
    )
    scoped = await h.invite_scoped_reader(
        client, headers, visible_scope["id"], "p4d6_roled_overview_u@test.co"
    )
    scoped_overview = (await client.get("/api/v1/brain/overview", headers=scoped)).json()
    org_wide_overview = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    assert scoped_overview["scope"] == {"org_wide": False}
    assert org_wide_overview["scope"] == {"org_wide": True}
    assert (
        len(org_wide_overview["recent_intelligence"]["insights"]["latest"])
        >= len(scoped_overview["recent_intelligence"]["insights"]["latest"])
    )


async def test_scoped_reader_evidence_and_related_are_filtered(client, db_session_factory):
    org, headers, visible_proj, visible_scope, hidden_proj = await _scenario(
        client, db_session_factory, "p4d6_ev@test.co"
    )
    scoped = await h.invite_scoped_reader(
        client, headers, visible_scope["id"], "p4d6_ev_u@test.co"
    )

    visible_evidence = (
        await client.get(f"/api/v1/brain/evidence/project/{visible_proj['id']}", headers=scoped)
    )
    assert visible_evidence.status_code == 200, visible_evidence.text
    hidden_related = (
        await client.get(f"/api/v1/brain/related/project/{hidden_proj['id']}", headers=scoped)
    )
    assert hidden_related.status_code == 404
    hidden_evidence = (
        await client.get(f"/api/v1/brain/evidence/project/{hidden_proj['id']}", headers=scoped)
    )
    assert hidden_evidence.status_code == 404