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
import pytest_asyncio
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file::memory:?cache=shared"
os.environ["REDIS_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["EMAIL_TRANSPORT"] = "console"
os.environ["AI_PROVIDER"] = "none"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["APP_ENV"] = "test"
os.environ["VCOS_TEST_MODE"] = "1"

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool, NullPool
from sqlalchemy import text  # noqa: E402

from app.db.database import Base  # noqa: E402
from app import models  # noqa: E402, F401
from tests.concurrency import (  # noqa: E402, F401
    concurrency_organization,
    concurrency_db_session_factory,
    ten_actors_same_company,
    cross_company_actors,
)


# PostgreSQL test infrastructure
TEST_POSTGRES_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"
)


@pytest_asyncio.fixture(scope="function")
async def postgres_engine():
    """Function-scoped PostgreSQL engine for testing.

    Must be function-scoped: asyncpg connections are bound to the event loop
    that created them, and pytest-asyncio runs each test (and its
    function-scoped fixtures) in a fresh function-scoped event loop when no
    default fixture loop scope is configured. The engine is disposed at the
    end of each test, so no connections are retained between tests.
    """
    engine = create_async_engine(
        os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"),
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    
    # Tables already created via alembic, just verify connection
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    
    yield engine
    
    # Cleanup - dispose engine at test end
    try:
        await engine.dispose()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="function")
async def pg_db_session_factory(postgres_engine):
    """Session factory bound to the PostgreSQL test engine."""
    return async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture(scope="function")
