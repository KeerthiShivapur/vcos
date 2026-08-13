"""Slice 4D.7 — persona-aware reasoning.

The same question produces different reasoning for different callers because
the evidence they may access differs — not because text is filtered after
generation. An org-wide executive sees the full picture; a scoped manager
never sees hidden evidence in claims, timeline, related projections, the
what-changed digest, or expertise ("who knows") claims.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _scenario_with_hidden_scope(client, db_session_factory, email):
    """Two projects: one visible to the manager, one deliberately hidden."""
    org = await register_org(client, email=email)
    headers = org["headers"]
    visible = await h.blocked_project(client, headers, count=2, name="Visible 4D7")
    hidden = await h.blocked_project(client, headers, count=2, name="Hidden Phoenix 4D7")
    await h.seed_memory(client, headers, hidden["id"], "Hidden Phoenix secret precedent")
    await h.drive_full_stack(client, db_session_factory)

    scope = await h.scope_for_project(client, headers, visible["id"])
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], f"reader{org['organization']['id'][:6]}@test.co"
    )
    return org, headers, visible, hidden, scoped


async def test_hidden_evidence_never_reaches_scoped_answer(client, db_session_factory):
    org, headers, visible, hidden, scoped = await _scenario_with_hidden_scope(
        client, db_session_factory, "p4d7_persona1@test.co"
    )

    # The CEO (org-wide) sees the hidden project's evidence.
    ceo = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is the hidden project delayed?"},
            headers=headers,
        )
    ).json()
    ceo_ids = {e["id"] for c in ceo["claims"] for e in c["evidence"]}
    assert hidden["id"] in ceo_ids, ceo_ids
    assert ceo["scope"]["org_wide"] is True
    assert ceo["scope"] == {"org_wide": True}
    assert ceo["persona"]["org_wide"] is True

    # The scoped manager never sees the hidden project — claims, timeline,
    # related projections, digest all exclude it.
    manager = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is the hidden project delayed?"},
            headers=scoped,
        )
    ).json()
    manager_ids = {e["id"] for c in manager["claims"] for e in c["evidence"]}
    assert hidden["id"] not in manager_ids, manager_ids
    assert manager["scope"]["org_wide"] is False
    assert manager["persona"]["org_wide"] is False
    assert "persona" not in manager["scope"]
    assert manager["persona"]["visible_project_count"] == 1
    timeline_ids = {t["id"] for t in manager.get("timeline", [])}
    assert hidden["id"] not in timeline_ids
    related_ids = {
        r["id"] for key in ("related_patterns", "related_memories", "related_insights")
        for r in manager.get(key, [])
    }
    assert hidden["id"] not in related_ids
    for category in manager.get("what_changed", {}).get("categories", []):
        for item in category.get("items", []):
            assert item["id"] != hidden["id"]

    # Timeline endpoint is equally governed.
    timeline = (
        await client.get(
            "/api/v1/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": hidden["id"]},
            headers=scoped,
        )
    )
    assert timeline.status_code == 404


async def test_governed_expertise_never_leaks_to_scoped_caller(client, db_session_factory):
    org = await register_org(client, email="p4d7_persona2@test.co")
    headers = org["headers"]
    visible = await h.blocked_project(client, headers, count=1, name="Expertise 4D7")
    scope = await h.scope_for_project(client, headers, visible["id"])
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], f"reader{org['organization']['id'][:6]}@test.co"
    )

    question = "who knows most about this?"
    ceo = (
        await client.post("/api/v1/brain/answer", json={"question": question}, headers=headers)
    ).json()
    manager = (
        await client.post("/api/v1/brain/answer", json={"question": question}, headers=scoped)
    ).json()

    # The CEO may see employee expertise (employee evidence is org-wide).
    ceo_employee_refs = [
        e for c in ceo["claims"] for e in c["evidence"] if e["type"] == "employee"
    ]
    # The scoped caller's reasoning never names employees — employee evidence
    # is org-wide-only in company_context, so the reasoning engine emits no
    # expertise claims for them. Different reasoning, not post-filtering.
    manager_employee_refs = [
        e for c in manager["claims"] for e in c["evidence"] if e["type"] == "employee"
    ]
    assert not manager_employee_refs, manager_employee_refs
    # Expertise claims exist for org-wide callers when data matches.
    assert any("knows most" in c["claim"].lower() or "expert" in c["claim"].lower() for c in ceo["claims"]) or not ceo_employee_refs
    # Manager scope persona is scoped in both surfaces.
    assert manager["persona"]["org_wide"] is False


async def test_own_visible_project_is_reachable_for_scoped_caller(client, db_session_factory):
    org, headers, visible, hidden, scoped = await _scenario_with_hidden_scope(
        client, db_session_factory, "p4d7_persona3@test.co"
    )

    manager = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": visible["id"],
            },
            headers=scoped,
        )
    ).json()
    manager_ids = {e["id"] for c in manager["claims"] for e in c["evidence"]}
    assert visible["id"] in manager_ids, manager_ids
    assert hidden["id"] not in manager_ids

    # Follow-up continuity works for the scoped caller within their scope.
    conversation = (
        await client.post("/api/v1/brain/conversations", json={}, headers=scoped)
    ).json()
    first = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": visible["id"],
                "conversation_id": conversation["id"],
            },
            headers=scoped,
        )
    ).json()
    assert first["conversation"]["turn"] == 1
    followup = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "has this happened before?", "conversation_id": conversation["id"]},
            headers=scoped,
        )
    ).json()
    assert followup["conversation"]["turn"] == 2
    assert ("project", visible["id"]) in {
        (e["type"], e["id"]) for c in followup["claims"] for e in c["evidence"]
    }


async def test_tenant_isolation_of_persona_surfaces(client, db_session_factory):
    org_a = await register_org(client, email="p4d7_persona4a@test.co")
    org_b = await register_org(client, email="p4d7_persona4b@test.co")
    proj_b = await h.blocked_project(client, org_b["headers"], count=2, name="Tenant B 4D7")
    await h.seed_memory(client, org_b["headers"], proj_b["id"], "Tenant B secret")
    await h.drive_full_stack(client, db_session_factory)

    # Org A's org-wide caller cannot see Org B's project in any surface.
    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={
                "question": "why is this project delayed?",
                "entity_type": "project",
                "entity_id": proj_b["id"],
            },
            headers=org_a["headers"],
        )
    ).json()
    assert proj_b["id"] not in {e["id"] for c in answer["claims"] for e in c["evidence"]}
    timeline = await client.get(
        "/api/v1/brain/timeline/unified",
        params={"entity_type": "project", "entity_id": proj_b["id"]},
        headers=org_a["headers"],
    )
    assert timeline.status_code == 404
    changed = (
        await client.get("/api/v1/brain/what-changed", params={"days": 7}, headers=org_a["headers"])
    ).json()
    for category in changed["categories"]:
        for item in category.get("items", []):
            assert item["id"] != proj_b["id"]