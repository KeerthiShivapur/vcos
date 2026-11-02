"""Canonical Meeting Service — Gate 8.2.

This service implements the canonical meeting primitive with:
- Canonical temporal truth (historical immutability, valid intervals, supersession)
- Governance enforcement (tenant/scope isolation, permissions)
- Exact-once semantics (fingerprint-based deduplication)
- Provenance tracking
- Optimistic concurrency (version-based)
- Provenance chain preservation
- Epistemic separation: meeting ≠ decision ≠ authorization ≠ commitment
- Contextual references to canonical company reality
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Optional

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.models.meeting import (
    Meeting,
    MeetingAttendee,
    MeetingAgendaItem,
    MeetingActionItem,
)
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.services.event_service import event_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.intelligence.canonical_mutation import (
    validate_optimistic_concurrency,
    ExactOnceViolation,
    ConcurrencyViolation,
    CanonicalMutationError,
    EpistemicStatus,
)
from app.models.execution_strategy import CompanyAuthorization
from app.work.meeting_service import meeting_service

logger = logging.getLogger("vcos.people.canonical_meeting")

# Canonical meeting states
CANONICAL_MEETING_STATES = (
    "scheduled",
    "in_progress",
    "completed",
    "cancelled",
    "archived",
)

# Canonical meeting types
CANONICAL_MEETING_TYPES = (
    "team",
    "project",
    "one_on_one",
    "standup",
    "review",
    "client",
    "all_hands",
    "other",
)


class CanonicalMeetingError(Exception):
    """Base exception for canonical meeting violations."""
    pass


class InvalidMeetingState(CanonicalMeetingError):
    """Invalid meeting state requested."""
    pass


class InvalidMeetingType(CanonicalMeetingError):
    """Invalid meeting type requested."""
    pass


class MeetingGovernanceViolation(Exception):
    """Meeting mutation violates governance/scope rules."""
    pass


class MeetingTemporalViolation(Exception):
    """Meeting mutation violates temporal integrity."""
    pass


class CanonicalMeetingService:
    """Canonical service for managing meetings with full canonical guarantees."""

    def __init__(self):
        self._valid_states = set(CANONICAL_MEETING_STATES)
        self._valid_types = set(CANONICAL_MEETING_TYPES)

    def _validate_meeting_state(self, state: str) -> str:
        """Validate and normalize meeting state."""
        state_lower = state.lower()
        if state_lower not in self._valid_states:
            raise InvalidMeetingState(
                f"Invalid meeting state: {state}. Valid states: {', '.join(CANONICAL_MEETING_STATES)}"
            )
        return state_lower

    def _validate_meeting_type(self, meeting_type: str) -> str:
        """Validate and normalize meeting type."""
        meeting_type_lower = meeting_type.lower()
        if meeting_type_lower not in self._valid_types:
            raise InvalidMeetingType(
                f"Invalid meeting type: {meeting_type}. Valid types: {', '.join(CANONICAL_MEETING_TYPES)}"
            )
        return meeting_type_lower

    def _compute_fingerprint(self, data: dict) -> str:
        """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
        # Convert datetime objects to ISO format strings for JSON serialization
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [serialize(v) for v in obj]
            return obj
        
        serialized = serialize(data)
        canonical = json.dumps(serialized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:160]

    async def _get_meeting(
        self, db: AsyncSession, organization_id: str, meeting_id: str
    ) -> Optional[Meeting]:
        """Get a meeting by ID with organization check."""
        result = await db.execute(
            select(Meeting).where(
                Meeting.id == meeting_id,
                Meeting.organization_id == organization_id,
            )
        )
        return result.scalars().first()

    async def _get_current_meeting(
        self, db: AsyncSession, organization_id: str, meeting_id: str
    ) -> Optional[Meeting]:
        """Get current valid meeting (valid_to is None or in future)."""
        now = utcnow()
        result = await db.execute(
            select(Meeting).where(
                Meeting.id == meeting_id,
                Meeting.organization_id == organization_id,
                Meeting.valid_to.is_(None) | (Meeting.valid_to > now),
            )
        )
        return result.scalars().first()

    async def _get_meeting_history(
        self, db: AsyncSession, organization_id: str, meeting_id: str
    ) -> List[Meeting]:
        """Get full meeting history for a meeting."""
        result = await db.execute(
            select(Meeting).where(
                Meeting.id == meeting_id,
                Meeting.organization_id == organization_id,
            ).order_by(Meeting.valid_from.desc())
        )
        return list(result.scalars().all())

    async def _check_meeting_governance(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        meeting_id: str,
        action: str = "update",
    ) -> Meeting:
        """Check governance permissions for meeting operations."""
        meeting = await self._get_meeting(db, caller.organization_id, meeting_id)
        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        # Cross-tenant check
        if meeting.organization_id != caller.organization_id:
            raise MeetingGovernanceViolation("Cross-tenant meeting access denied")

        # Check if caller is organizer or attendee
        is_organizer = meeting.organizer_id == caller.employee_id
        
        attendee_result = await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.meeting_id == meeting_id,
                MeetingAttendee.employee_id == caller.employee_id,
            )
        )
        is_attendee = attendee_result.scalars().first() is not None

        # Allow if organizer or attendee
        if not (is_organizer or is_attendee):
            # Check if caller has management permissions
            permissions = await caller.get_permissions(db)
            management_perms = {
                "meetings:manage",
                "meetings:manage",
            }
            if not any(p in permissions for p in management_perms):
                raise MeetingGovernanceViolation(
                    f"Insufficient permissions for {action} on meeting"
                )

        # Scope check if not org-wide
        if not caller.org_wide:
            if meeting.scope_id and meeting.scope_id not in caller.visible_scope_ids:
                raise MeetingGovernanceViolation("Cross-scope meeting access denied")

        return meeting

    async def create_meeting(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        title: str,
        meeting_type: str = "team",
        description: Optional[str] = None,
        organizer_id: Optional[str] = None,
        project_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        start_at: Optional[datetime] = None,
        end_at: Optional[datetime] = None,
        location: Optional[str] = None,
        meeting_link: Optional[str] = None,
        timezone: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        objective_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        responsibility_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        action_id: Optional[str] = None,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        attendee_ids: Optional[List[str]] = None,
        agenda_items: Optional[List[Dict]] = None,
        action_items: Optional[List[Dict]] = None,
        source_event_id: Optional[str] = None,
    ) -> Meeting:
        """Create a canonical meeting with full canonical guarantees."""
        # Validate meeting type
        meeting_type = self._validate_meeting_type(meeting_type)

        # Check governance
        if not caller.org_wide and scope_id and scope_id not in caller.visible_scope_ids:
            raise MeetingGovernanceViolation("Cross-scope meeting creation denied")
        
        # Cross-tenant check for scope_id - even org-wide callers cannot reference scopes from other tenants
        if scope_id:
            # Verify the scope_id belongs to the same organization
            from app.models.governance import GovernanceScope
            scope = await db.get(GovernanceScope, scope_id)
            if scope and scope.organization_id != caller.organization_id:
                raise MeetingGovernanceViolation("Cross-tenant meeting creation denied: scope_id belongs to different organization")

        # Compute effective start/end times for fingerprint
        effective_start_at = start_at or utcnow() + timedelta(hours=1)
        effective_end_at = end_at or (start_at or utcnow() + timedelta(hours=1)) + timedelta(minutes=duration_minutes or 60)

        # Build meeting data for fingerprint
        meeting_data = {
            "organization_id": caller.organization_id,
            "title": title,
            "meeting_type": meeting_type,
            "description": description,
            "organizer_id": organizer_id or caller.employee_id,
            "project_id": project_id,
            "goal_id": goal_id,
            "start_at": effective_start_at,
            "end_at": effective_end_at,
            "location": location,
            "meeting_link": meeting_link,
            "timezone": timezone,
            "duration_minutes": duration_minutes,
            "status": "scheduled",
            "actor_id": caller.user_id,
            "objective_id": objective_id,
            "commitment_id": commitment_id,
            "responsibility_id": responsibility_id,
            "decision_id": decision_id,
            "action_id": action_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }

        fingerprint = self._compute_fingerprint(meeting_data)

        # Check exact-once: if identical fingerprint exists and is current, return existing
        existing = await db.execute(
            select(Meeting).where(
                Meeting.organization_id == caller.organization_id,
                Meeting.fingerprint == fingerprint,
                Meeting.valid_to.is_(None) | (Meeting.valid_to > utcnow()),
            )
        )
        existing_meeting = existing.scalars().first()
        if existing_meeting:
            logger.info(f"Exact-once: identical meeting fingerprint, returning existing")
            return existing_meeting

        # Use default start_at if not provided
        effective_start_at = start_at or utcnow() + timedelta(hours=1)
        effective_end_at = end_at or (start_at or utcnow() + timedelta(hours=1)) + timedelta(minutes=duration_minutes or 60)

        # Build meeting record with canonical fields
        now = utcnow()
        meeting = Meeting(
            organization_id=caller.organization_id,
            title=title,
            meeting_type=meeting_type,
            description=description,
            organizer_id=organizer_id or caller.employee_id,
            project_id=project_id,
            goal_id=goal_id,
            start_at=effective_start_at,
            end_at=effective_end_at,
            location=location,
            meeting_link=meeting_link,
            timezone=timezone,
            duration_minutes=duration_minutes,
            status="scheduled",
            valid_from=utcnow(),
            valid_to=None,
            source_event_id=source_event_id or f"meeting_create:{uuid.uuid4().hex[:8]}",
            actor_id=caller.user_id,
            version=1,
            fingerprint=fingerprint,
            objective_id=objective_id,
            commitment_id=commitment_id,
            responsibility_id=responsibility_id,
            decision_id=decision_id,
            action_id=action_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )

        db.add(meeting)
        await db.flush()

        # Add agenda items if provided
        if agenda_items:
            for idx, item in enumerate(agenda_items):
                agenda_item = MeetingAgendaItem(
                    organization_id=caller.organization_id,
                    meeting_id=meeting.id,
                    title=item.get("title", f"Agenda {idx + 1}"),
                    description=item.get("description"),
                    sort_order=idx,
                    duration_minutes=item.get("duration_minutes"),
                    valid_from=utcnow(),
                    fingerprint=self._compute_fingerprint({
                        "meeting_id": meeting.id,
                        "title": item.get("title", f"Agenda {idx + 1}"),
                        "sort_order": idx,
                    }),
                )
                db.add(agenda_item)
            await db.flush()

        # Add attendees if provided
        if attendee_ids:
            for attendee_id in attendee_ids:
                attendee = MeetingAttendee(
                    organization_id=caller.organization_id,
                    meeting_id=meeting.id,
                    employee_id=attendee_id,
                    role="participant",
                )
                db.add(attendee)
            await db.flush()

        # Add action items if provided
        if action_items:
            for item in action_items:
                action_item = MeetingActionItem(
                    organization_id=caller.organization_id,
                    meeting_id=meeting.id,
                    title=item.get("title", "Action Item"),
                    description=item.get("description"),
                    assignee_id=item.get("assignee_id"),
                    due_date=item.get("due_date"),
                    valid_from=utcnow(),
                    fingerprint=self._compute_fingerprint({
                        "meeting_id": meeting.id,
                        "title": item.get("title", "Action Item"),
                        "assignee_id": item.get("assignee_id"),
                    }),
                )
                db.add(action_item)
            await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.created",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting.id,
                "title": title,
                "meeting_type": meeting_type,
                "source_event_id": source_event_id or f"meeting_create:{uuid.uuid4().hex[:8]}",
            },
        )

        logger.info(f"Canonical meeting created: meeting={meeting.id}, type={meeting_type}")
        return meeting

    async def update_meeting(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        updates: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Meeting:
        """Update a meeting with canonical guarantees."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "update")

        # Check optimistic concurrency
        if expected_version is not None:
            validate_optimistic_concurrency(meeting, expected_version)

        # Validate state transition if status is being updated
        if "status" in updates:
            new_status = self._validate_meeting_state(updates["status"])
            # Valid transitions
            valid_transitions = {
                "scheduled": ["in_progress", "cancelled"],
                "in_progress": ["completed", "cancelled"],
                "completed": [],
                "cancelled": [],
                "archived": [],
            }
            current_status = meeting.status
            if new_status not in valid_transitions.get(current_status, []):
                raise InvalidMeetingState(
                    f"Invalid state transition: {current_status} -> {new_status}. "
                    f"Valid transitions: {valid_transitions.get(current_status, [])}"
                )
            updates["status"] = new_status

        # Apply updates
        for key, value in updates.items():
            if hasattr(meeting, key) and key not in ("id", "organization_id", "fingerprint", "version"):
                setattr(meeting, key, value)

        meeting.updated_at = utcnow()
        meeting.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.updated",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting.id,
                "changes": list(updates.keys()),
            },
        )

        logger.info(f"Canonical meeting updated: meeting={meeting.id}")
        return meeting

    async def complete_meeting(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        expected_version: Optional[int] = None,
    ) -> Meeting:
        """Complete a meeting with canonical guarantees."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "complete")

        if expected_version is not None:
            validate_optimistic_concurrency(meeting, expected_version)

        # Complete the meeting
        meeting.status = "completed"
        meeting.valid_to = utcnow()
        meeting.updated_at = utcnow()
        meeting.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.completed",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting.id,
                "title": meeting.title,
            },
        )

        logger.info(f"Canonical meeting completed: meeting={meeting.id}")
        return meeting

    async def cancel_meeting(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        expected_version: Optional[int] = None,
    ) -> Meeting:
        """Cancel a meeting with canonical guarantees."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "cancel")

        if expected_version is not None:
            validate_optimistic_concurrency(meeting, expected_version)

        # Cancel the meeting
        meeting.status = "cancelled"
        meeting.valid_to = utcnow()
        meeting.updated_at = utcnow()
        meeting.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.cancelled",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting.id,
                "title": meeting.title,
            },
        )

        logger.info(f"Canonical meeting cancelled: meeting={meeting.id}")
        return meeting

    async def add_attendee(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        employee_id: str,
        role: str = "participant",
    ) -> MeetingAttendee:
        """Add an attendee to a meeting."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "add_attendee")

        # Check if already an attendee
        existing = await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.meeting_id == meeting_id,
                MeetingAttendee.employee_id == employee_id,
            )
        )
        existing_attendee = existing.scalars().first()
        if existing_attendee:
            if existing_attendee.valid_to is None:
                raise ValueError("Employee is already an attendee of this meeting")
            # Reactivate
            existing_attendee.valid_to = None
            existing_attendee.role = role
            existing_attendee.rsvp_at = utcnow()
            await db.flush()
            return existing_attendee

        # Check governance for target employee
        target_employee = await db.get(Employee, employee_id)
        if not target_employee:
            raise ValueError(f"Employee not found: {employee_id}")

        if target_employee.organization_id != caller.organization_id:
            raise MeetingGovernanceViolation("Cross-tenant attendee addition denied")

        # Create attendance
        attendee = MeetingAttendee(
            organization_id=caller.organization_id,
            meeting_id=meeting_id,
            employee_id=employee_id,
            role=role,
            rsvp_at=utcnow(),
            valid_from=utcnow(),
        )
        db.add(attendee)
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.attendee_added",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "employee_id": employee_id,
                "role": role,
            },
        )

        return attendee

    async def set_rsvp(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        employee_id: str,
        status: str,
    ) -> MeetingAttendee:
        """Set RSVP status for an attendee."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "rsvp")

        attendee = await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.meeting_id == meeting_id,
                MeetingAttendee.employee_id == employee_id,
            )
        )
        attendee = attendee.scalars().first()
        if not attendee:
            raise ValueError("Attendee not found")

        old_status = attendee.status
        attendee.status = status
        attendee.rsvp_at = utcnow()
        attendee.updated_at = utcnow()
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.rsvp_changed",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "employee_id": employee_id,
                "from": old_status,
                "to": status,
            },
        )

        return attendee

    async def add_agenda_item(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        title: str,
        description: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        sort_order: Optional[int] = None,
        context_references: Optional[Dict[str, Optional[str]]] = None,
        source_event_id: Optional[str] = None,
    ) -> MeetingAgendaItem:
        """Add an agenda item to a meeting."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "add_agenda")

        # Determine sort order
        if sort_order is None:
            max_order = await db.execute(
                select(func.max(MeetingAgendaItem.sort_order)).where(
                    MeetingAgendaItem.meeting_id == meeting_id
                )
            )
            sort_order = (max_order.scalar() or 0) + 1

        # Build fingerprint data
        agenda_data = {
            "meeting_id": meeting_id,
            "title": title,
            "sort_order": sort_order,
        }
        fingerprint = self._compute_fingerprint(agenda_data)

        # Check exact-once
        existing = await db.execute(
            select(MeetingAgendaItem).where(
                MeetingAgendaItem.meeting_id == meeting_id,
                MeetingAgendaItem.fingerprint == fingerprint,
            )
        )
        existing_item = existing.scalars().first()
        if existing_item:
            logger.info(f"Exact-once: identical agenda item fingerprint, returning existing")
            return existing_item

        agenda_item = MeetingAgendaItem(
            organization_id=caller.organization_id,
            meeting_id=meeting_id,
            title=title,
            description=description,
            duration_minutes=duration_minutes,
            sort_order=sort_order,
            valid_from=utcnow(),
            fingerprint=fingerprint,
        )
        db.add(agenda_item)
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.agenda_item_added",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "agenda_item_id": agenda_item.id,
                "title": title,
            },
        )

        return agenda_item

    async def add_action_item(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        title: str,
        description: Optional[str] = None,
        assignee_id: Optional[str] = None,
        due_date: Optional[datetime] = None,
        context_references: Optional[Dict[str, Optional[str]]] = None,
        source_event_id: Optional[str] = None,
    ) -> MeetingActionItem:
        """Add an action item to a meeting."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "add_action_item")

        # Build fingerprint data
        action_data = {
            "meeting_id": meeting_id,
            "title": title,
            "assignee_id": assignee_id,
        }
        fingerprint = self._compute_fingerprint(action_data)

        # Check exact-once
        existing = await db.execute(
            select(MeetingActionItem).where(
                MeetingActionItem.meeting_id == meeting_id,
                MeetingActionItem.fingerprint == fingerprint,
            )
        )
        existing_item = existing.scalars().first()
        if existing_item:
            logger.info(f"Exact-once: identical action item fingerprint, returning existing")
            return existing_item

        action_item = MeetingActionItem(
            organization_id=caller.organization_id,
            meeting_id=meeting_id,
            title=title,
            description=description,
            assignee_id=assignee_id,
            due_date=due_date,
            fingerprint=fingerprint,
            valid_from=utcnow(),
        )
        db.add(action_item)
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.action_item_added",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "action_item_id": action_item.id,
                "title": title,
                "assignee_id": assignee_id,
            },
        )

        return action_item

    async def complete_action_item(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        action_item_id: str,
        expected_version: Optional[int] = None,
    ) -> MeetingActionItem:
        """Complete an action item."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "complete_action_item")

        action_item = await db.get(MeetingActionItem, action_item_id)
        if not action_item or action_item.meeting_id != meeting_id:
            raise ValueError("Action item not found")

        if expected_version is not None:
            validate_optimistic_concurrency(action_item, expected_version)

        action_item.status = "completed"
        action_item.completed_at = utcnow()
        action_item.updated_at = utcnow()
        action_item.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.action_item_completed",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "action_item_id": action_item_id,
            },
        )

        return action_item

    def _validate_meeting_type(self, meeting_type: str) -> str:
        """Validate and normalize meeting type."""
        meeting_type_lower = meeting_type.lower()
        if meeting_type_lower not in self._valid_types:
            raise InvalidMeetingType(
                f"Invalid meeting type: {meeting_type}. Valid types: {', '.join(CANONICAL_MEETING_TYPES)}"
            )
        return meeting_type_lower

    def _validate_meeting_state(self, state: str) -> str:
        """Validate and normalize meeting state."""
        state_lower = state.lower()
        if state_lower not in self._valid_states:
            raise InvalidMeetingState(
                f"Invalid meeting state: {state}. Valid states: {', '.join(CANONICAL_MEETING_STATES)}"
            )
        return state_lower

    async def link_meeting_to_decision(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        decision_id: str,
    ) -> Meeting:
        """Link a meeting to a canonical decision."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "link_decision")

        # Verify decision exists and is accessible - look up by decision_id field
        result = await db.execute(
            select(CompanyDecision).where(
                CompanyDecision.decision_id == decision_id,
                CompanyDecision.organization_id == caller.organization_id,
            )
        )
        decision = result.scalars().first()
        if not decision:
            raise ValueError("Decision not found or not accessible")

        meeting.decision_id = decision_id
        meeting.updated_at = utcnow()
        meeting.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.decision_linked",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "decision_id": decision_id,
            },
        )

        logger.info(f"Meeting linked to decision: meeting={meeting_id}, decision={decision_id}")
        return meeting

    async def link_meeting_to_commitment(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        commitment_id: str,
    ) -> Meeting:
        """Link a meeting to a canonical commitment."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "link_commitment")

        # Verify commitment exists and is accessible
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != caller.organization_id:
            raise ValueError("Commitment not found or not accessible")

        meeting.commitment_id = commitment_id
        meeting.updated_at = utcnow()
        meeting.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="meeting.commitment_linked",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "meeting_id": meeting_id,
                "commitment_id": commitment_id,
            },
        )

        logger.info(f"Meeting linked to commitment: meeting={meeting_id}, commitment={commitment_id}")
        return meeting

    async def get_meeting_with_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
    ) -> Optional[Meeting]:
        """Get a meeting with full contextual information."""
        meeting = await self._check_meeting_governance(db, caller, meeting_id, "read")

        # Load related entities
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, OrganizationalResponsibility

        if meeting.decision_id:
            decision = await db.get(CompanyDecision, meeting.decision_id)
            meeting.decision = decision

        if meeting.commitment_id:
            commitment = await db.get(CompanyCommitment, meeting.commitment_id)
            meeting.commitment = commitment

        if meeting.objective_id:
            from app.models.execution_strategy import CompanyObjective
            objective = await db.get(CompanyObjective, meeting.objective_id)
            meeting.objective = objective

        if meeting.commitment_id:
            commitment = await db.get(CompanyCommitment, meeting.commitment_id)
            meeting.commitment = commitment

        if meeting.responsibility_id:
            responsibility = await db.get(OrganizationalResponsibility, meeting.responsibility_id)
            meeting.responsibility = responsibility

        if meeting.decision_id:
            decision = await db.get(CompanyDecision, meeting.decision_id)
            meeting.decision = decision

        if meeting.action_id:
            from app.models.company_actions import CompanyAction
            action = await db.get(CompanyAction, meeting.action_id)
            meeting.action = action

        # Load attendees
        attendees = await db.execute(
            select(MeetingAttendee).where(
                MeetingAttendee.meeting_id == meeting_id,
                MeetingAttendee.valid_to.is_(None) | (MeetingAttendee.valid_to > utcnow()),
            )
        )
        meeting.attendees = list(attendees.scalars().all())

        # Load agenda
        agenda = await db.execute(
            select(MeetingAgendaItem).where(
                MeetingAgendaItem.meeting_id == meeting_id,
                MeetingAgendaItem.valid_to.is_(None) | (MeetingAgendaItem.valid_to > utcnow()),
            ).order_by(MeetingAgendaItem.sort_order)
        )
        meeting.agenda = list(agenda.scalars().all())

        # Load action items
        action_items = await db.execute(
            select(MeetingActionItem).where(
                MeetingActionItem.meeting_id == meeting_id,
                MeetingActionItem.valid_to.is_(None) | (MeetingActionItem.valid_to > utcnow()),
            ).order_by(MeetingActionItem.created_at)
        )
        meeting.action_items = list(action_items.scalars().all())

        return meeting


# Global instance
canonical_meeting_service = CanonicalMeetingService()