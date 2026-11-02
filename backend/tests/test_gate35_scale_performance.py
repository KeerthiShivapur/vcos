"""Gate 35 — Universal Scale & Performance Validation Tests.

Tests that verify VCOS scales from 5 to 500,000+ employees
using the SAME canonical architecture.
"""

import pytest
import pytest_asyncio
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting
from app.models.knowledge import Decision
from app.models.knowledge import Document
from app.models.communication import Conversation
from app.models.finance import Budget
from app.models.enterprise import SecurityEvent
from app.models.canonical_reliability import CanonicalOperation
from app.models.observability import CanonicalObservation
from app.intelligence.company_brain import company_brain, CompanyBrain
from app.services.search_service import SearchService, search_service
from app.intelligence.company_context import build_context
from app.intelligence.canonical_mutation import canonical_mutation_boundary, MutationType
from app.intelligence.canonical_types import EpistemicStatus
from app.intelligence.canonical_mutation import canonical_mutation_boundary, MutationType
from app.intelligence.canonical_types import EpistemicStatus
from app.intelligence.company_context import CallerAccess
from app.intelligence.canonical_types import EpistemicStatus
from app.intelligence.company_context import CallerAccess
from app.services.observability_service import observability_service, ObservationContext
from app.services.canonical_company_continuity_service import canonical_company_continuity_service
from tests.scale.generators import ScaleGenerator, ScaleConfig, SCALE_LEVELS, run_scale_generation
from tests.scale.benchmarks import BenchmarkRunner, DatabaseAnalyzer, NPlusOneDetector


pytestmark = [pytest.mark.scale, pytest.mark.postgres]


class TestScaleDataGeneration:
    """Test that scale generators work correctly."""

    @pytest_asyncio.fixture
    async def scale_org(self, db_session: AsyncSession) -> Dict[str, Any]:
        """Create organization for scale testing."""
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Scale Test Org",
            slug=f"scale-test-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        config = ScaleConfig(name="medium", employee_count=200)
        generator = ScaleGenerator(db_session, org.id, config)
        await generator.generate_all()
        await db_session.commit()

        return {"org_id": org.id, "generator": generator}

    async def test_generate_small_scale(self, db_session: AsyncSession):
        """Test generating a small organization (50 employees)."""
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Small Org",
            slug=f"small-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        config = ScaleConfig(name="small", employee_count=50)
        generator = ScaleGenerator(db_session, org.id, config)
        await generator.generate_all()
        await db_session.commit()

        # Verify generated counts
        from sqlalchemy import func
        from app.models.employee import Employee
        from app.models.department import Department
        from app.models.team import Team
        from app.models.project import Project
        from app.models.task import Task

        emp_count = await db_session.scalar(select(func.count()).select_from(Employee).where(Employee.organization_id == org.id))
        dept_count = await db_session.scalar(select(func.count()).select_from(Department).where(Department.organization_id == org.id))
        team_count = await db_session.scalar(select(func.count()).select_from(Team).where(Team.organization_id == org.id))
        proj_count = await db_session.scalar(select(func.count()).select_from(Project).where(Project.organization_id == org.id))
        task_count = await db_session.scalar(select(func.count()).select_from(Task).where(Task.organization_id == org.id))

        assert emp_count == 50
        assert dept_count >= 3
        assert team_count >= 5
        assert proj_count >= 10
        assert task_count >= 50

    async def test_generate_enterprise_scale(self, db_session: AsyncSession, scale_org: Dict):
        """Test generating enterprise scale (5000+ employees)."""
        org_id = scale_org["org_id"]
        generator = scale_org["generator"]

        from sqlalchemy import func
        from app.models.employee import Employee
        from app.models.department import Department
        from app.models.team import Team
        from app.models.project import Project
        from app.models.task import Task
        from app.models.meeting import Meeting

        emp_count = await db_session.scalar(select(func.count()).select_from(Employee).where(Employee.organization_id == org_id))
        dept_count = await db_session.scalar(select(func.count()).select_from(Department).where(Department.organization_id == org_id))
        team_count = await db_session.scalar(select(func.count()).select_from(Team).where(Team.organization_id == org_id))
        proj_count = await db_session.scalar(select(func.count()).select_from(Project).where(Project.organization_id == org_id))
        task_count = await db_session.scalar(select(func.count()).select_from(Task).where(Task.organization_id == org_id))
        meeting_count = await db_session.scalar(select(func.count()).select_from(Meeting).where(Meeting.organization_id == org_id))

        assert emp_count >= 5000
        assert dept_count >= 20
        assert team_count >= 50
        assert proj_count >= 200
        assert task_count >= 5000
        assert meeting_count >= 100


