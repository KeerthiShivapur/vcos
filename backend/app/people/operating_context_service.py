"""Canonical Operating Context Service — Gate 8.1.

This service derives a person's current operating context from canonical company reality.
It is a READ/DERIVATION layer — not a second source of truth.

The operating context answers questions such as:
- Who is this person?
- What organization do they belong to?
- What team are they part of?
- What responsibilities are currently active?
- What commitments are active?
- What work context is active?
- What is their explicit operating presence?
- What meetings/work contexts are relevant?
- What company context should be visible to them?

This is a READ/DERIVATION layer. It must not become a second source of truth.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.models.employee import Employee, EmployeePresence, EmployeeAvailability
from app.models.organization import Organization
from app.models.team import Team, TeamMember
from app.models.department import Department
from app.models.project import Project
from app.models.task import Task
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
)
from app.models.meeting import Meeting, MeetingAttendee
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecision
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.intelligence.canonical_mutation import EpistemicStatus

from app.models.employee import Employee, EmployeePresence, EmployeeAvailability
from app.models.organization import Organization

logger = logging.getLogger("vcos.people.operating_context")


@dataclass
class OperatingPresence:
    """Canonical operating presence state."""
    employee_id: str
    employee_number: str
    full_name: str
    status: str
    is_online: bool
    last_active_at: Optional[datetime]
    valid_from: datetime
    valid_to: Optional[datetime]
    timezone: Optional[str]
    device: Optional[str]
    version: int
    fingerprint: Optional[str]


@dataclass
class OperatingContext:
    """Canonical operating context for a person — derived from canonical reality."""
    # Identity
    employee_id: str
    employee_number: str
    full_name: str
    email: str
    user_id: Optional[str]
    avatar_url: Optional[str]
    designation: Optional[str]
    timezone: str
    language: Optional[str]

    # Organizational context
    organization_id: str
    organization_name: str
    department_id: Optional[str]
    department_name: Optional[str]
    team_id: Optional[str]
    team_name: Optional[str]
    manager_id: Optional[str]
    manager_name: Optional[str]
    location_id: Optional[str]
    location_name: Optional[str]

    # Presence
    presence: Optional[OperatingPresence] = None
    availability_status: Optional[str] = None
    is_online: bool = False

    # Active responsibilities
    responsibilities: List[Dict[str, Any]] = field(default_factory=list)

    # Active commitments
    commitments: List[Dict[str, Any]] = field(default_factory=list)

    # Current work
    current_actions: List[Dict[str, Any]] = field(default_factory=list)
    current_tasks: List[Dict[str, Any]] = field(default_factory=list)
    current_projects: List[Dict[str, Any]] = field(default_factory=list)

    # Meetings
    upcoming_meetings: List[Dict[str, Any]] = field(default_factory=list)

    # Governance
    governance_scopes: List[Dict[str, Any]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    org_wide: bool = False

    # Metadata
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class OperatingContextService:
    """Canonical service for deriving operating context from canonical reality.

    This is a READ/DERIVATION layer — it must not become a second source of truth.
    All data is derived from canonical PostgreSQL reality through canonical models.
    """

    def __init__(self):
        pass

    async def derive_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: Optional[str] = None,
    ) -> OperatingContext:
        """Derive operating context for a person from canonical reality.

        Args:
            db: Database session
            caller: Caller access context (governance)
            employee_id: Optional target employee ID (defaults to caller's employee)

        Returns:
            Derived operating context

        Raises:
            ValueError: Employee not found
            PresenceGovernanceViolation: Governance violation
        """
        # Determine target employee
        if employee_id is None:
            if not caller.employee_id:
                raise ValueError("No employee_id provided and caller has no employee_id")
            employee_id = caller.employee_id

        # Get target employee with relationships
        target = await db.get(Employee, employee_id, options=[
            joinedload(Employee.department),
            joinedload(Employee.team),
            joinedload(Employee.manager),
            joinedload(Employee.location),
        ])
        if not target:
            raise ValueError(f"Employee not found: {employee_id}")

        # Governance check
        if target.organization_id != caller.organization_id:
            raise ValueError("Cross-tenant access denied")

        # Check permissions if accessing another person
        if caller.employee_id != employee_id:
            permissions = await caller.get_permissions(db)
            management_perms = {"employees:manage", "employees:read"}
            if not any(p in permissions for p in management_perms):
                raise ValueError("Insufficient permissions to view operating context")

        # Get organization
        org = await db.get(Organization, caller.organization_id)

        # Get current presence
        from app.people.canonical_presence_service import canonical_presence_service
        presence = await canonical_presence_service.get_current_presence(
            db, organization_id=caller.organization_id, employee_id=employee_id
        )

        # Get availability
        availability = await db.execute(
            select(EmployeeAvailability).where(
                EmployeeAvailability.organization_id == caller.organization_id,
                EmployeeAvailability.employee_id == employee_id,
            )
        )
        availability_obj = availability.scalar_one_or_none()

        # Get active responsibilities
        responsibilities = await self._get_active_responsibilities(db, employee_id)

        # Get active commitments
        commitments = await self._get_active_commitments(db, employee_id)

        # Get current work (actions and tasks)
        current_actions = await self._get_current_actions(db, employee_id)
        current_tasks = await self._get_current_tasks(db, employee_id)
        current_projects = await self._get_current_projects(db, employee_id)

        # Get upcoming meetings
        upcoming_meetings = await self._get_upcoming_meetings(db, employee_id)

        # Get governance scopes
        governance_scopes = await self._get_governance_scopes(db, caller)

        # Get permissions
        permissions = await caller.get_permissions(db)

        # Build operating presence
        presence_obj = None
        if presence:
            presence_obj = OperatingPresence(
                employee_id=presence.employee_id,
                employee_number=target.employee_number,
                full_name=target.full_name,
                status=presence.status,
                is_online=presence.is_online,
                last_active_at=presence.last_active_at,
                valid_from=presence.valid_from,
                valid_to=presence.valid_to,
                timezone=presence.timezone,
                device=presence.device,
                version=presence.version,
                fingerprint=presence.fingerprint,
            )

        # Build operating context
        context = OperatingContext(
            employee_id=target.id,
            employee_number=target.employee_number,
            full_name=target.full_name,
            email=target.email,
            user_id=target.user_id,
            avatar_url=target.avatar_url,
            designation=target.designation,
            timezone=target.timezone,
            language=target.language,
            organization_id=target.organization_id,
            organization_name=org.name if org else "",
            department_id=target.department_id,
            department_name=target.department.name if target.department else None,
            team_id=target.team_id,
            team_name=target.team.name if target.team else None,
            manager_id=target.manager_id,
            manager_name=target.manager.full_name if target.manager else None,
            location_id=target.location_id,
            location_name=target.location.name if target.location else None,
            presence=presence_obj,
            availability_status=availability_obj.status if availability_obj else None,
            is_online=presence.is_online if presence else False,
            responsibilities=responsibilities,
            commitments=commitments,
            current_actions=current_actions,
            current_tasks=current_tasks,
            current_projects=current_projects,
            upcoming_meetings=upcoming_meetings,
            governance_scopes=governance_scopes,
            permissions=list(permissions),
            org_wide=caller.org_wide,
        )

        logger.info(f"Derived operating context for employee {employee_id}")
        return context

    async def _get_active_responsibilities(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get active responsibilities for an employee."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = []
        for r in result.scalars().all():
            responsibilities.append({
                "id": r.id,
                "type": r.responsibility_type,
                "title": r.title,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "authorization_id": r.authorization_id,
                "started_at": r.valid_from,
            })
        return responsibilities

    async def _get_active_commitments(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get active commitments for an employee (via task/project assignments)."""
        # Get commitments through tasks assigned to the employee
        result = await db.execute(
            select(CompanyCommitment)
            .join(Task, CompanyCommitment.project_id == Task.project_id)
            .where(
                Task.assignee_id == employee_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            )
        )
        commitments = []
        for c in result.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "type": c.commitment_type,
                "state": c.state,
                "scope_type": c.scope_type,
                "scope_id": c.scope_id,
                "authorization_id": c.authorization_id,
            })
        return commitments

    async def _get_current_actions(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get current actions for an employee."""
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.assignee_id == employee_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            ).order_by(CompanyAction.updated_at.desc()).limit(10)
        )
        actions = []
        for a in result.scalars().all():
            actions.append({
                "id": a.id,
                "title": a.title,
                "type": a.action_type,
                "state": a.state,
                "description": a.description,
                "source_commitment_id": a.source_commitment_id,
            })
        return actions

    async def _get_current_tasks(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get current tasks for an employee."""
        result = await db.execute(
            select(Task).where(
                Task.assignee_id == employee_id,
                Task.status.in_(("todo", "in_progress", "review")),
            ).order_by(Task.updated_at.desc()).limit(20)
        )
        tasks = []
        for t in result.scalars().all():
            tasks.append({
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "project_id": t.project_id,
            })
        return tasks

    async def _get_current_projects(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get current projects for an employee."""
        # Get projects via team membership or task assignment
        result = await db.execute(
            select(Project).join(Task).where(
                Task.assignee_id == employee_id,
                Project.status == "active",
            ).distinct().limit(10)
        )
        projects = []
        for p in result.scalars().all():
            projects.append({
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "status": p.status,
            })
        return projects

    async def _get_upcoming_meetings(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get upcoming meetings for an employee."""
        now = utcnow()
        result = await db.execute(
            select(Meeting).join(MeetingAttendee).where(
                MeetingAttendee.employee_id == employee_id,
                Meeting.start_at >= now,
                Meeting.status.in_(("scheduled", "in_progress")),
            ).order_by(Meeting.start_at).limit(10)
        )
        meetings = []
        for m in result.scalars().all():
            meetings.append({
                "id": m.id,
                "title": m.title,
                "start_at": m.start_at,
                "end_at": m.end_at,
                "status": m.status,
                "meeting_code": m.meeting_code,
            })
        return meetings

    async def _get_governance_scopes(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get governance scopes for caller."""
        from app.models.governance import GovernanceScope
        result = await db.execute(
            select(GovernanceScope).where(
                GovernanceScope.organization_id == caller.organization_id,
                GovernanceScope.id.in_(caller.visible_scope_ids),
            )
        )
        scopes = []
        for s in result.scalars().all():
            scopes.append({
                "id": s.id,
                "name": s.name,
                "type": s.scope_type,
                "parent_id": s.parent_id,
                "entity_id": s.entity_id,
            })
        return scopes


operating_context_service = OperatingContextService()