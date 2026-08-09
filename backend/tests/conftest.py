"""PyTest configuration.

Tests run against an isolated SQLite database (in-memory) so the suite is
fully hermetic — no external Postgres or Redis required. The same test
scenarios validate the multi-tenant + RBAC invariants that Postgres enforces
in production.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EMAIL_TRANSPORT"] = "console"
os.environ["AI_PROVIDER"] = "none"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["APP_ENV"] = "test"

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.db.database import Base  # noqa: E402
from app import models  # noqa: E402, F401


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402


@pytest.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


@pytest.fixture
async def app_factory(engine):
    """FastAPI app wired to the isolated test database."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from app.api.v1 import (
        academy,
        accounts,
        agents,
        ai,
        ai_actions,
        ai_memory,
        ai_predictions,
        ai_planning,
        ai_recommendations,
        ai_search,
        ai_voice,
        analytics,
        approvals,
        assets,
        assessments,
        attendance,
        audit,
        auth,
        autonomy,
        automation,
        calendar,
        career,
        certifications,
        collaboration_intel,
        collaboration_live,
        compliance,
        contracts,
        contacts,
        courses,
        customers,
        dashboard,
        decisions,
        departments,
        developers,
        digital_twin,
        documents,
        employees,
        enterprise,
        events,
        exec_health,
        exec_predictions,
        exec_recommendations,
        exec_reports,
        exec_risks,
        exec_simulations,
        exec_strategy,
        executive,
        execution,
        expertise,
        extensions,
        finance,
        goals,
        health,
        hr,
        industry,
        infrastructure,
        insights,
        intelligence,
        intelligence_briefs,
        knowledge,
        leads,
        learning,
        learning_paths,
        leave,
        meeting_intel,
        meeting_rooms,
        meetings,
        memory,
        mentorship,
        notifications,
        offboarding,
        onboarding,
        opportunities,
        organization,
        organizations,
        partners,
        payroll,
        performance,
        policies,
        portal,
        posts,
        prediction,
        presence,
        projects,
        recording_library,
        recordings,
        recommendations,
        recruitment,
        risks,
        roles,
        search,
        skills,
        sops,
        support,
        tasks,
        teams,
        templates,
        users,
        wellbeing,
        webhooks,
        wiki,
        workforce,
        workload,
        workspace,
        network,
        brain,
    )

    test_app = FastAPI(title="VCOS Test", lifespan=None)

    async def override_get_db():
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session

    from app.db.database import get_db

    test_app.dependency_overrides[get_db] = override_get_db

    prefix = "/api/v1"
    test_app.include_router(health.router)
    test_app.include_router(health.platform_router, prefix=prefix)
    test_app.include_router(ai.router, prefix=prefix)
    test_app.include_router(ai_actions.router, prefix=prefix)
    test_app.include_router(ai_memory.router, prefix=prefix)
    test_app.include_router(ai_predictions.router, prefix=prefix)
    test_app.include_router(ai_planning.router, prefix=prefix)
    test_app.include_router(ai_recommendations.router, prefix=prefix)
    test_app.include_router(ai_search.router, prefix=prefix)
    test_app.include_router(ai_voice.router, prefix=prefix)
    test_app.include_router(auth.router, prefix=prefix)
    test_app.include_router(organizations.router, prefix=prefix)
    test_app.include_router(users.router, prefix=prefix)
    test_app.include_router(roles.router, prefix=prefix)
    test_app.include_router(notifications.router, prefix=prefix)
    test_app.include_router(workspace.router, prefix=prefix)
    test_app.include_router(audit.router, prefix=prefix)
    test_app.include_router(events.router, prefix=prefix)
    test_app.include_router(execution.router, prefix=prefix)
    test_app.include_router(search.router, prefix=prefix)
    test_app.include_router(dashboard.router, prefix=prefix)
    test_app.include_router(employees.router, prefix=prefix)
    test_app.include_router(departments.router, prefix=prefix)
    test_app.include_router(teams.router, prefix=prefix)
    test_app.include_router(organization.router, prefix=prefix)
    test_app.include_router(expertise.router, prefix=prefix)
    test_app.include_router(presence.router, prefix=prefix)
    test_app.include_router(projects.router, prefix=prefix)
    test_app.include_router(tasks.router, prefix=prefix)
    test_app.include_router(goals.router, prefix=prefix)
    test_app.include_router(meeting_intel.router, prefix=prefix)
    test_app.include_router(recording_library.router, prefix=prefix)
    test_app.include_router(meetings.router, prefix=prefix)
    test_app.include_router(calendar.router, prefix=prefix)
    test_app.include_router(meeting_rooms.router, prefix=prefix)
    test_app.include_router(collaboration_live.router, prefix=prefix)
    test_app.include_router(recordings.router, prefix=prefix)
    test_app.include_router(approvals.router, prefix=prefix)
    test_app.include_router(risks.router, prefix=prefix)
    test_app.include_router(workload.router, prefix=prefix)
    test_app.include_router(documents.router, prefix=prefix)
    test_app.include_router(wiki.router, prefix=prefix)
    test_app.include_router(policies.router, prefix=prefix)
    test_app.include_router(sops.router, prefix=prefix)
    test_app.include_router(templates.router, prefix=prefix)
    test_app.include_router(decisions.router, prefix=prefix)
    test_app.include_router(knowledge.router, prefix=prefix)
    test_app.include_router(executive.router, prefix=prefix)
    test_app.include_router(exec_health.router, prefix=prefix)
    test_app.include_router(exec_risks.router, prefix=prefix)
    test_app.include_router(exec_recommendations.router, prefix=prefix)
    test_app.include_router(exec_predictions.router, prefix=prefix)
    test_app.include_router(exec_simulations.router, prefix=prefix)
    test_app.include_router(exec_reports.router, prefix=prefix)
    test_app.include_router(exec_strategy.router, prefix=prefix)
    test_app.include_router(intelligence.router, prefix=prefix)
    test_app.include_router(collaboration_intel.router, prefix=prefix)
    test_app.include_router(intelligence_briefs.router, prefix=prefix)
    test_app.include_router(recommendations.router, prefix=prefix)
    test_app.include_router(insights.router, prefix=prefix)
    test_app.include_router(learning.router, prefix=prefix)
    test_app.include_router(courses.router, prefix=prefix)
    test_app.include_router(learning_paths.router, prefix=prefix)
    test_app.include_router(skills.router, prefix=prefix)
    test_app.include_router(assessments.router, prefix=prefix)
    test_app.include_router(mentorship.router, prefix=prefix)
    test_app.include_router(certifications.router, prefix=prefix)
    test_app.include_router(career.router, prefix=prefix)
    test_app.include_router(academy.router, prefix=prefix)
    test_app.include_router(onboarding.router, prefix=prefix)
    test_app.include_router(attendance.router, prefix=prefix)
    test_app.include_router(leave.router, prefix=prefix)
    test_app.include_router(hr.router, prefix=prefix)
    test_app.include_router(recruitment.router, prefix=prefix)
    test_app.include_router(performance.router, prefix=prefix)
    test_app.include_router(assets.router, prefix=prefix)
    test_app.include_router(offboarding.router, prefix=prefix)
    test_app.include_router(compliance.router, prefix=prefix)
    test_app.include_router(workforce.router, prefix=prefix)
    test_app.include_router(wellbeing.router, prefix=prefix)
    test_app.include_router(payroll.router, prefix=prefix)
    test_app.include_router(customers.router, prefix=prefix)
    test_app.include_router(contacts.router, prefix=prefix)
    test_app.include_router(leads.router, prefix=prefix)
    test_app.include_router(opportunities.router, prefix=prefix)
    test_app.include_router(contracts.router, prefix=prefix)
    test_app.include_router(support.router, prefix=prefix)
    test_app.include_router(partners.router, prefix=prefix)
    test_app.include_router(accounts.router, prefix=prefix)
    test_app.include_router(portal.router, prefix=prefix)
    test_app.include_router(analytics.router, prefix=prefix)
    test_app.include_router(finance.router, prefix=prefix)
    test_app.include_router(automation.router, prefix=prefix)
    test_app.include_router(enterprise.router, prefix=prefix)
    test_app.include_router(infrastructure.router, prefix=prefix)
    test_app.include_router(industry.router, prefix=prefix)
    test_app.include_router(digital_twin.router, prefix=prefix)
    test_app.include_router(developers.router, prefix=prefix)
    test_app.include_router(agents.router, prefix=prefix)
    test_app.include_router(webhooks.router, prefix=prefix)
    test_app.include_router(extensions.router, prefix=prefix)
    test_app.include_router(extensions.theme_router, prefix=prefix)
    test_app.include_router(memory.memory_router, prefix=prefix)
    test_app.include_router(memory.timeline_router, prefix=prefix)
    test_app.include_router(memory.context_router, prefix=prefix)

    test_app.include_router(autonomy.autonomy_router, prefix=prefix)
    test_app.include_router(autonomy.briefing_router, prefix=prefix)
    test_app.include_router(autonomy.decision_router, prefix=prefix)
    test_app.include_router(prediction.router, prefix=prefix)
    test_app.include_router(network.router, prefix=prefix)

    test_app.include_router(brain.router, prefix=prefix)

    from app.industry.api import INDUSTRY_ROUTERS
    for _industry_router in INDUSTRY_ROUTERS.values():
        test_app.include_router(_industry_router, prefix=prefix)

    from app.services.permission_service import permission_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        await permission_service.sync_catalog(db)
        await db.commit()
    return test_app


@pytest.fixture
async def client(app_factory):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app_factory), base_url="http://test") as c:
        yield c


async def register_org(client, *, name="Acme Corp", slug=None, email="owner@acme.test.co", password="StrongPass123!"):
    import uuid

    slug = slug or f"acme-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": name,
            "organization_slug": slug,
            "industry": "Software",
            "country": "US",
            "timezone": "UTC",
            "currency": "USD",
            "full_name": "Ada Owner",
            "email": email,
            "username": email.split("@")[0],
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "refresh": data["refresh_token"],
        "user": data["user"],
        "organization": data["organization"],
        "access": data["access_token"],
    }