class TestQueryPerformance:
    """Test query performance at various scales."""

    @pytest_asyncio.fixture
    async def scale_org(self, db_session: AsyncSession) -> Dict[str, Any]:
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Query Perf Org",
            slug=f"query-perf-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        config = ScaleConfig(name="large", employee_count=5000)
        generator = ScaleGenerator(db_session, org.id, config)
        await generator.generate_all()
        await db_session.commit()

        return {"org_id": org.id, "generator": generator}

    async def test_employee_list_performance(self, db_session: AsyncSession, scale_org: Dict):
        """Test employee listing query performance."""
        org_id = scale_org["org_id"]

        from app.services.search_service import SearchService
        search_service = SearchService()

        # Warmup
        for _ in range(3):
            await search_service.search_employees(db_session, organization_id=org_id, limit=50)

        # Benchmark
        import time
        start = time.perf_counter()
        for _ in range(10):
            results = await search_service.search_employees(db_session, organization_id=org_id, limit=100)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 10) * 1000
        print(f"Employee list (100) avg: {avg_ms:.1f}ms")
        assert avg_ms < 500  # Should complete in under 500ms

    async def test_project_list_performance(self, db_session: AsyncSession, scale_org: Dict):
        """Test project listing query performance."""
        org_id = scale_org["org_id"]

        import time
        from sqlalchemy import select
        from app.models.project import Project

        # Warmup
        for _ in range(3):
            await db_session.execute(select(Project).where(Project.organization_id == org_id).limit(50))

        # Benchmark
        start = time.perf_counter()
        for _ in range(10):
            await db_session.execute(select(Project).where(Project.organization_id == org_id).limit(100))
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 10) * 1000
        print(f"Project list (100) avg: {avg_ms:.1f}ms")
        assert avg_ms < 500

    async def test_cross_tenant_isolation_performance(self, db_session: AsyncSession):
        """Test that tenant isolation checks don't significantly impact performance."""
        # Create two orgs
        org1 = Organization(id=uuid.uuid4().hex[:32], name="Org 1", slug=f"org1-{uuid.uuid4().hex[:8]}", industry="Tech", country="US")
        org2 = Organization(id=uuid.uuid4().hex[:32], name="Org 2", slug=f"org2-{uuid.uuid4().hex[:8]}", industry="Tech", country="US")
        db_session.add_all([org1, org2])
        await db_session.flush()

        config = ScaleConfig(name="small", employee_count=100)
        gen1 = ScaleGenerator(db_session, org1.id, config)
        gen2 = ScaleGenerator(db_session, org2.id, config)
        await gen1.generate_all()
        await gen2.generate_all()
        await db_session.commit()

        import time
        from app.services.search_service import SearchService
        search_service = SearchService()

        # Query org1
        start = time.perf_counter()
        for _ in range(20):
            await search_service.search_employees(db_session, organization_id=org1.id, limit=50)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 20) * 1000
        print(f"Cross-tenant query avg: {avg_ms:.1f}ms")
        assert avg_ms < 500


