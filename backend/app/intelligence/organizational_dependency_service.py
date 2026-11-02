"""Organizational Dependency Service — Gate 8.5.

This service derives cross-team and cross-organizational dependencies from canonical reality.
It traces dependency chains through the canonical graph:
Person -> Team -> Responsibility -> Commitment -> Action -> Task -> Dependency -> Other Team/Person
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
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.company_actions import CompanyAction
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
)
from app.models.company_operating import CompanyDecision
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.workload import WorkloadSnapshot

logger = logging.getLogger("vcos.intelligence.organizational_dependency")


@dataclass
class DependencyChain:
    """A traced dependency chain through the organizational graph."""
    path: List[Dict[str, Any]]  # Ordered from source to destination
    total_hops: int
    is_blocking: bool
    critical_path: bool
    affected_commitments: List[str]
    affected_objectives: List[str]


class OrganizationalDependencyService:
    """Service for deriving cross-team and cross-organizational dependencies from canonical reality."""

    def __init__(self):
        pass

    async def trace_dependency_chain(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        start_entity_type: str,  # "person", "team", "commitment", "objective"
        start_entity_id: str,
        max_depth: int = 5,
    ) -> DependencyChain:
        """Trace a dependency chain from a starting entity through the organizational graph."""
        
        path = []
        current_type = start_entity_type
        current_id = start_entity_id
        visited = set()
        affected_commitments = set()
        affected_objectives = set()
        is_blocking = False
        critical_path = False
        
        for depth in range(max_depth):
            if (current_type, current_id) in visited:
                break
            visited.add((current_type, current_id))
            
            if current_type == "person":
                node = await self._get_person_info(db, caller, current_id)
                if not node:
                    break
                path.append({
                    "type": "person",
                    "id": node["id"],
                    "name": node["full_name"],
                    "team_id": node.get("team_id"),
                    "department_id": node.get("department_id"),
                    "role": "source" if depth == 0 else "intermediate",
                })
                
                # Get commitments -> responsibilities
                commitments = await self._get_commitments_for_person(db, caller, current_id)
                for c in commitments:
                    affected_commitments.add(c["id"])
                    if c.get("objective_id"):
                        affected_objectives.add(c["objective_id"])
                
                # Get actions
                actions = await self._get_actions_for_person(db, caller, current_id)
                for a in actions:
                    if a.get("target_type") == "task" and a.get("target_id"):
                        current_type = "task"
                        current_id = a["target_id"]
                        break
                
            elif current_type == "task":
                # Add task to path
                from app.models.task import Task
                task = await db.get(Task, current_id)
                if task:
                    path.append({
                        "type": "task",
                        "id": task.id,
                        "name": task.title,
                        "status": task.status,
                        "project_id": task.project_id,
                        "role": "source" if depth == 0 else "intermediate",
                    })
                
                # Task dependencies
                deps = await self._get_task_dependencies(db, caller, current_id)
                if deps:
                    # Follow first blocking dependency
                    for dep in deps:
                        if dep.get("blocking_task"):
                            current_type = "task"
                            current_id = dep["blocking_task"]["id"]
                            is_blocking = True
                            break
                
            elif current_type == "commitment":
                # Add commitment to path
                from app.models.execution_strategy import CompanyCommitment
                commitment = await db.get(CompanyCommitment, current_id)
                if commitment:
                    path.append({
                        "type": "commitment",
                        "id": commitment.id,
                        "name": commitment.title,
                        "state": commitment.state,
                        "objective_id": commitment.objective_id,
                        "role": "source" if depth == 0 else "intermediate",
                    })
                    if commitment.objective_id:
                        affected_objectives.add(commitment.objective_id)
                
                # Get actions for commitment
                actions = await self._get_actions_for_commitment(db, caller, current_id)
                for a in actions:
                    if a.get("target_type") == "task" and a.get("target_id"):
                        current_type = "task"
                        current_id = a["target_id"]
                        break
                
                # Get responsibilities
                responsibilities = await self._get_responsibilities_for_commitment(db, caller, current_id)
                for r in responsibilities:
                    if r.get("person_id"):
                        affected_commitments.add(current_id)
                
            elif current_type == "objective":
                # Add objective to path
                from app.models.execution_strategy import CompanyObjective
                objective = await db.get(CompanyObjective, current_id)
                if objective:
                    path.append({
                        "type": "objective",
                        "id": objective.id,
                        "name": objective.title,
                        "status": objective.status,
                        "role": "source" if depth == 0 else "intermediate",
                    })
                
                # Get initiatives
                initiatives = await self._get_initiatives_for_objective(db, caller, current_id)
                for init in initiatives:
                    affected_objectives.add(current_id)
                
                # Get commitments
                commitments = await self._get_commitments_for_objective(db, caller, current_id)
                for c in commitments:
                    affected_commitments.add(c["id"])
            
            else:
                break
        
        return DependencyChain(
            path=path,
            total_hops=len(path),
            is_blocking=is_blocking,
            critical_path=critical_path,
            affected_commitments=list(affected_commitments),
            affected_objectives=list(affected_objectives),
        )

    async def _get_person_info(
        self, db: AsyncSession, caller: CallerAccess, person_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get person info with team/department."""
        from app.models.employee import Employee
        emp = await db.get(Employee, person_id)
        if not emp or emp.organization_id != caller.organization_id:
            return None
        return {
            "id": emp.id,
            "full_name": emp.full_name,
            "employee_number": emp.employee_number,
            "team_id": emp.team_id,
            "department_id": emp.department_id,
        }

    async def _get_commitments_for_person(
        self, db: AsyncSession, caller: CallerAccess, person_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.execution_strategy import OrganizationalResponsibility, CompanyCommitment
        
        # Get responsibilities for person
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == person_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = resp_result.scalars().all()
        
        commitments = []
        for resp in responsibilities:
            if resp.commitment_id:
                commitment = await db.get(CompanyCommitment, resp.commitment_id)
                if commitment:
                    affected_commitments.add(commitment.id)
                    if commitment.objective_id:
                        affected_objectives.add(commitment.objective_id)
        
        return list(affected_commitments)

    async def _get_actions_for_person(
        self, db: AsyncSession, caller: CallerAccess, person_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.company_actions import CompanyAction
        
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.assignee_id == person_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            ).limit(10)
        )
        actions = []
        for a in result.scalars().all():
            actions.append({
                "id": a.id,
                "title": a.title,
                "action_type": a.action_type,
                "state": a.state,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "source_commitment_id": a.source_commitment_id,
                "source_responsibility_id": a.source_responsibility_id,
            })
        return actions

    async def _get_actions_for_commitment(
        self, db: AsyncSession, caller: CallerAccess, commitment_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.company_actions import CompanyAction
        
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.source_commitment_id == commitment_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            ).limit(10)
        )
        actions = []
        for a in result.scalars().all():
            actions.append({
                "id": a.id,
                "title": a.title,
                "action_type": a.action_type,
                "state": a.state,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "source_commitment_id": a.source_commitment_id,
                "source_responsibility_id": a.source_responsibility_id,
            })
        return actions

    async def _get_task_dependencies(
        self, db: AsyncSession, caller: CallerAccess, task_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.task import Task, TaskDependency
        
        from sqlalchemy.orm import aliased
        DependsOnTask = aliased(Task)
        
        result = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == caller.organization_id,
                TaskDependency.task_id == task_id,
            )
        )
        deps = []
        for dep in result.scalars().all():
            blocking_task = await db.get(Task, dep.depends_on_task_id)
            if blocking_task:
                deps.append({
                    "dependency_kind": dep.kind,
                    "blocking_task": {
                        "id": blocking_task.id,
                        "title": blocking_task.title,
                        "status": blocking_task.status,
                    } if blocking_task else None,
                })
        return deps

    async def _get_commitments_for_commitment(
        self, caller: CallerAccess, commitment_id: str
    ) -> List[Dict[str, Any]]:
        # This doesn't make sense - commitments don't have commitments
        return []

    async def _get_responsibilities_for_commitment(
        self, db: AsyncSession, caller: CallerAccess, commitment_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.execution_strategy import OrganizationalResponsibility
        
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.commitment_id == commitment_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        return [{
            "id": r.id,
            "person_id": r.person_id,
            "type": r.responsibility_type,
            "title": r.title,
        } for r in result.scalars().all()]

    async def _get_commitments_for_objective(
        self, db: AsyncSession, caller: CallerAccess, objective_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.execution_strategy import CompanyCommitment
        
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.objective_id == objective_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            )
        )
        return [{
            "id": c.id,
            "title": c.title,
            "state": c.state,
        } for c in result.scalars().all()]

    async def _get_initiatives_for_objective(
        self, db: AsyncSession, caller: CallerAccess, objective_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.execution_strategy import CompanyInitiative
        
        result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
                CompanyInitiative.objective_id == objective_id,
                CompanyInitiative.status == "active",
            )
        )
        return [{
            "id": i.id,
            "title": i.title,
        } for i in result.scalars().all()]

    async def get_bottleneck_analysis(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> Dict[str, Any]:
        """Analyze organizational bottlenecks."""
        from app.models.workload import WorkloadSnapshot
        from app.models.employee import Employee
        from app.models.team import Team
        from app.models.department import Department
        from app.models.task import Task, TaskDependency
        from app.models.execution_strategy import OrganizationalResponsibility, CompanyCommitment
        from app.models.company_actions import CompanyAction
        from sqlalchemy import func
        
        bottlenecks = {
            "person_bottlenecks": [],
            "team_bottlenecks": [],
            "department_bottlenecks": [],
            "dependency_hubs": [],
        }
        
        # Person bottlenecks - people with high responsibility + high workload + many blockers
        resp_counts = await db.execute(
            select(
                OrganizationalResponsibility.person_id,
                func.count(OrganizationalResponsibility.id).label("resp_count"),
            ).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.state == "active",
            ).group_by(OrganizationalResponsibility.person_id).having(
                func.count(OrganizationalResponsibility.id) >= 3
            ).limit(20)
        )
        
        for row in resp_counts.all():
            emp = await db.get(Employee, row.person_id)
            if not emp:
                continue
            
            workload = await db.execute(
                select(WorkloadSnapshot).where(
                    WorkloadSnapshot.organization_id == caller.organization_id,
                    WorkloadSnapshot.employee_id == row.person_id,
                ).order_by(WorkloadSnapshot.period_start.desc())
            )
            workload = workload.scalars().first()
            
            blocked_count = await db.execute(
                select(func.count(TaskDependency.id)).join(
                    Task, Task.id == TaskDependency.task_id
                ).where(
                    TaskDependency.organization_id == caller.organization_id,
                    Task.assignee_id == row.person_id,
                    Task.status.in_(("todo", "in_progress")),
                )
            )
            blocked_count = blocked_count.scalar() or 0
            
            # Check actions in progress
            actions_count = await db.execute(
                select(func.count(CompanyAction.id)).where(
                    CompanyAction.organization_id == caller.organization_id,
                    CompanyAction.assignee_id == row.person_id,
                    CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
                )
            )
            actions_count = actions_count.scalar() or 0
            
            criticality = row.resp_count * 2
            if workload and workload.utilization > 100:
                criticality += 5
            criticality += blocked_count
            criticality += min(actions_count, 10)
            
            if criticality >= 10:
                severity = "critical"
            elif criticality >= 7:
                severity = "high"
            elif criticality >= 4:
                severity = "medium"
            else:
                continue
            
            emp = await db.get(Employee, row.person_id)
            if emp:
                bottlenecks["person_bottlenecks"].append({
                    "employee_id": row.person_id,
                    "name": emp.full_name,
                    "severity": severity,
                    "responsibility_count": row.resp_count,
                    "utilization": workload.utilization if workload else 0,
                    "blocked_tasks": blocked_count,
                    "active_actions": actions_count,
                    "criticality_score": criticality,
                })
        
        # Team bottlenecks
        team_workloads = await db.execute(
            select(
                Team.id.label("team_id"),
                Team.name.label("team_name"),
                func.avg(WorkloadSnapshot.utilization).label("avg_utilization"),
                func.count(WorkloadSnapshot.id).label("overloaded_count"),
            ).join(
                Employee, Employee.team_id == Team.id
            ).join(
                WorkloadSnapshot, WorkloadSnapshot.employee_id == Employee.id
            ).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.is_overloaded == True,
            ).group_by(Team.id, Team.name).having(
                func.count(WorkloadSnapshot.id) >= 2
            ).limit(10)
        )
        
        for row in team_workloads.all():
            bottlenecks["team_bottlenecks"].append({
                "team_id": row.team_id,
                "team_name": row.team_name,
                "avg_utilization": float(row.avg_utilization),
                "overloaded_count": row.overloaded_count,
            })
        
        # Dependency hubs - tasks that block many others
        from app.models.task import Task, TaskDependency
        from sqlalchemy.orm import aliased
        
        DependsOnTask = aliased(Task)
        dep_hubs = await db.execute(
            select(
                TaskDependency.depends_on_task_id,
                func.count(TaskDependency.id).label("dep_count"),
            ).join(
                Task, Task.id == TaskDependency.depends_on_task_id
            ).where(
                TaskDependency.organization_id == caller.organization_id,
                Task.status != "completed",
            ).group_by(TaskDependency.depends_on_task_id).having(
                func.count(TaskDependency.id) >= 3
            ).limit(15)
        )
        
        for row in dep_hubs.all():
            blocking_task = await db.get(Task, row.depends_on_task_id)
            if blocking_task:
                bottlenecks["dependency_hubs"].append({
                    "task_id": blocking_task.id,
                    "task_title": blocking_task.title,
                    "project_id": blocking_task.project_id,
                    "blocked_count": row.dep_count,
                })
        
        return bottlenecks


# Global instance
organizational_dependency_service = OrganizationalDependencyService()