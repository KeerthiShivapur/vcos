"""Slice 4F.6 — capability lifecycle & preserved history.

Lifecycle is a deterministic, evidence-backed state machine. Under test:

* unknown -> emerging -> established -> strong -> strategic with evidence,
* declining when current activity is well below recent history,
* dormant when the capability has no fresh evidence,
* every transition preserves a monthly CapabilityHistory snapshot
  (history is never destroyed).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.org_capability_intelligence import CapabilityHistory, OrgCapability
from app.models.skills_intelligence import CanonicalSkill, Expertise
from tests.conftest import register_org

BRAIN = "/api/v1/brain"


async def _drain(db_session_factory, limit=200, rounds=4):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _hire(client, headers, email, first, last):
    body = {"first_name": first, "last_name": last, "email": email}
    created = await client.post("/api/v1/employees", json=body, headers=headers)
    assert created.status_code in (200, 201), created.text
    return created.json()


async def _skill_id(db, org_id, name):
    from app.people.skill_engine import skill_engine

    await skill_engine.ensure_taxonomy(db, organization_id=org_id)
    row = (
        await db.execute(
            select(CanonicalSkill.id).where(
                CanonicalSkill.organization_id == org_id,
                CanonicalSkill.canonical_name == name,
            )
        )
    ).scalar_one_or_none()
    assert row is not None, f"starter taxonomy must include {name}"
    return row


async def _set_cell(db, org_id, person_id, skill_id, score, evidence,
                    lifecycle="established", last_observed=None,
                    successful=0, failed=0):
    cell = (
        await db.execute(
            select(Expertise).where(
                Expertise.organization_id == org_id,
                Expertise.person_id == person_id,
                Expertise.skill_id == skill_id,
            )
        )
    ).scalar_one_or_none()
    if cell is None:
        cell = Expertise(
            organization_id=org_id, person_id=person_id, skill_id=skill_id,
        )
        db.add(cell)
    cell.score = score
    cell.evidence_count = evidence
    cell.lifecycle = lifecycle
    cell.successful_count = successful
    cell.failed_count = failed
    cell.last_observed = last_observed or datetime.now(timezone.utc)
    cell.frequency_90d = evidence
    return cell


async def _refresh(client, db_session_factory, org_id, actor_id, skill_id):
    from app.events.event_bus import event_bus

    async with db_session_factory() as db:
        await event_bus.publish(
            db, name="skill.updated", organization_id=org_id, actor_id=actor_id,
            payload={"skill_id": skill_id}, enqueue=True, flush=False,
        )
        await db.commit()
    await _drain(db_session_factory)


async def _row(client, headers, skill_id):
    res = await client.get(f"{BRAIN}/capabilities/{skill_id}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------- lifecycle


async def test_lifecycle_climbs_with_evidence(client, db_session_factory):
    org = await register_org(client, email="4f6_life@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    p1 = await _hire(client, headers, "4f6-l1@test.co", "Jean", "Bartik")
    p2 = await _hire(client, headers, "4f6-l2@test.co", "Mary", "Jackson")
    p3 = await _hire(client, headers, "4f6-l3@test.co", "Annie", "Easley")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Distributed Systems")
        await _set_cell(db, org_id, p1["id"], skill_id, 55.0, 2)
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] == "emerging", detail["explain"]
    assert detail["expert_count"] == 1

    # second expert + more evidence -> established
    async with db_session_factory() as db:
        await _set_cell(db, org_id, p2["id"], skill_id, 60.0, 3,
                        lifecycle="established")
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] in ("established", "strong"), detail["explain"]
    assert detail["expert_count"] == 2

    # two strong cells with big evidence -> strong
    async with db_session_factory() as db:
        for person_id, evidence in ((p1["id"], 12), (p2["id"], 11)):
            await _set_cell(db, org_id, person_id, skill_id, 82.0, evidence,
                            lifecycle="strong", successful=evidence)
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] == "strong", detail["explain"]
    assert detail["strong_expert_count"] >= 2
    assert detail["confidence"] > 0.5
    assert detail["outcome_ratio"] is not None

    # three strong cells + 30+ evidence -> strategic
    async with db_session_factory() as db:
        await _set_cell(db, org_id, p3["id"], skill_id, 85.0, 14,
                        lifecycle="strong", successful=14)
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] == "strategic", detail["explain"]
    assert detail["strong_expert_count"] >= 3
    assert detail["evidence_count"] >= 30


async def test_lifecycle_declines_and_archives_history(client, db_session_factory):
    org = await register_org(client, email="4f6_decl@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-dd1@test.co", "Radia", "Perlman")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Machine Learning")
        await _set_cell(db, org_id, person["id"], skill_id, 72.0, 6,
                        lifecycle="strong", successful=6)
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] in ("strong", "established")

    # simulate a hot previous month, then a quiet current month: set the
    # capability row as if last month carried high points, then refresh with
    # no new evidence -> the engine archives last month and marks decline.
    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == org_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
        ).scalar_one()
        now = datetime.now(timezone.utc)
        if now.month == 1:
            prev_key = f"{now.year - 1}-12"
        else:
            prev_key = f"{now.year}-{now.month - 1:02d}"
        row.month_key = prev_key
        row.points_cur_month = 10.0
        row.points_prev_month = 2.0
        await db.commit()

    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] == "declining", detail["explain"]

    async with db_session_factory() as db:
        history = list(
            (
                await db.execute(
                    select(CapabilityHistory).where(
                        CapabilityHistory.organization_id == org_id,
                        CapabilityHistory.skill_id == skill_id,
                    )
                )
            ).scalars().all()
        )
    assert any(
        h.month_key == prev_key and h.points == 10.0 for h in history
    ), [(h.month_key, h.points) for h in history]


async def test_stale_evidence_goes_dormant(client, db_session_factory):
    org = await register_org(client, email="4f6_dorm@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-dm@test.co", "Barbara", "Liskov")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Kubernetes")
        await _set_cell(
            db, org_id, person["id"], skill_id, 70.0, 8,
            lifecycle="strong", successful=8,
            last_observed=datetime.now(timezone.utc) - timedelta(days=400),
        )
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert detail["lifecycle"] == "dormant", detail["explain"]


async def test_history_is_never_destroyed(client, db_session_factory):
    org = await register_org(client, email="4f6_hist@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    person = await _hire(client, headers, "4f6-hs@test.co", "Alan", "Kay")

    async with db_session_factory() as db:
        skill_id = await _skill_id(db, org_id, "Python")
        await _set_cell(db, org_id, person["id"], skill_id, 60.0, 5)
        await db.commit()
    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)

    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == org_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
        ).scalar_one()
        now = datetime.now(timezone.utc)
        if now.month == 1:
            prev_key = f"{now.year - 1}-12"
        else:
            prev_key = f"{now.year}-{now.month - 1:02d}"
        row.month_key = prev_key
        row.points_cur_month = 4.0
        row.points_prev_month = 6.0
        await db.commit()

    await _refresh(client, db_session_factory, org_id, org["user"]["id"], skill_id)
    detail = await _row(client, headers, skill_id)
    assert any(h["month"] == prev_key for h in detail["history"]), detail["history"]
    snapshot = next(h for h in detail["history"] if h["month"] == prev_key)
    assert snapshot["evidence_count"] >= 5
    assert snapshot["lifecycle"] in docstring_states()
    # current month record exists as well (still live)
    assert len(detail["history"]) >= 1


def docstring_states():
    return ("unknown", "emerging", "established", "strong", "strategic",
            "declining", "dormant")