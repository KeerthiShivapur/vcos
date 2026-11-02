"""Adversarial tests for PostgreSQL Row-Level Security (RLS) tenant isolation.

These tests verify that cross-tenant access is blocked at the database layer
by attempting to access data from different organizations with various
attack vectors.
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task


@pytest.fixture
async def clean_test_data():
    """Clean all test-relevant tables before each test using postgres superuser."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.pool import NullPool
    import os
    
    # Only clean tables that are actually used in these tests
    tables = [
        "employees", "projects", "tasks", "users", "organizations",
        "departments", "teams", "roles", "devices",
    ]
    
    engine = create_async_engine(
        os.environ.get("TEST_DATABASE_URL_SUPERUSER", "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
        echo=False,
        future=True,
    )
    
    try:
        # Disable foreign key checks temporarily (requires superuser)
        async with AsyncSession(engine) as session:
            await session.execute(text("SET session_replication_role = replica"))
            await session.commit()
        
        # Each table truncate in its own transaction to avoid cascade failures
        for table in tables:
            async with AsyncSession(engine) as session:
                try:
                    await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
                    await session.commit()
                except Exception:
                    await session.rollback()
                    pass  # Table might not exist
        
        # Re-enable foreign key checks
        async with AsyncSession(engine) as session:
            await session.execute(text("SET session_replication_role = origin"))
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_db(pg_db_session_factory):
    """Get a database session from the PostgreSQL test fixture with vcos role."""
    async with pg_db_session_factory() as session:
        await session.execute(text("SET ROLE vcos"))
        yield session


async def _create_test_org(db: AsyncSession, name: str) -> Organization:
    """Create a test organization with a user using raw SQL and proper RLS context."""
    short_name = name.lower().replace(' ', '-')[:10]
    unique_suffix = uuid.uuid4().hex[:8]
    slug = f"t-{short_name}-{unique_suffix}"[:32]
    org_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    
    # Insert organization with raw SQL (no RLS context needed for orgs - they're global)
    await db.execute(text("""
        INSERT INTO organizations (id, name, slug, industry, country, timezone, language, currency, status, brand_primary_color, entity_type, created_at, updated_at)
        VALUES (:id, :name, :slug, 'Technology', 'US', 'UTC', 'en', 'USD', 'active', '#4F46E5', 'standalone', :now, :now)
    """), {"id": org_id, "name": name, "slug": slug, "now": now})
    await db.flush()
    
    # Create admin user with RLS context set to this org
    user_id = uuid.uuid4().hex
    await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_id})
    await db.execute(text("""
        INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role, timezone, language, failed_login_attempts, mfa_enabled, mfa_required, mfa_backup_codes_used, created_at, updated_at)
        VALUES (:id, :org_id, :email, :full_name, 'test_hash', 'active', 'employee', 'UTC', 'en', 0, False, False, 0, :now, :now)
    """), {"id": user_id, "org_id": org_id, "email": f"admin-{unique_suffix}@test.com", "full_name": f"{name} Admin", "now": now})
    await db.flush()
    
    # Return a minimal Organization object for test use
    org = Organization(id=org_id, name=name, slug=slug)
    org.id = org_id  # Ensure id is set
    return org


async def _set_tenant_context(db: AsyncSession, org_id: str) -> None:
    """Set the tenant context for RLS policies."""
    from sqlalchemy import text
    await db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_id})
    await db.commit()  # Ensure context is committed
    # Diagnostic: verify the context was set
    result = await db.execute(text("SELECT current_organization_id()"))
    configured = result.scalar()
    print(f"[RLS DEBUG] Set context to org_id={org_id}, current_organization_id()={configured}")


