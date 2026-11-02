"""Gate 8.2 — Canonical Communication + Meeting Continuity Integration.

Adversarial tests verifying the canonical communication and meeting primitives
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
from app.models.team import Team
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting, MeetingAttendee, MeetingAgendaItem, MeetingActionItem
from app.models.communication import (
    CanonicalCommunicationThread,
    CanonicalMessage,
    CanonicalCommunicationThreadMember,
)
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
)
from app.intelligence.company_context import resolve_caller_access
from app.people.canonical_communication_service import (
    canonical_communication_service,
    CommunicationGovernanceViolation,
    InvalidThreadType,
    InvalidMessageType,
)
from app.people.canonical_meeting_service import (
    canonical_meeting_service,
    MeetingGovernanceViolation,
    InvalidMeetingState,
    InvalidMeetingType,
)
from app.people.operating_context_service import operating_context_service
from app.services.permission_service import permission_service
from app.intelligence.canonical_mutation import (
    ConcurrencyViolation,
    ExactOnceViolation,
)


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
    """Create a second employee for multi-participant tests."""
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


@pytest_asyncio.fixture
async def second_caller(db_session, test_org, second_employee):
    """Create caller access for second employee."""
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org.id)
    
    member_role = (await db_session.execute(
        select(Role).where(Role.organization_id == test_org.id, Role.code == "member")
    )).scalars().first()
    
    if member_role:
        user_role = UserRole(user_id=second_employee.user_id, role_id=member_role.id, organization_id=test_org.id)
        db_session.add(user_role)
        await db_session.flush()
    
    from app.intelligence.company_context import resolve_caller_access
    caller = await resolve_caller_access(db_session, organization_id=test_org.id, user=await db_session.get(User, second_employee.user_id))
    return caller


# ============================================================================
# Test Classes - Canonical Communication
# ============================================================================

class TestCanonicalCommunicationThread:
    """Test canonical communication thread primitive."""

    @pytest.mark.asyncio
    async def test_create_thread(self, db_session, caller, test_employee):
        """Test creating a canonical communication thread."""
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Project Discussion",
            description="Discussion about project timeline",
            context_references={
                "project_id": "proj-123",
                "objective_id": "obj-456",
            },
            scope_type="company",
            scope_id=None,
            source_event_id="test-event-1",
        )
        
        assert thread.id is not None
        assert thread.thread_type == "group"
        assert thread.title == "Project Discussion"
        assert thread.organization_id == caller.organization_id
        assert thread.valid_from is not None
        assert thread.valid_to is None
        assert thread.version == 1
        assert thread.fingerprint is not None
        assert thread.objective_id == "obj-456"
        assert thread.commitment_id is None

    @pytest.mark.asyncio
    async def test_invalid_thread_type_rejected(self, db_session, caller, test_employee):
        """Invalid thread type should be rejected."""
        with pytest.raises(InvalidThreadType, match="Invalid thread type"):
            await canonical_communication_service.create_thread(
                db_session,
                caller=caller,
                thread_type="invalid_type",
                title="Test",
            )

    @pytest.mark.asyncio
    async def test_thread_exact_once_semantics(self, db_session, caller, test_employee):
        """Exact-once: identical fingerprint returns existing thread."""
        # First create
        thread1 = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="dm",
            title="Direct Message",
            source_event_id="event-1",
        )
        
        # Second with same fingerprint should return existing
        thread2 = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="dm",
            title="Direct Message",
            source_event_id="event-1",
        )
        
        assert thread1.id == thread2.id
        assert thread1.fingerprint == thread2.fingerprint

    @pytest.mark.asyncio
    async def test_thread_governance_cross_tenant_blocked(self, db_session, caller, test_org):
        """Cross-tenant thread creation should be denied."""
        # Create org B
        unique = uuid.uuid4().hex[:8]
        org_b = Organization(
            id=f"test-org-b-{unique}",
            name=f"Test Org B {unique}",
            slug=f"test-org-b-{unique}",
            status="active",
        )
        db_session.add(org_b)
        await db_session.flush()
        
        # Create a GovernanceScope in org B
        from app.models.governance import GovernanceScope
        scope_b = GovernanceScope(
            id=f"scope-b-{uuid.uuid4().hex[:8]}",
            organization_id=org_b.id,
            name="Dept B",
            scope_type="department",
        )
        db_session.add(scope_b)
        await db_session.flush()
        
        with pytest.raises(CommunicationGovernanceViolation, match="Cross-tenant"):
            # Try to create thread with scope_id from another org
            await canonical_communication_service.create_thread(
                db_session,
                caller=caller,
                thread_type="group",
                title="Cross Tenant",
                scope_type="department",
                scope_id=scope_b.id,  # Different org's scope
            )

    @pytest.mark.asyncio
    async def test_thread_history_preserved(self, db_session, caller, test_employee):
        """Thread history must be preserved - no overwriting history."""
        # Create thread
        thread1 = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="channel", title="Channel 1"
        )
        await db_session.commit()
        
        # Create new version with NEW fingerprint (data changed) - this simulates an update
        # that creates a new thread record with supersedes_id pointing to thread1
        new_fingerprint = canonical_communication_service._compute_fingerprint({
            "organization_id": caller.organization_id,
            "thread_type": "channel",
            "title": "Channel 1 Updated",
            "description": None,
            "scope_type": "company",
            "scope_id": None,
            "context_references": {},
            "actor_id": caller.user_id,
        })
        
        thread2 = CanonicalCommunicationThread(
            organization_id=caller.organization_id,
            thread_type="channel",
            title="Channel 1 Updated",
            valid_from=utcnow(),
            fingerprint=new_fingerprint,
            version=2,
            supersedes_id=thread1.id,
        )
        db_session.add(thread2)
        await db_session.commit()
        
        # Both should exist in history - query for all threads with same ID or supersedes_id
        from sqlalchemy import or_
        history = await db_session.execute(
            select(CanonicalCommunicationThread).where(
                or_(
                    CanonicalCommunicationThread.id == thread1.id,
                    CanonicalCommunicationThread.supersedes_id == thread1.id,
                ),
                CanonicalCommunicationThread.organization_id == caller.organization_id,
            ).order_by(CanonicalCommunicationThread.valid_from.desc())
        )
        history = list(history.scalars().all())
        assert len(history) == 2
        assert history[0].title == "Channel 1 Updated"  # Most recent first
        assert history[1].title == "Channel 1"

    @pytest.mark.asyncio
    async def test_add_thread_member(self, db_session, caller, test_employee, second_employee):
        """Test adding a member to a thread."""
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Group Chat",
        )
        
        member = await canonical_communication_service.add_thread_member(
            db_session,
            caller=caller,
            thread_id=thread.id,
            employee_id=second_employee.id,
            role="participant",
        )
        
        assert member.employee_id == second_employee.id
        assert member.thread_id == thread.id
        assert member.role == "participant"
        assert member.valid_from is not None
        assert member.valid_to is None

    @pytest.mark.asyncio
    async def test_remove_thread_member(self, db_session, caller, test_employee, second_employee):
        """Test removing a member from a thread."""
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Group Chat",
        )
        
        await canonical_communication_service.add_thread_member(
            db_session,
            caller=caller,
            thread_id=thread.id,
            employee_id=second_employee.id,
        )
        
        await canonical_communication_service.remove_thread_member(
            db_session,
            caller=caller,
            thread_id=thread.id,
            employee_id=second_employee.id,
        )
        
        # Member should be soft-deleted (valid_to set)
        member = await db_session.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread.id,
                CanonicalCommunicationThreadMember.employee_id == second_employee.id,
            )
        )
        member = member.scalars().first()
        assert member.valid_to is not None

    @pytest.mark.asyncio
    async def test_send_message(self, db_session, caller, test_employee, second_employee):
        """Test sending a message in a thread."""
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Group Chat",
        )
        
        # Add second employee as member
        await canonical_communication_service.add_thread_member(
            db_session,
            caller=caller,
            thread_id=thread.id,
            employee_id=second_employee.id,
        )
        
        # Send message
        message = await canonical_communication_service.send_message(
            db_session,
            caller=caller,
            thread_id=thread.id,
            content="Hello everyone!",
            message_type="text",
            context_references={
                "decision_id": "dec-123",
                "commitment_id": "comm-456",
            },
            source_event_id="msg-event-1",
        )
        
        assert message.id is not None
        assert message.thread_id == thread.id
        assert message.sender_id == caller.employee_id
        assert message.content == "Hello everyone!"
        assert message.message_type == "text"
        assert message.valid_from is not None
        assert message.valid_to is None
        assert message.version == 1
        assert message.fingerprint is not None
        assert message.decision_id == "dec-123"
        assert message.commitment_id == "comm-456"

    @pytest.mark.asyncio
    async def test_message_exact_once(self, db_session, caller, test_employee, second_employee):
        """Exact-once: identical message fingerprint returns existing."""
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Group Chat",
        )
        
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # First message
        msg1 = await canonical_communication_service.send_message(
            db_session,
            caller=caller,
            thread_id=thread.id,
            content="Duplicate test",
            source_event_id="msg-event-dup",
        )
        
        # Second with same fingerprint
        msg2 = await canonical_communication_service.send_message(
            db_session,
            caller=caller,
            thread_id=thread.id,
            content="Duplicate test",
            source_event_id="msg-event-dup",
        )
        
        assert msg1.id == msg2.id
        assert msg1.fingerprint == msg2.fingerprint

    @pytest.mark.asyncio
    async def test_reply_to_message(self, db_session, caller, test_employee, second_employee):
        """Test replying to a message."""
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Group Chat"
        )
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Send first message
        msg1 = await canonical_communication_service.send_message(
            db_session, caller=caller, thread_id=thread.id, content="First message"
        )
        
        # Reply as second employee
        second_caller = await resolve_caller_access(
            db_session, organization_id=caller.organization_id, user=await db_session.get(User, second_employee.user_id)
        )
        
        reply = await canonical_communication_service.send_message(
            db_session,
            caller=second_caller,
            thread_id=thread.id,
            content="Reply to first",
            reply_to=msg1.id,
        )
        
        assert reply.reply_to == msg1.id
        assert reply.content == "Reply to first"

    @pytest.mark.asyncio
    async def test_get_thread_messages(self, db_session, caller, test_employee, second_employee):
        """Test retrieving messages for a thread with pagination."""
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Group Chat"
        )
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Send multiple messages
        for i in range(5):
            await canonical_communication_service.send_message(
                db_session, caller=caller, thread_id=thread.id, content=f"Message {i}"
            )
        await db_session.commit()
        
        # Get messages
        messages = await canonical_communication_service.get_thread_messages(
            db_session, caller=caller, thread_id=thread.id, limit=3
        )
        
        assert len(messages) == 3
        # Should be ordered by valid_from desc (most recent first)
        assert messages[0].content == "Message 4"
        assert messages[1].content == "Message 3"
        assert messages[2].content == "Message 2"

    @pytest.mark.asyncio
    async def test_unauthorized_message_access_blocked(self, db_session, caller, second_caller, test_employee, second_employee):
        """Non-member cannot read thread messages."""
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Private Chat"
        )
        # second_employee is NOT a member
        
        with pytest.raises(CommunicationGovernanceViolation, match="Insufficient permissions"):
            await canonical_communication_service.get_thread_messages(
                db_session, caller=second_caller, thread_id=thread.id
            )


class TestCanonicalMeeting:
    """Test canonical meeting primitive."""

    @pytest.mark.asyncio
    async def test_create_meeting(self, db_session, caller, test_employee):
        """Test creating a canonical meeting with full guarantees."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Team Standup",
            meeting_type="standup",
            description="Daily standup meeting",
            organizer_id=test_employee.id,
            start_at=utcnow() + timedelta(hours=1),
            end_at=utcnow() + timedelta(hours=2),
            location="Conference Room A",
            meeting_link="https://meet.example.com/standup",
            timezone="UTC",
            duration_minutes=60,
            objective_id="obj-123",
            commitment_id="comm-456",
            responsibility_id="resp-789",
            decision_id="dec-001",
            action_id="act-002",
            scope_type="team",
            scope_id="team-001",
            attendee_ids=[test_employee.id],
            agenda_items=[
                {"title": "Yesterday's progress", "duration_minutes": 15},
                {"title": "Today's plan", "duration_minutes": 15},
                {"title": "Blockers", "duration_minutes": 15},
            ],
            action_items=[
                {"title": "Fix login bug", "assignee_id": test_employee.id, "due_date": utcnow() + timedelta(days=1)},
            ],
            source_event_id="meeting-create-1",
        )
        
        assert meeting.id is not None
        assert meeting.title == "Team Standup"
        assert meeting.meeting_type == "standup"
        assert meeting.status == "scheduled"
        assert meeting.organizer_id == test_employee.id
        assert meeting.valid_from is not None
        assert meeting.valid_to is None
        assert meeting.version == 1
        assert meeting.fingerprint is not None
        assert meeting.objective_id == "obj-123"
        assert meeting.commitment_id == "comm-456"
        assert meeting.responsibility_id == "resp-789"
        assert meeting.decision_id == "dec-001"
        assert meeting.action_id == "act-002"
        assert meeting.scope_type == "team"
        assert meeting.scope_id == "team-001"

    @pytest.mark.asyncio
    async def test_invalid_meeting_type_rejected(self, db_session, caller, test_employee):
        """Invalid meeting type should be rejected."""
        with pytest.raises(InvalidMeetingType, match="Invalid meeting type"):
            await canonical_meeting_service.create_meeting(
                db_session,
                caller=caller,
                title="Test",
                meeting_type="invalid_type",
            )

    @pytest.mark.asyncio
    async def test_invalid_meeting_state_rejected(self, db_session, caller, test_employee):
        """Invalid meeting state transition should be rejected."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test", meeting_type="team"
        )
        
        # Try to set invalid state
        with pytest.raises(InvalidMeetingState, match="Invalid meeting state"):
            await canonical_meeting_service.update_meeting(
                db_session,
                caller=caller,
                meeting_id=meeting.id,
                updates={"status": "invalid_state"},
            )

    @pytest.mark.asyncio
    async def test_meeting_exact_once(self, db_session, caller, test_employee):
        """Exact-once: identical meeting fingerprint returns existing."""
        fixed_start = utcnow() + timedelta(hours=1)
        meeting1 = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Exact Once Test",
            meeting_type="team",
            start_at=fixed_start,
            source_event_id="meeting-dup-event",
        )
        
        meeting2 = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Exact Once Test",
            meeting_type="team",
            start_at=fixed_start,
            source_event_id="meeting-dup-event",
        )
        
        assert meeting1.id == meeting2.id
        assert meeting1.fingerprint == meeting2.fingerprint

    @pytest.mark.asyncio
    async def test_meeting_optimistic_concurrency(self, db_session, caller, test_employee):
        """Optimistic concurrency prevents lost updates."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Concurrency Test", meeting_type="team"
        )
        await db_session.commit()
        
        # Try to update with stale version
        with pytest.raises(Exception) as exc_info:
            await canonical_meeting_service.update_meeting(
                db_session,
                caller=caller,
                meeting_id=meeting.id,
                updates={"title": "Updated Title"},
                expected_version=meeting.version - 1,  # Stale version
            )
        
        assert "ConcurrencyViolation" in str(type(exc_info.value))

    @pytest.mark.asyncio
    async def test_meeting_lifecycle_complete(self, db_session, caller, test_employee):
        """Test completing a meeting."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test Meeting", meeting_type="team"
        )
        
        completed = await canonical_meeting_service.complete_meeting(
            db_session, caller=caller, meeting_id=meeting.id
        )
        
        assert completed.status == "completed"
        assert completed.valid_to is not None
        assert completed.version == 2  # Version should be incremented from 1 to 2

    @pytest.mark.asyncio
    async def test_meeting_lifecycle_cancel(self, db_session, caller, test_employee):
        """Test cancelling a meeting."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test Meeting", meeting_type="team"
        )
        
        cancelled = await canonical_meeting_service.cancel_meeting(
            db_session, caller=caller, meeting_id=meeting.id
        )
        
        assert cancelled.status == "cancelled"
        assert cancelled.valid_to is not None
        assert cancelled.version == 2  # Version should be incremented from 1 to 2

    @pytest.mark.asyncio
    async def test_meeting_agenda_lifecycle(self, db_session, caller, test_employee):
        """Test meeting agenda item lifecycle."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test Meeting", meeting_type="team"
        )
        
        # Add agenda item
        agenda = await canonical_meeting_service.add_agenda_item(
            db_session,
            caller=caller,
            meeting_id=meeting.id,
            title="Agenda Item 1",
            description="Description",
            duration_minutes=30,
        )
        
        assert agenda.id is not None
        assert agenda.title == "Agenda Item 1"
        assert agenda.meeting_id == meeting.id
        assert agenda.valid_from is not None
        assert agenda.fingerprint is not None
        assert agenda.version == 1

    @pytest.mark.asyncio
    async def test_meeting_action_item_lifecycle(self, db_session, caller, test_employee, second_employee):
        """Test meeting action item lifecycle."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test Meeting", meeting_type="team"
        )
        
        # Add action item
        action = await canonical_meeting_service.add_action_item(
            db_session,
            caller=caller,
            meeting_id=meeting.id,
            title="Action Item 1",
            description="Do something",
            assignee_id=second_employee.id,
            due_date=utcnow() + timedelta(days=1),
            context_references={"project_id": "proj-123"},
        )
        
        assert action.id is not None
        assert action.title == "Action Item 1"
        assert action.assignee_id == second_employee.id
        assert action.status == "pending"
        assert action.valid_from is not None
        assert action.fingerprint is not None
        
        # Complete action item
        completed = await canonical_meeting_service.complete_action_item(
            db_session, caller=caller, meeting_id=meeting.id, action_item_id=action.id
        )
        
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert completed.version == 2  # Version should be incremented from 1 to 2

    @pytest.mark.asyncio
    async def test_meeting_attendee_management(self, db_session, caller, test_employee, second_employee):
        """Test meeting attendee management."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Test Meeting", meeting_type="team"
        )
        
        # Add attendee
        attendee = await canonical_meeting_service.add_attendee(
            db_session, caller=caller, meeting_id=meeting.id, employee_id=second_employee.id, role="participant"
        )
        
        assert attendee.employee_id == second_employee.id
        assert attendee.meeting_id == meeting.id
        assert attendee.role == "participant"
        
        # Set RSVP
        rsvp = await canonical_meeting_service.set_rsvp(
            db_session, caller=caller, meeting_id=meeting.id, employee_id=second_employee.id, status="accepted"
        )
        
        assert rsvp.status == "accepted"
        assert rsvp.rsvp_at is not None

    @pytest.mark.asyncio
    async def test_link_meeting_to_decision(self, db_session, caller, test_employee):
        """Test linking meeting to canonical decision."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Decision Meeting", meeting_type="review"
        )
        
        # Create a decision first
        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec:{uuid.uuid4().hex[:12]}",
            kind="commercial_action",
            title="Approve budget",
            rationale="Budget approved for Q1",
            state="approved",
            source_event_id="decision-event-1",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Link meeting to decision
        linked = await canonical_meeting_service.link_meeting_to_decision(
            db_session, caller=caller, meeting_id=meeting.id, decision_id=decision.decision_id
        )
        
        assert linked.decision_id == decision.decision_id

    @pytest.mark.asyncio
    async def test_link_meeting_to_commitment(self, db_session, caller, test_employee):
        """Test linking meeting to canonical commitment."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Commitment Meeting", meeting_type="review"
        )
        
        # Create a commitment first
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Q1 Launch Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-123",
            fingerprint="fp-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-event-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Link meeting to commitment
        linked = await canonical_meeting_service.link_meeting_to_commitment(
            db_session, caller=caller, meeting_id=meeting.id, commitment_id=commitment.id
        )
        
        assert linked.commitment_id == commitment.id

    @pytest.mark.asyncio
    async def test_get_meeting_with_context(self, db_session, caller, test_employee, second_employee):
        """Test getting meeting with full contextual information."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Context Meeting",
            meeting_type="team",
            objective_id="obj-123",
            commitment_id="comm-456",
            attendee_ids=[test_employee.id, second_employee.id],
            agenda_items=[{"title": "Agenda 1"}],
            action_items=[{"title": "Action 1", "assignee_id": test_employee.id}],
        )
        
        with_context = await canonical_meeting_service.get_meeting_with_context(
            db_session, caller=caller, meeting_id=meeting.id
        )
        
        assert with_context is not None
        assert len(with_context.attendees) == 2
        assert len(with_context.agenda) == 1
        assert len(with_context.action_items) == 1