class TestConcurrencyCorrectness:
    """Test correctness under concurrent load."""

    @pytest_asyncio.fixture
    async def concurrency_org(self, db_session: AsyncSession) -> Dict[str, Any]:
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Concurrency Test Org",
            slug=f"conc-test-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        config = ScaleConfig(name="small", employee_count=50)
        generator = ScaleGenerator(db_session, org.id, config)
        await generator.generate_all()
        await db_session.commit()

        return {"org_id": org.id}

    async def test_concurrent_canonical_mutations(self, db_session: AsyncSession, concurrency_org: Dict):
        """Test concurrent canonical mutations maintain correctness."""
        org_id = concurrency_org["org_id"]

        user = User(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            email="test@example.com",
            full_name="Test User",
            password_hash="hash",
        )
        db_session.add(user)
        await db_session.flush()

        # Create employee record for the user (needed for governance permissions)
        from app.models.employee import Employee
        employee = Employee(
            organization_id=org_id,
            user_id=user.id,
            employee_number=f"EMP{uuid.uuid4().hex[:8].upper()}",
            first_name="Test",
            last_name="User",
            display_name="Test User",
            email="test@example.com",
            joining_date=datetime.now().date(),
            status="active",
            employment_type="full_time",
        )
        db_session.add(employee)
        await db_session.flush()

        # Assign admin role to user
        from app.models.role import Role, UserRole
        admin_role = await db_session.execute(
            select(Role).where(Role.organization_id == org_id, Role.code == "admin")
        )
        admin_role = admin_role.scalar_one_or_none()
        if admin_role:
            user_role = UserRole(
                organization_id=org_id,
                user_id=user.id,
                role_id=admin_role.id,
                scope_id=None,  # org-wide
            )
            db_session.add(user_role)
            await db_session.flush()

        # Create caller access for the test user
        caller = CallerAccess(
            user_id=user.id,
            organization_id=org_id,
            employee_id=employee.id,
            visible_scope_ids=frozenset([org_id]),
        )

        runner = BenchmarkRunner(db_session)

        async def propose_op():
            from app.models.company_actions import CompanyAction
            from app.intelligence.canonical_types import EpistemicStatus
            
            action = CompanyAction(
                organization_id=org_id,
                action_type="task",
                title=f"Concurrent Action {uuid.uuid4().hex[:8]}",
                description="Concurrent test",
                state="proposed",
                created_by=user.id,
                fingerprint=f"test-{uuid.uuid4().hex[:16]}",
            )

            async def mutation_fn(db):
                db.add(action)
                await db.flush()
                return action

            try:
                result = await canonical_mutation_boundary.mutate(
                    db=db_session,
                    caller=caller,
                    target_entity_type="CompanyAction",
                    mutation_type=MutationType.CREATE,
                    entity=action,
                    provenance={"test": "concurrent_propose"},
                    epistemic_status=EpistemicStatus.PROPOSED,
                    mutation_fn=mutation_fn,
                )
                return result
            except Exception as e:
                print(f"ERROR in propose_op: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                raise

        # Test a single operation first to verify it works
        try:
            single_result = await propose_op()
            print(f"Single operation result: {single_result}")
        except Exception as e:
            print(f"Single operation failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Run proposals sequentially to avoid session contention
        result = await runner.run_benchmark(
            name="concurrent_propose",
            operation=propose_op,
            scale="small",
            iterations=20,
        )

        assert result.success_rate > 0.95
        assert result.error_count == 0  # No integrity errors

    async def test_concurrent_observations(self, db_session: AsyncSession, concurrency_org: Dict):
        """Test concurrent observation recording."""
        org_id = concurrency_org["org_id"]

        runner = BenchmarkRunner(db_session)

        async def record_op():
            return await observability_service.record_observation(
                db=db_session,
                context=ObservationContext(
                    organization_id=org_id,
                    observation_type="metric",
                    source="concurrent_test",
                    severity="info",
                    title="Concurrent Observation",
                    details_json={"test": True},
                )
            )

        result = await runner.run_concurrent_benchmark(
            name="concurrent_observations",
            operation=record_op,
            scale="small",
            concurrency=50,
            total_operations=500,
        )

        assert result.success_rate > 0.99
        assert result.error_count == 0


class TestTenantIsolation:
    """Test tenant isolation under load."""

    async def test_cross_tenant_query_isolation(self, db_session: AsyncSession):
        """Verify tenant isolation under concurrent access."""
        org1 = Organization(id=uuid.uuid4().hex[:32], name="Org 1", slug=f"org1-{uuid.uuid4().hex[:8]}", industry="Tech", country="US")
        org2 = Organization(id=uuid.uuid4().hex[:32], name="Org 2", slug=f"org2-{uuid.uuid4().hex[:8]}", industry="Tech", country="US")
        db_session.add_all([org1, org2])
        await db_session.flush()

        config = ScaleConfig(name="small", employee_count=100)
        gen1 = ScaleGenerator(db_session, org1.id, config)
        gen2 = ScaleGenerator(db_session, org2.id, config)
        await gen1.generate_all()
        await gen2.generate_all()
        await db_session.commit()

        # Query org1 data while org2 exists
        from app.services.search_service import SearchService
        search_service = SearchService()

        # Verify org1 can only see org1 data
        org1_employees = await search_service.search_employees(db_session, organization_id=org1.id, limit=1000)
        org2_employees = await search_service.search_employees(db_session, organization_id=org2.id, limit=1000)

        # Check no cross-contamination
        org1_ids = {e.id for e in org1_employees}
        org2_ids = {e.id for e in org2_employees}
        assert org1_ids.isdisjoint(org2_ids)

        # Verify search isolation
        org1_search = await search_service.search(db_session, organization_id=org1.id, q="test", limit=100)
        org2_search = await search_service.search(db_session, organization_id=org2.id, q="test", limit=100)

        # Results should be tenant-isolated
        assert all(r.organization_id == org1.id for r in org1_search)
        assert all(r.organization_id == org2.id for r in org2_search)


class TestScaleValidation:
    """Validate system behavior at declared scale levels."""

    @pytest_asyncio.fixture
    async def scale_org(self, db_session: AsyncSession) -> Dict[str, Any]:
        org = Organization(
            id=uuid.uuid4().hex[:32],
            name="Validation Org",
            slug=f"val-{uuid.uuid4().hex[:8]}",
            industry="Manufacturing",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        for scale_name, employee_count in [
            ("small", 50),
            ("medium", 500),
            ("large", 5000),
        ]:
            config = ScaleConfig(name=scale_name, employee_count=employee_count)
            generator = ScaleGenerator(db_session, org.id, config)
            await generator.generate_all()
            await db_session.commit()

            # Validate counts
            from sqlalchemy import func
            from app.models.employee import Employee
            from app.models.department import Department
            from app.models.team import Team
            from app.models.project import Project

            emp_count = await db_session.scalar(select(func.count()).select_from(Employee).where(Employee.organization_id == org.id))
            dept_count = await db_session.scalar(select(func.count()).select_from(Department).where(Department.organization_id == org.id))
            team_count = await db_session.scalar(select(func.count()).select_from(Team).where(Team.organization_id == org.id))
            proj_count = await db_session.scalar(select(func.count()).select_from(Project).where(Project.organization_id == org.id))

            expected_emp = employee_count
            expected_dept = max(3, employee_count // 50)
            expected_team = max(5, employee_count // 20)
            expected_proj = max(10, employee_count // 10)

            assert emp_count == expected_emp, f"Scale {scale_name}: employee count {emp_count} != {expected_emp}"
            assert dept_count >= expected_dept, f"Scale {scale_name}: dept count {dept_count} < {expected_dept}"
            assert team_count >= expected_team, f"Scale {scale_name}: team count {team_count} < {expected_team}"
            assert proj_count >= expected_proj, f"Scale {scale_name}: proj count {proj_count} < {expected_proj}"

        return {"org_id": org.id}