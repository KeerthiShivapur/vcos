"""Gate 8.6 — Canonical Resource & Organizational Capacity Continuity Tests.

Tests for organizational capacity intelligence derived from canonical reality.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee, EmployeeAvailability, EmployeeSkill
from app.models.team import Team, TeamMember
from app.models.department import Department
from app.models.project import Project, ProjectMember
from app.models.task import Task, TaskDependency
from app.models.workload import WorkloadSnapshot
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilityProjectLink,
    CapabilitySignal,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.skills_intelligence import CanonicalSkill, Expertise as ExpertiseState, ExpertiseEvidence
from app.models.skill import Skill as LegacySkill
from app.models.skill_gap import SkillGap, SkillSnapshot
from app.intelligence.organizational_capacity_service import (
    organizational_capacity_service,
    CapacityConflict,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session):
    """Create test organization."""
    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session, test_org):
    """Create test user."""
    user = User(
        organization_id=test_org.id,
        email=f"test{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        full_name="Test User",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_employee(db_session, test_org, test_user):
    """Create test employee with user link."""
    emp = Employee(
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Employee",
        email=f"employee{uuid.uuid4().hex[:6]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def second_employee(db_session, test_org):
    """Create second employee."""
    emp = Employee(
        organization_id=test_org.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Second",
        last_name="Employee",
        email=f"employee2-{uuid.uuid4().hex[:6]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def caller(db_session, test_org, test_user, test_employee):
    """Create caller access for test user with CEO permissions."""
    from app.models.role import Role, UserRole
    from app.services.permission_service import permission_service
    
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
    
    caller = await resolve_caller_access(
        db_session, organization_id=test_org.id, user=test_user
    )
    caller.employee_id = test_employee.id
    return caller


@pytest_asyncio.fixture
async def test_team(db_session, test_org, test_employee):
    """Create test team."""
    team = Team(
        organization_id=test_org.id,
        name="Test Team",
        code=f"TM{uuid.uuid4().hex[:4]}",
    )
    db_session.add(team)
    await db_session.flush()
    
    test_employee.team_id = team.id
    await db_session.flush()
    return team


@pytest_asyncio.fixture
async def test_department(db_session, test_org):
    """Create test department."""
    dept = Department(
        organization_id=test_org.id,
        name="Test Department",
        code=f"DEP{uuid.uuid4().hex[:4]}",
    )
    db_session.add(dept)
    await db_session.flush()
    return dept


@pytest_asyncio.fixture
async def test_skill(db_session, test_org):
    """Create test canonical skill."""
    skill = CanonicalSkill(
        organization_id=test_org.id,
        canonical_name="Python Development",
        category="Engineering",
        description="Python programming expertise",
    )
    db_session.add(skill)
    await db_session.flush()
    return skill


@pytest_asyncio.fixture
async def test_legacy_skill(db_session, test_org):
    """Create test legacy skill."""
    skill = LegacySkill(
        organization_id=test_org.id,
        name="Python Development",
        category="Engineering",
        description="Python programming expertise",
    )
    db_session.add(skill)
    await db_session.flush()
    return skill


# ============================================================================
# Person Capacity Tests
# ============================================================================

class TestPersonCapacity:
    """Test person-level capacity derivation."""

    @pytest.mark.asyncio
    async def test_derive_person_capacity_basic(
        self, db_session, caller, test_employee
    ):
        """Test basic person capacity derivation."""
        # Create workload snapshot
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=30.0,
            utilization=75.0,
            tasks_count=5,
            is_overloaded=False,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="person",
            scope_id=test_employee.id,
        )
        
        assert context.scope_type == "person"
        assert context.scope_id == test_employee.id
        assert context.total_potential == 40
        assert context.total_committed == 30
        assert context.total_available == 10
        assert context.utilization == 75.0
        assert context.capacity_state == "available"

    @pytest.mark.asyncio
    async def test_derive_person_capacity_overloaded(
        self, db_session, caller, test_employee
    ):
        """Test person capacity when overloaded."""
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=50.0,
            utilization=125.0,
            tasks_count=8,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="person",
            scope_id=test_employee.id,
        )
        
        assert context.utilization == 125.0
        assert context.capacity_state == "constrained"
        assert context.total_committed == 50
        assert context.total_available == 0  # max(0, 40-50) = 0

    @pytest.mark.asyncio
    async def test_derive_person_capacity_with_skills(
        self, db_session, caller, test_employee, test_skill
    ):
        """Test person capacity with skill details."""
        # Add skill to employee
        emp_skill = EmployeeSkill(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            skill_id=test_skill.id,
            level=4,
            years_experience=5.0,
            verified=True,
        )
        db_session.add(emp_skill)
        
        # Add expertise
        expertise = ExpertiseState(
            organization_id=caller.organization_id,
            person_id=test_employee.id,
            skill_id=test_skill.id,
            score=60.0,
            evidence_count=10,
            lifecycle="strong",
        )
        db_session.add(expertise)
        
        # Add OrgCapability
        org_cap = OrgCapability(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            canonical_name="Python Development",
            category="Engineering",
            lifecycle="strong",
            expert_count=1,
            strong_expert_count=1,
            evidence_count=10,
            capacity_potential=1,
            capacity_committed=1,
            capacity_reserved=0,
            capacity_available=0,
            capacity_state="constrained",
            demand_count=1,
            demand_state="low",
        )
        db_session.add(org_cap)
        
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=30.0,
            utilization=75.0,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="person",
            scope_id=test_employee.id,
        )
        
        assert len(context.capability_details) >= 1
        cap_detail = context.capability_details[0]
        assert cap_detail["skill_id"] == test_skill.id
        assert cap_detail["is_expert"] is True


# ============================================================================
# Team Capacity Tests
# ============================================================================

class TestTeamCapacity:
    """Test team-level capacity derivation."""

    @pytest.mark.asyncio
    async def test_derive_team_capacity(
        self, db_session, caller, test_employee, second_employee, test_team
    ):
        """Test team capacity derivation."""
        # Assign both employees to team
        test_employee.team_id = test_team.id
        second_employee.team_id = test_team.id
        
        # Workload for first employee
        workload1 = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=35.0,
            utilization=87.5,
            is_overloaded=False,
        )
        
        # Workload for second employee (overloaded)
        workload2 = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=second_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=50.0,
            utilization=125.0,
            is_overloaded=True,
        )
        
        db_session.add_all([workload1, workload2])
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="team",
            scope_id=test_team.id,
        )
        
        assert context.scope_type == "team"
        assert context.scope_id == test_team.id
        assert context.total_potential == 80
        assert context.total_committed == 85
        assert context.total_available == 0  # max(0, 80-85)
        assert context.capacity_state == "constrained"  # one overloaded member


# ============================================================================
# Department Capacity Tests
# ============================================================================

class TestDepartmentCapacity:
    """Test department-level capacity derivation."""

    @pytest.mark.asyncio
    async def test_derive_department_capacity(
        self, db_session, caller, test_employee, test_department
    ):
        """Test department capacity derivation."""
        test_employee.department_id = test_department.id
        
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=20.0,
            utilization=50.0,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="department",
            scope_id=test_department.id,
        )
        
        assert context.scope_type == "department"
        assert context.scope_id == test_department.id
        assert context.total_potential == 40
        assert context.total_committed == 20
        assert context.utilization == 50.0
        assert context.capacity_state == "available"


# ============================================================================
# Organization Capacity Tests
# ============================================================================

class TestOrganizationCapacity:
    """Test organization-wide capacity derivation."""

    @pytest.mark.asyncio
    async def test_derive_organization_capacity(
        self, db_session, caller, test_skill
    ):
        """Test organization capacity derivation."""
        org_cap = OrgCapability(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            canonical_name="Python Development",
            category="Engineering",
            lifecycle="strong",
            expert_count=3,
            strong_expert_count=2,
            evidence_count=50,
            capacity_potential=3,
            capacity_committed=2,
            capacity_reserved=0,
            capacity_available=1,
            capacity_state="available",
            demand_count=2,
            demand_state="low",
            concentration_share=0.4,
        )
        db_session.add(org_cap)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session,
            caller=caller,
            scope_type="organization",
        )
        
        assert context.scope_type == "organization"
        assert context.total_potential == 3
        assert context.total_committed == 2
        assert context.total_available == 1
        assert context.total_demand == 2
        assert len(context.capability_details) == 1
        assert context.capability_details[0]["capability_name"] == "Python Development"


# ============================================================================
# Capability Capacity Tests
# ============================================================================

class TestCapabilityCapacity:
    """Test capability-specific capacity queries."""

    @pytest.mark.asyncio
    async def test_get_capability_capacity(
        self, db_session, caller, test_skill
    ):
        """Test getting detailed capability capacity."""
        org_cap = OrgCapability(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            canonical_name="Python Development",
            category="Engineering",
            lifecycle="strong",
            expert_count=3,
            strong_expert_count=2,
            evidence_count=50,
            capacity_potential=3,
            capacity_committed=2,
            capacity_reserved=1,
            capacity_available=0,
            capacity_state="constrained",
            demand_count=3,
            demand_state="high",
            concentration_share=0.5,
        )
        db_session.add(org_cap)
        
        # Add project link
        project_link = CapabilityProjectLink(
            organization_id=caller.organization_id,
            project_id="proj-1",
            project_name="Project Alpha",
            skill_id=test_skill.id,
            skill_name="Python Development",
            source_event_id="evt-1",
            status="active",
        )
        db_session.add(project_link)
        
        # Add allocation demand
        alloc_demand = AllocationDemand(
            organization_id=caller.organization_id,
            project_id="proj-1",
            capability="Python Development",
            units=2,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            proficiency="high",
        )
        db_session.add(alloc_demand)
        
        # Add capacity allocation
        alloc = CapacityAllocation(
            organization_id=caller.organization_id,
            project_id="proj-1",
            project_label="Project Alpha",
            capability="Python Development",
            units=2,
            window_start=date.today(),
            window_end=date.today() + timedelta(days=30),
            status="active",
            source_event_id="evt-2",
        )
        db_session.add(alloc)
        
        # Add signal
        signal = CapabilitySignal(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            skill_name="Python Development",
            kind="capacity_constraint",
            severity="warning",
            detail="Every Python Development expert is committed",
            status="open",
        )
        db_session.add(signal)
        
        await db_session.commit()
        
        result = await organizational_capacity_service.get_capability_capacity(
            db_session,
            caller=caller,
            capability_name="Python Development",
        )
        
        assert result["found"] is True
        assert result["capability"] == "Python Development"
        assert result["lifecycle"] == "strong"
        assert result["capacity"]["available"] == 0
        assert result["capacity"]["state"] == "constrained"
        assert result["demand"]["projects"] == 1
        assert result["demand"]["allocation_demands"] == 1
        assert len(result["allocations"]) == 1
        assert len(result["signals"]) == 1
        assert result["signals"][0]["kind"] == "capacity_constraint"


# ============================================================================
# Capacity Conflict Detection Tests
# ============================================================================

class TestCapacityConflicts:
    """Test capacity conflict detection."""

    @pytest.mark.asyncio
    async def test_detect_person_capacity_deficit(
        self, db_session, caller, test_employee
    ):
        """Test detection of person capacity deficit."""
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=50.0,
            utilization=125.0,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        conflicts = await organizational_capacity_service.detect_capacity_conflicts(
            db_session, caller=caller
        )
        
        person_conflicts = [c for c in conflicts if c.kind == "capacity_deficit" and c.scope_type == "person"]
        assert len(person_conflicts) >= 1
        conflict = person_conflicts[0]
        assert conflict.severity in ("high", "critical")
        assert conflict.scope_id == test_employee.id
        assert conflict.deficit > 0
        assert "overloaded" in conflict.risk_factors

    @pytest.mark.asyncio
    async def test_detect_capability_gap(
        self, db_session, caller, test_skill
    ):
        """Test detection of capability gap."""
        org_cap = OrgCapability(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            canonical_name="Python Development",
            category="Engineering",
            lifecycle="strong",
            expert_count=1,
            strong_expert_count=1,
            evidence_count=10,
            capacity_potential=1,
            capacity_committed=1,
            capacity_reserved=0,
            capacity_available=0,
            capacity_state="constrained",
            demand_count=2,
            demand_state="high",
        )
        db_session.add(org_cap)
        await db_session.commit()
        
        conflicts = await organizational_capacity_service.detect_capacity_conflicts(
            db_session, caller=caller
        )
        
        capability_conflicts = [c for c in conflicts if c.kind == "capability_gap"]
        assert len(capability_conflicts) >= 1
        conflict = capability_conflicts[0]
        assert conflict.capability == "Python Development"
        assert conflict.required == 2
        assert conflict.available == 0
        assert conflict.deficit == 2

    @pytest.mark.asyncio
    async def test_detect_concentration_risk(
        self, db_session, caller, test_skill
    ):
        """Test detection of concentration risk."""
        org_cap = OrgCapability(
            organization_id=caller.organization_id,
            skill_id=test_skill.id,
            canonical_name="Python Development",
            category="Engineering",
            lifecycle="strong",
            expert_count=2,
            evidence_count=100,
            concentration_share=0.75,  # High concentration
            second_share=0.15,
        )
        db_session.add(org_cap)
        await db_session.commit()
        
        conflicts = await organizational_capacity_service.detect_capacity_conflicts(
            db_session, caller=caller
        )
        
        concentration_conflicts = [c for c in conflicts if c.kind == "concentration_risk"]
        assert len(concentration_conflicts) >= 1
        conflict = concentration_conflicts[0]
        assert conflict.severity == "critical"
        assert conflict.capability == "Python Development"
        assert "single_point_of_failure" in conflict.risk_factors


# ============================================================================
# Capacity Deficit Propagation Tests
# ============================================================================

class TestCapacityPropagation:
    """Test capacity deficit propagation through organizational chain."""

    @pytest.mark.asyncio
    async def test_propagate_capacity_deficit(
        self, db_session, caller, test_employee, test_skill
    ):
        """Test propagation of person capacity deficit."""
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Test Commitment",
            state="active",
            scope_type="project",
            scope_id="proj-1",
            fingerprint="comm-fp-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Create responsibility linking person to commitment
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
            fingerprint="resp-fp-" + uuid.uuid4().hex[:32],
            source_event_id="resp-1",
        )
        db_session.add(responsibility)
        
        # Create goal first (required for objective)
        goal = CompanyGoal(
            organization_id=caller.organization_id,
            title="Test Goal",
            status="active",
            kind="other",
            priority=3,
        )
        db_session.add(goal)
        await db_session.flush()
        
        # Create objective
        objective = CompanyObjective(
            organization_id=caller.organization_id,
            goal_id=goal.id,
            title="Test Objective",
            status="active",
            fingerprint="obj-fp-" + uuid.uuid4().hex[:32],
        )
        db_session.add(objective)
        await db_session.flush()
        
        commitment.objective_id = objective.id
        
        # Create initiative
        initiative = CompanyInitiative(
            organization_id=caller.organization_id,
            objective_id=objective.id,
            title="Test Initiative",
            status="active",
            fingerprint="init-fp-" + uuid.uuid4().hex[:32],
        )
        db_session.add(initiative)
        
        # Create action
        action = CompanyAction(
            organization_id=caller.organization_id,
            action_type="task",
            title="Test Action",
            state="in_progress",
            scope_type="project",
            scope_id="proj-1",
            fingerprint="action-fp-" + uuid.uuid4().hex[:32],
            source_event_id="action-1",
            source_commitment_id=commitment.id,
            source_responsibility_id=responsibility.id,
            assignee_id=test_employee.id,
            target_type="task",
            target_id="",  # Will be set after task creation
        )
        db_session.add(action)
        await db_session.flush()
        
        # Create task
        task = Task(
            organization_id=caller.organization_id,
            project_id="proj-1",
            title="Test Task",
            status="in_progress",
            assignee_id=test_employee.id,
        )
        db_session.add(task)
        await db_session.flush()
        
        # Link action to task
        action.target_id = task.id
        await db_session.commit()
        
        propagation = await organizational_capacity_service.propagate_capacity_deficit(
            db_session,
            caller=caller,
            person_id=test_employee.id,
        )
        
        assert "source_person_id" in propagation
        assert propagation["source_person_id"] == test_employee.id
        assert propagation["responsibilities_affected"] == 1
        assert propagation["commitments_affected"] == 1
        assert propagation["objectives_affected"] == 1
        assert propagation["initiatives_affected"] == 1
        assert propagation["actions_affected"] == 1
        assert propagation["tasks_affected"] == 1
        assert len(propagation["commitments"]) == 1
        assert propagation["commitments"][0]["id"] == commitment.id
        assert len(propagation["objectives"]) == 1
        assert propagation["objectives"][0]["id"] == objective.id


# ============================================================================
# Regression Tests
# ============================================================================

class TestFullRegression:
    """Ensure existing regression stays green."""

    @pytest.mark.asyncio
    async def test_gate85_org_intelligence_still_works(
        self, db_session, caller, test_employee
    ):
        """Gate 8.5 organizational intelligence should still work."""
        from app.intelligence.organizational_intelligence_service import organizational_intelligence_service
        
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=20.0,
            utilization=50.0,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_intelligence_service.derive_organizational_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert context.employee_id == test_employee.id
        assert context.workload is not None
        assert context.utilization == 50.0

    @pytest.mark.asyncio
    async def test_gate85_org_attention_still_works(
        self, db_session, caller, test_employee
    ):
        """Gate 8.5 organizational attention should still work."""
        from app.intelligence.organizational_attention_service import organizational_attention_service
        
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=50.0,
            utilization=125.0,
            is_overloaded=True,
        )
        db_session.add(workload)
        await db_session.commit()
        
        attention = await organizational_attention_service.derive_organizational_attention(
            db_session, caller=caller
        )
        
        capacity_conflicts = [a for a in attention if a["kind"] == "capacity_conflict"]
        assert len(capacity_conflicts) >= 1


# ============================================================================
# Test Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])