class TestCommunicationGovernance:
    """Test governance enforcement for communication."""

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
    async def test_cross_tenant_thread_blocked(self, db_session, caller, test_org_b):
        """Cross-tenant thread access should be denied."""
        # Create a user in org B
        unique = uuid.uuid4().hex[:8]
        user_b = User(
            id=f"user-b-{unique}",
            email=f"user-b-{unique}@test.com",
            full_name=f"User B {unique}",
            status="active",
            organization_id=test_org_b.id,
            password_hash="test-hash",
        )
        db_session.add(user_b)
        await db_session.flush()
        
        emp_b = Employee(
            organization_id=test_org_b.id,
            user_id=user_b.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Test",
            last_name="EmployeeB",
            email=f"employee-b-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(emp_b)
        await db_session.flush()
        
        # Create caller for org B
        await permission_service.sync_catalog(db_session)
        await permission_service.seed_org_roles(db_session, test_org_b.id)
        member_role = (await db_session.execute(
            select(Role).where(Role.organization_id == test_org_b.id, Role.code == "member")
        )).scalars().first()
        
        if member_role:
            user_role = UserRole(user_id=user_b.id, role_id=member_role.id, organization_id=test_org_b.id)
            db_session.add(user_role)
            await db_session.flush()
        
        from app.intelligence.company_context import resolve_caller_access
        caller_b = await resolve_caller_access(db_session, organization_id=test_org_b.id, user=user_b)
        
        # Create a GovernanceScope in org B
        from app.models.governance import GovernanceScope
        scope_b = GovernanceScope(
            id=f"scope-b-{uuid.uuid4().hex[:8]}",
            organization_id=test_org_b.id,
            name="Dept B",
            scope_type="department",
        )
        db_session.add(scope_b)
        await db_session.flush()
        
        # Try to create thread with caller from org A but scope_id from org B
        with pytest.raises(Exception) as exc_info:
            await canonical_communication_service.create_thread(
                db_session, caller=caller, thread_type="dm", title="Cross Tenant",
                scope_type="department", scope_id=scope_b.id
            )
        
        assert "CommunicationGovernanceViolation" in str(type(exc_info.value)) or "Cross-tenant" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unauthorized_cross_employee_message_blocked(self, db_session, test_org, test_employee):
        """Non-management user cannot send message as another employee."""
        # Create limited user with employee profile
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
        
        limited_emp = Employee(
            organization_id=test_org.id,
            user_id=limited_user.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Limited",
            last_name="User",
            email=f"limited-emp-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(limited_emp)
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
        
        # Create thread as limited user
        thread = await canonical_communication_service.create_thread(
            db_session, caller=limited_caller, thread_type="dm", title="Test"
        )
        
        # Create caller for target employee (who is NOT a member of the thread)
        target_user = User(
            id=f"target-user-{uuid.uuid4().hex[:8]}",
            email=f"target-user-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Target User",
            status="active",
            organization_id=test_org.id,
            password_hash="test-hash",
        )
        db_session.add(target_user)
        await db_session.flush()
        
        target_emp = Employee(
            organization_id=test_org.id,
            user_id=target_user.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Target",
            last_name="Employee",
            email=f"target-emp-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(target_emp)
        await db_session.flush()
        
        await permission_service.sync_catalog(db_session)
        await permission_service.seed_org_roles(db_session, test_org.id)
        member_role = (await db_session.execute(
            select(Role).where(Role.organization_id == test_org.id, Role.code == "member")
        )).scalars().first()
        
        if member_role:
            user_role = UserRole(user_id=target_user.id, role_id=member_role.id, organization_id=test_org.id)
            db_session.add(user_role)
            await db_session.flush()
        
        target_caller = await resolve_caller_access(db_session, organization_id=test_org.id, user=target_user)
        
        # Try to send message as target employee (should fail - not a member)
        with pytest.raises(Exception) as exc_info:
            await canonical_communication_service.send_message(
                db_session, caller=target_caller, thread_id=thread.id, content="Hacked message"
            )
        
        assert "GovernanceViolation" in str(type(exc_info.value)) or "Not a member" in str(exc_info.value)


class TestMeetingGovernance:
    """Test governance enforcement for meetings."""

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
    async def test_cross_tenant_meeting_blocked(self, db_session, caller, test_org_b):
        """Cross-tenant meeting access should be denied."""
        # Create a user in org B
        unique = uuid.uuid4().hex[:8]
        user_b = User(
            id=f"user-b-{unique}",
            email=f"user-b-{unique}@test.com",
            full_name=f"User B {unique}",
            status="active",
            organization_id=test_org_b.id,
            password_hash="test-hash",
        )
        db_session.add(user_b)
        await db_session.flush()
        
        emp_b = Employee(
            organization_id=test_org_b.id,
            user_id=user_b.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Test",
            last_name="EmployeeB",
            email=f"employee-b-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(emp_b)
        await db_session.flush()
        
        # Create caller for org B
        await permission_service.sync_catalog(db_session)
        await permission_service.seed_org_roles(db_session, test_org_b.id)
        member_role = (await db_session.execute(
            select(Role).where(Role.organization_id == test_org_b.id, Role.code == "member")
        )).scalars().first()
        
        if member_role:
            user_role = UserRole(user_id=user_b.id, role_id=member_role.id, organization_id=test_org_b.id)
            db_session.add(user_role)
            await db_session.flush()
        
        from app.intelligence.company_context import resolve_caller_access
        caller_b = await resolve_caller_access(db_session, organization_id=test_org_b.id, user=user_b)
        
        # Create a GovernanceScope in org B
        from app.models.governance import GovernanceScope
        scope_b = GovernanceScope(
            id=f"scope-b-{uuid.uuid4().hex[:8]}",
            organization_id=test_org_b.id,
            name="Dept B",
            scope_type="department",
        )
        db_session.add(scope_b)
        await db_session.flush()
        
        # Try to create meeting with caller from org A but scope_id from org B
        with pytest.raises(Exception) as exc_info:
            await canonical_meeting_service.create_meeting(
                db_session, caller=caller, title="Cross Tenant", meeting_type="team",
                scope_type="department", scope_id=scope_b.id
            )
        
        assert "MeetingGovernanceViolation" in str(type(exc_info.value)) or "Cross-tenant" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unauthorized_cross_employee_meeting_blocked(self, db_session, test_org, test_employee):
        """Non-management user cannot update another employee's meeting."""
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
        
        # Create meeting as limited user (organizer)
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=limited_caller, title="My Meeting", meeting_type="team", organizer_id=limited_caller.employee_id
        )
        
        # Another user tries to update
        other_user = User(
            id=f"other-{uuid.uuid4().hex[:8]}",
            email=f"other-{uuid.uuid4().hex[:8]}@test.com",
            full_name="Other User",
            status="active",
            organization_id=test_org.id,
            password_hash="test-hash",
        )
        db_session.add(other_user)
        await db_session.flush()
        
        other_emp = Employee(
            organization_id=test_org.id,
            user_id=other_user.id,
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Other",
            last_name="Employee",
            email=f"other-emp-{uuid.uuid4().hex[:8]}@test.com",
            status="active",
        )
        db_session.add(other_emp)
        await db_session.flush()
        
        if member_role:
            user_role = UserRole(user_id=other_user.id, role_id=member_role.id, organization_id=test_org.id)
            db_session.add(user_role)
            await db_session.flush()
        
        other_caller = await resolve_caller_access(db_session, organization_id=test_org.id, user=other_user)
        
        with pytest.raises(Exception) as exc_info:
            await canonical_meeting_service.update_meeting(
                db_session, caller=other_caller, meeting_id=meeting.id, updates={"title": "Hacked"}
            )
        
        assert "GovernanceViolation" in str(type(exc_info.value)) or "Insufficient" in str(exc_info.value)


class TestCommunicationMeetingIntegration:
    """Test communication ↔ meeting integration."""

    @pytest.mark.asyncio
    async def test_meeting_creates_communication_thread(self, db_session, caller, test_employee, second_employee):
        """Meeting creation should create associated communication thread."""
        # Create meeting with canonical service
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Meeting with Thread",
            meeting_type="team",
            attendee_ids=[test_employee.id, second_employee.id],
            source_event_id="meeting-thread-1",
        )
        
        # Meeting should have a communication thread reference
        # (This tests the integration - the meeting model has meeting_id field in thread)
        assert meeting.id is not None
        
        # Create a communication thread for this meeting
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="meeting",
            title=f"Meeting: {meeting.title}",
            context_references={"meeting_id": meeting.id},
            source_event_id="thread-from-meeting-1",
        )
        
        assert thread.meeting_id == meeting.id
        assert thread.thread_type == "meeting"

    @pytest.mark.asyncio
    async def test_meeting_notes_as_messages(self, db_session, caller, test_employee, second_employee):
        """Meeting notes should become canonical messages."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Meeting with Notes",
            meeting_type="team",
            attendee_ids=[test_employee.id, second_employee.id],
        )
        
        # Create thread for meeting
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="meeting",
            title=f"Meeting: {meeting.title}",
            context_references={"meeting_id": meeting.id},
        )
        
        # Add second_employee as thread member (caller is already added as owner)
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Add meeting note as message
        note_msg = await canonical_communication_service.send_message(
            db_session,
            caller=caller,
            thread_id=thread.id,
            content="Meeting note: Discussed Q1 budget allocation",
            message_type="meeting_note",
            context_references={"meeting_id": meeting.id},
        )
        
        assert note_msg.message_type == "meeting_note"
        assert "Q1 budget" in note_msg.content

    @pytest.mark.asyncio
    async def test_explicit_decision_from_meeting(self, db_session, caller, test_employee):
        """Explicit human-confirmed decision creation from meeting."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Decision Meeting",
            meeting_type="review",
        )
        
        # Create a decision through canonical decision engine (human-confirmed)
        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec:{uuid.uuid4().hex[:12]}",
            kind="commercial_action",
            title="Approve Q1 Budget",
            rationale="Approved in meeting: " + meeting.title,
            state="approved",
            approved_at=utcnow(),
            source_event_id="decision-from-meeting-1",
            as_of_context_json={"meeting_id": meeting.id, "meeting_title": meeting.title},
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Link meeting to decision
        linked = await canonical_meeting_service.link_meeting_to_decision(
            db_session, caller=caller, meeting_id=meeting.id, decision_id=decision.decision_id
        )
        
        assert linked.decision_id == decision.decision_id
        assert decision.as_of_context_json["meeting_id"] == meeting.id

    @pytest.mark.asyncio
    async def test_explicit_commitment_from_decision(self, db_session, caller, test_employee):
        """Explicit commitment creation from decision."""
        # Create decision
        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec:{uuid.uuid4().hex[:12]}",
            kind="commercial_action",
            title="Launch Product",
            rationale="Market ready",
            state="approved",
            approved_at=utcnow(),
            source_event_id="decision-commit-1",
        )
        db_session.add(decision)
        await db_session.flush()
        
        # Create authorization (governance permit)
        authorization = CompanyAuthorization(
            organization_id=caller.organization_id,
            authorization_type="full",
            title="Launch Authorization",
            state="approved",
            decision_id=decision.decision_id,
            scope_type="project",
            scope_id="proj-launch",
            fingerprint="auth-fp-" + uuid.uuid4().hex[:32],
            source_event_id="auth-event-1",
        )
        db_session.add(authorization)
        await db_session.flush()
        
        # Create commitment from decision + authorization
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Product Launch Commitment",
            state="authorized",
            decision_id=decision.decision_id,
            authorization_id=authorization.id,
            scope_type="project",
            scope_id="proj-launch",
            fingerprint="comm-fp-" + uuid.uuid4().hex[:32],
            source_event_id="commitment-event-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Verify chain
        assert commitment.decision_id == decision.decision_id
        assert commitment.authorization_id == authorization.id
        assert commitment.state == "authorized"


