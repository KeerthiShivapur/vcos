"""Organizational Intelligence Service — Gate 8.5.

This service derives organizational intelligence from canonical company reality:
- responsibility intelligence (gaps, overlaps, concentration)
- capacity intelligence (team/department overload, specialist bottlenecks)
- dependency intelligence (cross-team dependencies, critical paths)
- organizational fragility (single points of failure, concentration risks)

All derived from canonical reality — no parallel state.
"""

import logging
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, or_, func, join
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team, TeamMember
from app.models.meeting import Meeting, MeetingParticipant
from app.models.workload import WorkloadSnapshot
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.intelligence.company_context import CallerAccess

logger = logging.getLogger("vcos.intelligence.organizational_intelligence")


@dataclass
class OrganizationalContext:
    """Organizational context for an employee/team/department."""
    organization_id: str
    employee_id: Optional[str] = None
    team_id: Optional[str] = None
    department_id: Optional[str] = None
    
    # Responsibilities
    responsibilities: List[Dict[str, Any]] = None
    
    # Commitments
    commitments: List[Dict[str, Any]] = None
    
    # Accountability
    accountability_links: List[Dict[str, Any]] = None
    
    # Capacity
    workload: Optional[Dict[str, Any]] = None
    capacity_hours: float = 0.0
    allocated_hours: float = 0.0
    utilization: float = 0.0
    
    # Dependencies
    dependencies: List[Dict[str, Any]] = None
    blocked_by: List[Dict[str, Any]] = None
    blocking: List[Dict[str, Any]] = None
    
    # Organizational position
    department: Optional[Dict[str, Any]] = None
    team: Optional[Dict[str, Any]] = None
    manager: Optional[Dict[str, Any]] = None
    direct_reports: List[Dict[str, Any]] = None
    
    # Temporal
    derived_at: datetime = None
    version: int = 1


