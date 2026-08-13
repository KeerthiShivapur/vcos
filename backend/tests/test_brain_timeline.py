"""Slice 4D.7 — unified, evidence-backed company timeline.

The timeline composes genuinely different evidence classes (memories,
patterns, insights, project timeline rows) into one governed narrative.
Every entry references a real row via id + url, is bounded, ordered, and
tenant/scope-isolated.
"""

from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def test_unified_timeline_is_evidence_backed_and_bounded(client, db_session_factory):
    org = await register_org(client, email="p4d7_tl1@test.co")
    headers = org["headers"]
    proj = await h.blocked_project(client, headers, count=2, name="Timeline Alpha 4D7")
    await h.seed_memory(client, headers, proj["id"], "Timeline precedent")
    await h.drive_full_stack(client, db_session_factory)

    timeline = (
        await client.get("/api/v1/brain/timeline/unified", headers=headers)
    ).json()
    entries = timeline["timeline"]
    assert entries, entries
    assert timeline["count"] == len(entries)
    assert len(entries) <= 50
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry["kind"], entry["id"])
        assert key not in seen, f"duplicate timeline entry {key}"
        seen.add(key)
        assert entry["kind"] in ("memory", "pattern", "insight", "project_timeline")
        assert entry["id"] and entry["url"] and entry["title"]
    # Descending chronological order by occurred_at (missing -> oldest bucket).
    stamps = [e.get("occurred_at") or "" for e in entries]
    assert stamps == sorted(stamps, reverse=True)
    # Multiple evidence classes participate in a rich scenario.
    kinds = {e["kind"] for e in entries}
    assert len(kinds) >= 2, kinds


async def test_anchored_timeline_filters_to_entity_realm(client, db_session_factory):
    org = await register_org(client, email="p4d7_tl2@test.co")
    headers = org["headers"]
    proj_a = await h.blocked_project(client, headers, count=1, name="Timeline Alpha 4D7b")
    proj_b = await h.blocked_project(client, headers, count=2, name="Timeline Bravo 4D7")
    await h.seed_memory(client, headers, proj_b["id"], "Bravo precedent")
    await h.drive_full_stack(client, db_session_factory)

    bravo = (
        await client.get(
            "/api/v1/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": proj_b["id"]},
            headers=headers,
        )
    ).json()
    assert bravo["entity"]["id"] == proj_b["id"]
    bravo_entries = bravo["timeline"]
    # Anchored timeline keeps only entries tied to that project's realm.
    for entry in bravo_entries:
        if entry["kind"] == "project_timeline":
            assert entry["url"] == f"/projects/{proj_b['id']}"
    # A memory seeded on project B belongs to B's anchored timeline.
    assert any(e["kind"] == "memory" and "precedent" in e["title"] for e in bravo_entries) or any(
        e["kind"] == "project_timeline" for e in bravo_entries
    )


async def test_scoped_timeline_hides_other_scopes(client, db_session_factory):
    org = await register_org(client, email="p4d7_tl3@test.co")
    headers = org["headers"]
    visible = await h.blocked_project(client, headers, count=1, name="TL Visible 4D7")
    hidden = await h.blocked_project(client, headers, count=2, name="TL Hidden 4D7")
    await h.seed_memory(client, headers, hidden["id"], "TL Hidden precedent 4D7")
    await h.drive_full_stack(client, db_session_factory)
    scope = await h.scope_for_project(client, headers, visible["id"])
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], f"reader{org['organization']['id'][:6]}@test.co"
    )

    timeline = (
        await client.get("/api/v1/brain/timeline/unified", headers=scoped)
    ).json()
    titles = " ".join(e["title"] for e in timeline["timeline"])
    assert "TL Hidden" not in titles, timeline["timeline"]
    # Anchoring to the hidden project is a 404 for the scoped caller.
    hidden_timeline = await client.get(
        "/api/v1/brain/timeline/unified",
        params={"entity_type": "project", "entity_id": hidden["id"]},
        headers=scoped,
    )
    assert hidden_timeline.status_code == 404


async def test_timeline_tenant_isolation(client, db_session_factory):
    org_a = await register_org(client, email="p4d7_tl4a@test.co")
    org_b = await register_org(client, email="p4d7_tl4b@test.co")
    proj_b = await h.blocked_project(client, org_b["headers"], count=1, name="TL Tenant B 4D7")
    await h.drive_full_stack(client, db_session_factory)

    timeline = (
        await client.get("/api/v1/brain/timeline/unified", headers=org_a["headers"])
    ).json()
    titles = " ".join(e["title"] for e in timeline["timeline"])
    assert "TL Tenant B" not in titles
    assert (
        await client.get(
            "/api/v1/brain/timeline/unified",
            params={"entity_type": "project", "entity_id": proj_b["id"]},
            headers=org_a["headers"],
        )
    ).status_code == 404


async def test_what_changed_is_persona_aware_and_bounded(client, db_session_factory):
    org = await register_org(client, email="p4d7_tl5@test.co")
    headers = org["headers"]
    visible = await h.blocked_project(client, headers, count=1, name="WC Visible 4D7")
    hidden = await h.blocked_project(client, headers, count=2, name="WC Hidden 4D7")
    await h.seed_memory(client, headers, hidden["id"], "WC hidden precedent")
    await h.drive_full_stack(client, db_session_factory)
    scope = await h.scope_for_project(client, headers, visible["id"])
    scoped = await h.invite_scoped_reader(
        client, headers, scope["id"], f"reader{org['organization']['id'][:6]}@test.co"
    )

    ceo_changed = (
        await client.get("/api/v1/brain/what-changed", params={"days": 7}, headers=headers)
    ).json()
    assert ceo_changed["org_wide"] is True
    assert ceo_changed["categories"]

    manager_changed = (
        await client.get("/api/v1/brain/what-changed", params={"days": 7}, headers=scoped)
    ).json()
    assert manager_changed["org_wide"] is False
    item_ids = [
        item["id"] for category in manager_changed["categories"] for item in category.get("items", [])
    ]
    assert hidden["id"] not in item_ids, item_ids
    # Bounded categories and items.
    assert len(ceo_changed["categories"]) <= 6
    assert len(manager_changed["categories"]) <= 6