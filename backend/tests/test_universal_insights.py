"""Slice 4D.5 — universal company insight intelligence.

Proves the change-driven insight composition pipeline end to end:

* execution-bottleneck insights form from repeated blocked tasks (via the
  4D.4 pattern layer) and consolidate per project (one insight, deduped key),
* evidence lineage is exactly-once and replay-safe (InsightEvent links +
  durable job uniqueness), replays never duplicate,
* confidence is compositional (bounded [0, 1]) with an explaining
  ``confidence_components`` map,
* governance: project-scoped insights are visible inside the scope only, a
  hidden insight is indistinguishable from a missing one (404),
* tenant isolation: organizations never see each other's insights,
* the /brain/insights API (list, get, evidence, history, related) respects
  access and status,
* reasoning answers surface evidence-backed insight claims,
* the pipeline is observational: no operating entity is ever mutated.

The pipeline is never a chatbot, dashboard, recommender or predictor: it only
needs patterns/memories/decisions/approvals — insights never invent facts.
"""

from sqlalchemy import select

from app.models.intelligence import (
    BackgroundJob,
    InsightEvent,
    PatternDetection,
    UniversalInsight,
)
from app.models.task import Task as TaskRow
from tests.conftest import register_org


async def _project(client, headers, name="Insight Project"):
    response = await client.post(
        "/api/v1/projects",
        json={"name": name, "description": "insight test", "status": "active"},
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


async def _decision(client, headers, project_id, title):
    response = await client.post(
        "/api/v1/decisions",
        json={
            "title": title,
            "project_id": project_id,
            "description": "insight pending decision",
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


async def _approval(client, headers, entity_type, entity_id, title):
    response = await client.post(
        "/api/v1/approvals",
        json={
            "title": title,
            "approval_type": "project",
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()

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


async def _run_insights(db_session_factory, limit=50, rounds=8):
    from app.workers import insight_worker

    total = 0
    for _ in range(rounds):
        async with db_session_factory() as session:
            processed = await insight_worker.run_once(db=session, limit=limit)
            await session.commit()
        total += processed
        if processed == 0:
            break
    return total


async def _insights(db, organization_id):
    return list(
        (
            await db.execute(
                select(UniversalInsight).where(
                    UniversalInsight.organization_id == organization_id
                )
            )
        ).scalars().all()
    )


async def _eval_jobs(db, organization_id):
    return list(
        (
            await db.execute(
                select(BackgroundJob).where(
                    BackgroundJob.name == "insight.evaluate",
                    BackgroundJob.organization_id == organization_id,
                )
            )
        ).scalars().all()
    )


async def _blocked_project(client, headers, *, count=3, name="Blocked Insight Project"):
    project = await _project(client, headers, name)
    for i in range(count):
        task = await _task(client, headers, project["id"], f"blocked task {i}")
        await _transition(client, headers, task["id"], "blocked")
    return project


async def _drive_full_stack(client, db_session_factory):
    """Events -> pattern evaluation -> pattern events -> insight evaluation."""
    await _drain_events(db_session_factory)
    await _run_patterns(db_session_factory)
    await _drain_events(db_session_factory)
    return await _run_insights(db_session_factory)


# ------------------------------------------------- 1. change-driven composition


async def test_execution_bottleneck_insight_forms_from_blocked_tasks(
    client, db_session_factory
):
    org = await register_org(client, email="p4d5_form@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers)

    processed = await _drive_full_stack(client, db_session_factory)
    assert processed >= 1

    async with db_session_factory() as db:
        rows = await _insights(db, org_id)
        bottlenecks = [
            row for row in rows if row.insight_type == "execution_bottleneck"
        ]
        assert len(bottlenecks) == 1  # consolidated into one project insight
        insight = bottlenecks[0]
        assert insight.key == f"project:{project['id']}"
        assert insight.auth_project_id == project["id"]
        assert insight.domain == "execution"
        assert insight.status == "active"
        assert insight.title
        assert insight.claim
        assert insight.summary
        assert 0.0 <= insight.confidence <= 1.0
        assert insight.confidence_components
        components = insight.confidence_components
        for key in (
            "occurrence_strength",
            "evidence_completeness",
            "pattern_confidence",
            "memory_corroboration",
            "recency",
        ):
            assert key in components, components
        # composition explains itself: weights present and bounded
        assert abs(
            sum(components["weights"].values()) - 1.0
        ) < 0.001
        assert insight.evidence_json
        supported = insight.supporting_pattern_ids
        assert supported  # composed from a real 4D.4 pattern
        assert insight.affected_entities
        assert {
            e.get("type") for e in insight.affected_entities
        }.issubset({"project", "decision", "task", "employee"})

        # Lineage: exactly-one link per feeding event.
        links = (
            await db.execute(
                select(InsightEvent).where(InsightEvent.insight_id == insight.id)
            )
        ).scalars().all()
        assert links
        assert len({link.event_id for link in links}) == len(links)

        jobs = await _eval_jobs(db, org_id)
        assert jobs and all(job.status == "done" for job in jobs)

    listed = (await client.get("/api/v1/brain/insights", headers=headers)).json()
    assert listed["insights"]
    listed_ids = {insight["id"] for insight in listed["insights"]}
    async with db_session_factory() as db:
        rows = await _insights(db, org_id)
    bottleneck_row = next(
        row for row in rows if row.insight_type == "execution_bottleneck"
    )
    assert bottleneck_row.id in listed_ids


# ----------------------------------------------------- 2. decision bottleneck


async def test_pending_decision_with_blocked_work_forms_decision_bottleneck(
    client, db_session_factory
):
    org = await register_org(client, email="p4d5_decision@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers, count=1, name="Decision Bottleneck Project")
    decision = await _decision(client, headers, project["id"], "approve extra budget")

    processed = await _drive_full_stack(client, db_session_factory)
    assert processed >= 1

    async with db_session_factory() as db:
        rows = await _insights(db, org_id)
        decision_insights = [
            row for row in rows if row.insight_type == "decision_bottleneck"
        ]
        assert decision_insights
        insight = decision_insights[0]
        assert decision["id"] in insight.key
        assert insight.severity in ("info", "warning", "critical")

    # The decision itself must NOT be mutated by insight work.
    async with db_session_factory() as db:
        from app.models.knowledge import Decision

        row = await db.get(Decision, decision["id"])
        assert row.status == "proposed"


# ----------------------------------------------------- 3. governance scoping


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
        json={"email": email, "full_name": "Scoped Insight Reader", "role": "employee"},
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    joined = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invited.json()["token"], "full_name": "Scoped Insight Reader", "password": "S4DPass123!"},
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
        json={"granted_to_user": user_id, "permission_code": "brain:read", "reason": "slice 4d.5 scoped insights"},
        headers=headers,
    )
    return scoped_headers


async def test_insight_governance_scoping(client, db_session_factory):
    org = await register_org(client, email="p4d5_gov@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]

    visible_project = await _blocked_project(
        client, headers, count=3, name="Visible Insight Project"
    )
    scope = await _scope_for_project(client, headers, visible_project["id"])
    hidden_project = await _blocked_project(
        client, headers, count=3, name="Hidden Insight Project"
    )
    await _drive_full_stack(client, db_session_factory)

    async with db_session_factory() as db:
        rows = await _insights(db, org_id)
    visible_insight = next(
        row for row in rows if row.auth_project_id == visible_project["id"]
    )
    hidden_insight = next(
        row for row in rows if row.auth_project_id == hidden_project["id"]
    )
    assert visible_insight.scope_type == "project"
    assert visible_insight.scope_id == scope["id"]
    assert hidden_insight.scope_type in ("org", "project")

    scoped_headers = await _invite_scoped_reader(
        client, headers, scope["id"], "p4d5_gov_u@test.co"
    )

    listed = (await client.get("/api/v1/brain/insights", headers=scoped_headers)).json()
    listed_ids = {insight["id"] for insight in listed["insights"]}
    assert visible_insight.id in listed_ids
    assert hidden_insight.id not in listed_ids

    shown = await client.get(
        f"/api/v1/brain/insights/{visible_insight.id}", headers=scoped_headers
    )
    assert shown.status_code == 200
    hidden = await client.get(
        f"/api/v1/brain/insights/{hidden_insight.id}", headers=scoped_headers
    )
    assert hidden.status_code == 404  # hidden is indistinguishable from missing

    hidden_evidence = await client.get(
        f"/api/v1/brain/insights/{hidden_insight.id}/evidence", headers=scoped_headers
    )
    assert hidden_evidence.status_code == 404


# ------------------------------------------------------- 4. existence of API


async def test_brain_insights_api_evidence_history_related(client, db_session_factory):
    org = await register_org(client, email="p4d5_api@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers, count=4, name="API Insight Project")

    await _drive_full_stack(client, db_session_factory)

    listed = (await client.get("/api/v1/brain/insights", headers=headers)).json()
    assert listed["insights"]
    insight = next(
        i for i in listed["insights"] if i["insight_type"] == "execution_bottleneck"
    )
    insight_id = insight["id"]

    got = await client.get(f"/api/v1/brain/insights/{insight_id}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == insight_id
    assert got.json()["claim"]
    assert got.json()["evidence"]
    assert got.json()["confidence_components"]

    evidence = await client.get(
        f"/api/v1/brain/insights/{insight_id}/evidence", headers=headers
    )
    assert evidence.status_code == 200, evidence.text
    types = {item["type"] for item in evidence.json()["evidence"]}
    assert types
    assert evidence.json()["supporting_pattern_ids"]

    history = await client.get(
        f"/api/v1/brain/insights/{insight_id}/history", headers=headers
    )
    assert history.status_code == 200, history.text
    assert len(history.json()["history"]) >= 1
    assert history.json()["status"] == "active"

    related = await client.get(
        f"/api/v1/brain/insights/{insight_id}/related", headers=headers
    )
    assert related.status_code == 200, related.text
    assert related.json()["insight_id"] == insight_id

    missing = await client.get(
        "/api/v1/brain/insights/does-not-exist", headers=headers
    )
    assert missing.status_code == 404


# ------------------------------------------------------- 6. tenant isolation


async def test_insights_are_tenant_isolated(client, db_session_factory):
    org_a = await register_org(client, email="p4d5_iso_a@test.co")
    org_b = await register_org(client, email="p4d5_iso_b@test.co")
    await _blocked_project(client, org_a["headers"], count=3, name="Isolated A Project")
    await _blocked_project(client, org_b["headers"], count=3, name="Isolated B Project")

    await _drive_full_stack(client, db_session_factory)

    async with db_session_factory() as db:
        rows_a = await _insights(db, org_a["organization"]["id"])
        rows_b = await _insights(db, org_b["organization"]["id"])
        assert rows_a and rows_b
        assert {
            row.organization_id for row in rows_a
        } == {org_a["organization"]["id"]}
        assert {
            row.organization_id for row in rows_b
        } == {org_b["organization"]["id"]}
        assert not ({r.id for r in rows_a} & {r.id for r in rows_b})

    listed_a = (
        await client.get("/api/v1/brain/insights", headers=org_a["headers"])
    ).json()
    assert listed_a["insights"]
    ids_a = {insight["id"] for insight in listed_a["insights"]}
    assert len(ids_a) == len(rows_a)


# ------------------------------------------------------- 7. exactly-once replay


async def test_insight_evaluation_is_exactly_once_across_replays(
    client, db_session_factory
):
    org = await register_org(client, email="p4d5_idem@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    await _blocked_project(client, headers)

    await _drive_full_stack(client, db_session_factory)

    async with db_session_factory() as db:
        first = await _insights(db, org_id)
        bottleneck = next(
            row for row in first if row.insight_type == "execution_bottleneck"
        )
        first_evidence = len(bottleneck.evidence_json or [])
        first_links = len(
            (
                await db.execute(
                    select(InsightEvent).where(InsightEvent.insight_id == bottleneck.id)
                )
            ).scalars().all()
        )
    assert first_evidence >= 1

    # Replaying the same events must never duplicate evidence or links.
    await _drive_full_stack(client, db_session_factory)

    async with db_session_factory() as db:
        rows = await _insights(db, org_id)
        bottleneck = next(
            row for row in rows if row.insight_type == "execution_bottleneck"
        )
        links = (
            await db.execute(
                select(InsightEvent).where(InsightEvent.insight_id == bottleneck.id)
            )
        ).scalars().all()
        assert len(links) == first_links
        # the same insight row (no duplicate), evidence did not grow from replay
        assert len(bottleneck.evidence_json or []) == first_evidence
        assert len(rows) == 1  # no duplicate insight rows created


# ------------------------------------------------------- 8. observational only


async def test_insight_work_never_mutates_operating_tables(client, db_session_factory):
    org = await register_org(client, email="p4d5_mut@test.co")
    headers = org["headers"]
    org_id = org["organization"]["id"]
    project = await _blocked_project(client, headers, count=3)
    tasks_before = []
    async with db_session_factory() as db:
        tasks_before = list(
            (
                await db.execute(
                    select(TaskRow).where(
                        TaskRow.organization_id == org_id,
                        TaskRow.project_id == project["id"],
                    )
                )
            ).scalars().all()
        )
        statuses_before = [(t.id, t.status) for t in tasks_before]

    await _drive_full_stack(client, db_session_factory)

    async with db_session_factory() as db:
        tasks_after = list(
            (
                await db.execute(
                    select(TaskRow).where(
                        TaskRow.organization_id == org_id,
                        TaskRow.project_id == project["id"],
                    )
                )
            ).scalars().all()
        )
        assert [(t.id, t.status) for t in tasks_after] == statuses_before
        patterns = list(
            (
                await db.execute(
                    select(PatternDetection).where(
                        PatternDetection.organization_id == org_id
                    )
                )
            ).scalars().all()
        )
        assert patterns  # patterns exist (composed, not invented by insights)
        insights = await _insights(db, org_id)
        assert insights
        # nothing besides pattern/intelligence tables was written by this test's
        # insight passes — approvals/decisions untouched (no rows created)
        from app.models.approval import Approval

        approvals = (
            await db.execute(
                select(Approval).where(Approval.organization_id == org_id)
            )
        ).scalars().all()
        assert approvals == []


# ------------------------------------------------------- 9. reasoning claims


async def test_reasoning_answers_surface_insight_claims(client, db_session_factory):
    org = await register_org(client, email="p4d5_claim@test.co")
    headers = org["headers"]
    await _blocked_project(client, headers, count=3, name="Claim Insight Project")

    await _drive_full_stack(client, db_session_factory)

    answer = (
        await client.post(
            "/api/v1/brain/answer",
            json={"question": "what is happening in this organization right now?"},
            headers=headers,
        )
    ).json()
    insight_claims = [
        claim for claim in answer["claims"] if claim.get("kind") == "insight"
    ]
    assert insight_claims, answer["claims"]
    for claim in insight_claims:
        assert claim["evidence"]
        assert claim["evidence"][0]["type"] == "insight"
        assert claim["evidence"][0]["url"].startswith("/brain/insights/")
        assert claim["severity"] in ("info", "warning", "critical")