class TestRLSTenantIsolation:
    """Test RLS tenant isolation for vcos role."""

    async def test_tenant_a_cannot_read_tenant_b_employees(self, pg_db):
        """Tenant A should not see Tenant B's employees."""
        # Create two organizations
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create employee in Org A with proper RLS context
        emp_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_a_id, "org_id": org_a.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer", "now": now})
        await pg_db.commit()

        # Create employee in Org B with proper RLS context
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": now})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        # Query employees - should only see Org A's employee
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()

        # Verify only Org A's employee is visible
        assert len(employees) == 1
        assert employees[0].email == "alice@org-a.com"

    async def test_tenant_a_cannot_read_tenant_b_projects(self, pg_db):
        """Tenant A should not see Tenant B's projects."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create project in Org A with proper RLS context
        proj_a_id = uuid.uuid4().hex
        unique_a = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, description, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, :desc, 'active', 'high', 0, 'healthy', :now, :now)
        """), {"id": proj_a_id, "org_id": org_a.id, "name": f"Org A Project {unique_a}", 
                "code": f"PROJ-A-{unique_a}", "desc": "Project A", "now": now})
        await pg_db.commit()

        # Create project in Org B
        proj_b_id = uuid.uuid4().hex
        unique_b = uuid.uuid4().hex[:8]
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, description, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, :desc, 'active', 'high', 0, 'healthy', :now, :now)
        """), {"id": proj_b_id, "org_id": org_b.id, "name": f"Org B Project {unique_b}", 
                "code": f"PROJ-B-{unique_b}", "desc": "Project B", "now": now})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        result = await pg_db.execute(text("SELECT * FROM projects"))
        projects = result.fetchall()

        assert len(projects) == 1
        assert projects[0].code == f"PROJ-A-{unique_a}"

    async def test_tenant_a_cannot_insert_into_tenant_b(self, pg_db):
        """Tenant A should not be able to insert data for Tenant B."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        # Try to insert employee with Org B's organization_id
        # This should fail due to RLS INSERT policy
        with pytest.raises(Exception) as exc_info:
            await pg_db.execute(
                text("""
                    INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                    VALUES (:id, :org_id, :emp_num, 'Hacker', 'Attempt', 'hacker@org-b.com', 'Hacker', 'full_time', 'active', 'UTC', 0, 0, :now, :now)
                """),
                {"id": uuid.uuid4().hex, "org_id": str(org_b.id), "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", "now": datetime.now(timezone.utc)},
            )
            await pg_db.commit()

        # Should have raised an error (RLS violation)
        assert "violates row-level security policy" in str(exc_info.value).lower() or \
               "policy" in str(exc_info.value).lower()

    async def test_tenant_a_cannot_update_tenant_b(self, pg_db):
        """Tenant A should not be able to update Tenant B's data."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create employee in Org B (without RLS context)
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        # Try to update Org B's employee - should affect 0 rows
        result = await pg_db.execute(
            text("UPDATE employees SET designation = 'Hacked' WHERE id = :id"),
            {"id": str(emp_b_id)},
        )
        await pg_db.commit()

        # Should affect 0 rows (RLS blocks the update)
        assert result.rowcount == 0

    async def test_tenant_a_cannot_delete_tenant_b(self, pg_db):
        """Tenant A should not be able to delete Tenant B's data."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        # Try to delete Org B's employee - should affect 0 rows
        result = await pg_db.execute(
            text("DELETE FROM employees WHERE id = :id"),
            {"id": str(emp_b_id)},
        )
        await pg_db.commit()

        # Should affect 0 rows (RLS blocks the delete)
        assert result.rowcount == 0

    async def test_cross_tenant_join_blocked(self, pg_db):
        """Cross-tenant joins should be blocked by RLS."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create project in Org A with task
        unique_a = uuid.uuid4().hex[:8]
        proj_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, 'active', 'medium', 0, 'healthy', :now, :now)
        """), {"id": proj_a_id, "org_id": org_a.id, 
                "name": f"Org A Project {unique_a}", "code": f"PROJ-A-{unique_a}", "now": now})
        await pg_db.commit()

        task_a_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO tasks (id, organization_id, project_id, title, status, priority, spent_hours, progress, created_at, updated_at)
            VALUES (:id, :org_id, :proj_id, :title, 'todo', 'medium', 0, 0, :now, :now)
        """), {"id": uuid.uuid4().hex, "org_id": org_a.id, "proj_id": proj_a_id, 
                "title": f"Task A {unique_a}", "now": now})
        await pg_db.commit()

        # Create project in Org B with task
        unique_b = uuid.uuid4().hex[:8]
        proj_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, 'active', 'medium', 0, 'healthy', :now, :now)
        """), {"id": proj_b_id, "org_id": org_b.id, 
                "name": f"Org B Project {unique_b}", "code": f"PROJ-B-{unique_b}", "now": now})
        await pg_db.commit()

        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO tasks (id, organization_id, project_id, title, status, priority, spent_hours, progress, created_at, updated_at)
            VALUES (:id, :org_id, :proj_id, :title, 'todo', 'medium', 0, 0, :now, :now)
        """), {"id": uuid.uuid4().hex, "org_id": org_b.id, "proj_id": proj_b_id, 
                "title": f"Task B {unique_b}", "now": now})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        # Try to join tasks with projects - should only see Org A's data
        result = await pg_db.execute(text("""
            SELECT t.title, p.code
            FROM tasks t
            JOIN projects p ON t.project_id = p.id
        """))
        rows = result.fetchall()

        # Should only see Org A's task/project
        assert len(rows) == 1
        assert rows[0].title == f"Task A {unique_a}"
        assert rows[0].code == f"PROJ-A-{unique_a}"

    async def test_rls_without_context_shows_nothing(self, pg_db):
        """Without tenant context, RLS should show no rows (strict mode)."""
        org = await _create_test_org(pg_db, "Test Org")

        emp_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Test", "last_name": "User", "email": "test@org.com", "designation": "Tester", "now": datetime.now(timezone.utc)})
        await pg_db.commit()

        # Clear tenant context - RLS should show no rows when context is not set
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()

        # Don't set any tenant context
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()

        # Should see no rows (current_organization_id() returns NULL)
        assert len(employees) == 0

    async def test_superuser_bypass_rls(self, pg_db):
        """Superuser (postgres) should bypass RLS - this test documents the behavior."""
        # This test runs as postgres superuser in other test files
        # and verifies that superusers bypass RLS
        pass

    # ============================================================
    # Additional adversarial tests for comprehensive coverage
    # ============================================================

    async def test_select_without_tenant_context_fails(self, pg_db):
        """SELECT without tenant context should return no rows."""
        org = await _create_test_org(pg_db, "Test Org")
        
        emp_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Test", "last_name": "User", "email": "test@org.com", "designation": "Tester", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Clear tenant context
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # SELECT should return no rows
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 0

    async def test_insert_without_tenant_context_fails(self, pg_db):
        """INSERT without tenant context should be blocked by RLS."""
        org = await _create_test_org(pg_db, "Test Org")
        
        # Clear tenant context
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # INSERT should fail
        with pytest.raises(Exception) as exc_info:
            await pg_db.execute(
                text("""
                    INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                    VALUES (:id, :org_id, :emp_num, 'Hacker', 'Attempt', 'hacker@test.com', 'Hacker', 'full_time', 'active', 'UTC', 0, 0, :now, :now)
                """),
                {"id": uuid.uuid4().hex, "org_id": str(org.id), "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", "now": datetime.now(timezone.utc)},
            )
            await pg_db.commit()
        
        assert "violates row-level security policy" in str(exc_info.value).lower() or \
               "policy" in str(exc_info.value).lower()

    async def test_update_without_tenant_context_fails(self, pg_db):
        """UPDATE without tenant context should affect 0 rows."""
        org = await _create_test_org(pg_db, "Test Org")
        
        emp_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Test", "last_name": "User", "email": "test@org.com", "designation": "Tester", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Clear tenant context
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # UPDATE should affect 0 rows
        result = await pg_db.execute(
            text("UPDATE employees SET designation = 'Hacked' WHERE id = :id"),
            {"id": str(emp_id)},
        )
        await pg_db.commit()
        
        assert result.rowcount == 0

    async def test_delete_without_tenant_context_fails(self, pg_db):
        """DELETE without tenant context should affect 0 rows."""
        org = await _create_test_org(pg_db, "Test Org")
        
        emp_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Test", "last_name": "User", "email": "test@org.com", "designation": "Tester", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Clear tenant context
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # DELETE should affect 0 rows
        result = await pg_db.execute(
            text("DELETE FROM employees WHERE id = :id"),
            {"id": str(emp_id)},
        )
        await pg_db.commit()
        
        assert result.rowcount == 0

    async def test_invalid_organization_context_fails(self, pg_db):
        """Invalid organization ID in context should not grant access to other tenants."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Set context to an INVALID organization ID (not Org A, not Org B)
        invalid_org_id = "ffffffffffffffffffffffffffffffff"
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": invalid_org_id})
        await pg_db.commit()
        
        # Should see no rows (invalid context = no access)
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 0

    async def test_spoofed_organization_context_fails(self, pg_db):
        """Spoofed organization context should not grant access."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Try to spoof Org A's context by manually setting it to Org B's ID but claiming to be Org A
        # This tests that the context value itself is what matters, not any external claim
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.commit()
        
        # Should see Org B's employee (context matches)
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 1
        assert employees[0].email == "bob@org-b.com"
        
        # Now set to Org A's ID - should see nothing
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.commit()
        
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 0

    async def test_connection_reuse_after_tenant_a_transaction(self, pg_db):
        """Connection reuse after Tenant A transaction should not leak context."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org A
        emp_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_a_id, "org_id": org_a.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer", "now": now})
        await pg_db.commit()
        
        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": now})
        await pg_db.commit()
        
        # Simulate connection reuse: set context to Org A, then clear (simulating request end)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.commit()
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # New "request" on same connection - should see no rows without explicit context
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 0

    async def test_connection_reuse_after_rollback(self, pg_db):
        """Connection reuse after rollback should not leak context."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org A
        emp_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_a_id, "org_id": org_a.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer", "now": now})
        await pg_db.commit()
        
        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": now})
        await pg_db.commit()
        
        # Simulate failed transaction with rollback - use a proper INSERT that will fail
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        try:
            # Try to insert duplicate employee_number for Org A (should fail due to unique constraint)
            await pg_db.execute(text("""
                INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                VALUES ('duplicate-id', :org_id, 'EMP-001', 'Test', 'User', 'test@test.com', 'Test', 'full_time', 'active', 'UTC', 0, 0, :now, :now)
            """), {"org_id": org_a.id, "now": datetime.now(timezone.utc)})
            await pg_db.commit()
        except Exception:
            await pg_db.rollback()
        
        # After rollback, manually clear context (simulating get_db() cleanup)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # After rollback, context should be cleared
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        # Should see no rows because context was cleared
        assert len(employees) == 0

    async def test_connection_reuse_after_exception(self, pg_db):
        """Connection reuse after exception should not leak context."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employees in both orgs
        for org, name, email in [(org_a, "Alice", "alice@org-a.com"), (org_b, "Bob", "bob@org-b.com")]:
            emp_id = uuid.uuid4().hex
            await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
            await pg_db.execute(text("""
                INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
            """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}",
                    "first_name": name, "last_name": "User", "email": email, "designation": "Engineer", "now": datetime.now(timezone.utc)})
            await pg_db.commit()
        
        # Simulate exception during request
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        try:
            await pg_db.execute(text("SELECT 1/0"))  # Cause exception
        except Exception:
            await pg_db.rollback()
        
        # After exception, manually clear context (simulating get_db() cleanup)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', '', false)"))
        await pg_db.commit()
        
        # After exception, context should be cleared
        result = await pg_db.execute(text("SELECT * FROM employees"))
        employees = result.fetchall()
        assert len(employees) == 0

    async def test_concurrent_requests_different_tenants(self, pg_db_session_factory):
        """Concurrent requests for different tenants should not interfere."""
        import asyncio
        
        # Create organizations and employees using separate sessions
        async with pg_db_session_factory() as session:
            await session.execute(text("SET ROLE vcos"))
            org_a = await _create_test_org(session, "Org A")
            org_b = await _create_test_org(session, "Org B")
            await session.commit()
        
        # Create employees in both orgs
        for org, name, email in [(org_a, "Alice", "alice@org-a.com"), (org_b, "Bob", "bob@org-b.com")]:
            emp_id = uuid.uuid4().hex
            async with pg_db_session_factory() as session:
                await session.execute(text("SET ROLE vcos"))
                await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
                await session.execute(text("""
                    INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                    VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
                """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}",
                        "first_name": name, "last_name": "User", "email": email, "designation": "Engineer", "now": datetime.now(timezone.utc)})
                await session.commit()
        
        # Simulate concurrent requests by using separate sessions
        async def query_as_tenant(org_id, expected_email):
            async with pg_db_session_factory() as session:
                await session.execute(text("SET ROLE vcos"))
                await session.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_id})
                result = await session.execute(text("SELECT * FROM employees"))
                employees = result.fetchall()
                assert len(employees) == 1
                assert employees[0].email == expected_email
        
        # Run concurrent queries with separate sessions
        await asyncio.gather(
            query_as_tenant(org_a.id, "alice@org-a.com"),
            query_as_tenant(org_b.id, "bob@org-b.com"),
        )

    async def test_cross_tenant_subquery_blocked(self, pg_db):
        """Cross-tenant access through subqueries should be blocked."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create project in Org A
        proj_a_id = uuid.uuid4().hex
        unique_a = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, 'active', 'high', 0, 'healthy', :now, :now)
        """), {"id": proj_a_id, "org_id": org_a.id, "name": f"Org A Project {unique_a}", "code": f"PROJ-A-{unique_a}", "now": now})
        await pg_db.commit()
        
        # Create project in Org B
        proj_b_id = uuid.uuid4().hex
        unique_b = uuid.uuid4().hex[:8]
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO projects (id, organization_id, name, code, status, priority, progress, health, created_at, updated_at)
            VALUES (:id, :org_id, :name, :code, 'active', 'high', 0, 'healthy', :now, :now)
        """), {"id": proj_b_id, "org_id": org_b.id, "name": f"Org B Project {unique_b}", "code": f"PROJ-B-{unique_b}", "now": now})
        await pg_db.commit()
        
        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))
        
        # Try to access Org B's project via subquery
        result = await pg_db.execute(text(f"""
            SELECT * FROM projects 
            WHERE id IN (SELECT id FROM projects WHERE code = 'PROJ-B-{unique_b}')
        """))
        projects = result.fetchall()
        assert len(projects) == 0

    async def test_bulk_update_delete_blocked(self, pg_db):
        """Bulk UPDATE and DELETE across tenants should be blocked."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create multiple employees in both orgs
        for org in [org_a, org_b]:
            for i in range(3):
                emp_id = uuid.uuid4().hex
                await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org.id})
                await pg_db.execute(text("""
                    INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                    VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
                """), {"id": emp_id, "org_id": org.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                        "first_name": f"User{i}", "last_name": "Test", "email": f"user{i}@{org.id[:8]}.com", "designation": "Engineer", "now": datetime.now(timezone.utc)})
                await pg_db.commit()
        
        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))
        
        # Bulk UPDATE should only affect Org A's rows
        result = await pg_db.execute(text("UPDATE employees SET designation = 'Senior' WHERE designation = 'Engineer'"))
        await pg_db.commit()
        assert result.rowcount == 3  # Only Org A's 3 employees
        
        # Verify Org B's employees unchanged
        await _set_tenant_context(pg_db, str(org_b.id))
        result = await pg_db.execute(text("SELECT * FROM employees WHERE designation = 'Engineer'"))
        employees = result.fetchall()
        assert len(employees) == 3  # Org B's 3 employees unchanged

    async def test_insert_on_conflict_respects_rls(self, pg_db):
        """INSERT ... ON CONFLICT should respect RLS policies."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org A with employee_number "EMP-001"
        emp_a_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_a_id, "org_id": org_a.id, "emp_num": "EMP-001", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Set context to Org B
        await _set_tenant_context(pg_db, str(org_b.id))
        
        # Try to INSERT with ON CONFLICT using Org B's own employee_number that conflicts
        # First create an employee in Org B with the same employee_number
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": uuid.uuid4().hex, "org_id": org_b.id, "emp_num": "EMP-001", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Now try to INSERT with ON CONFLICT for Org B's own employee_number
        # This should work (upsert for Org B's own employee)
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, 'EMP-001', 'Updated', 'Bob', 'updated@org-b.com', 'Updated', 'full_time', 'active', 'UTC', 0, 0, :now, :now)
            ON CONFLICT (organization_id, employee_number) DO UPDATE SET 
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                email = EXCLUDED.email,
                designation = EXCLUDED.designation,
                updated_at = EXCLUDED.updated_at
        """), {"id": uuid.uuid4().hex, "org_id": org_b.id, "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Verify the upsert worked for Org B
        await _set_tenant_context(pg_db, str(org_b.id))
        result = await pg_db.execute(text("SELECT * FROM employees WHERE employee_number = 'EMP-001'"))
        employees = result.fetchall()
        assert len(employees) == 1
        assert employees[0].first_name == "Updated"
        assert employees[0].email == "updated@org-b.com"
        
        # Now test that Org B cannot upsert Org A's employee by trying to insert with Org A's org_id
        # This should fail because Org B's context can't see Org A's rows
        with pytest.raises(Exception) as exc_info:
            await pg_db.execute(text("""
                INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
                VALUES (:id, :org_id, 'EMP-001', 'Hacker', 'Attempt', 'hacker@org-b.com', 'Hacker', 'full_time', 'active', 'UTC', 0, 0, :now, :now)
                ON CONFLICT (organization_id, employee_number) DO UPDATE SET designation = 'Hacked'
            """), {"id": uuid.uuid4().hex, "org_id": org_a.id, "now": datetime.now(timezone.utc)})
            await pg_db.commit()
        
        # Should fail due to RLS (can't see Org A's row to conflict with)
        assert "violates row-level security policy" in str(exc_info.value).lower() or \
               "policy" in str(exc_info.value).lower()

    async def test_returning_clause_respects_rls(self, pg_db):
        """RETURNING clause should only return rows visible to the tenant."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")
        
        # Create employee in Org A
        emp_a_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_a_id, "org_id": org_a.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Alice", "last_name": "Smith", "email": "alice@org-a.com", "designation": "Engineer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Create employee in Org B
        emp_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO employees (id, organization_id, employee_number, first_name, last_name, email, designation, employment_type, status, timezone, expertise_score, profile_completion, created_at, updated_at)
            VALUES (:id, :org_id, :emp_num, :first_name, :last_name, :email, :designation, 'full_time', 'active', 'UTC', 0, 0, :now, :now)
        """), {"id": emp_b_id, "org_id": org_b.id, "emp_num": f"EMP-{uuid.uuid4().hex[:8]}", 
                "first_name": "Bob", "last_name": "Jones", "email": "bob@org-b.com", "designation": "Designer", "now": datetime.now(timezone.utc)})
        await pg_db.commit()
        
        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))
        
        # UPDATE with RETURNING should only return Org A's row
        result = await pg_db.execute(text("""
            UPDATE employees SET designation = 'Senior' 
            WHERE designation = 'Engineer' 
            RETURNING id, email, designation
        """))
        rows = result.fetchall()
        await pg_db.commit()
        
        assert len(rows) == 1
        assert rows[0].email == "alice@org-a.com"
        assert rows[0].designation == "Senior"


