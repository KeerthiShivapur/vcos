"""Canonical Operating Presence Service — Gate 8.1.

This service implements the canonical operating presence primitive with:
- Canonical temporal truth (historical immutability, valid intervals, supersession)
- Governance enforcement (tenant/scope isolation, permissions)
- Exact-once semantics (fingerprint-based deduplication)
- Provenance tracking
- Optimistic concurrency (version-based)
- Provenance chain preservation
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, List

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.employee import Employee, EmployeePresence, CANONICAL_PRESENCE_STATES
from app.models.organization import Organization
from app.models.user import User
from app.services.event_service import event_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.intelligence.canonical_mutation import (
    validate_optimistic_concurrency,
    ExactOnceViolation,
    ConcurrencyViolation,
    CanonicalMutationError,
    EpistemicStatus,
)

logger = logging.getLogger("vcos.people.canonical_presence")

# Canonical presence states per Gate 8.1
CANONICAL_PRESENCE_STATES = (
    "AVAILABLE",
    "IN_MEETING",
    "FOCUS_WORK",
    "AWAY",
    "OFFLINE",
    "DO_NOT_DISTURB",
    "UNAVAILABLE",
)

# Epistemic status for presence: observed when explicitly set by person
PRESENCE_EPISTEMIC_STATUS = EpistemicStatus.OBSERVED


class CanonicalPresenceError(Exception):
    """Base exception for canonical presence violations."""
    pass


class InvalidPresenceState(CanonicalPresenceError):
    """Invalid presence state requested."""
    pass


class PresenceGovernanceViolation(CanonicalPresenceError):
    """Presence mutation violates governance/scope rules."""
    pass


class PresenceTemporalViolation(CanonicalPresenceError):
    """Presence mutation violates temporal integrity."""
    pass


class CanonicalPresenceService:
    """Canonical service for managing operating presence with full canonical guarantees."""

    def __init__(self):
        self._valid_states = set(CANONICAL_PRESENCE_STATES)

    def _validate_state(self, state: str) -> str:
        """Validate and normalize presence state."""
        state_upper = state.upper()
        if state_upper not in self._valid_states:
            raise InvalidPresenceState(
                f"Invalid presence state: {state}. Valid states: {', '.join(CANONICAL_PRESENCE_STATES)}"
            )
        return state_upper

    def _compute_fingerprint(self, data: dict) -> str:
        """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:160]

    async def _get_current_presence(
        self, db: AsyncSession, organization_id: str, employee_id: str
    ) -> Optional[EmployeePresence]:
        """Get current valid presence (valid_to is None or in future)."""
        now = utcnow()
        result = await db.execute(
            select(EmployeePresence).where(
                EmployeePresence.organization_id == organization_id,
                EmployeePresence.employee_id == employee_id,
                EmployeePresence.valid_to.is_(None) | (EmployeePresence.valid_to > now),
            ).order_by(EmployeePresence.valid_from.desc())
        )
        return result.scalars().first()

    async def _get_presence_history(
        self, db: AsyncSession, organization_id: str, employee_id: str
    ) -> List[EmployeePresence]:
        """Get full presence history for an employee."""
        result = await db.execute(
            select(EmployeePresence).where(
                EmployeePresence.organization_id == organization_id,
                EmployeePresence.employee_id == employee_id,
            ).order_by(EmployeePresence.valid_from.desc())
        )
        return list(result.scalars().all())

    async def _check_governance(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        target_employee_id: str,
        action: str = "update",
    ) -> Employee:
        """Check governance permissions for presence operations."""
        # Get target employee
        target = await db.get(Employee, target_employee_id)
        if not target:
            raise ValueError(f"Employee not found: {target_employee_id}")

        # Cross-tenant check
        if target.organization_id != caller.organization_id:
            raise PresenceGovernanceViolation("Cross-tenant presence access denied")

        # Self-update allowed
        if caller.employee_id == target_employee_id:
            return target

        # Check if caller has management permissions
        permissions = await caller.get_permissions(db)
        management_perms = {
            "employees:manage",
            "presence:manage",
            "availability:manage",
        }
        if not any(p in permissions for p in management_perms):
            raise PresenceGovernanceViolation(
                f"Insufficient permissions for {action} presence of another employee"
            )

        # Scope check if not org-wide
        if not caller.org_wide:
            # Check if caller's visible scopes include target's scope
            # For now, deny cross-scope unless org-wide
            if target.department_id and target.department_id not in caller.visible_scope_ids:
                raise PresenceGovernanceViolation("Cross-scope presence access denied")

        return target

    async def set_presence(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: str,
        state: str,
        note: Optional[str] = None,
        source_event_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> EmployeePresence:
        """Set canonical presence with full canonical guarantees.

        Args:
            db: Database session
            caller: Caller access context (governance)
            employee_id: Target employee ID
            state: Canonical presence state
            note: Optional note
            source_event_id: Source event ID for provenance
            expected_version: Expected version for optimistic concurrency

        Returns:
            The new canonical presence record

        Raises:
            InvalidPresenceState: Invalid state
            PresenceGovernanceViolation: Governance violation
            ConcurrencyViolation: Optimistic concurrency conflict
            ExactOnceViolation: Duplicate presence detected
        """
        # Validate state
        state = self._validate_state(state)

        # Check governance
        target = await self._check_governance(db, caller, employee_id, "update")

        # Get current presence for version check and supersession
        current = await self._get_current_presence(db, caller.organization_id, employee_id)

        # Check optimistic concurrency
        if expected_version is not None:
            if current:
                validate_optimistic_concurrency(current, expected_version)
            elif expected_version != 1:
                raise ConcurrencyViolation(
                    f"Expected version {expected_version} but no current presence exists"
                )

        # Prepare presence data for fingerprint (exclude timestamp for exact-once)
        presence_data = {
            "organization_id": caller.organization_id,
            "employee_id": employee_id,
            "state": state,
            "note": note,
            "source_event_id": source_event_id,
            "actor_id": caller.user_id,
        }

        fingerprint = self._compute_fingerprint(presence_data)

        # Check exact-once: if identical fingerprint exists and is current, return existing
        if current and current.fingerprint == fingerprint:
            logger.info(
                f"Exact-once: identical presence fingerprint for employee {employee_id}, returning existing"
            )
            return current

        # Build presence record with canonical fields
        now = utcnow()
        new_presence = EmployeePresence(
            organization_id=caller.organization_id,
            employee_id=employee_id,
            is_online=(state in ("AVAILABLE", "IN_MEETING", "FOCUS_WORK", "DO_NOT_DISTURB")),
            status=state,
            last_active_at=utcnow(),
            timezone=target.timezone,
            valid_from=now,
            valid_to=None,
            source_event_id=source_event_id or f"presence_set:{uuid.uuid4().hex[:8]}",
            actor_id=caller.user_id,
            version=1,
            fingerprint=fingerprint,
            supersedes_id=current.id if current else None,
        )

        # If superseding, close previous presence
        if current:
            current.valid_to = now
            current.updated_at = now
            await db.flush()

        # Check exact-once at database level
        db.add(new_presence)
        try:
            await db.flush()
        except IntegrityError as e:
            if "uq_emp_presence" in str(e):
                raise ExactOnceViolation(f"Duplicate presence for employee {employee_id}")
            raise

        # Emit event
        await event_service.emit(
            db,
            name="employee.presence.changed",
            actor_id=caller.user_id,
            organization_id=caller.organization_id,
            payload={
                "employee_id": employee_id,
                "from": current.status if current else None,
                "to": state,
                "note": None,
                "source_event_id": source_event_id,
            },
        )

        logger.info(f"Canonical presence set: employee={employee_id}, state={state}, version={new_presence.version}")
        return new_presence

    async def get_current_presence(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> Optional[EmployeePresence]:
        """Get current presence for an employee."""
        return await self._get_current_presence(db, organization_id, employee_id)

    async def get_presence_history(
        self, db: AsyncSession, *, organization_id: str, employee_id: str
    ) -> List[EmployeePresence]:
        """Get full presence history for an employee."""
        return await self._get_presence_history(db, organization_id, employee_id)

    async def get_presence_at(
        self, db: AsyncSession, *, organization_id: str, employee_id: str, at: datetime
    ) -> Optional[EmployeePresence]:
        """Get presence at a specific point in time (temporal query)."""
        result = await db.execute(
            select(EmployeePresence).where(
                EmployeePresence.organization_id == organization_id,
                EmployeePresence.employee_id == employee_id,
                EmployeePresence.valid_from <= at,
                EmployeePresence.valid_to.is_(None) | (EmployeePresence.valid_to > at),
            ).order_by(EmployeePresence.valid_from.desc())
        )
        return result.scalars().first()

    async def get_governed_company_presence(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[dict[str, Any]]:
        """Get governed company presence view for caller's visible scope."""
        # Get visible employees based on governance
        visible_employee_ids = set()
        
        if caller.org_wide:
            result = await db.execute(
                select(Employee.id).where(Employee.organization_id == caller.organization_id)
            )
            visible_employee_ids = {row.id for row in result.scalars().all()}
        else:
            # For scoped callers, only visible scope employees
            for scope_id in caller.visible_scope_ids:
                result = await db.execute(
                    select(Employee.id).where(
                        Employee.organization_id == caller.organization_id,
                        Employee.department_id == scope_id,
                    )
                )
                visible_employee_ids.update(row.id for row in result.scalars().all())

        # Get current presence for visible employees
        if not visible_employee_ids:
            return []

        presences = await db.execute(
            select(EmployeePresence, Employee).join(Employee).where(
                EmployeePresence.organization_id == caller.organization_id,
                EmployeePresence.employee_id.in_(visible_employee_ids),
                EmployeePresence.valid_to.is_(None) | (EmployeePresence.valid_to > utcnow()),
            )
        )

        results = []
        for presence, employee in presences.all():
            results.append({
                "employee_id": employee.id,
                "employee_number": employee.employee_number,
                "full_name": employee.full_name,
                "department_id": employee.department_id,
                "team_id": employee.team_id,
                "presence": {
                    "state": presence.status,
                    "is_online": presence.is_online,
                    "last_active_at": presence.last_active_at,
                    "valid_from": presence.valid_from,
                }
            })
        return results


canonical_presence_service = CanonicalPresenceService()