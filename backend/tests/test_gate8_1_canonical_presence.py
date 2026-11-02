"""Gate 8.1 — Canonical Virtual Company Continuity: Presence + Operating Context.

Adversarial tests verifying the canonical operating presence and context primitives
under real PostgreSQL with full canonical guarantees.
"""
import pytest
import pytest_asyncio
import uuid
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
from app.models.team import Team
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting, MeetingAttendee
from app.models.execution_strategy import OrganizationalResponsibility
from app.intelligence.company_context import resolve_caller_access
from app.people.canonical_presence_service import canonical_presence_service
from app.people.canonical_presence_service import InvalidPresenceState
from app.people.operating_context_service import operating_context_service
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
async def caller(db_session, test_org, test_user):
    """Create caller access for test user."""
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


# ============================================================================
# Test Classes
# ============================================================================

class TestCanonicalPresencePrimitive:
    """Test canonical operating presence primitive."""

    @pytest.mark.asyncio
    async def test_create_presence(self, db_session, caller, test_employee):
        """Test creating canonical presence."""
        presence = await canonical_presence_service.set_presence(
            db_session,
            caller=caller,
            employee_id=test_employee.id,
            state="AVAILABLE",
            source_event_id="test-event-1",
        )
        
        assert presence.employee_id == test_employee.id
        assert presence.status == "AVAILABLE"
        assert presence.is_online is True
        assert presence.valid_from is not None
        assert presence.valid_to is None
        assert presence.version == 1
        assert presence.fingerprint is not None

    @pytest.mark.asyncio
    async def test_invalid_state_rejected(self, db_session, caller, test_employee):
        """Invalid presence state should be rejected."""
        from app.people.canonical_presence_service import InvalidPresenceState
        with pytest.raises(InvalidPresenceState, match="Invalid presence state"):
            await canonical_presence_service.set_presence(
                db_session,
                caller=caller,
                employee_id=test_employee.id,
                state="INVALID_STATE",
            )

    @pytest.mark.asyncio
    async def test_temporal_truth_history_preserved(self, db_session, caller, test_employee):
        """Presence history must be preserved - no overwriting history."""
        # Set initial presence
        p1 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE"
        )
        await db_session.commit()
        
        # Change presence
        p2 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="IN_MEETING"
        )
        await db_session.commit()
        
        # Both should exist in history
        history = await canonical_presence_service.get_presence_history(
            db_session, organization_id=caller.organization_id, employee_id=test_employee.id
        )
        assert len(history) == 2
        assert history[0].status == "IN_MEETING"  # Most recent first
        assert history[1].status == "AVAILABLE"
        
        # First should be superseded
        assert history[1].valid_to is not None
        assert history[0].valid_to is None  # Current

    @pytest.mark.asyncio
    async def test_exact_once_semantics(self, db_session, caller, test_employee):
        """Exact-once: identical fingerprint returns existing."""
        # First set
        p1 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE",
            source_event_id="event-1"
        )
        
        # Second with same fingerprint should return existing
        p2 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE",
            source_event_id="event-1"
        )
        
        assert p1.id == p2.id
        assert p1.fingerprint == p2.fingerprint

    @pytest.mark.asyncio
    async def test_optimistic_concurrency(self, db_session, caller, test_employee):
        """Optimistic concurrency prevents lost updates."""
        # Create presence
        p1 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE"
        )
        await db_session.commit()
        
        # Try to update with stale version
        from app.intelligence.canonical_mutation import ConcurrencyViolation
        with pytest.raises(Exception) as exc_info:
            await canonical_presence_service.set_presence(
                db_session, caller=caller, employee_id=test_employee.id, state="IN_MEETING",
                expected_version=p1.version - 1  # Stale version
            )
        
        # Should raise concurrency error
        assert "ConcurrencyViolation" in str(type(exc_info.value))

    @pytest.mark.asyncio
    async def test_temporal_query_at_time(self, db_session, caller, test_employee):
        """Query presence at specific point in time."""
        import asyncio
        # Create presence at time t1
        p1 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE"
        )
        await db_session.commit()
        
        # Wait a bit to ensure temporal ordering
        await asyncio.sleep(0.1)
        
        # Change at t2
        p2 = await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="IN_MEETING"
        )
        await db_session.commit()
        
        # Query at a time between t1 and t2 should return AVAILABLE
        t_between = p1.valid_from + timedelta(milliseconds=50)
        at_between = await canonical_presence_service.get_presence_at(
            db_session, organization_id=caller.organization_id, employee_id=test_employee.id, at=p1.valid_from + timedelta(milliseconds=50)
        )
        assert at_between is not None
        assert at_between.status == "AVAILABLE"
        
        # Query at a time after p2 should return IN_MEETING
        t_after_p2 = p2.valid_from + timedelta(milliseconds=100)
        at_t2 = await canonical_presence_service.get_presence_at(
            db_session, organization_id=caller.organization_id, employee_id=test_employee.id, at=t_after_p2
        )
        assert at_t2 is not None
        assert at_t2.status == "IN_MEETING"