async def pg_db_session(pg_db_session_factory):
    """Individual test session with proper lifecycle management."""
    # Initialize adapter registry for tests
    from app.services.adapter_registry import adapter_registry
    from app.core.config import get_settings
    if not adapter_registry._initialized:
        adapter_registry.initialize(get_settings())
    
    # Comprehensive cleanup - clean all tables that tests typically create
    from sqlalchemy import text
    cleanup_tables = [
        "employees", "projects", "tasks", "users", "departments", "teams",
        "roles", "organizations", "meetings", "documents", "decisions",
        "approvals", "risks", "goals", "events", "messages", "conversations",
        "notifications", "announcements", "posts", "comments", "wiki_pages",
        "calendar_events", "meeting_rooms", "meeting_sessions", "meeting_notes",
        "meeting_transcripts", "meeting_captions", "meeting_whiteboards",
        "meeting_recordings", "meeting_action_items", "meeting_agenda_items",
        "meeting_participants", "leave_requests", "leave_balances", "leave_types",
        "attendance_records", "attendance_corrections", "certifications",
        "certifications_earned", "skills", "employee_skills", "certification_attempts",
        "career_paths", "career_path_steps", "career_progress", "learning_paths",
        "learning_path_steps", "course_enrollments", "courses", "course_modules",
        "course_quizzes", "training_completions", "training_requirements",
        "performance_reviews", "performance_goals", "performance_cycles",
        "devices", "api_keys", "developer_api_keys", "developer_applications",
        "developer_certifications", "developer_subscriptions", "developer_usage",
        "developers", "marketplace_reviews", "marketplace_items", "extension_installs",
        "plugins", "plugin_versions", "feature_flags",
        "feature_flag_evaluations", "feature_flag_history", "feature_flag_audit_log",
        "observability_logs", "canonical_observations", "correlation_contexts", "degradations",
        "slo_targets", "health_metrics", "security_events", "security_audit_events",
        "alerts", "incident_responses", "incident_timeline_events",
        "devices", "api_keys", "developer_api_keys", "developer_applications",
        "developer_certifications", "developer_subscriptions", "developer_usage",
        "developers", "marketplace_reviews", "marketplace_items", "extension_installs",
        "plugins", "plugin_versions", "feature_flags",
        "feature_flag_evaluations", "feature_flag_history", "feature_flag_audit_log",
        "observability_logs", "canonical_observations", "correlation_contexts", "degradations",
        "slo_targets", "health_metrics", "security_events", "security_audit_events",
        "alerts", "incident_responses", "incident_timeline_events",
        "departments", "teams", "roles", "organizations", "meetings", "documents",
        "decisions", "approvals", "risks", "goals", "events", "messages", "conversations",
        "notifications", "announcements", "posts", "comments", "wiki_pages",
        "calendar_events", "meeting_rooms", "meeting_sessions", "meeting_notes",
        "meeting_transcripts", "meeting_captions", "meeting_whiteboards",
        "meeting_recordings", "meeting_action_items", "meeting_agenda_items",
        "meeting_participants", "leave_requests", "leave_balances", "leave_types",
        "attendance_records", "attendance_corrections", "certifications",
        "certifications_earned", "skills", "employee_skills", "certification_attempts",
        "career_paths", "career_path_steps", "career_progress", "learning_paths",
        "learning_path_steps", "course_enrollments", "courses", "course_modules",
        "course_quizzes", "training_completions", "training_requirements",
        "performance_reviews", "performance_goals", "performance_cycles",
        "devices", "api_keys", "developer_api_keys", "developer_applications",
        "developer_certifications", "developer_subscriptions", "developer_usage",
        "developers", "marketplace_reviews", "marketplace_items", "extension_installs",
        "plugins", "plugin_versions", "feature_flags",
        "feature_flag_evaluations", "feature_flag_history", "feature_flag_audit_log",
        "observability_logs", "canonical_observations", "correlation_contexts", "degradations",
        "slo_targets", "health_metrics", "security_events", "security_audit_events",
        "alerts", "incident_responses", "incident_timeline_events",
        "users", "organizations", "departments", "teams", "roles",
        "meetings", "documents", "decisions", "approvals", "risks", "goals",
        "events", "messages", "conversations", "notifications", "announcements",
        "posts", "comments", "wiki_pages", "calendar_events", "meeting_rooms",
        "meeting_sessions", "meeting_notes", "meeting_transcripts", "meeting_captions",
        "meeting_whiteboards", "meeting_recordings", "meeting_action_items",
        "meeting_agenda_items", "meeting_participants", "leave_requests",
        "leave_balances", "leave_types", "attendance_records", "attendance_corrections",
        "certifications", "certifications_earned", "skills", "employee_skills",
        "certification_attempts", "career_paths", "career_path_steps", "career_progress",
        "learning_paths", "learning_path_steps", "course_enrollments", "courses",
        "course_modules", "course_quizzes", "training_completions", "training_requirements",
        "performance_reviews", "performance_goals", "performance_cycles",
        "backup_manifests", "restore_operations", "connectors", "connector_instances",
        "provisionings", "health_dimensions", "approval_policies", "company_authorizations",
        "webhook_deliveries", "webhook_endpoints", "sync_cursors", "sync_runs",
        "external_events",
    ]
    
    # Deduplicate
    cleanup_tables = list(dict.fromkeys(cleanup_tables))
    
    # Use the same session factory for cleanup
    async with pg_db_session_factory() as cleanup_session:
        # Disable triggers temporarily when permitted (requires superuser).
        # TRUNCATE ... RESTART IDENTITY CASCADE does not need it for FK
        # integrity, so a non-superuser test role degrades gracefully.
        replica_set = False
        try:
            await cleanup_session.execute(text("SET session_replication_role = replica"))
            replica_set = True
        except Exception as exc:
            print(f"[pg_db_session] session_replication_role unavailable: {exc!r}", flush=True)
            await cleanup_session.rollback()
        for table in cleanup_tables:
            try:
                result = await cleanup_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count > 0:
                    print(f"Table {table} has {count} rows before truncate")
                await cleanup_session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                await cleanup_session.commit()
                print(f"Truncated {table}")
            except Exception as e:
                await cleanup_session.rollback()
                print(f"Failed to truncate {table}: {e}")
        if replica_set:
            try:
                await cleanup_session.execute(text("SET session_replication_role = origin"))
            except Exception as exc:
                print(f"[pg_db_session] failed to reset session_replication_role: {exc!r}", flush=True)
                await cleanup_session.rollback()
        await cleanup_session.commit()
    
    # Create session for the test
    session = pg_db_session_factory()
    session.expire_on_commit = False
    
    try:
        yield session
    finally:
        # Ensure session is properly closed
        try:
            await session.close()
        except Exception as exc:
            print(f"[pg_db_session] close failed: {exc!r}", flush=True)