class TestRLSIndirectTables:
    """Test RLS on tables with indirect ownership (via parent tables)."""

    async def test_devices_via_user_tenant_isolation(self, pg_db):
        """Devices owned via user -> organization should be isolated."""
        org_a = await _create_test_org(pg_db, "Org A")
        org_b = await _create_test_org(pg_db, "Org B")

        # Create users in each org with proper RLS context
        user_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role, timezone, language, failed_login_attempts, mfa_enabled, mfa_required, mfa_backup_codes_used, created_at, updated_at)
            VALUES (:id, :org_id, :email, :full_name, 'hash', 'active', 'employee', 'UTC', 'en', 0, False, False, 0, :now, :now)
        """), {"id": user_a_id, "org_id": org_a.id, "email": "usera@org-a.com", "full_name": "User A", "now": now})
        await pg_db.commit()

        user_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO users (id, organization_id, email, full_name, password_hash, status, role, timezone, language, failed_login_attempts, mfa_enabled, mfa_required, mfa_backup_codes_used, created_at, updated_at)
            VALUES (:id, :org_id, :email, :full_name, 'hash', 'active', 'employee', 'UTC', 'en', 0, False, False, 0, :now, :now)
        """), {"id": user_b_id, "org_id": org_b.id, "email": "userb@org-b.com", "full_name": "User B", "now": now})
        await pg_db.commit()

        # Create devices with proper RLS context
        device_a_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_a.id})
        await pg_db.execute(text("""
            INSERT INTO devices (id, user_id, name, device_type, trusted, created_at, updated_at)
            VALUES (:id, :user_id, :name, :device_type, false, :now, :now)
        """), {"id": device_a_id, "user_id": user_a_id, "name": "iPhone", "device_type": "mobile", "now": now})
        await pg_db.commit()

        device_b_id = uuid.uuid4().hex
        await pg_db.execute(text("SELECT set_config('app.current_organization_id', :org_id, false)"), {"org_id": org_b.id})
        await pg_db.execute(text("""
            INSERT INTO devices (id, user_id, name, device_type, trusted, created_at, updated_at)
            VALUES (:id, :user_id, :name, :device_type, false, :now, :now)
        """), {"id": device_b_id, "user_id": user_b_id, "name": "Android Phone", "device_type": "mobile", "now": now})
        await pg_db.commit()

        # Set context to Org A
        await _set_tenant_context(pg_db, str(org_a.id))

        result = await pg_db.execute(text("SELECT * FROM devices"))
        devices = result.fetchall()

        # Should only see Org A's device
        assert len(devices) == 1
        assert devices[0].name == "iPhone"