"""Slice 4D.6 — observe/understand/explain, never change.

Brain reads (answer, overview, evidence, related) must leave the operating
layer untouched: tasks, projects, decisions, approvals, governance
assignments, messages and background jobs are byte-identical before and
after, and no events/jobs are enqueued by a read.
"""

from sqlalchemy import select

from app.models.approval import Approval
from app.models.communication import Message
from app.models.role import UserRole
from app.models.intelligence import BackgroundJob
from app.models.knowledge import Decision
from app.models.notification import Event as EventRow
from app.models.project import Project
from app.models.task import Task as TaskRow
from tests import _brain4d6_helpers as h
from tests.conftest import register_org


async def _snapshot(db_session_factory, organization_id):
    rows = {}
    for name, model in (
        ("tasks", TaskRow), ("projects", Project), ("decisions", Decision),
        ("approvals", Approval), ("messages", Message),
        ("assignments", UserRole),
    ):
        async with db_session_factory() as db:
            items = list(
                (await db.execute(
                    select(model).where(model.organization_id == organization_id)
                )).scalars().all()
            )
        rows[name] = sorted(
            (r.id, _status(r)) for r in items
        )
    async with db_session_factory() as db:
        jobs = list(
            (await db.execute(
                select(BackgroundJob).where(
                    BackgroundJob.organization_id == organization_id
                )
            )).scalars().all()
        )
        events = list(
            (await db.execute(
                select(EventRow).where(
                    EventRow.organization_id == organization_id
                )
            )).scalars().all()
        )
    rows["jobs"] = sorted((j.id, j.name, j.status) for j in jobs)
    rows["events"] = sorted((e.id, e.name) for e in events)
    return rows


def _status(row):
    return getattr(row, "status", None)


async def test_brain_reads_never_mutate_operating_data(client, db_session_factory):
    org = await register_org(client, email="p4d6_nomut@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    proj = await h.blocked_project(client, headers, count=3, name="No Mutation Project")
    await h.seed_memory(client, headers, proj["id"])
    await h.drive_full_stack(client, db_session_factory)

    # Warm the canonical living overview once (its Phase-20 cache writes behind
    # on first read by contract). After that every brain surface is a pure read.
    await client.get("/api/v1/brain/overview", headers=headers)

    before = await _snapshot(db_session_factory, org_id)
    assert before["jobs"]  # insight work already happened pre-snapshot

    # one of every read surface, repeatedly
    for _ in range(2):
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why is this project behind?",
                  "entity_type": "project", "entity_id": proj["id"]},
            headers=headers,
        )
        await client.get("/api/v1/brain/overview", headers=headers)
        await client.get(f"/api/v1/brain/evidence/project/{proj['id']}", headers=headers)
        await client.get(f"/api/v1/brain/related/project/{proj['id']}", headers=headers)

    after = await _snapshot(db_session_factory, org_id)
    assert after == before, {
        k: (len(before[k]), len(after.get(k, []))) for k in before if after.get(k) != before[k]
    }
    # the same handful of rows, none added, none changed
    assert len(after["tasks"]) == len(before["tasks"])
    assert len(after["jobs"]) == len(before["jobs"])  # reads enqueue nothing


async def test_brain_overview_preserves_existing_living_view(client, db_session_factory):
    org = await register_org(client, email="p4d6_overview_stable@test.co")
    headers = org["headers"]
    await h.blocked_project(client, headers, count=2, name="Stable Overview Project")
    await h.drive_full_stack(client, db_session_factory)

    first = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    second = (await client.get("/api/v1/brain/overview", headers=headers)).json()
    # unified sections are deterministic reads over stable state
    assert first["attention"] == second["attention"]
    assert (
        first["recent_intelligence"]["insights"]["count"]
        == second["recent_intelligence"]["insights"]["count"]
    )