@pytest_asyncio.fixture(scope="function")
async def pg_db_with_tenant(pg_db_session_factory):
    """PostgreSQL session with tenant context set for RLS testing.
    
    Creates a test organization, sets up the tenant context for RLS policies,
    and yields the session along with the organization ID.
    """
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import text
    from app.models.organization import Organization
    from app.models.user import User
    from app.core.security import hash_password
    from app.db.rls import set_tenant_context
    
    # Create a session
    session = pg_db_session_factory()
    session.expire_on_commit = False
    
    try:
        # Create test organization
        org_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        short_name = "test-org"
        unique_suffix = uuid.uuid4().hex[:8]
        slug = f"t-{short_name}-{unique_suffix}"[:32]
        
        # Insert organization (global, no RLS context needed)
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=slug,
            industry="Technology",
            country="US",
            timezone="UTC",
            language="en",
            currency="USD",
            status="active",
            brand_primary_color="#4F46E5",
            entity_type="standalone",
            created_at=now,
            updated_at=now,
        )
        async with pg_db_session_factory() as session:
            session.add(org)
            await session.flush()
            
            # Create admin user with RLS context set to this org
            user_id = uuid.uuid4().hex
            await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_id})
            await session.execute(text("""
                INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role, timezone, language, failed_login_attempts, mfa_enabled, mfa_required, mfa_backup_codes_used, created_at, updated_at)
                VALUES (:id, :org_id, :email, :full_name, 'test_hash', 'active', 'employee', 'UTC', 'en', 0, False, False, 0, :now, :now)
            """), {"id": uuid.uuid4().hex, "org_id": org_id, "email": f"admin-{uuid.uuid4().hex[:8]}@test.com", "full_name": "Test Admin", "now": now})
            await session.flush()
            await session.commit()
        
        # Set tenant context for the test session
        await set_tenant_context(pg_db_session_factory, org_id)
        
        yield pg_db_session_factory, org_id
    finally:
        pass  # Session cleanup handled by pg_db_session fixture
@pytest.fixture(scope="function")
def sync_postgres_engine():
    """Function-scoped synchronous PostgreSQL engine for data generation.
    
    Uses psycopg2 driver to avoid asyncpg greenlet concurrency issues.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session, sessionmaker
    
    # Convert async URL to sync URL
    async_url = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test")
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    
    engine = create_engine(
        sync_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"options": "-c search_path=public"},
        echo=False,
        future=True,
    )
    
    # Verify connection
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    
    yield engine
    
    # Cleanup
    try:
        engine.dispose()
    except Exception:
        pass


@pytest.fixture(scope="function")
def sync_db_session_factory(sync_postgres_engine):
    """Session factory bound to the synchronous PostgreSQL test engine."""
    from sqlalchemy.orm import Session, sessionmaker
    return sessionmaker(
        sync_postgres_engine,
        class_=Session,
        expire_on_commit=False,
    )


@pytest.fixture(scope="function")
def sync_db_session(sync_db_session_factory):
    """Individual synchronous test session."""
    session = sync_db_session_factory()
    try:
        yield session
    finally:
        try:
            session.close()
        except Exception:
            pass


# PostgreSQL-specific test markers
def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: marks tests requiring PostgreSQL")


PG_TEST_FIXTURES = {"pg_db_session", "pg_db_session_factory", "postgres_engine"}


def pytest_collection_modifyitems(config, items):
    """Mark PostgreSQL-backed tests."""
    for item in items:
        if PG_TEST_FIXTURES & set(getattr(item, "fixturenames", ()) or ()):
            item.add_marker(pytest.mark.postgres)


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()


@pytest.fixture(scope="session")
async def engine():
    """Session-scoped engine with StaticPool for shared in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create universal indexes for query plan optimization
    from app.db.database import _create_universal_indexes
    await _create_universal_indexes(engine)
    
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def db_session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
import uuid


@pytest.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


