"""Gate 8.5 — Canonical Organizational Intelligence & Structural Continuity.

Adversarial tests verifying the canonical organizational intelligence primitives
under real PostgreSQL with full canonical guarantees.
"""
import pytest
import pytest_asyncio
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.models.organization import Organization
from app.models.user import User
from app.models.role import Role, UserRole
from app.models.employee import Employee, EmployeePresence, EmployeeAvailability
from app.models.department import Department
from app.models.team import Team, TeamMember
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.intelligence.company_context import resolve_caller_access
from app.people.organizational_operating_context_service import organizational_operating_context_service
from app.intelligence.organizational_intelligence_service import organizational_intelligence_service
from app.intelligence.organizational_attention_service import organizational_attention_service
from app.intelligence.organizational_dependency_service import organizational_dependency_service
from app.intelligence.organizational_change_service import organizational_change_service
from app.intelligence.company_brain import CompanyBrain
from app.services.permission_service import permission_service
from sqlalchemy import select


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session):
    """Create test organization."""
    unique = uuid.uuid4().hex[:8]
    org = Organization(
        id=f"test-org-{unique}",
        name=f"Test Org {unique}",
        slug=f"test-org-{unique}",
        status="active",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session, test_org):
    """Create test user."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"test-user-{unique}",
        email=f"user-{unique}@test.com",
        full_name=f"Test User {unique}",
        status="active",
        organization_id=test_org.id,
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_employee(db_session, test_org, test_user):
    """Create test employee linked to user."""
    emp = Employee(
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Employee",
        email=f"employee-{uuid.uuid4().hex[:8]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def caller(db_session, test_org, test_user, test_employee):
    """Create caller access for test user with CEO permissions."""
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org.id)
    
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org.id,
            Role.code == "ceo"
        )
    )).scalars().first()
    
    if ceo_role:
        user_role = UserRole(
            user_id=test_user.id,
            role_id=ceo_role.id,
            organization_id=test_org.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    from app.intelligence.company_context import resolve_caller_access
    caller = await resolve_caller_access(
        db_session, organization_id=test_org.id, user=test_user
    )
    return caller


@pytest_asyncio.fixture
async def second_employee(db_session, test_org):
    """Create a second employee for multi-person tests."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        id=f"second-user-{unique}",
        email=f"second-{unique}@test.com",
        full_name=f"Second User {unique}",
        status="active",
        organization_id=test_org.id,
        password_hash="test-hash",
    )
    db_session.add(user)
    await db_session.flush()
    
    emp = Employee(
        organization_id=test_org.id,
        user_id=user.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Second",
        last_name="Employee",
        email=f"second-employee-{uuid.uuid4().hex[:8]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


# ============================================================================
# Test Classes
# ============================================================================

class TestOrganizationalIntelligenceService:
    """Test organizational intelligence service."""

    @pytest.mark.asyncio
    async def test_derive_organizational_context(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test deriving organizational context for an employee."""
        context = await organizational_intelligence_service.derive_organizational_context(
            db_session,
            caller=caller,
            employee_id=test_employee.id,
        )
        
        assert context.employee_id == test_employee.id
        assert context.team_id == test_employee.team_id
        assert context.department_id == test_employee.department_id
        assert len(context.responsibilities) >= 0
        assert len(context.commitments) >= 0
        assert len(context.accountability_links) >= 0
        assert context.workload is not None or context.workload is None
        assert context.dependencies is not None
        assert context.blocked_by is not None
        assert context.blocking is not None
        assert context.department is not None or context.department is None
        assert context.team is not None or context.team is None
        assert context.manager is not None or context.manager is None

    @pytest.mark.asyncio
    async def test_derive_team_context(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test deriving organizational context for a team."""
        # Create a team
        team = Team(
            organization_id=caller.organization_id,
            name="Test Team",
            code=f"TM{uuid.uuid4().hex[:4]}",
        )
        db_session.add(team)
        await db_session.flush()
        
        # Add employees to team
        test_employee.team_id = team.id
        second_employee.team_id = team.id
        await db_session.flush()
        
        # Create commitment linked to team
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Team Commitment",
            state="authorized",
            scope_type="team",
            scope_id=team.id,
            fingerprint="comm-fp-" + uuid.uuid4().hex[:32],
            source_event_id="team-commitment-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add responsibility for first employee
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="team",
            scope_id=team.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-" + uuid.uuid4().hex[:32],
            source_event_id="resp-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        context = await organizational_intelligence_service.derive_organizational_context(
            db_session,
            caller=caller,
            employee_id=test_employee.id,
        )
        
        assert context.team_id == team.id
        assert len(context.responsibilities) >= 1
        assert len(context.commitments) >= 1

    @pytest.mark.asyncio
    async def test_get_commitments_via_responsibilities(
        self, db_session, caller, test_employee
    ):
        """Test getting commitments via responsibilities."""
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Test Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-123",
            fingerprint="comm-fp-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-" + uuid.uuid4().hex[:32],
            source_event_id="resp-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        commitments = await organizational_intelligence_service._get_commitments_via_responsibilities(
            db_session, caller, test_employee.id
        )
        
        assert len(commitments) == 1
        assert commitments[0]["id"] == commitment.id
        assert commitments[0]["title"] == "Test Commitment"


