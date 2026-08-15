"""Slice 4F.3 — legacy skill-id bridge (profile -> canonical trust)."""

import pytest

from tests import _brain4d6_helpers as h
from tests.conftest import register_org

BRAIN = "/api/v1/brain"


async def _hire(client, headers, email, first, last):
    created = await client.post("/api/v1/employees",
                                json={"first_name": first, "last_name": last,
                                      "email": email}, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


@pytest.mark.asyncio
async def test_profile_skill_id_resolves_to_canonical_trust(client, db_session):
    from app.intelligence.expertise_engine import expertise_engine
    from app.models.skill import ExpertiseScore, Skill
    from sqlalchemy import select

    org = await register_org(client, email="4f3_legacy_bridge@test.co")
    headers = org["headers"]
    person = await _hire(client, headers, "4f3-bridge@test.co", "Ana", "Lin")

    await expertise_engine.record_evidence(
        db_session, organization_id=org["organization"]["id"],
        employee_id=person["id"], event_name="task.completed",
        tokens=["python"], source_type="task", source_id="task-bridge-1",
    )
    await db_session.commit()

    # The profile surface is powered by the legacy mirror (ExpertiseScore rows
    # keyed on the phase-2 Skills table) — grab THAT skill id, not the engine's.
    profile = (
        await client.get(
            f"{BRAIN}/people/{person['id']}/expertise", headers=headers)).json()
    cells = profile["expertise"]
    assert cells, "expertise must be visible for the seeded person"
    canonical = cells[0]["skill_id"]

    legacy_rows = (
        await db_session.execute(
            select(ExpertiseScore).where(
                ExpertiseScore.employee_id == person["id"])
        )
    ).scalars().all()
    assert legacy_rows, "the legacy mirror must have written profile scores"
    legacy_id = legacy_rows[0].skill_id

    legacy = await db_session.get(Skill, legacy_id)
    assert legacy is not None and legacy.name.lower() == "python", (
        "the mirror must create the legacy skill row itself")

    for sid in {canonical, legacy_id}:
        resp = await client.get(
            f"{BRAIN}/people/{person['id']}/expertise/{sid}/trust",
            headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["skill_name"] == "Python"