class OrganizationalIntelligenceService:
    """Service for deriving organizational intelligence from canonical reality."""

    def __init__(self):
        pass

    async def derive_organizational_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: Optional[str] = None,
        team_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> OrganizationalContext:
        """Derive organizational context for an employee/team/department."""
        
        if employee_id is None:
            if not caller.employee_id:
                raise ValueError("No employee_id provided and caller has no employee_id")
            employee_id = caller.employee_id

        # Get target employee with relationships
        target = await db.get(Employee, employee_id, options=[
            # Note: Would need joinedload for relationships
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
                raise ValueError("Insufficient permissions to view organizational context")

        # Build context
        context = OrganizationalContext(
            organization_id=caller.organization_id,
            employee_id=target.id,
            team_id=target.team_id,
            department_id=target.department_id,
            derived_at=utcnow(),
        )

        # Get responsibilities
        context.responsibilities = await self._get_responsibilities(db, caller, target.id)
        
        # Get commitments via responsibilities
        context.commitments = await self._get_commitments_via_responsibilities(db, caller, target.id)
        
        # Get accountability links
        context.accountability_links = await self._get_accountability_links(db, caller, target.id)
        
        # Get capacity/workload
        workload_data = await self._get_workload(db, caller.organization_id, target.id)
        context.workload = workload_data
        if workload_data:
            context.capacity_hours = workload_data.get("capacity_hours", 0)
            context.allocated_hours = workload_data.get("allocated_hours", 0)
            context.utilization = workload_data.get("utilization", 0)

        # Get dependencies
        context.dependencies = await self._get_dependencies(db, caller, target.id)
        context.blocked_by = await self._get_blocked_by(db, caller, target.id)
        context.blocking = await self._get_blocking(db, caller, target.id)

        # Organizational position
        context.department = await self._get_department_info(db, target.department_id)
        context.team = await self._get_team_info(db, target.team_id)
        context.manager = await self._get_manager_info(db, target.manager_id)
        context.direct_reports = await self._get_direct_reports(db, target.id)

        return context

    async def _get_responsibilities(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get active responsibilities for an employee."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.state == "active",
            ).order_by(OrganizationalResponsibility.valid_from.desc())
        )
        responsibilities = []
        for r in result.scalars().all():
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
                "commitment_id": r.commitment_id,
                "authorization_id": r.authorization_id,
                "objective_id": r.objective_id,
                "initiative_id": r.initiative_id,
                "project_id": r.project_id,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "supersedes_id": r.supersedes_id,
                "version": r.version,
            })
        return responsibilities

    async def _get_commitments_via_responsibilities(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get commitments via employee's responsibilities."""
        from app.models.execution_strategy import CompanyCommitment
        
        # Get responsibilities first
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = resp_result.scalars().all()
        commitment_ids = [r.commitment_id for r in responsibilities if r.commitment_id]
        
        if not commitment_ids:
            return []
        
        # Get commitments
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.id.in_(commitment_ids),
            )
        )
        commitments = []
        for c in result.scalars().all():
            commitments.append({
                "id": c.id,
                "type": c.commitment_type,
                "title": c.title,
                "description": c.description,
                "state": c.state,
                "scope_type": c.scope_type,
                "scope_id": c.scope_id,
                "objective_id": c.objective_id,
                "initiative_id": c.initiative_id,
                "project_id": c.project_id,
                "decision_id": c.decision_id,
                "authorization_id": c.authorization_id,
                "fingerprint": c.fingerprint,
                "version": c.version,
            })
        return commitments

    async def _get_accountability_links(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get accountability links for an employee via their responsibilities."""
        from app.models.execution_strategy import AccountabilityLink, OrganizationalResponsibility
        
        # Get responsibilities first
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = resp_result.scalars().all()
        responsibility_ids = [r.id for r in responsibilities]
        
        if not responsibility_ids:
            return []
        
        result = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == caller.organization_id,
                AccountabilityLink.responsibility_id.in_(responsibility_ids),
            )
        )
        links = []
        for link in result.scalars().all():
            links.append({
                "id": link.id,
                "commitment_id": link.commitment_id,
                "authorization_id": link.authorization_id,
                "responsibility_id": link.responsibility_id,
                "accountability_type": link.accountability_type,
                "delegated_from_id": link.delegated_from_id,
                "delegation_depth": link.delegation_depth,
                "valid_from": link.valid_from,
                "valid_to": link.valid_to,
                "fingerprint": link.fingerprint,
                "version": link.version,
            })
        return links

    async def _get_workload(
        self, db: AsyncSession, organization_id: str, employee_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get current workload snapshot for an employee."""
        from app.models.workload import WorkloadSnapshot
        
        result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == organization_id,
                WorkloadSnapshot.employee_id == employee_id,
            ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
        )
        workload = result.scalars().first()
        if not workload:
            return None
        
        return {
            "id": workload.id,
            "period_start": workload.period_start,
            "period_end": workload.period_end,
            "capacity_hours": workload.capacity_hours,
            "allocated_hours": workload.allocated_hours,
            "utilization": workload.utilization,
            "tasks_count": workload.tasks_count,
            "meetings_hours": workload.meetings_hours,
            "is_overloaded": workload.is_overloaded,
        }

    async def _get_dependencies(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get task dependencies for an employee."""
        from app.models.task import Task, TaskDependency
        
        # Get tasks assigned to employee
        tasks_result = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.assignee_id == employee_id,
                Task.status.in_(("todo", "in_progress", "review")),
            )
        )
        tasks = tasks_result.scalars().all()
        task_ids = [t.id for t in tasks]
        
        if not task_ids:
            return []
        
        # Get dependencies
        result = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == caller.organization_id,
                TaskDependency.task_id.in_(task_ids),
            )
        )
        deps = []
        for dep in result.scalars().all():
            dep_task = await db.get(Task, dep.depends_on_task_id)
            deps.append({
                "task_id": dep.task_id,
                "depends_on_task_id": dep.depends_on_task_id,
                "kind": dep.kind,
                "blocking_task": {
                    "id": dep_task.id,
                    "title": dep_task.title,
                    "status": dep_task.status,
                } if dep_task else None,
            })
        return deps

    async def _get_blocked_by(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get tasks blocked by other tasks."""
        from app.models.task import Task, TaskDependency
        from sqlalchemy.orm import aliased
        
        DependsOnTask = aliased(Task)
        
        # Find tasks assigned to employee that depend on incomplete tasks
        DependsOnTask = aliased(Task)
        result = await db.execute(
            select(Task).join(
                TaskDependency, Task.id == TaskDependency.task_id
            ).join(
                DependsOnTask, TaskDependency.depends_on_task_id == DependsOnTask.id
            ).where(
                TaskDependency.organization_id == caller.organization_id,
                Task.assignee_id == employee_id,
                Task.status.in_(("todo", "in_progress")),
                DependsOnTask.status != "completed",
            ).limit(20)
        )
        blocked_tasks = result.scalars().all()
        
        blocked = []
        for task in blocked_tasks:
            deps = await db.execute(
                select(TaskDependency).where(
                    TaskDependency.organization_id == caller.organization_id,
                    TaskDependency.task_id == task.id,
                )
            )
            blocking = []
            for dep in deps.scalars().all():
                blocking_task = await db.get(Task, dep.depends_on_task_id)
                if blocking_task and blocking_task.status != "completed":
                    blocking.append({
                        "task_id": blocking_task.id,
                        "title": blocking_task.title,
                        "status": blocking_task.status,
                        "dependency_kind": dep.kind,
                    })
            if blocking:
                blocked.append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "blocking": blocking,
                })
        return blocked

    async def _get_blocking(
        self, db: AsyncSession, caller: CallerAccess, employee_id: str
    ) -> List[Dict[str, Any]]:
        """Get tasks that are blocked by this employee's tasks."""
        from app.models.task import Task, TaskDependency
        
        # Find tasks assigned to employee that other tasks depend on
        tasks_result = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.assignee_id == employee_id,
                Task.status.in_(("todo", "in_progress", "review")),
            )
        )
        tasks = tasks_result.scalars().all()
        task_ids = [t.id for t in tasks]
        
        if not task_ids:
            return []
        
        # Find tasks that depend on these tasks
        from sqlalchemy.orm import aliased
        DependentTask = aliased(Task)
        result = await db.execute(
            select(TaskDependency, Task).join(
                DependentTask, TaskDependency.task_id == DependentTask.id
            ).where(
                TaskDependency.organization_id == caller.organization_id,
                TaskDependency.depends_on_task_id.in_(task_ids),
                DependentTask.status.in_(("todo", "in_progress")),
            )
        )
        blocking = []
        for dep, dependent_task in result.all():
            blocking.append({
                "task_id": dependent_task.id,
                "title": dependent_task.title,
                "status": dependent_task.status,
                "depends_on_task_id": dep.depends_on_task_id,
                "dependency_kind": dep.kind,
            })
        return blocking

    async def _get_department_info(
        self, db: AsyncSession, department_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not department_id:
            return None
        dept = await db.get(Department, department_id)
        if not dept:
            return None
        return {
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "description": dept.description,
            "parent_id": dept.parent_id,
            "head_id": dept.head_id,
        }

    async def _get_team_info(
        self, db: AsyncSession, team_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not team_id:
            return None
        team = await db.get(Team, team_id)
        if not team:
            return None
        return {
            "id": team.id,
            "name": team.name,
            "code": team.code,
            "description": team.description,
            "department_id": team.department_id,
            "lead_id": team.lead_id,
        }

    async def _get_manager_info(
        self, db: AsyncSession, manager_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not manager_id:
            return None
        mgr = await db.get(Employee, manager_id)
        if not mgr:
            return None
        return {
            "id": mgr.id,
            "employee_number": mgr.employee_number,
            "full_name": mgr.full_name,
            "designation": mgr.designation,
            "email": mgr.email,
        }

    async def _get_direct_reports(
        self, db: AsyncSession, employee_id: str
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Employee).where(
                Employee.manager_id == employee_id,
                Employee.status == "active",
            )
        )
        reports = []
        for emp in result.scalars().all():
            reports.append({
                "id": emp.id,
                "employee_number": emp.employee_number,
                "full_name": emp.full_name,
                "designation": emp.designation,
                "email": emp.email,
                "team_id": emp.team_id,
                "department_id": emp.department_id,
            })
        return reports


# Global instance
organizational_intelligence_service = OrganizationalIntelligenceService()