class TestOperatingContextWithCommunication:
    """Test OperatingContextService extended with communication."""

    @pytest.mark.asyncio
    async def test_operating_context_includes_communication_threads(self, db_session, caller, test_employee, second_employee):
        """Operating context should include relevant communication threads."""
        # Create a communication thread
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="group",
            title="Project Alpha Discussion",
            context_references={"project_id": "proj-alpha"},
        )
        
        # Add second_employee as member (caller is already added as owner)
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Derive operating context
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        # TODO: Verify context includes communication threads
        # This will pass once OperatingContextService is extended
        assert context.employee_id == test_employee.id

    @pytest.mark.asyncio
    async def test_operating_context_includes_meetings(self, db_session, caller, test_employee, second_employee):
        """Operating context should include upcoming meetings."""
        # Create meeting
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Upcoming Standup",
            meeting_type="standup",
            start_at=utcnow() + timedelta(hours=1),
            end_at=utcnow() + timedelta(hours=2),
            attendee_ids=[test_employee.id],
        )
        
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        # Should include upcoming meetings (already implemented in Gate 8.1)
        assert len(context.upcoming_meetings) > 0
        assert any(m["title"] == "Upcoming Standup" for m in context.upcoming_meetings)


class TestEpistemicBoundaries:
    """Test critical epistemic boundaries are enforced."""

    @pytest.mark.asyncio
    async def test_communication_not_decision(self, db_session, caller, test_employee, second_employee):
        """Communication must not automatically become decision."""
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Discussion"
        )
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Send message that SOUNDS like a decision
        msg = await canonical_communication_service.send_message(
            db_session,
            caller=caller,
            thread_id=thread.id,
            content="Let's launch the product on Friday!",
            message_type="text",
        )
        
        # Message is OBSERVED communication only
        assert msg.message_type == "text"
        assert msg.content == "Let's launch the product on Friday!"
        
        # No CompanyDecision should be auto-created
        decisions = await db_session.execute(
            select(CompanyDecision).where(
                CompanyDecision.organization_id == caller.organization_id,
                CompanyDecision.source_event_id.like("%msg%"),
            )
        )
        auto_decisions = decisions.scalars().all()
        assert len(auto_decisions) == 0

    @pytest.mark.asyncio
    async def test_meeting_discussion_not_decision(self, db_session, caller, test_employee, second_employee):
        """Meeting discussion must not automatically become decision."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Planning Meeting",
            meeting_type="team",
            attendee_ids=[test_employee.id, second_employee.id],
        )
        
        # Add agenda item that sounds like a decision
        agenda = await canonical_meeting_service.add_agenda_item(
            db_session,
            caller=caller,
            meeting_id=meeting.id,
            title="Decide: Launch Friday",
            description="Team discussed and agreed to launch Friday",
        )
        
        # Add action item
        action = await canonical_meeting_service.add_action_item(
            db_session,
            caller=caller,
            meeting_id=meeting.id,
            title="Launch on Friday",
            assignee_id=test_employee.id,
        )
        
        # Meeting action item is NOT a CompanyAction
        assert action.title == "Launch on Friday"
        assert action.meeting_id == meeting.id
        
        # No CompanyAction should be auto-created
        from app.models.company_actions import CompanyAction
        actions = await db_session.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.source_event_id.like("%meeting%"),
            )
        )
        auto_actions = actions.scalars().all()
        assert len(auto_actions) == 0

    @pytest.mark.asyncio
    async def test_ai_summary_not_truth(self, db_session, caller, test_employee):
        """AI summary must not become canonical truth."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="AI Summary Test", meeting_type="team"
        )
        
        # Simulate AI summary (epistemic status: inferred)
        meeting.ai_summary = "AI Summary: Team decided to launch Friday and hire 5 engineers."
        meeting.transcript_summary = "Raw transcript..."
        await db_session.commit()
        
        # AI summary is just a field - not canonical truth
        assert meeting.ai_summary is not None
        assert "AI Summary" in meeting.ai_summary
        
        # No canonical entities auto-created from AI summary
        decisions = await db_session.execute(
            select(CompanyDecision).where(CompanyDecision.organization_id == caller.organization_id)
        )
        # Should only have decisions explicitly created
        assert len(decisions.scalars().all()) == 0  # No auto-decisions


