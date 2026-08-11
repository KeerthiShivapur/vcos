"""Slice 4D.1 — change-driven consumers over the durable event bus.

Operating events (messaging.*, governance.*) must trigger a bounded,
idempotent refresh of the affected entity's company evidence: graph edges +
CompanyInsight freshness. Handlers never commit on their own and are safe to
retry (unique-key upserts).
"""

from sqlalchemy import func, select

from app.events.event_bus import event_bus
from app.models.intelligence import CompanyInsight, OrgGraphEdge
from tests.conftest import register_org


async def _drain(db_session_factory, limit=50):
    async with db_session_factory() as session:
        processed = await event_bus.process_pending(session, limit=limit)
        await session.commit()
        return processed


async def _company_insight_rows(db, org_id):
    return (
        await db.execute(
            select(CompanyInsight).where(CompanyInsight.organization_id == org_id)
        )
    ).scalars().all()


async def test_message_event_refreshes_conversation_evidence(client, db_session_factory):
    org = await register_org(client, email="s4d_events_msg@test.co")
    headers = org["headers"]
    me = (await client.get("/api/v1/employees/me", headers=headers)).json()["id"]
    conversation = (
        await client.post(
            "/api/v1/conversations",
            json={"type": "channel", "title": "ops-room", "member_ids": [me]},
            headers=headers,
        )
    ).json()
    message = (
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"content": "Rollback window confirmed"},
            headers=headers,
        )
    ).json()

    processed = await _drain(db_session_factory, limit=50)
    assert processed >= 1  # messaging.message_sent consumed

    async with db_session_factory() as db:
        edge = (
            await db.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == org["organization"]["id"],
                    OrgGraphEdge.source_type == "conversation",
                    OrgGraphEdge.source_id == conversation["id"],
                    OrgGraphEdge.target_type == "message",
                    OrgGraphEdge.target_id == message["id"],
                )
            )
        ).scalar_one_or_none()
        assert edge is not None and edge.relation == "contains"

        insights = await _company_insight_rows(db, org["organization"]["id"])
        assert any(
            i.entity_type == "conversation" and i.entity_id == conversation["id"]
            and i.reason == "messaging.message_sent"
            for i in insights
        )

        await _drain(db_session_factory, limit=50)  # no new events
        again = await _company_insight_rows(db, org["organization"]["id"])
        assert len(again) == len(insights)  # idempotent: no duplicate rows

        count = (
            await db.execute(
                select(func.count()).select_from(CompanyInsight).where(
                    CompanyInsight.organization_id == org["organization"]["id"],
                    CompanyInsight.entity_type == "conversation",
                    CompanyInsight.entity_id == conversation["id"],
                )
            )
        ).scalar_one()
        assert count == 1  # unique upsert


async def test_scope_event_refreshes_scope_insight(client, db_session_factory):
    org = await register_org(client, email="s4d_events_scope@test.co")
    headers = org["headers"]
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Scoped Ops", "description": "scope events", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Scoped Ops", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()

    processed = await _drain(db_session_factory, limit=50)
    assert processed >= 1  # governance.scope.created consumed

    async with db_session_factory() as db:
        insights = await _company_insight_rows(db, org["organization"]["id"])
        scope_insight = next(
            (i for i in insights if i.entity_type == "scope" and i.entity_id == scope["id"]), None
        )
        assert scope_insight is not None
        assert scope_insight.reason == "governance.scope.created"
        assert scope_insight.title == "Scoped Ops"
        assert scope_insight.status == "project"


async def test_assignment_event_touches_scope_insight(client, db_session_factory):
    org = await register_org(client, email="s4d_events_assign@test.co")
    headers = org["headers"]
    invite = await client.post(
        "/api/v1/users/invite",
        json={"email": "s4d_events_assign_u@test.co", "full_name": "Assignee", "role": "employee"},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    registered = await client.post(
        "/api/v1/auth/register/invite",
        json={"token": invite.json()["token"], "full_name": "Assignee", "password": "S4DPass123!"},
    )
    assert registered.status_code == 201, registered.text
    user = registered.json()["user"]

    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Assigned Ops", "description": "assignment", "status": "active"},
            headers=headers,
        )
    ).json()
    scope = (
        await client.post(
            "/api/v1/governance/scopes",
            json={"name": "Assigned Ops", "scope_type": "project", "entity_id": project["id"]},
            headers=headers,
        )
    ).json()
    roles = (await client.get("/api/v1/roles", headers=headers)).json()
    manager_role = next(r for r in roles if r["code"] == "manager")
    assigned = await client.post(
        "/api/v1/governance/assignments",
        json={"user_id": user["id"], "role_id": manager_role["id"], "scope_id": scope["id"]},
        headers=headers,
    )
    assert assigned.status_code == 201, assigned.text

    processed = await _drain(db_session_factory, limit=50)
    assert processed >= 1  # governance.assignment.created consumed

    async with db_session_factory() as db:
        scope_insight = (
            await db.execute(
                select(CompanyInsight).where(
                    CompanyInsight.organization_id == org["organization"]["id"],
                    CompanyInsight.entity_type == "scope",
                    CompanyInsight.entity_id == scope["id"],
                )
            )
        ).scalar_one_or_none()
        assert scope_insight is not None
        assert scope_insight.reason in ("governance.scope.created", "governance.assignment.created")