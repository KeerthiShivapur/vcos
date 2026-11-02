"""Organizational Change Continuity Service — Gate 8.5.

This service preserves historical organizational structure and enables
temporal queries about organizational state at any point in time.
"""

import logging
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team, TeamMember
from app.models.execution_strategy import OrganizationalResponsibility
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.intelligence.company_context import CallerAccess

logger = logging.getLogger("vcos.intelligence.organizational_change")


@dataclass
class OrganizationalSnapshot:
    """Point-in-time organizational snapshot."""
    timestamp: datetime
    employee_id: str
    department_id: Optional[str]
    department_name: Optional[str]
    team_id: Optional[str]
    team_name: Optional[str]
    manager_id: Optional[str]
    manager_name: Optional[str]
    role_id: Optional[str]
    role_name: Optional[str]
    responsibilities: List[Dict[str, Any]]
    commitments: List[Dict[str, Any]]
    workload: Optional[Dict[str, Any]]


class OrganizationalChangeContinuityService:
    """Service for preserving and querying historical organizational state."""
    
    def __init__(self):
        pass

    async def get_organizational_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[OrganizationalSnapshot]:
        """Get organizational history for an employee."""
        from app.models.employee import Employee, EmployeeTimeline
        
        # Get employee timeline
        query = select(EmployeeTimeline).where(
            EmployeeTimeline.organization_id == caller.organization_id,
            EmployeeTimeline.employee_id == employee_id,
        )
        
        if from_date:
            query = query.where(EmployeeTimeline.occurred_at >= from_date)
        if to_date:
            query = query.where(EmployeeTimeline.occurred_at <= to_date)
        
        query = query.order_by(EmployeeTimeline.occurred_at.asc())
        result = await db.execute(query)
        
        snapshots = []
        for event in result.scalars().all():
            # Reconstruct state at this point
            snapshot = await self._reconstruct_snapshot_at(
                db, caller, employee_id, event.occurred_at
            )
            if snapshot:
                snapshots.append(snapshot)
        
        return snapshots

    async def _reconstruct_snapshot_at(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        employee_id: str,
        at_time: datetime,
    ) -> Optional[OrganizationalSnapshot]:
        """Reconstruct organizational state at a specific point in time."""
        from app.models.employee import Employee
        from app.models.execution_strategy import OrganizationalResponsibility, CompanyCommitment
        from app.models.workload import WorkloadSnapshot
        
        # Get employee state at time (using timeline events)
        emp = await db.get(Employee, employee_id)
        if not emp:
            return None
        
        # Get department at time
        dept_name = None
        # Current department
        dept = await db.get(Department, emp.department_id)
        dept_name = dept.name if dept else None
        
        # Get team at time
        team_name = None
        team = await db.get(Team, emp.team_id)
        team_name = team.name if team else None
        
        # Get manager at time
        manager_name = None
        mgr = await db.get(Employee, emp.manager_id)
        manager_name = mgr.full_name if mgr else None
        
        # Get responsibilities at time
        responsibilities = []
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.valid_from <= at_time,
                or_(
                    OrganizationalResponsibility.valid_to.is_(None),
                    OrganizationalResponsibility.valid_to > at_time,
                ),
                OrganizationalResponsibility.state == "active",
            )
        )
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
            })
        
        # Get commitments at time
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.valid_from <= at_time,
                or_(
                    CompanyCommitment.valid_to.is_(None),
                    CompanyCommitment.valid_to > at_time,
                ),
            )
        )
        commitments = []
        for c in commitments_result.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "state": c.state,
            })
        
        # Workload at time
        workload = None
        from app.models.workload import WorkloadSnapshot
        workload_result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.employee_id == employee_id,
                WorkloadSnapshot.period_start <= at_time,
                WorkloadSnapshot.period_end >= at_time,
            ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
        )
        workload = workload_result.scalars().first()
        workload_data = None
        if workload:
            workload_data = {
                "capacity_hours": workload.capacity_hours,
                "allocated_hours": workload.allocated_hours,
                "utilization": workload.utilization,
            }
        
        return OrganizationalSnapshot(
            timestamp=at_time,
            employee_id=employee_id,
            department_id=emp.department_id,
            department_name=dept_name,
            team_id=emp.team_id,
            team_name=team_name,
            manager_id=emp.manager_id,
            manager_name=manager_name,
            role_id=None,  # Would need role history
            role_name=None,
            responsibilities=[],
            commitments=[],
            workload=workload_data,
        )

    async def get_department_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        department_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get department history including membership changes."""
        from app.models.department import Department
        from app.models.employee import Employee
        
        # Get department timeline events
        # This would require a dedicated timeline table for departments
        # For now, return current state
        return []

    async def get_team_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        team_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get team history including membership changes."""
        from app.models.team import Team, TeamMember
        
        team = await db.get(Team, team_id)
        if not team or team.organization_id != caller.organization_id:
            return []
        
        # Get membership timeline
        query = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.organization_id == caller.organization_id,
        )
        if from_date:
            query = query.where(TeamMember.joined_at >= from_date)
        if to_date:
            query = query.where(TeamMember.joined_at <= to_date)
        
        query = query.order_by(TeamMember.joined_at.asc())
        result = await db.execute(query)
        
        history = []
        for tm in result.scalars().all():
            emp = await db.get(Employee, tm.employee_id)
            history.append({
                "employee_id": tm.employee_id,
                "employee_name": emp.full_name if emp else None,
                "role": tm.role,
                "joined_at": tm.joined_at,
                "left_at": tm.left_at,
            })
        
        return history

    async def get_responsibility_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get responsibility history for a person."""
        from app.models.execution_strategy import OrganizationalResponsibility
        
        query = select(OrganizationalResponsibility).where(
            OrganizationalResponsibility.organization_id == caller.organization_id,
            OrganizationalResponsibility.person_id == person_id,
        )
        
        if from_date:
            query = query.where(OrganizationalResponsibility.valid_from >= from_date)
        if to_date:
            query = query.where(OrganizationalResponsibility.valid_to <= to_date)
        
        query = query.order_by(OrganizationalResponsibility.valid_from.desc())
        result = await db.execute(query)
        
        history = []
        for r in result.scalars().all():
            history.append({
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
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "state": r.state,
                "supersedes_id": r.supersedes_id,
            })
        
        return history

    async def get_commitment_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        commitment_id: str,
    ) -> List[Dict[str, Any]]:
        """Get commitment history including state changes."""
        from app.models.execution_strategy import CompanyCommitment
        
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != caller.organization_id:
            return []
        
        # Get state changes via timeline (would need a dedicated timeline table)
        # For now return current state
        return [{
            "id": commitment.id,
            "title": commitment.title,
            "state": commitment.state,
            "valid_from": commitment.valid_from,
            "valid_to": commitment.valid_to,
            "supersedes_id": commitment.supersedes_id,
        }]

    async def get_cross_domain_timeline(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get cross-domain timeline for an entity (responsibility + commitment + action + outcome)."""
        from app.models.execution_strategy import OrganizationalResponsibility, CompanyCommitment
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        from app.models.execution_strategy import CompanyObjective
        
        timeline = []
        
        if entity_type == "commitment":
            # Get commitment
            from app.models.execution_strategy import CompanyCommitment
            commitment = await db.get(CompanyCommitment, entity_id)
            if commitment and commitment.organization_id == caller.organization_id:
                # Get linked responsibilities
                from app.models.execution_strategy import OrganizationalResponsibility
                resp_result = await db.execute(
                    select(OrganizationalResponsibility).where(
                        OrganizationalResponsibility.commitment_id == entity_id,
                    )
                )
                for resp in resp_result.scalars().all():
                    timeline.append({
                        "event_type": "responsibility_assigned",
                        "entity_type": "responsibility",
                        "entity_id": resp.id,
                        "title": resp.title,
                        "type": resp.responsibility_type,
                        "person_id": resp.person_id,
                        "valid_from": resp.valid_from,
                        "valid_to": resp.valid_to,
                        "state": resp.state,
                    })
                
                # Create actions
                from app.models.company_actions import CompanyAction
                actions = await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.source_commitment_id == entity_id,
                    )
                )
                for action in actions.scalars().all():
                    timeline.append({
                        "event_type": "action_created",
                        "entity_type": "action",
                        "entity_id": action.id,
                        "title": action.title,
                        "state": action.state,
                        "created_at": action.created_at,
                    })
                    
                    # Get outcomes
                    from app.models.company_actions import CompanyActionOutcome
                    outcomes = await db.execute(
                        select(CompanyActionOutcome).where(
                            CompanyActionOutcome.action_id == action.id,
                        )
                    )
                    for outcome in outcomes.scalars().all():
                        timeline.append({
                            "event_type": "outcome_recorded",
                            "entity_type": "outcome",
                            "entity_id": outcome.id,
                            "outcome_type": outcome.outcome_type,
                            "verdict": outcome.verdict,
                            "effectiveness": outcome.effectiveness,
                            "recorded_at": outcome.measured_at,
                        })
        
        # Sort by time
        timeline.sort(key=lambda x: x.get("created_at") or x.get("valid_from") or x.get("recorded_at") or datetime.min)
        return timeline


# Global instance
organizational_change_service = OrganizationalChangeContinuityService()