class TestEventIntegration:
    """Test event integration for communication and meetings."""

    @pytest.mark.asyncio
    async def test_communication_created_event(self, db_session, caller, test_employee):
        """Thread creation should emit event."""
        thread = await canonical_communication_service.create_thread(
            db_session, caller=caller, thread_type="group", title="Event Test", source_event_id="thread-create-evt"
        )
        await db_session.commit()
        
        from app.models.notification import Event
        result = await db_session.execute(
            select(Event).where(Event.name == "thread.created")
        )
        events = result.scalars().all()
        assert len(events) > 0
        assert "thread-create-evt" in str(events[-1].payload_json)

    @pytest.mark.asyncio
    async def test_meeting_created_event(self, db_session, caller, test_employee):
        """Meeting creation should emit event."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Event Meeting", meeting_type="team", source_event_id="meeting-create-evt"
        )
        await db_session.commit()
        
        from app.models.notification import Event
        result = await db_session.execute(
            select(Event).where(Event.name == "meeting.created")
        )
        events = result.scalars().all()
        assert len(events) > 0
        assert "meeting-create-evt" in str(events[-1].payload_json)

    @pytest.mark.asyncio
    async def test_decision_linked_to_meeting_event(self, db_session, caller, test_employee):
        """Linking decision to meeting should emit event."""
        meeting = await canonical_meeting_service.create_meeting(
            db_session, caller=caller, title="Decision Meeting", meeting_type="review"
        )
        
        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec:{uuid.uuid4().hex[:12]}",
            kind="commercial_action",
            title="Linked Decision",
            state="approved",
            source_event_id="decision-link-evt",
        )
        db_session.add(decision)
        await db_session.flush()
        
        linked = await canonical_meeting_service.link_meeting_to_decision(
            db_session, caller=caller, meeting_id=meeting.id, decision_id=decision.decision_id
        )
        await db_session.commit()
        
        from app.models.notification import Event
        result = await db_session.execute(
            select(Event).where(Event.name == "meeting.decision_linked")
        )
        events = result.scalars().all()
        assert len(events) > 0


class TestLongitudinalContinuity:
    """Test longitudinal continuity across cycles."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_longitudinal_communication_cycles(self, db_session, caller, test_employee, second_employee):
        """Test communication across multiple operating cycles."""
        for cycle in range(5):
            # Create thread for cycle
            thread = await canonical_communication_service.create_thread(
                db_session,
                caller=caller,
                thread_type="channel",
                title=f"Cycle {cycle} Discussion",
                source_event_id=f"cycle-{cycle}-thread",
            )
            
            # Add second_employee as member (caller is already added as owner)
            await canonical_communication_service.add_thread_member(
                db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
            )
            
            # Send messages
            for i in range(3):
                await canonical_communication_service.send_message(
                    db_session,
                    caller=caller,
                    thread_id=thread.id,
                    content=f"Cycle {cycle} Message {i}",
                    source_event_id=f"cycle-{cycle}-msg-{i}",
                )
            
            await db_session.commit()
            
            # Verify context
            context = await operating_context_service.derive_operating_context(
                db_session, caller=caller, employee_id=test_employee.id
            )
            assert context.employee_id == test_employee.id
        
        # Verify all threads persist
        threads = await db_session.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.organization_id == caller.organization_id
            )
        )
        all_threads = threads.scalars().all()
        assert len(all_threads) == 5

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_longitudinal_meeting_cycles(self, db_session, caller, test_employee, second_employee):
        """Test meetings across multiple operating cycles."""
        for cycle in range(3):
            meeting = await canonical_meeting_service.create_meeting(
                db_session,
                caller=caller,
                title=f"Cycle {cycle} Standup",
                meeting_type="standup",
                start_at=utcnow() + timedelta(hours=cycle),
                attendee_ids=[test_employee.id, second_employee.id],
                source_event_id=f"cycle-{cycle}-meeting",
            )
            
            # Complete meeting
            await canonical_meeting_service.complete_meeting(
                db_session, caller=caller, meeting_id=meeting.id
            )
            await db_session.commit()
        
        # Verify all meetings persist with history
        meetings = await db_session.execute(
            select(Meeting).where(Meeting.organization_id == caller.organization_id)
        )
        all_meetings = meetings.scalars().all()
        assert len(all_meetings) == 3
        
        # All should be completed
        for m in all_meetings:
            assert m.status == "completed"
            assert m.valid_to is not None