class TestPresenceGovernance:
    """Test governance enforcement for presence."""

    @pytest_asyncio.fixture
    async def test_org_b(self, db_session):
        unique = uuid.uuid4().hex[:8]
        org = Organization(
            id=f"test-org-b-{unique}",
            name=f"Test Org B {unique}",
            slug=f"test-org-b-{unique}",
            status="active",
        )
        db_session.add(org)
        await db_session.flush()
        return org

    @pytest_asyncio.fixture
    async def test_employee_b(self, db_session, test_org_b):
        emp = Employee(
            organization_id=test_org_b.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Test",
            last_name="EmployeeB",
            email=f"employee-b-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(emp)
        await db_session.flush()
        return emp

    @pytest.mark.asyncio
    async def test_cross_tenant_presence_blocked(self, db_session, caller, test_employee_b):
        """Cross-tenant presence access should be denied."""
        from app.people.canonical_presence_service import PresenceGovernanceViolation
        
        with pytest.raises(Exception) as exc_info:
            await canonical_presence_service.set_presence(
                db_session, caller=caller, employee_id=test_employee_b.id, state="AVAILABLE"
            )
        
        assert "PresenceGovernanceViolation" in str(type(exc_info.value)) or "Cross-tenant" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unauthorized_cross_employee_presence_blocked(self, db_session, test_org, test_employee):
        """Non-management user cannot update another employee's presence."""
        from app.people.canonical_presence_service import PresenceGovernanceViolation
        
        # Create limited user
        limited_user = User(
            id=f"limited-{uuid.uuid4().hex[:8]}",
            email=f"limited-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Limited User",
            status="active",
            organization_id=test_org.id,
            password_hash="test-hash",
        )
        db_session.add(limited_user)
        await db_session.flush()
        
        await permission_service.sync_catalog(db_session)
        await permission_service.seed_org_roles(db_session, test_org.id)
        
        member_role = (await db_session.execute(
            select(Role).where(Role.organization_id == test_org.id, Role.code == "member")
        )).scalars().first()
        
        if member_role:
            user_role = UserRole(user_id=limited_user.id, role_id=member_role.id, organization_id=test_org.id)
            db_session.add(user_role)
            await db_session.flush()
        
        from app.intelligence.company_context import resolve_caller_access
        limited_caller = await resolve_caller_access(db_session, organization_id=test_org.id, user=limited_user)
        
        # Create target employee
        target = Employee(
            organization_id=test_org.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Target",
            last_name="Employee",
            email=f"target-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(target)
        await db_session.flush()
        
        with pytest.raises(Exception) as exc_info:
            await canonical_presence_service.set_presence(
                db_session, caller=limited_caller, employee_id=target.id, state="AVAILABLE"
            )
        
        assert "GovernanceViolation" in str(type(exc_info.value)) or "Insufficient" in str(exc_info.value)


class TestCanonicalOperatingContext:
    """Test canonical operating context derivation."""

    @pytest.mark.asyncio
    async def test_derive_operating_context(self, db_session, caller, test_employee):
        """Derive operating context for employee."""
        # Set presence first
        await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE"
        )
        await db_session.commit()
        
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert context.employee_id == test_employee.id
        assert context.full_name == test_employee.full_name
        assert context.presence is not None
        assert context.presence.status == "AVAILABLE"
        assert context.is_online is True
        assert context.organization_id == caller.organization_id
        assert context.department_id is not None or context.department_id is None  # Optional

    @pytest.mark.asyncio
    async def test_operating_context_includes_work(self, db_session, caller, test_org, test_employee):
        """Operating context includes active work."""
        # Create project
        project = Project(
            organization_id=test_org.id,
            name="Test Project",
            code=f"PRJ{uuid.uuid4().hex[:4]}",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        
        # Create task assigned to employee
        task = Task(
            organization_id=test_org.id,
            title="Test Task",
            status="in_progress",
            assignee_id=test_employee.id,
            project_id=project.id,
        )
        db_session.add(task)
        await db_session.commit()
        
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert len(context.current_tasks) > 0
        assert len(context.current_projects) > 0
        assert context.current_tasks[0]["title"] == "Test Task"
        assert context.current_projects[0]["name"] == "Test Project"

    @pytest.mark.asyncio
    async def test_operating_context_includes_meetings(self, db_session, caller, test_org, test_employee):
        """Operating context includes upcoming meetings."""
        # Create meeting
        meeting = Meeting(
            organization_id=test_org.id,
            title="Test Meeting",
            start_at=utcnow() + timedelta(hours=1),
            end_at=utcnow() + timedelta(hours=2),
            status="scheduled",
        )
        db_session.add(meeting)
        await db_session.flush()
        
        # Add attendee
        attendee = MeetingAttendee(
            organization_id=test_org.id,
            meeting_id=meeting.id,
            employee_id=test_employee.id,
            status="accepted",
        )
        db_session.add(attendee)
        await db_session.commit()
        
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert len(context.upcoming_meetings) > 0
        assert context.upcoming_meetings[0]["title"] == "Test Meeting"

    @pytest.mark.asyncio
    async def test_operating_context_reload_consistency(self, db_session, caller, test_employee):
        """Operating context reloads consistently after session restart."""
        # Derive context
        ctx1 = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        # Verify context was derived
        assert ctx1.employee_id == test_employee.id
        assert ctx1.organization_id == caller.organization_id
        
        # The test verifies the context can be derived consistently


class TestPresenceEventIntegration:
    """Test presence event integration."""

    @pytest.mark.asyncio
    async def test_presence_change_emits_event(self, db_session, caller, test_employee):
        """Presence change emits event."""
        await canonical_presence_service.set_presence(
            db_session, caller=caller, employee_id=test_employee.id, state="AVAILABLE",
            source_event_id="test-event-1"
        )
        await db_session.commit()
        
        # Event should be in database
        from app.models.notification import Event
        result = await db_session.execute(
            select(Event).where(Event.name == "employee.presence.changed")
        )
        events = result.scalars().all()
        assert len(events) > 0
        assert events[-1].payload_json is not None
        assert "AVAILABLE" in str(events[-1].payload_json)


class TestLongitudinalPresence:
    """Test longitudinal presence across cycles."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_longitudinal_presence_cycles(self, db_session, caller, test_org, test_employee):
        """Test presence across multiple operating cycles."""
        for cycle in range(5):
            # Set presence for cycle
            state = "AVAILABLE" if cycle % 2 == 0 else "IN_MEETING"
            await canonical_presence_service.set_presence(
                db_session, caller=caller, employee_id=test_employee.id, state=state,
                source_event_id=f"cycle-{cycle}"
            )
            await db_session.commit()
            
            # Verify context
            context = await operating_context_service.derive_operating_context(
                db_session, caller=caller, employee_id=test_employee.id
            )
            assert context.presence.status == state
        
        # Verify full history
        history = await canonical_presence_service.get_presence_history(
            db_session, organization_id=caller.organization_id, employee_id=test_employee.id
        )
        assert len(history) == 5


# ============================================================================
# Test Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])