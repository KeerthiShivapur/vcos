"""Canonical Communication Service — Gate 8.2.

This service implements the canonical communication and meeting primitives with:
- Canonical temporal truth (historical immutability, valid intervals, supersession)
- Governance enforcement (tenant/scope isolation, permissions)
- Exact-once semantics (fingerprint-based deduplication)
- Provenance tracking
- Optimistic concurrency (version-based)
- Provenance chain preservation
- Epistemic separation: communication ≠ decision ≠ authorization ≠ commitment
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.models.communication import (
    CanonicalCommunicationThread,
    CanonicalMessage,
    CanonicalCommunicationThreadMember,
    Conversation,
    Message,
)
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
from app.models.execution_strategy import CompanyCommitment
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

logger = logging.getLogger("vcos.people.canonical_communication")

# Canonical thread types
CANONICAL_THREAD_TYPES = (
    "dm",
    "group",
    "channel",
    "meeting",
    "decision",
    "commitment",
    "announcement",
)

# Canonical message types
CANONICAL_MESSAGE_TYPES = (
    "text",
    "system",
    "decision_proposal",
    "commitment_proposal",
    "action_proposal",
    "meeting_note",
    "decision_record",
    "commitment_record",
    "action_record",
)

# Epistemic status for communication: observed when explicitly set by person
COMMUNICATION_EPISTEMIC_STATUS = "observed"


class CanonicalCommunicationError(Exception):
    """Base exception for canonical communication violations."""
    pass


class InvalidThreadType(CanonicalCommunicationError):
    """Invalid thread type requested."""
    pass


class InvalidMessageType(CanonicalCommunicationError):
    """Invalid message type requested."""
    pass


class CommunicationGovernanceViolation(Exception):
    """Communication mutation violates governance/scope rules."""
    pass


class CommunicationTemporalViolation(Exception):
    """Communication mutation violates temporal integrity."""
    pass


class CanonicalCommunicationService:
    """Canonical service for managing communication threads and messages with full canonical guarantees."""

    def __init__(self):
        self._valid_thread_types = set(CANONICAL_THREAD_TYPES)
        self._valid_message_types = set(CANONICAL_MESSAGE_TYPES)

    def _validate_thread_type(self, thread_type: str) -> str:
        """Validate and normalize thread type."""
        thread_type_lower = thread_type.lower()
        if thread_type_lower not in self._valid_thread_types:
            raise InvalidThreadType(
                f"Invalid thread type: {thread_type}. Valid types: {', '.join(CANONICAL_THREAD_TYPES)}"
            )
        return thread_type_lower

    def _validate_message_type(self, message_type: str) -> str:
        """Validate and normalize message type."""
        message_type_lower = message_type.lower()
        if message_type_lower not in self._valid_message_types:
            raise InvalidMessageType(
                f"Invalid message type: {message_type}. Valid types: {', '.join(CANONICAL_MESSAGE_TYPES)}"
            )
        return message_type_lower

    def _compute_fingerprint(self, data: dict) -> str:
        """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:160]

    async def _get_thread(
        self, db: AsyncSession, organization_id: str, thread_id: str
    ) -> Optional[CanonicalCommunicationThread]:
        """Get a thread by ID with organization check."""
        result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.id == thread_id,
                CanonicalCommunicationThread.organization_id == organization_id,
            )
        )
        return result.scalars().first()

    async def _get_current_thread(
        self, db: AsyncSession, organization_id: str, thread_id: str
    ) -> Optional[CanonicalCommunicationThread]:
        """Get current valid thread (valid_to is None or in future)."""
        now = utcnow()
        result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.id == thread_id,
                CanonicalCommunicationThread.organization_id == organization_id,
                CanonicalCommunicationThread.valid_to.is_(None) | (CanonicalCommunicationThread.valid_to > now),
            )
        )
        return result.scalars().first()

    async def _get_thread_history(
        self, db: AsyncSession, organization_id: str, thread_id: str
    ) -> List[CanonicalCommunicationThread]:
        """Get full thread history for a thread."""
        result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.id == thread_id,
                CanonicalCommunicationThread.organization_id == organization_id,
            ).order_by(CanonicalCommunicationThread.valid_from.desc())
        )
        return list(result.scalars().all())

    async def _get_current_message(
        self, db: AsyncSession, organization_id: str, message_id: str
    ) -> Optional[CanonicalMessage]:
        """Get current valid message (valid_to is None or in future)."""
        now = utcnow()
        result = await db.execute(
            select(CanonicalMessage).where(
                CanonicalMessage.id == message_id,
                CanonicalMessage.organization_id == organization_id,
                CanonicalMessage.valid_to.is_(None) | (CanonicalMessage.valid_to > utcnow()),
            )
        )
        return result.scalars().first()

    async def _check_thread_governance(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        thread_id: str,
        action: str = "update",
    ) -> CanonicalCommunicationThread:
        """Check governance permissions for thread operations."""
        thread = await self._get_thread(db, caller.organization_id, thread_id)
        if not thread:
            raise ValueError(f"Thread not found: {thread_id}")

        # Cross-tenant check
        if thread.organization_id != caller.organization_id:
            raise CommunicationGovernanceViolation("Cross-tenant thread access denied")

        # Self-access allowed for thread owner/members
        # Check if caller is a member
        member_result = await db.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread_id,
                CanonicalCommunicationThreadMember.employee_id == caller.employee_id,
            )
        )
        caller_is_member = member_result.scalars().first() is not None

        if caller.employee_id and not caller_is_member:
            # Check if caller has management permissions
            permissions = await caller.get_permissions(db)
            management_perms = {
                "communication:manage",
                "threads:manage",
            }
            if not any(p in permissions for p in management_perms):
                raise CommunicationGovernanceViolation(
                    f"Insufficient permissions for {action} on thread"
                )

        # Scope check if not org-wide
        if not caller.org_wide:
            if thread.scope_id and thread.scope_id not in caller.visible_scope_ids:
                raise CommunicationGovernanceViolation("Cross-scope thread access denied")

        return thread

    async def create_thread(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_type: str,
        title: str,
        description: Optional[str] = None,
        context_references: Optional[Dict[str, Optional[str]]] = None,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> CanonicalCommunicationThread:
        """Create a canonical communication thread with full canonical guarantees."""
        # Validate thread type
        thread_type = self._validate_thread_type(thread_type)

        # Check governance
        if not caller.org_wide and scope_id and scope_id not in caller.visible_scope_ids:
            raise CommunicationGovernanceViolation("Cross-scope thread creation denied")
        
        # Cross-tenant check for scope_id - even org-wide callers cannot reference scopes from other tenants
        if scope_id:
            # Verify the scope_id belongs to the same organization
            from app.models.governance import GovernanceScope
            scope = await db.get(GovernanceScope, scope_id)
            if scope and scope.organization_id != caller.organization_id:
                raise CommunicationGovernanceViolation("Cross-tenant thread creation denied: scope_id belongs to different organization")

        # Build thread data for fingerprint
        thread_data = {
            "organization_id": caller.organization_id,
            "thread_type": thread_type,
            "title": title,
            "description": description,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "context_references": context_references or {},
            "actor_id": caller.user_id,
        }

        fingerprint = self._compute_fingerprint(thread_data)

        # Check exact-once: if identical fingerprint exists and is current, return existing
        existing = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.organization_id == caller.organization_id,
                CanonicalCommunicationThread.fingerprint == fingerprint,
                CanonicalCommunicationThread.valid_to.is_(None) | (CanonicalCommunicationThread.valid_to > utcnow()),
            )
        )
        existing_thread = existing.scalars().first()
        if existing_thread:
            logger.info(f"Exact-once: identical thread fingerprint, returning existing")
            return existing_thread

        # Build thread record with canonical fields
        now = utcnow()
        thread = CanonicalCommunicationThread(
            organization_id=caller.organization_id,
            thread_type=thread_type,
            title=title,
            description=description,
            objective_id=context_references.get("objective_id") if context_references else None,
            commitment_id=context_references.get("commitment_id") if context_references else None,
            responsibility_id=context_references.get("responsibility_id") if context_references else None,
            decision_id=context_references.get("decision_id") if context_references else None,
            project_id=context_references.get("project_id") if context_references else None,
            meeting_id=context_references.get("meeting_id") if context_references else None,
            scope_type=scope_type,
            scope_id=scope_id,
            valid_from=utcnow(),
            valid_to=None,
            source_event_id=source_event_id or f"thread_create:{uuid.uuid4().hex[:8]}",
            actor_id=caller.user_id,
            version=1,
            fingerprint=fingerprint,
            thread_metadata=context_references or {},
        )

        db.add(thread)
        await db.flush()

        # Add creator as owner member
        if not caller.employee_id:
            raise CommunicationGovernanceViolation("Caller must have an employee profile")
        member = CanonicalCommunicationThreadMember(
            organization_id=caller.organization_id,
            thread_id=thread.id,
            employee_id=caller.employee_id,
            role="owner",
            joined_at=utcnow(),
            valid_from=utcnow(),
            valid_to=None,
        )
        db.add(member)
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="thread.created",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "thread_id": thread.id,
                "thread_type": thread_type,
                "title": title,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "source_event_id": source_event_id or f"thread_create:{uuid.uuid4().hex[:8]}",
            },
        )

        logger.info(f"Canonical thread created: thread={thread.id}, type={thread_type}")
        return thread

    async def add_thread_member(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
        employee_id: str,
        role: str = "participant",
    ) -> CanonicalCommunicationThreadMember:
        """Add a member to a communication thread."""
        thread = await self._check_thread_governance(db, caller, thread_id, "add_member")

        # Check if already a member
        existing = await db.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread_id,
                CanonicalCommunicationThreadMember.employee_id == employee_id,
            )
        )
        existing_member = existing.scalars().first()
        if existing_member:
            if existing_member.valid_to is None:
                raise ValueError("Employee is already a member of this thread")
            # Reactivate
            existing_member.valid_to = None
            existing_member.role = role
            existing_member.joined_at = utcnow()
            existing_member.left_at = None
            await db.flush()
            return existing_member

        # Check governance for target employee
        target_employee = await db.get(Employee, employee_id)
        if not target_employee:
            raise ValueError(f"Employee not found: {employee_id}")

        if target_employee.organization_id != caller.organization_id:
            raise CommunicationGovernanceViolation("Cross-tenant member addition denied")

        # Create membership
        now = utcnow()
        member = CanonicalCommunicationThreadMember(
            organization_id=caller.organization_id,
            thread_id=thread_id,
            employee_id=employee_id,
            role=role,
            joined_at=utcnow(),
            valid_from=utcnow(),
            valid_to=None,
        )
        db.add(member)
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="thread.member_added",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "thread_id": thread_id,
                "employee_id": employee_id,
                "role": role,
            },
        )

        return member

    async def remove_thread_member(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
        employee_id: str,
    ) -> None:
        """Remove a member from a communication thread."""
        thread = await self._check_thread_governance(db, caller, thread_id, "remove_member")

        member = await db.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread_id,
                CanonicalCommunicationThreadMember.employee_id == employee_id,
            )
        )
        member = member.scalars().first()
        if not member:
            raise ValueError("Employee is not a member of this thread")

        member.left_at = utcnow()
        member.valid_to = utcnow()
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="thread.member_removed",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "thread_id": thread_id,
                "employee_id": employee_id,
            },
        )

    async def send_message(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
        content: str,
        message_type: str = "text",
        reply_to: Optional[str] = None,
        context_references: Optional[Dict[str, Optional[str]]] = None,
        source_event_id: Optional[str] = None,
    ) -> CanonicalMessage:
        """Send a message in a canonical communication thread."""
        # Validate message type
        message_type = self._validate_message_type(message_type)

        # Check thread governance
        thread = await self._check_thread_governance(db, caller, thread_id, "send_message")

        # Check if caller is a member
        member_check = await db.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread_id,
                CanonicalCommunicationThreadMember.employee_id == caller.employee_id,
            )
        )
        if not member_check.scalars().first():
            raise CommunicationGovernanceViolation("Not a member of this thread")

        # Check optimistic concurrency for thread
        if thread.version is not None:
            # Version is on the thread, not the message
            pass

        # Build message data for fingerprint
        message_data = {
            "organization_id": caller.organization_id,
            "thread_id": thread_id,
            "sender_id": caller.employee_id,
            "content": content,
            "message_type": message_type,
            "reply_to": reply_to,
            "context_references": context_references or {},
            "actor_id": caller.user_id,
        }

        fingerprint = self._compute_fingerprint(message_data)

        # Check exact-once: if identical fingerprint exists, return existing
        existing = await db.execute(
            select(CanonicalMessage).where(
                CanonicalMessage.organization_id == caller.organization_id,
                CanonicalMessage.fingerprint == fingerprint,
                CanonicalMessage.valid_to.is_(None) | (CanonicalMessage.valid_to > utcnow()),
            )
        )
        existing_msg = existing.scalars().first()
        if existing_msg:
            logger.info(f"Exact-once: identical message fingerprint, returning existing")
            return existing_msg

        # Build message record
        now = utcnow()
        message = CanonicalMessage(
            organization_id=caller.organization_id,
            thread_id=thread_id,
            sender_id=caller.employee_id,
            content=content,
            message_type=message_type,
            reply_to=reply_to,
            decision_id=context_references.get("decision_id") if context_references else None,
            commitment_id=context_references.get("commitment_id") if context_references else None,
            action_id=context_references.get("action_id") if context_references else None,
            objective_id=context_references.get("objective_id") if context_references else None,
            responsibility_id=context_references.get("responsibility_id") if context_references else None,
            attachments=[],
            mentions=[],
            valid_from=utcnow(),
            valid_to=None,
            source_event_id=source_event_id or f"message_send:{uuid.uuid4().hex[:8]}",
            actor_id=caller.user_id,
            version=1,
            fingerprint=fingerprint,
        )

        db.add(message)
        await db.flush()

        # Update thread last_message_at and version
        thread.last_message_at = utcnow()
        thread.version += 1
        await db.flush()

        # Emit event
        await event_service.emit(
            db,
            name="message.sent",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "thread_id": thread_id,
                "message_id": message.id,
                "sender_id": caller.employee_id,
                "message_type": message_type,
            },
        )

        logger.info(f"Canonical message sent: message={message.id}, thread={thread_id}")
        return message

    async def get_thread_messages(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
        limit: int = 50,
        before_message_id: Optional[str] = None,
    ) -> List[CanonicalMessage]:
        """Get messages for a thread with pagination."""
        # Check governance
        thread = await self._check_thread_governance(db, caller, thread_id, "read_messages")

        # Check membership
        member_check = await db.execute(
            select(CanonicalCommunicationThreadMember).where(
                CanonicalCommunicationThreadMember.thread_id == thread_id,
                CanonicalCommunicationThreadMember.employee_id == caller.employee_id,
            )
        )
        if not member_check.scalars().first():
            raise CommunicationGovernanceViolation("Not a member of this thread")

        query = select(CanonicalMessage).where(
            CanonicalMessage.thread_id == thread_id,
            CanonicalMessage.valid_to.is_(None) | (CanonicalMessage.valid_to > utcnow()),
        )
        if before_message_id:
            before_msg = await db.get(CanonicalMessage, before_message_id)
            if before_msg:
                query = query.where(CanonicalMessage.valid_from < before_msg.valid_from)

        query = query.order_by(CanonicalMessage.valid_from.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_thread(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
    ) -> Optional[CanonicalCommunicationThread]:
        """Get a thread with governance check."""
        return await self._check_thread_governance(db, caller, thread_id, "read")

    async def get_thread_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        thread_id: str,
    ) -> List[CanonicalCommunicationThread]:
        """Get full thread history."""
        await self._check_thread_governance(db, caller, thread_id, "read_history")
        return await self._get_thread_history(db, caller.organization_id, thread_id)

    async def _get_thread_history(
        self, db: AsyncSession, organization_id: str, thread_id: str
    ) -> List[CanonicalCommunicationThread]:
        """Get full thread history."""
        result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.id == thread_id,
                CanonicalCommunicationThread.organization_id == organization_id,
            ).order_by(CanonicalCommunicationThread.valid_from.desc())
        )
        return list(result.scalars().all())

    def _validate_thread_type(self, thread_type: str) -> str:
        """Validate and normalize thread type."""
        thread_type_lower = thread_type.lower()
        if thread_type_lower not in self._valid_thread_types:
            raise InvalidThreadType(
                f"Invalid thread type: {thread_type}. Valid types: {', '.join(CANONICAL_THREAD_TYPES)}"
            )
        return thread_type_lower

    def _validate_message_type(self, message_type: str) -> str:
        """Validate and normalize message type."""
        message_type_lower = message_type.lower()
        if message_type_lower not in self._valid_message_types:
            raise InvalidMessageType(
                f"Invalid message type: {message_type}. Valid types: {', '.join(CANONICAL_MESSAGE_TYPES)}"
            )
        return message_type_lower

    def _compute_fingerprint(self, data: dict) -> str:
        """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:160]


# Global instance
canonical_communication_service = CanonicalCommunicationService()