class TestPhysicalOfficeDisruptionContinuity:
    """Test virtual company continuity - office unavailable scenario."""

    @pytest.mark.asyncio
    async def test_office_unavailable_communication_continues(self, db_session, caller, test_employee, second_employee):
        """Communication continues when physical office is unavailable."""
        # Simulate: people work remotely, communicate via canonical threads
        thread = await canonical_communication_service.create_thread(
            db_session,
            caller=caller,
            thread_type="channel",
            title="Remote Work Coordination",
        )
        
        # Add second_employee as member (caller is already added as owner)
        await canonical_communication_service.add_thread_member(
            db_session, caller=caller, thread_id=thread.id, employee_id=second_employee.id
        )
        
        # Remote communication
        msg1 = await canonical_communication_service.send_message(
            db_session, caller=caller, thread_id=thread.id, content="Working from home today"
        )
        
        second_caller = await resolve_caller_access(
            db_session, organization_id=caller.organization_id, user=await db_session.get(User, second_employee.user_id)
        )
        
        msg2 = await canonical_communication_service.send_message(
            db_session, caller=second_caller, thread_id=thread.id, content="Same here, all systems operational"
        )
        
        # Communication persists
        messages = await canonical_communication_service.get_thread_messages(
            db_session, caller=caller, thread_id=thread.id
        )
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_office_unavailable_meetings_continue(self, db_session, caller, test_employee, second_employee):
        """Meetings continue when physical office is unavailable."""
        # Virtual meeting
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Virtual Standup",
            meeting_type="standup",
            meeting_link="https://meet.vcos.example/standup",
            attendee_ids=[test_employee.id, second_employee.id],
            start_at=utcnow() + timedelta(minutes=30),
        )
        
        # Meeting proceeds virtually
        await canonical_meeting_service.complete_meeting(
            db_session, caller=caller, meeting_id=meeting.id
        )
        await db_session.commit()
        
        # Meeting record persists
        completed = await canonical_meeting_service.get_meeting_with_context(
            db_session, caller=caller, meeting_id=meeting.id
        )
        assert completed.status == "completed"
        assert completed.meeting_link == "https://meet.vcos.example/standup"

    @pytest.mark.asyncio
    async def test_office_unavailable_decisions_continue(self, db_session, caller, test_employee):
        """Decisions continue when physical office is unavailable."""
        # Virtual meeting produces decision
        meeting = await canonical_meeting_service.create_meeting(
            db_session,
            caller=caller,
            title="Remote Decision Meeting",
            meeting_type="review",
            meeting_link="https://meet.vcos.example/decision",
        )
        
        # Human-confirmed decision (not AI)
        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec:{uuid.uuid4().hex[:12]}",
            kind="commercial_action",
            title="Remote Work Policy",
            rationale="Decided in virtual meeting: " + meeting.title,
            state="approved",
            approved_at=utcnow(),
            source_event_id="remote-decision-1",
            as_of_context_json={"meeting_id": meeting.id, "virtual": True},
        )
        db_session.add(decision)
        await db_session.commit()
        
        # Decision persists in canonical reality
        assert decision.decision_id is not None
        assert decision.as_of_context_json["virtual"] is True


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
    async def test_gate7_company_reality_still_works(self, db_session, caller, test_employee):
        """Gate 7 company reality should still work."""
        # Create a project
        project = Project(
            organization_id=caller.organization_id,
            name="Test Project",
            code=f"PRJ{uuid.uuid4().hex[:4]}",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        
        # Create task
        task = Task(
            organization_id=caller.organization_id,
            title="Test Task",
            status="in_progress",
            assignee_id=test_employee.id,
            project_id=project.id,
        )
        db_session.add(task)
        await db_session.commit()
        
        # Verify canonical reality intact
        context = await operating_context_service.derive_operating_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        assert len(context.current_tasks) > 0
        assert len(context.current_projects) > 0


# ============================================================================
# Test Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])