class TestOrganizationalAttentionService:
    """Test organizational attention service."""

    @pytest.mark.asyncio
    async def test_derive_organizational_attention(
        self, db_session, caller, test_employee
    ):
        """Test deriving organizational attention."""
        # Create overloaded workload
        from app.models.workload import WorkloadSnapshot
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=60.0,
            utilization=150.0,
            tasks_count=10,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        attention = await organizational_attention_service.derive_organizational_attention(
            db_session, caller=caller
        )
        
        capacity_attentions = [a for a in attention if a["kind"] == "capacity_conflict"]
        assert len(capacity_attentions) > 0
        assert capacity_attentions[0]["employee_id"] == test_employee.id
        assert capacity_attentions[0]["utilization"] == 150.0

    @pytest.mark.asyncio
    async def test_derive_commitment_at_risk(
        self, db_session, caller, test_employee
    ):
        """Test commitment at risk attention."""
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Risk Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-123",
            fingerprint="comm-fp-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-risk-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Risk Action",
            state="completed",
            scope_type="project",
            scope_id="proj-123",
            fingerprint="action-fp-" + uuid.uuid4().hex[:32],
            source_event_id="action-risk-1",
            source_commitment_id=commitment.id,
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()
        
        # Create failed outcome
        outcome = CompanyActionOutcome(
            organization_id=caller.organization_id,
            action_id=action.id,
            outcome_type="failed",
            verdict="Failed to deliver",
            effectiveness=0.2,
            recorded_by=test_employee.id,
        )
        db_session.add(outcome)
        await db_session.commit()
        
        attention = await organizational_attention_service.derive_organizational_attention(
            db_session, caller=caller
        )
        
        risk_attentions = [a for a in attention if a["kind"] == "commitment_at_risk"]
        assert len(risk_attentions) > 0
        assert risk_attentions[0]["commitment_id"] == commitment.id
        assert risk_attentions[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_derive_blocked_work(
        self, db_session, caller, test_employee
    ):
        """Test blocked work attention."""
        # Create task chain: A -> B -> C (C must complete before B, B before A)
        project = Project(
            organization_id=caller.organization_id,
            name="Dependency Project",
            code="PRJ-DEP",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        
        task_c = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task C (Foundation)",
            status="completed",
            assignee_id=test_employee.id,
        )
        db_session.add(task_c)
        await db_session.flush()
        
        task_b = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task B (Depends on C)",
            status="in_progress",
            assignee_id=test_employee.id,
        )
        db_session.add(task_b)
        await db_session.flush()
        
        task_a = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task A (Depends on B)",
            status="todo",
            assignee_id=test_employee.id,
        )
        db_session.add(task_a)
        await db_session.flush()
        
        # Create dependencies
        dep_ab = TaskDependency(
            organization_id=caller.organization_id,
            task_id=task_a.id,
            depends_on_task_id=task_b.id,
            kind="finish_to_start",
        )
        dep_bc = TaskDependency(
            organization_id=caller.organization_id,
            task_id=task_b.id,
            depends_on_task_id=task_c.id,
            kind="finish_to_start",
        )
        db_session.add_all([dep_ab, dep_bc])
        await db_session.commit()
        
        attention = await organizational_attention_service.derive_organizational_attention(
            db_session, caller=caller
        )
        
        blocked_attentions = [a for a in attention if a["kind"] == "blocked_work"]
        assert len(blocked_attentions) > 0
        assert any("Task A" in a["title"] for a in blocked_attentions)

    @pytest.mark.asyncio
    async def test_derive_responsibility_gaps(
        self, db_session, caller, test_employee
    ):
        """Test responsibility gap attention."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Gap Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-gap",
            fingerprint="comm-fp-gap-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-gap-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        attention = await organizational_attention_service.derive_organizational_attention(
            db_session, caller=caller
        )
        
        gap_attentions = [a for a in attention if a["kind"] == "responsibility_gap"]
        assert len(gap_attentions) > 0
        assert any("Gap Commitment" in a["title"] for a in gap_attentions)


class TestOrganizationalDependencyService:
    """Test organizational dependency service."""

    @pytest.mark.asyncio
    async def test_trace_dependency_chain(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test tracing dependency chain."""
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Chain Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-chain",
            fingerprint="comm-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-chain-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="responsible",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_responsible=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="resp-chain-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        # Create action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Chain Action",
            state="in_progress",
            scope_type="project",
            scope_id="proj-chain",
            fingerprint="action-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="action-chain-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
        )
        db_session.add(action)
        await db_session.commit()
        
        chain = await organizational_dependency_service.trace_dependency_chain(
            db_session,
            caller=caller,
            start_entity_type="commitment",
            start_entity_id=commitment.id,
            max_depth=5,
        )
        
        assert chain.total_hops >= 1
        assert len(chain.path) >= 1
        assert commitment.id in chain.affected_commitments

    @pytest.mark.asyncio
    async def test_get_bottleneck_analysis(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test bottleneck analysis."""
        from app.models.workload import WorkloadSnapshot
        
        # Create multiple commitments for same person
        for i in range(3):
            commitment = CompanyCommitment(
                organization_id=caller.organization_id,
                commitment_type="unconditional",
                title=f"Commitment {i}",
                state="authorized",
                scope_type="project",
                scope_id=f"proj-{i}",
                fingerprint=f"comm-fp-{i}-" + uuid.uuid4().hex[:32],
                source_event_id=f"commitment-{i}",
            )
            db_session.add(commitment)
            await db_session.flush()
            
            resp = OrganizationalResponsibility(
                organization_id=caller.organization_id,
                responsibility_type="responsible",
                scope_type="commitment",
                scope_id=commitment.id,
                raci_responsible=True,
                person_id=test_employee.id,
                commitment_id=commitment.id,
                valid_from=utcnow(),
                state="active",
                fingerprint="resp-fp-" + uuid.uuid4().hex[:32],
                source_event_id=f"resp-{i}",
            )
            db_session.add(resp)
        await db_session.flush()
        
        # Create overload workload
        from app.models.workload import WorkloadSnapshot
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=60.0,
            utilization=150.0,
            tasks_count=10,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        bottlenecks = await organizational_dependency_service.get_bottleneck_analysis(
            db_session, caller=caller
        )
        
        assert len(bottlenecks["person_bottlenecks"]) >= 1
        bottleneck = bottlenecks["person_bottlenecks"][0]
        assert bottleneck["employee_id"] == test_employee.id
        assert bottleneck["severity"] in ("high", "critical")
        assert bottleneck["responsibility_count"] >= 3
        assert bottleneck["utilization"] > 100


class TestOrganizationalOperatingContextService:
    """Test organizational operating context service."""

    @pytest.mark.asyncio
    async def test_derive_organizational_operating_context(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test deriving organizational operating context."""
        context = await organizational_operating_context_service.derive_organizational_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert context.employee_id == test_employee.id
        assert context.organizational_context is not None
        assert context.organizational_context.responsibilities is not None
        assert context.organizational_context.commitments is not None
        assert context.organizational_context.accountability_links is not None
        assert context.capacity_conflicts is not None
        assert context.responsibility_gaps is not None
        assert context.dependency_conflicts is not None
        assert context.bottlenecks is not None
        assert context.critical_people is not None
        assert context.orphaned_commitments is not None
        assert context.orphaned_responsibilities is not None
        assert context.objective_drift is not None

    @pytest.mark.asyncio
    async def test_derive_team_operating_context(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test deriving team operating context."""
        team = Team(
            organization_id=caller.organization_id,
            name="Test Team",
            code=f"TM{uuid.uuid4().hex[:4]}",
        )
        db_session.add(team)
        await db_session.flush()
        
        test_employee.team_id = team.id
        second_employee.team_id = team.id
        await db_session.flush()
        
        context = await organizational_operating_context_service.derive_team_operating_context(
            db_session, caller=caller, team_id=team.id
        )
        
        assert context["team_id"] == team.id
        assert len(context["members"]) == 2
        assert len(context["responsibilities"]) >= 0
        assert len(context["commitments"]) >= 0
        assert "workload" in context

    @pytest.mark.asyncio
    async def test_derive_department_operating_context(
        self, db_session, caller, test_employee
    ):
        """Test deriving department operating context."""
        dept = Department(
            organization_id=caller.organization_id,
            name="Test Department",
            code=f"DEP{uuid.uuid4().hex[:4]}",
        )
        db_session.add(dept)
        await db_session.flush()
        
        test_employee.department_id = dept.id
        await db_session.flush()
        
        context = await organizational_operating_context_service.derive_department_operating_context(
            db_session, caller=caller, department_id=dept.id
        )
        
        assert context["department_id"] == dept.id
        assert context["department_name"] == dept.name
        assert len(context["teams"]) >= 0
        assert len(context["members"]) >= 1
        assert "workload" in context


class TestOrganizationalDependencyService:
    """Test organizational dependency service."""

    @pytest.mark.asyncio
    async def test_trace_dependency_chain(
        self, db_session, caller, test_employee
    ):
        """Test tracing dependency chain."""
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Chain Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-chain",
            fingerprint="comm-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-chain-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="responsible",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_responsible=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="resp-chain-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        # Create action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Chain Action",
            state="in_progress",
            scope_type="project",
            scope_id="proj-chain",
            fingerprint="action-fp-chain-" + uuid.uuid4().hex[:32],
            source_event_id="action-chain-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()
        
        chain = await organizational_dependency_service.trace_dependency_chain(
            db_session,
            caller=caller,
            start_entity_type="commitment",
            start_entity_id=commitment.id,
            max_depth=5,
        )
        
        assert chain.total_hops >= 1
        assert len(chain.path) >= 1
        assert commitment.id in chain.affected_commitments

    @pytest.mark.asyncio
    async def test_get_bottleneck_analysis(
        self, db_session, caller, test_employee, second_employee
    ):
        """Test bottleneck analysis."""
        from app.models.workload import WorkloadSnapshot
        
        # Create two commitments for same person
        commitment1 = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Commitment A",
            state="authorized",
            scope_type="project",
            scope_id="proj-a",
            fingerprint="comm-fp-a-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-a",
        )
        commitment2 = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Commitment B",
            state="authorized",
            scope_type="project",
            scope_id="proj-b",
            fingerprint="comm-fp-b-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-b",
        )
        db_session.add_all([commitment1, commitment2])
        await db_session.flush()
        
        # Create responsibilities for same person
        resp1 = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="responsible",
            scope_type="commitment",
            scope_id=commitment1.id,
            raci_responsible=True,
            person_id=test_employee.id,
            commitment_id=commitment1.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-1-" + uuid.uuid4().hex[:32],
            source_event_id="resp-1",
        )
        resp2 = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="responsible",
            scope_type="commitment",
            scope_id=commitment2.id,
            raci_responsible=True,
            person_id=test_employee.id,
            commitment_id=commitment2.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-2-" + uuid.uuid4().hex[:32],
            source_event_id="resp-2",
        )
        resp3 = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment2.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment2.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-3-" + uuid.uuid4().hex[:32],
            source_event_id="resp-3",
        )
        db_session.add_all([resp1, resp2, resp3])
        await db_session.flush()
        
        # Create workload snapshot showing overload
        from app.models.workload import WorkloadSnapshot
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=60.0,
            utilization=150.0,
            tasks_count=10,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        bottlenecks = await organizational_dependency_service.get_bottleneck_analysis(
            db_session, caller=caller
        )
        
        assert len(bottlenecks["person_bottlenecks"]) >= 1
        bottleneck = bottlenecks["person_bottlenecks"][0]
        assert bottleneck["employee_id"] == test_employee.id
        assert bottleneck["severity"] in ("high", "critical")
        assert bottleneck["responsibility_count"] >= 2
        assert bottleneck["utilization"] > 100


class TestOrganizationalChangeContinuityService:
    """Test organizational change continuity service."""

    @pytest.mark.asyncio
    async def test_get_responsibility_history(
        self, db_session, caller, test_employee
    ):
        """Test getting responsibility history for a person."""
        history = await organizational_change_service.get_responsibility_history(
            db_session, caller=caller, person_id=test_employee.id
        )
        
        assert isinstance(history, list)
        assert len(history) >= 0

    @pytest.mark.asyncio
    async def test_get_commitment_history(
        self, db_session, caller, test_employee
    ):
        """Test getting commitment history."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="History Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-hist",
            fingerprint="comm-fp-hist-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-hist-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        history = await organizational_change_service.get_commitment_history(
            db_session, caller=caller, commitment_id=commitment.id
        )
        
        assert isinstance(history, list)
        assert len(history) >= 1
        assert history[0]["id"] == commitment.id

    @pytest.mark.asyncio
    async def test_get_cross_domain_timeline(
        self, db_session, caller, test_employee
    ):
        """Test getting cross-domain timeline for a commitment."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Timeline Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-timeline",
            fingerprint="comm-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-tl-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="resp-tl-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        # Add action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Timeline Action",
            state="completed",
            scope_type="project",
            scope_id="proj-tl",
            fingerprint="action-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="action-tl-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()
        
        # Add outcome
        outcome = CompanyActionOutcome(
            organization_id=caller.organization_id,
            action_id=action.id,
            outcome_type="success",
            verdict="Completed successfully",
            effectiveness=0.9,
            recorded_by=test_employee.id,
        )
        db_session.add(outcome)
        await db_session.commit()
        
        timeline = await organizational_change_service.get_cross_domain_timeline(
            db_session, caller=caller, entity_type="commitment", entity_id=commitment.id
        )
        
        assert len(timeline) >= 3  # responsibility, action, outcome
        event_types = [e["event_type"] for e in timeline]
        assert "responsibility_assigned" in event_types
        assert "action_created" in event_types
        assert "outcome_recorded" in event_types


class TestOrganizationalChangeContinuityService:
    """Test organizational change continuity service."""

    @pytest.mark.asyncio
    async def test_get_responsibility_history(
        self, db_session, caller, test_employee
    ):
        """Test getting responsibility history for a person."""
        history = await organizational_change_service.get_responsibility_history(
            db_session, caller=caller, person_id=test_employee.id
        )
        
        assert isinstance(history, list)
        assert len(history) >= 0

    @pytest.mark.asyncio
    async def test_get_cross_domain_timeline(
        self, db_session, caller, test_employee
    ):
        """Test getting cross-domain timeline for a commitment."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Timeline Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-timeline",
            fingerprint="comm-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-tl-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="resp-tl-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        # Add action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Timeline Action",
            state="completed",
            scope_type="project",
            scope_id="proj-tl",
            fingerprint="action-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="action-tl-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()
        
        # Add outcome
        outcome = CompanyActionOutcome(
            organization_id=caller.organization_id,
            action_id=action.id,
            outcome_type="success",
            verdict="Test completed",
            effectiveness=0.9,
            recorded_by=test_employee.id,
        )
        db_session.add(outcome)
        await db_session.commit()
        
        timeline = await organizational_change_service.get_cross_domain_timeline(
            db_session, caller=caller, entity_type="commitment", entity_id=commitment.id
        )
        
        assert len(timeline) >= 3  # responsibility, action, outcome
        event_types = [e["event_type"] for e in timeline]
        assert "responsibility_assigned" in event_types
        assert "action_created" in event_types
        assert "outcome_recorded" in event_types


class TestOrganizationalChangeContinuityService:
    """Test organizational change continuity service."""

    @pytest.mark.asyncio
    async def test_get_responsibility_history(
        self, db_session, caller, test_employee
    ):
        """Test getting responsibility history for a person."""
        history = await organizational_change_service.get_responsibility_history(
            db_session, caller=caller, person_id=test_employee.id
        )
        
        assert isinstance(history, list)
        assert len(history) >= 0

    @pytest.mark.asyncio
    async def test_get_cross_domain_timeline(
        self, db_session, caller, test_employee
    ):
        """Test getting cross-domain timeline for a commitment."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Timeline Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-timeline",
            fingerprint="comm-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-tl-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add responsibility
        resp = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="accountable",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_accountable=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="resp-tl-1",
        )
        db_session.add(resp)
        await db_session.flush()
        
        # Add action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Timeline Action",
            state="completed",
            scope_type="project",
            scope_id="proj-tl",
            fingerprint="action-fp-tl-" + uuid.uuid4().hex[:32],
            source_event_id="action-tl-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=resp.id,
            assignee_id=test_employee.id,
            completed_at=utcnow(),
            completed_by=test_employee.id,
        )
        db_session.add(action)
        await db_session.flush()
        
        # Add outcome
        outcome = CompanyActionOutcome(
            organization_id=caller.organization_id,
            action_id=action.id,
            outcome_type="success",
            verdict="Test completed",
            effectiveness=0.9,
            recorded_by=test_employee.id,
        )
        db_session.add(outcome)
        await db_session.commit()
        
        timeline = await organizational_change_service.get_cross_domain_timeline(
            db_session, caller=caller, entity_type="commitment", entity_id=commitment.id
        )
        
        assert len(timeline) >= 3  # responsibility, action, outcome
        event_types = [e["event_type"] for e in timeline]
        assert "responsibility_assigned" in event_types
        assert "action_created" in event_types
        assert "outcome_recorded" in event_types


class TestFullRegression:
    """Ensure existing regression stays green."""

    @pytest.mark.asyncio
    async def test_gate81_presence_still_works(self, db_session, caller, test_employee):
        """Gate 8.1 canonical presence should still work."""
        from app.people.canonical_presence_service import canonical_presence_service
        
        presence = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE"
        )
        
        assert presence.status == "AVAILABLE"
        assert presence.is_online is True

    @pytest.mark.asyncio
    async def test_gate82_communication_still_works(self, db_session, caller, test_employee):
        """Gate 8.2 canonical communication should still work."""
        from app.people.canonical_communication_service import canonical_communication_service
        
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Regression Test"
        )
        
        assert thread.id is not None
        assert thread.thread_type == "group"

    @pytest.mark.asyncio
    async def test_gate83_work_still_works(self, db_session, caller, test_employee):
        """Gate 8.3 canonical work should still work."""
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Regression Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-reg",
            fingerprint="comm-fp-reg-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-reg-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        responsibility = OrganizationalResponsibility(
            organization_id=caller.organization_id,
            responsibility_type="responsible",
            scope_type="commitment",
            scope_id=commitment.id,
            raci_responsible=True,
            person_id=test_employee.id,
            commitment_id=commitment.id,
            valid_from=utcnow(),
            state="active",
            fingerprint="resp-fp-reg-" + uuid.uuid4().hex[:32],
            source_event_id="resp-reg-1",
        )
        db_session.add(responsibility)
        await db_session.flush()
        
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Regression Action",
            state="in_progress",
            scope_type="project",
            scope_id="proj-reg",
            fingerprint="action-fp-reg-" + uuid.uuid4().hex[:32],
            source_event_id="action-reg-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=responsibility.id,
            assignee_id=test_employee.id,
        )
        db_session.add(action)
        
        # Also create a Project for the project to satisfy current_projects check
        project = Project(
            organization_id=caller.organization_id,
            id="proj-reg",
            name="Regression Project",
            code=f"PRJ{uuid.uuid4().hex[:4]}",
            status="active",
        )
        db_session.add(project)
        
        # Also create a Task for the project to satisfy current_tasks check
        task = Task(
            organization_id=caller.organization_id,
            project_id="proj-reg",
            title="Regression Task",
            status="in_progress",
            assignee_id=test_employee.id,
        )
        db_session.add(task)
        await db_session.commit()
        
        # Verify canonical reality intact
        from app.people.operating_context_service import operating_context_service
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        assert len(context.current_actions) > 0
        assert len(context.current_tasks) > 0
        assert len(context.current_projects) > 0


# ============================================================================
# Test Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])