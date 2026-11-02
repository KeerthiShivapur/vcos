"""Organizational Operating Context Service — Gate 8.5.

Extends the existing OperatingContextService with organizational intelligence.
This is a READ/DERIVATION layer — not a second source of truth.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field

from sqlalchemy import select, and_, func, or_
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
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.models.meeting import Meeting, MeetingAttendee
from app.models.communication import (
    CanonicalCommunicationThread,
    CanonicalMessage,
    CanonicalCommunicationThreadMember,
)
from app.models.workload import WorkloadSnapshot
from app.intelligence.organizational_attention_service import organizational_attention_service
from app.intelligence.organizational_intelligence_service import organizational_intelligence_service
from app.intelligence.company_context import resolve_caller_access, CallerAccess
from app.intelligence.canonical_mutation import EpistemicStatus
from app.people.operating_context_service import operating_context_service

logger = logging.getLogger("vcos.people.organizational_operating_context")


@dataclass
class OrganizationalOperatingContext:
    """Company operating context with organizational intelligence — derived from canonical reality."""
    
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
    presence: Optional[Dict[str, Any]] = None
    availability_status: Optional[str] = None
    is_online: bool = False

    # Active responsibilities (enhanced with org intelligence)
    responsibilities: List[Dict[str, Any]] = field(default_factory=list)

    # Active commitments
    commitments: List[Dict[str, Any]] = field(default_factory=list)

    # Accountability
    accountability_links: List[Dict[str, Any]] = field(default_factory=list)

    # Current work
    current_actions: List[Dict[str, Any]] = field(default_factory=list)
    current_tasks: List[Dict[str, Any]] = field(default_factory=list)
    current_projects: List[Dict[str, Any]] = field(default_factory=list)

    # Meetings
    upcoming_meetings: List[Dict[str, Any]] = field(default_factory=list)

    # Communication
    communication_threads: List[Dict[str, Any]] = field(default_factory=list)

    # Organizational Intelligence (NEW for 8.5)
    organizational_context: Optional[Dict[str, Any]] = None
    capacity_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    responsibility_gaps: List[Dict[str, Any]] = field(default_factory=list)
    dependency_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    critical_people: List[Dict[str, Any]] = field(default_factory=list)
    orphaned_commitments: List[Dict[str, Any]] = field(default_factory=list)
    orphaned_responsibilities: List[Dict[str, Any]] = field(default_factory=list)
    objective_drift: List[Dict[str, Any]] = field(default_factory=list)

    # Governance
    governance_scopes: List[Dict[str, Any]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    org_wide: bool = False

    # Metadata
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class OrganizationalOperatingContextService:
    """Canonical service for deriving company operating context with organizational intelligence.
    
    Extends OperatingContextService with organizational intelligence layer.
    This is a READ/DERIVATION layer — it must not become a second source of truth.
    All data is derived from canonical PostgreSQL reality through canonical models.
    """

    def __init__(self):
        pass

    async def derive_organizational_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: Optional[str] = None,
    ) -> OrganizationalOperatingContext:
        """Derive organizational operating context for a person from canonical reality.
        
        Extends the base operating context with organizational intelligence.
        """
        # First get the base operating context
        base_context = await operating_context_service.derive_operating_context(
            db, caller=caller, employee_id=employee_id
        )
        
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
            management_perms = {"employees:manage", "employees:read", "orgchart:read"}
            if not any(p in permissions for p in management_perms):
                raise ValueError("Insufficient permissions to view operating context")

        # Get organization
        org = await db.get(Organization, caller.organization_id)

        # Get base context from OperatingContextService
        base_context = await operating_context_service.derive_operating_context(
            db, caller=caller, employee_id=employee_id
        )

        # Get organizational intelligence context
        org_intelligence = await organizational_intelligence_service.derive_organizational_context(
            db, caller=caller, employee_id=employee_id
        )

        # Get organizational attention
        org_attention = await organizational_attention_service.derive_organizational_attention(
            db, caller=caller
        )

        # Build enhanced organizational operating context
        context = OrganizationalOperatingContext(
            employee_id=base_context.employee_id,
            employee_number=base_context.employee_number,
            full_name=base_context.full_name,
            email=base_context.email,
            user_id=base_context.user_id,
            avatar_url=base_context.avatar_url,
            designation=base_context.designation,
            timezone=base_context.timezone,
            language=base_context.language,
            organization_id=base_context.organization_id,
            organization_name=base_context.organization_name,
            department_id=base_context.department_id,
            department_name=base_context.department_name,
            team_id=base_context.team_id,
            team_name=base_context.team_name,
            manager_id=base_context.manager_id,
            manager_name=base_context.manager_name,
            location_id=base_context.location_id,
            location_name=base_context.location_name,
            presence=base_context.presence,
            availability_status=base_context.availability_status,
            is_online=base_context.is_online,
            responsibilities=base_context.responsibilities,
            commitments=base_context.commitments,
            current_actions=base_context.current_actions,
            current_tasks=base_context.current_tasks,
            current_projects=base_context.current_projects,
            upcoming_meetings=base_context.upcoming_meetings,
            governance_scopes=base_context.governance_scopes,
            permissions=base_context.permissions,
            org_wide=base_context.org_wide,
            derived_at=base_context.derived_at,
            version=base_context.version,
            
            # NEW: Organizational Intelligence (8.5)
            organizational_context=org_intelligence,
            capacity_conflicts=[],
            responsibility_gaps=[],
            dependency_conflicts=[],
            bottlenecks=[],
            critical_people=[],
            orphaned_commitments=[],
            orphaned_responsibilities=[],
            objective_drift=[],
        )

        logger.info(f"Derived organizational operating context for employee {employee_id}")
        return context

    async def derive_team_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        team_id: str,
    ) -> Dict[str, Any]:
        """Derive operating context for a team."""
        # Get team
        team = await db.get(Team, team_id)
        if not team or team.organization_id != caller.organization_id:
            raise ValueError("Team not found or access denied")

        # Governance check
        if not caller.org_wide and team.department_id not in caller.visible_scope_ids:
            raise ValueError("Insufficient permissions for team")

        # Get team members (from TeamMember cross-memberships)
        members_result = await db.execute(
            select(TeamMember, Employee).join(Employee).where(
                TeamMember.team_id == team_id,
                TeamMember.organization_id == caller.organization_id,
            )
        )
        members = []
        for tm, emp in members_result.all():
            members.append({
                "id": emp.id,
                "employee_number": emp.employee_number,
                "full_name": emp.full_name,
                "designation": emp.designation,
                "role": tm.role,
                "joined_at": tm.joined_at,
            })
        
        # Also get direct team members via Employee.team_id
        direct_members_result = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.team_id == team_id,
            )
        )
        for emp in direct_members_result.scalars().all():
            # Check if already added via TeamMember
            if not any(m["id"] == emp.id for m in members):
                members.append({
                    "id": emp.id,
                    "employee_number": emp.employee_number,
                    "full_name": emp.full_name,
                    "designation": emp.designation,
                    "role": "member",
                    "joined_at": None,
                })

        # Get team's responsibilities
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.team_id == team_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = []
        for r in resp_result.scalars().all():
            responsibilities.append({
                "id": r.id,
                "type": r.responsibility_type,
                "title": r.title,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "raci": {
                    "accountable": r.raci_accountable,
                    "responsible": r.raci_responsible,
                    "consulted": r.raci_consulted,
                    "informed": r.raci_informed,
                },
                "person_id": r.person_id,
                "commitment_id": r.commitment_id,
            })

        # Get team's commitments (via scope_type="team")
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.scope_type == "team",
                CompanyCommitment.scope_id == team_id,
                CompanyCommitment.state.in_(("authorized", "active")),
            )
        )
        commitments = []
        for c in commitments_result.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "state": c.state,
                "commitment_type": c.commitment_type,
            })

        # Get team workload
        from app.models.workload import WorkloadSnapshot
        team_workload = await db.execute(
            select(
                func.sum(WorkloadSnapshot.capacity_hours).label("total_capacity"),
                func.sum(WorkloadSnapshot.allocated_hours).label("total_allocated"),
                func.count(WorkloadSnapshot.id).label("member_count"),
            ).join(Employee).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                Employee.team_id == team_id,
                WorkloadSnapshot.period_end >= utcnow(),
            )
        )
        workload_row = team_workload.first()

        return {
            "team_id": team.id,
            "team_name": team.name,
            "team_code": team.code,
            "department_id": team.department_id,
            "lead_id": team.lead_id,
            "members": members,
            "responsibilities": responsibilities,
            "commitments": commitments,
            "workload": {
                "total_capacity": workload_row.total_capacity or 0,
                "total_allocated": workload_row.total_allocated or 0,
                "utilization": (workload_row.total_allocated or 0) / (workload_row.total_capacity or 1) * 100 if workload_row.total_capacity else 0,
                "member_count": workload_row.member_count or 0,
            },
        }

    async def derive_department_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        department_id: str,
    ) -> Dict[str, Any]:
        """Derive operating context for a department."""
        dept = await db.get(Department, department_id)
        if not dept or dept.organization_id != caller.organization_id:
            raise ValueError("Department not found or access denied")

        # Governance check
        if not caller.org_wide and dept.id not in caller.visible_scope_ids:
            raise ValueError("Insufficient permissions for department")

        # Get sub-departments
        sub_depts = await db.execute(
            select(Department).where(
                Department.organization_id == caller.organization_id,
                Department.parent_id == department_id,
            )
        )
        sub_departments = []
        for d in sub_depts.scalars().all():
            sub_departments.append({
                "id": d.id,
                "name": d.name,
                "code": d.code,
                "head_id": d.head_id,
            })

        # Get teams in department
        teams_result = await db.execute(
            select(Team).where(
                Team.organization_id == caller.organization_id,
                Team.department_id == department_id,
            )
        )
        teams = []
        for t in teams_result.scalars().all():
            teams.append({
                "id": t.id,
                "name": t.name,
                "code": t.code,
                "lead_id": t.lead_id,
            })

        # Get department members
        members_result = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.department_id == department_id,
                Employee.status == "active",
            )
        )
        members = []
        for emp in members_result.scalars().all():
            members.append({
                "id": emp.id,
                "employee_number": emp.employee_number,
                "full_name": emp.full_name,
                "designation": emp.designation,
                "team_id": emp.team_id,
            })

        # Get department commitments (via scope_type="department" or project_id)
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                or_(
                    and_(
                        CompanyCommitment.scope_type == "department",
                        CompanyCommitment.scope_id == department_id,
                    ),
                ),
                CompanyCommitment.state.in_(("authorized", "active")),
            )
        )
        commitments = []
        for c in commitments_result.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "state": c.state,
                "commitment_type": c.commitment_type,
            })

        # Department workload
        from app.models.workload import WorkloadSnapshot
        dept_workload = await db.execute(
            select(
                func.sum(WorkloadSnapshot.capacity_hours).label("total_capacity"),
                func.sum(WorkloadSnapshot.allocated_hours).label("total_allocated"),
                func.count(WorkloadSnapshot.id).label("member_count"),
            ).join(Employee).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                Employee.department_id == department_id,
                WorkloadSnapshot.period_end >= utcnow(),
            )
        )
        workload_row = dept_workload.first()

        return {
            "department_id": dept.id,
            "department_name": dept.name,
            "department_code": dept.code,
            "parent_id": dept.parent_id,
            "head_id": dept.head_id,
            "sub_departments": sub_departments,
            "teams": teams,
            "members": members,
            "commitments": commitments,
            "workload": {
                "total_capacity": workload_row.total_capacity or 0,
                "total_allocated": workload_row.total_allocated or 0,
                "utilization": (workload_row.total_allocated or 0) / (workload_row.total_capacity or 1) * 100 if workload_row.total_capacity else 0,
                "member_count": workload_row.member_count or 0,
            },
        }


# Global instance
organizational_operating_context_service = OrganizationalOperatingContextService()