@pytest.fixture(scope="session")
async def app_factory(engine, db_session_factory):
    """FastAPI app wired to the shared test database."""
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
        canonical_integrity,
        canonical_reliability,
        observability,
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
        feature_flags,
        finance,
        goals,
        governance,
        governed_worker,
        organizational_responsibility,
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
        messaging,
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
        async with db_session_factory() as session:
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
    test_app.include_router(messaging.router, prefix=prefix)
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
    test_app.include_router(governance.router, prefix=prefix)
    test_app.include_router(governed_worker.router, prefix=prefix)
    test_app.include_router(organizational_responsibility.router, prefix=prefix)
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
    test_app.include_router(canonical_integrity.router, prefix=prefix)
    test_app.include_router(canonical_reliability.router, prefix=prefix)
    test_app.include_router(observability.router, prefix=prefix)
    test_app.include_router(developers.router, prefix=prefix)
    test_app.include_router(agents.router, prefix=prefix)
    test_app.include_router(webhooks.router, prefix=prefix)
    test_app.include_router(extensions.router, prefix=prefix)
    test_app.include_router(extensions.theme_router, prefix=prefix)
    test_app.include_router(memory.memory_router, prefix=prefix)
    test_app.include_router(memory.timeline_router, prefix=prefix)
    test_app.include_router(memory.context_router, prefix=prefix)
    test_app.include_router(feature_flags.router, prefix=prefix)

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

    # Tables already created by session-scoped engine fixture
    # Just sync permission catalog
    async with db_session_factory() as db:
        await permission_service.sync_catalog(db)
        await db.commit()
    return test_app


@pytest.fixture
async def client(app_factory, db_session_factory):
    from httpx import ASGITransport, AsyncClient
    from app.db.database import get_db

    # Create a shared session for this test client
    shared_session = db_session_factory()
    
    async def override_get_db():
        yield shared_session
    
    app_factory.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app_factory), base_url="http://test") as c:
        yield c
    
    # Cleanup
    await shared_session.close()


async def register_org(client, *, name="Acme Corp", slug=None, email=None, password="StrongPass123!"):
    import uuid

    if email is None:
        email = f"owner-{uuid.uuid4().hex[:8]}@acme.test.co"
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


@pytest_asyncio.fixture
async def pg_db_with_tenant(pg_db_session_factory, pg_db_session):
    """Provide a database session with tenant context set for RLS testing.
    
    Creates a test organization and sets the tenant context for RLS policies.
    Returns the session and the organization ID.
    """
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import text
    from app.models.organization import Organization
    from app.models.user import User
    from app.core.security import hash_password
    
    org_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    short_name = "test-org"
    unique_suffix = uuid.uuid4().hex[:8]
    slug = f"t-{short_name}-{uuid.uuid4().hex[:8]}"[:32]
    
    # Create organization (global, no RLS context needed)
    org = Organization(
        id=org_id,
        name="Test Org",
        slug=slug,
        industry="Technology",
        country="US",
        timezone="UTC",
        language="en",
        currency="USD",
        status="active",
        brand_primary_color="#4F46E5",
        entity_type="standalone",
    )
    pg_db_session.add(org)
    await pg_db_session.flush()
    
    # Create admin user with RLS context set to this org
    user_id = uuid.uuid4().hex
    await pg_db_session.execute(
        text("SELECT set_config('app.current_organization_id', :org_id, false)"),
        {"org_id": org_id}
    )
    user = User(
        id=uuid.uuid4().hex,
        organization_id=org_id,
        email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
        full_name="Test Admin",
        password_hash="test_hash",
        status="active",
        role="employee",
        timezone="UTC",
        language="en",
        failed_login_attempts=0,
        mfa_enabled=False,
        mfa_required=False,
        mfa_backup_codes_used=0,
        created_at=now,
        updated_at=now,
    )
    pg_db_session.add(user)
    await pg_db_session.flush()
    await pg_db_session.commit()
    
    # Set tenant context for subsequent operations
    await pg_db_session.execute(
        text("SELECT set_config('app.current_organization_id', :org_id, false)"),
        {"org_id": org_id}
    )
    
    yield pg_db_session, org_id
    
    # Clear tenant context
    await pg_db_session.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
    await pg_db_session.commit()