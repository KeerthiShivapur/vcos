"""Slice 4D.4 — universal organizational pattern intelligence.

Proves the change-driven pattern pipeline end to end:

* repeated-delay patterns form from task.blocked / blocked transitions and
  consolidate per project (one pattern, N occurrences),
* a single occurrence is never a pattern (observation buffer is invisible),
* evaluation is exactly-once and replay-safe (PatternEvent lineage links +
  durable job uniqueness),
* governance: project-scoped patterns are visible inside the scope only and
  a hidden pattern is indistinguishable from a missing one (404),
* the /brain/patterns API (list, get, evidence, history, status update)
  respects the lifecycle and the caller's access,
* reasoning answers surface evidence-backed pattern claims.

The pipeline is observational: operating entities are never mutated by
pattern work.
"""

from sqlalchemy import select

from app.models.intelligence import BackgroundJob, PatternDetection, PatternEvent
from tests.conftest import register_org


async def _project(client, headers, name="Pattern Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "pattern test", "status": "active"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _task(client, headers, project_id, title):
    response = await client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": project_id, "status": "todo"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(client, headers, task_id, status):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"status": status}, headers=headers
    )
    assert response.status_code == 200, response.text


async def _block(client, headers, task_id, blocker_id):
    response = await client.post(
        f"/api/v1/tasks/{task_id}/dependencies",
        json={"depends_on_task_id": blocker_id, "kind": "finish_to_start"},
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def _drain_events(db_session_factory, rounds=10):
    from app.events.event_bus import event_bus

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await event_bus.process_pending(session, limit=200)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _run_patterns(db_session_factory, limit=50, rounds=8):
    from app.workers import pattern_worker

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await pattern_worker.run_once(db=session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _patterns(db, organization_id):
    return list(
        (
            await db.execute(
                select(PatternDetection).where(
                    PatternDetection.organization_id == organization_id
                )
            )
        ).scalars().all()
    )


async def _eval_jobs(db, organization_id):
    return list(
        (
            await db.execute(
                select(BackgroundJob).where(
                    BackgroundJob.name == "pattern.evaluate",
                    BackgroundJob.organization_id == organization_id,
                )
            )
        ).scalars().all()
    )


async def _blocked_project(client, headers, *, count=3, name="Blocked Project"):
    """A project with `count` tasks transitioned to blocked (no deps needed:

    the transition itself emits a blocked-status event)."""
    project = await _project(client, headers, name)
    await _block_tasks_in(client, headers, project["id"], count=count)
    return project


async def _block_tasks_in(client, headers, project_id, *, count=3):
    for i in range(count):
        task = await _task(client, headers, project_id, f"blocked task {i}")
        await _transition(client, headers, task["id"], "blocked")


# --------------------------------------------------------- 1. change-driven form


async def test_blocked_tasks_form_consolidated_repeated_delay_pattern(
    client, db_session_factory
):
    org = await register_org(client, email="p4d4_form@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers)

    await _drain_events(db_session_factory)
    processed = await _run_patterns(db_session_factory)
    assert processed >= 1

    async with db_session_factory() as db:
        rows = await _patterns(db, org_id)
        delays = [row for row in rows if row.pattern_type == "repeated_delay"]
        assert len(delays) == 1  # consolidated into one project pattern
        pattern = delays[0]
        assert pattern.count == 3
        assert pattern.family == "execution"
        assert pattern.status in ("candidate", "emerging", "confirmed", "persistent")
        assert pattern.key == f"project:{project['id']}"
        assert pattern.scope_type == "org"
        assert pattern.confidence >= 0.3

        # Lineage: every occurrence is traceable to its event.
        links = (
            await db.execute(
                select(PatternEvent).where(PatternEvent.pattern_id == pattern.id)
            )
        ).scalars().all()
        assert len(links) == 3
        assert {link.relationship for link in links} == {"occurrence"}
        assert len(pattern.supporting_event_ids) == 3
        event_evidence = [
            item for item in (pattern.evidence_json or []) if item.get("type") == "event"
        ]
        assert len(event_evidence) == 3

        jobs = await _eval_jobs(db, org_id)
        assert jobs and all(job.status == "done" for job in jobs)

    listed = (await client.get("/api/v1/brain/patterns", headers=headers)).json()
    assert listed["patterns"]
    listed_ids = {p["id"] for p in listed["patterns"]}
    async with db_session_factory() as db:
        rows = await _patterns(db, org_id)
    assert next(p.id for p in rows if p.pattern_type == "repeated_delay") in listed_ids


# ------------------------------------------------------- 2. one event, no pattern


async def test_single_occurrence_is_never_a_pattern(client, db_session_factory):
    org = await register_org(client, email="p4d4_one@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _blocked_project(client, headers, count=1, name="Lone Blocked Project")

    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    async with db_session_factory() as db:
        rows = await _patterns(db, org_id)
    assert len(rows) == 1  # observation buffer exists...
    assert rows[0].count == 1
    assert rows[0].status == "candidate"

    listed = (await client.get("/api/v1/brain/patterns", headers=headers)).json()
    assert listed["patterns"] == []  # ...but it is never surfaced


# ------------------------------------------------------------- 3. exactly once


async def test_evaluation_is_exactly_once_across_replays(client, db_session_factory):
    org = await register_org(client, email="p4d4_idem@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _blocked_project(client, headers)

    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    async with db_session_factory() as db:
        first = await _patterns(db, org_id)
        delay = next(p for p in first if p.pattern_type == "repeated_delay")
        first_count = delay.count
        first_links = len(
            (
                await db.execute(
                    select(PatternEvent).where(PatternEvent.pattern_id == delay.id)
                )
            ).scalars().all()
        )
    assert first_count == 3

    # Replaying the same events must never double-count.
    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    async with db_session_factory() as db:
        rows = await _patterns(db, org_id)
        delay = next(p for p in rows if p.pattern_type == "repeated_delay")
        assert delay.count == first_count == 3
        links = (
            await db.execute(
                select(PatternEvent).where(PatternEvent.pattern_id == delay.id)
            )
        ).scalars().all()
        assert len(links) == first_links == 3


# ------------------------------------------------------------- 4. brain API


async def test_brain_patterns_api_evidence_history_and_status(
    client, db_session_factory
):
    org = await register_org(client, email="p4d4_api@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers, count=4, name="API Project")

    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    listed = (await client.get("/api/v1/brain/patterns", headers=headers)).json()
    assert listed["patterns"]
    pattern = next(
        p for p in listed["patterns"] if p["pattern_type"] == "repeated_delay"
    )
    pattern_id = pattern["id"]

    got = await client.get(f"/api/v1/brain/patterns/{pattern_id}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["count"] == 4
    assert got.json()["status"] in ("confirmed", "emerging", "persistent")

    evidence = await client.get(
        f"/api/v1/brain/patterns/{pattern_id}/evidence", headers=headers
    )
    assert evidence.status_code == 200, evidence.text
    event_items = [e for e in evidence.json()["evidence"] if e["type"] == "event"]
    assert len(event_items) >= 4

    history = await client.get(
        f"/api/v1/brain/patterns/{pattern_id}/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert len(history.json()["history"]) >= 4
    assert history.json()["occurrence_count"] == 4

    related = await client.get(
        f"/api/v1/brain/patterns/{pattern_id}/related", headers=headers
    )
    assert related.status_code == 200, related.text
    assert related.json()["pattern_id"] == pattern_id

    # Legacy Phase 9 surface still works on the same table while the pattern
    # is active ("open" maps to the 4D.4 active lifecycle statuses).
    legacy = (await client.get("/api/v1/intelligence/patterns", headers=headers)).json()
    assert legacy

    updated = await client.patch(
        f"/api/v1/brain/patterns/{pattern_id}",
        json={"status": "acknowledged"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "acknowledged"

    missing = await client.get(
        "/api/v1/brain/patterns/does-not-exist", headers=headers
    )
    assert missing.status_code == 404


# ------------------------------------------------------------- 5. governance


async def _scope_for_project(client, headers, project_id):
    return (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": f"Scope {project_id}", "scope_type": "project", "entity_id": project_id},
            headers=headers,
        )
    ).json()


async def _invite_scoped_reader(client, headers, scope_id, email):
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(role for role in roles if role["code"] == "manager")
    invited = await client.post(
        "/api/v1/users/invite",
        json={"email": email, "full_name": "Scoped Pattern Reader", "role": "employee"},
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invited.json()["token"], "full_name": "Scoped Pattern Reader", "password": "S4DPass123!"},
    )
    assert joined.status_code == 201, joined.text
    scoped_headers = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    user_id = joined.json()["user"]["id"]
    await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": user_id, "role_id": manager_role["id"], "scope_id": scope_id},
        headers=headers,
    )
    assignments = (
        await client.get("/api/v1/governance/assignments", params={"user_id": user_id}, headers=headers)
    ).json()
    org_wide = next(assignment for assignment in assignments if assignment["scope_id"] is None)
    await client.delete(f"/api/v1/governance/assignments/{org_wide['id']}", headers=headers)
    await client.post(
        "/api/v1/governance/delegations",
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "slice 4d.4 scoped patterns"},
        headers=headers,
    )
    return scoped_headers


async def test_pattern_governance_scoping(client, db_session_factory):
    org = await register_org(client, email="p4d4_gov@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    visible_project = await _project(client, headers, "Visible Pattern Project")
    scope = await _scope_for_project(client, headers, visible_project["id"])
    hidden_project = await _project(client, headers, "Hidden Pattern Project")
    await _block_tasks_in(client, headers, visible_project["id"], count=3)
    await _block_tasks_in(client, headers, hidden_project["id"], count=3)
    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    async with db_session_factory() as db:
        rows = await _patterns(db, org_id)
    visible_pattern = next(p for p in rows if p.key == f"project:{visible_project['id']}")
    hidden_pattern = next(p for p in rows if p.key == f"project:{hidden_project['id']}")
    assert visible_pattern.scope_type == "project"
    assert hidden_pattern.scope_type == "org"

    scoped_headers = await _invite_scoped_reader(
        client, headers, scope["id"], "p4d4_gov_u@test.co"
    )

    listed = (await client.get("/api/v1/brain/patterns", headers=scoped_headers)).json()
    listed_ids = {p["id"] for p in listed["patterns"]}
    assert visible_pattern.id in listed_ids
    assert hidden_pattern.id not in listed_ids

    shown = await client.get(
        f"/api/v1/brain/patterns/{visible_pattern.id}", headers=scoped_headers
    )
    assert shown.status_code == 200
    hidden = await client.get(
        f"/api/v1/brain/patterns/{hidden_pattern.id}", headers=scoped_headers
    )
    assert hidden.status_code == 404  # hidden is indistinguishable from missing

    hidden_evidence = await client.get(
        f"/api/v1/brain/patterns/{hidden_pattern.id}/evidence", headers=scoped_headers
    )
    assert hidden_evidence.status_code == 404


# ------------------------------------------------------------- 6. reasoning


async def test_reasoning_answers_surface_pattern_claims(client, db_session_factory):
    org = await register_org(client, email="p4d4_claim@test.co")
    headers = org["headers"]
    await _blocked_project(client, headers, count=3, name="Claim Project")

    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "why do delays keep recurring in this organization?"},
            headers=headers,
        )
    ).json()
    pattern_claims = [
        claim for claim in answer["claims"] if claim.get("kind") == "pattern"
    ]
    assert pattern_claims, answer["claims"]
    assert any("recurring pattern" in claim["claim"].lower() for claim in pattern_claims)
    for claim in pattern_claims:
        assert claim["evidence"]
        assert claim["evidence"][0]["type"] == "pattern"
        assert claim["evidence"][0]["url"].startswith("/brain/patterns/")
