"""Organizational Capacity Service — Gate 8.6.

This service derives company-wide capacity intelligence from canonical reality:
- Required capacity from commitments, responsibilities, actions, tasks
- Available capacity from workload, availability, skills, organizational capabilities
- Capacity conflicts (deficit/surplus) with provenance
- Capacity deficit propagation through responsibility → commitment → objective chain
- Capability vs capacity distinction

All derived from canonical reality — no parallel state, no second capacity graph.
"""

import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.workload import WorkloadSnapshot
from app.models.employee import Employee, EmployeeAvailability, EmployeeSkill
from app.models.team import Team, TeamMember
from app.models.department import Department
from app.models.project import Project, ProjectMember
from app.models.task import Task, TaskDependency
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilityProjectLink,
    CapabilitySignal,
    CapabilityHistory,
    CAPABILITY_STATES,
    CAPACITY_STATES,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.skills_intelligence import CanonicalSkill, Expertise as ExpertiseState, ExpertiseEvidence
from app.models.skill import Skill as LegacySkill
from app.models.skill_gap import SkillGap, SkillSnapshot

logger = logging.getLogger("vcos.intelligence.organizational_capacity")


@dataclass
class CapacityContext:
    """Capacity context for a person/team/department/organization."""
    # Identity
    organization_id: str
    scope_type: str  # "person", "team", "department", "organization"
    scope_id: Optional[str] = None
    
    # Capacity summary
    total_potential: int = 0
    total_committed: int = 0
    total_reserved: int = 0
    total_available: int = 0
    capacity_state: str = "unknown"
    utilization: float = 0.0
    
    # Demand
    total_demand: int = 0
    demand_by_capability: Dict[str, int] = field(default_factory=dict)
    
    # Allocations
    active_allocations: int = 0
    allocation_gap: int = 0
    
    # Details
    capability_details: List[Dict[str, Any]] = field(default_factory=list)
    overloaded_capabilities: List[Dict[str, Any]] = field(default_factory=list)
    underutilized_capabilities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Provenance
    derived_from: List[str] = field(default_factory=list)
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


@dataclass
class CapacityConflict:
    """A detected capacity conflict with provenance."""
    id: str
    kind: str  # "capacity_deficit", "capability_gap", "concentration_risk", "overcommitment"
    severity: str  # "low", "medium", "high", "critical"
    title: str
    description: str
    scope_type: str
    scope_id: str
    capability: Optional[str] = None
    required: int = 0
    available: int = 0
    deficit: int = 0
    affected_commitments: List[str] = field(default_factory=list)
    affected_objectives: List[str] = field(default_factory=list)
    affected_people: List[str] = field(default_factory=list)
    source_entities: List[Dict[str, Any]] = field(default_factory=list)
    affected_entities: List[Dict[str, Any]] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class OrganizationalCapacityService:
    """Service for deriving organizational capacity intelligence from canonical reality."""
    
    def __init__(self):
        pass

    # ================================================================
    # MAIN ENTRY POINTS
    # ================================================================

    async def derive_capacity_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str,  # "person", "team", "department", "organization"
        scope_id: Optional[str] = None,
    ) -> CapacityContext:
        """Derive capacity context for a given organizational scope."""
        
        if scope_type == "person":
            return await self._derive_person_capacity(db, caller, scope_id)
        elif scope_type == "team":
            return await self._derive_team_capacity(db, caller, scope_id)
        elif scope_type == "department":
            return await self._derive_department_capacity(db, caller, scope_id)
        elif scope_type == "organization":
            return await self._derive_organization_capacity(db, caller)
        else:
            raise ValueError(f"Invalid scope_type: {scope_type}")

    async def detect_capacity_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect all capacity conflicts across the organization."""
        conflicts = []
        
        # 1. Person-level capacity deficits
        person_conflicts = await self._detect_person_capacity_deficits(db, caller)
        conflicts.extend(person_conflicts)
        
        # 2. Team-level capacity overload
        team_conflicts = await self._detect_team_capacity_overload(db, caller)
        conflicts.extend(team_conflicts)
        
        # 3. Department-level capacity strain
        dept_conflicts = await self._detect_department_capacity_strain(db, caller)
        conflicts.extend(dept_conflicts)
        
        # 4. Capability gaps (demand > supply)
        capability_conflicts = await self._detect_capability_gaps(db, caller)
        conflicts.extend(capability_conflicts)
        
        # 5. Concentration risks (single-person dependencies)
        concentration_conflicts = await self._detect_concentration_risks(db, caller)
        conflicts.extend(concentration_conflicts)
        
        # 6. Overcommitment (commitments exceed capacity)
        overcommitment_conflicts = await self._detect_overcommitment(db, caller)
        conflicts.extend(overcommitment_conflicts)
        
        # 7. Allocation gaps (demand not met by allocations)
        allocation_conflicts = await self._detect_allocation_gaps(db, caller)
        conflicts.extend(allocation_conflicts)
        
        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        conflicts.sort(key=lambda c: severity_order.get(c.severity, 3))
        
        logger.info(f"Detected {len(conflicts)} capacity conflicts for org {caller.organization_id}")
        return conflicts

    async def propagate_capacity_deficit(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
    ) -> Dict[str, Any]:
        """Propagate a person's capacity deficit through the responsibility→commitment→objective chain."""
        
        # Get person's responsibilities
        responsibilities = await self._get_person_responsibilities(db, caller, person_id)
        if not responsibilities:
            return {"propagated": False, "reason": "no_responsibilities"}
        
        # Get commitments via responsibilities
        commitment_ids = [r.commitment_id for r in responsibilities if r.commitment_id]
        commitments = await self._get_commitments(db, caller, commitment_ids)
        
        # Get objectives via commitments
        objective_ids = [c.objective_id for c in commitments if c.objective_id]
        objectives = await self._get_objectives(db, caller, objective_ids)
        
        # Get initiatives via objectives
        initiative_ids = []
        for obj in objectives:
            initiatives = await self._get_initiatives_for_objective(db, caller, obj.id)
            initiative_ids.extend([i.id for i in initiatives])
        initiatives = await self._get_initiatives(db, caller, initiative_ids)
        
        # Get actions via commitments
        action_ids = []
        for c in commitments:
            actions = await self._get_actions_for_commitment(db, caller, c.id)
            action_ids.extend([a.id for a in actions])
        actions = await self._get_actions(db, caller, action_ids)
        
        # Get tasks via actions
        task_ids = []
        for a in actions:
            if a.target_type == "task" and a.target_id:
                task_ids.append(a.target_id)
        tasks = await self._get_tasks(db, caller, task_ids)
        
        # Build propagation chain
        propagation = {
            "source_person_id": person_id,
            "responsibilities_affected": len(responsibilities),
            "commitments_affected": len(commitments),
            "objectives_affected": len(objectives),
            "initiatives_affected": len(initiatives),
            "actions_affected": len(actions),
            "tasks_affected": len(tasks),
            "commitments": [
                {
                    "id": c.id,
                    "title": c.title,
                    "state": c.state,
                    "scope_type": c.scope_type,
                    "objective_id": c.objective_id,
                } for c in commitments
            ],
            "objectives": [
                {
                    "id": o.id,
                    "title": o.title,
                    "status": o.status,
                } for o in objectives
            ],
            "derived_at": utcnow().isoformat(),
        }
        
        return propagation

    async def get_capability_capacity(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        capability_name: str,
    ) -> Dict[str, Any]:
        """Get detailed capacity for a specific organizational capability."""
        
        # Get OrgCapability row
        org_cap = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
                OrgCapability.canonical_name == capability_name,
            )
        )
        org_cap = org_cap.scalars().first()
        
        if not org_cap:
            return {
                "capability": capability_name,
                "found": False,
                "message": "No organizational capability record found",
            }
        
        # Get experts
        experts = await self._get_capability_experts(db, caller, org_cap.skill_id)
        
        # Get active project links (demand)
        project_links = await self._get_active_project_links(db, caller, org_cap.skill_id)
        
        # Get allocation demands
        demands = await self._get_allocation_demands(db, caller, capability_name)
        
        # Get allocations
        allocations = await self._get_capacity_allocations(db, caller, capability_name)
        
        # Get signals
        signals = await self._get_capability_signals(db, caller, org_cap.skill_id)
        
        # Get history
        history = await self._get_capability_history(db, caller, org_cap.skill_id)
        
        return {
            "capability": capability_name,
            "found": True,
            "skill_id": org_cap.skill_id,
            "lifecycle": org_cap.lifecycle,
            "confidence": org_cap.confidence,
            "expert_count": org_cap.expert_count,
            "strong_expert_count": org_cap.strong_expert_count,
            "evidence_count": org_cap.evidence_count,
            "capacity": {
                "potential": org_cap.capacity_potential,
                "committed": org_cap.capacity_committed,
                "reserved": org_cap.capacity_reserved,
                "available": org_cap.capacity_available,
                "state": org_cap.capacity_state,
            },
            "demand": {
                "count": org_cap.demand_count,
                "state": org_cap.demand_state,
                "projects": len(project_links),
                "allocation_demands": len(demands),
            },
            "allocations": len(allocations),
            "concentration": {
                "top_share": org_cap.concentration_share,
                "second_share": org_cap.second_share,
            },
            "experts": experts,
            "projects": project_links,
            "demands": demands,
            "allocations": allocations,
            "signals": signals,
            "history": history,
            "explain": org_cap.explain,
            "derived_at": utcnow().isoformat(),
        }

    # ================================================================
    # PERSON CAPACITY
    # ================================================================

    async def _derive_person_capacity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: Optional[str],
    ) -> CapacityContext:
        """Derive capacity context for a person."""
        
        if person_id is None:
            if not caller.employee_id:
                raise ValueError("No person_id provided and caller has no employee_id")
            person_id = caller.employee_id
        
        # Get person
        person = await db.get(Employee, person_id)
        if not person or person.organization_id != caller.organization_id:
            raise ValueError("Person not found or cross-tenant access denied")
        
        # Get workload snapshot
        workload = await self._get_current_workload(db, caller.organization_id, person_id)
        
        # Get availability
        availability = await self._get_availability(db, caller.organization_id, person_id)
        
        # Get responsibilities
        responsibilities = await self._get_person_responsibilities(db, caller, person_id)
        
        # Get active actions
        actions = await self._get_person_active_actions(db, caller, person_id)
        
        # Get active tasks
        tasks = await self._get_person_active_tasks(db, caller, person_id)
        
        # Get skills/expertise
        skills = await self._get_person_skills(db, caller, person_id)
        
        # Calculate capacity
        capacity_hours = workload.capacity_hours if workload else (availability.available_hours if availability else 40.0)
        allocated_hours = workload.allocated_hours if workload else sum(t.get("estimated_hours", 0) for t in tasks)
        utilization = workload.utilization if workload else (allocated_hours / capacity_hours * 100 if capacity_hours > 0 else 0)
        
        # Get capability-level capacity for person's skills
        capability_details = []
        for skill in skills:
            cap_detail = await self._get_person_capability_capacity(db, caller, person_id, skill["skill_id"])
            capability_details.append(cap_detail)
        
        # Determine capacity state
        if utilization > 120:
            capacity_state = "constrained"
        elif utilization > 100:
            capacity_state = "stretched"
        elif utilization > 80:
            capacity_state = "available"
        else:
            capacity_state = "available"
        
        context = CapacityContext(
            organization_id=caller.organization_id,
            scope_type="person",
            scope_id=person_id,
            total_potential=int(capacity_hours),
            total_committed=int(allocated_hours),
            total_reserved=0,  # Could be derived from pending tasks
            total_available=max(0, int(capacity_hours - allocated_hours)),
            capacity_state=capacity_state,
            utilization=round(utilization, 1),
            total_demand=len(tasks) + len(actions),
            capability_details=capability_details,
            derived_from=["workload_snapshot", "employee_availability", "responsibilities", "actions", "tasks", "skills"],
            derived_at=utcnow(),
        )
        
        return context

    async def _get_current_workload(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> Optional[WorkloadSnapshot]:
        """Get current workload snapshot for a person."""
        result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == organization_id,
                WorkloadSnapshot.employee_id == person_id,
            ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
        )
        return result.scalars().first()

    async def _get_availability(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> Optional[EmployeeAvailability]:
        """Get availability for a person."""
        result = await db.execute(
            select(EmployeeAvailability).where(
                EmployeeAvailability.organization_id == organization_id,
                EmployeeAvailability.employee_id == person_id,
            )
        )
        return result.scalars().first()

    async def _get_person_responsibilities(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
    ) -> List[OrganizationalResponsibility]:
        """Get active responsibilities for a person."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == person_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        return result.scalars().all()

    async def _get_person_active_actions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
    ) -> List[CompanyAction]:
        """Get active actions for a person."""
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.assignee_id == person_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            )
        )
        return result.scalars().all()

    async def _get_person_active_tasks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
    ) -> List[Task]:
        """Get active tasks for a person."""
        result = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.assignee_id == person_id,
                Task.status.in_(("backlog", "todo", "in_progress", "review", "blocked")),
            )
        )
        return result.scalars().all()

    async def _get_person_skills(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
    ) -> List[Dict[str, Any]]:
        """Get skills for a person with expertise scores."""
        result = await db.execute(
            select(EmployeeSkill, CanonicalSkill).join(
                CanonicalSkill, EmployeeSkill.skill_id == CanonicalSkill.id
            ).where(
                EmployeeSkill.organization_id == caller.organization_id,
                EmployeeSkill.employee_id == person_id,
            )
        )
        skills = []
        for emp_skill, skill in result.all():
            skills.append({
                "skill_id": skill.id,
                "skill_name": skill.canonical_name,
                "category": skill.category,
                "level": emp_skill.level,
                "years_experience": emp_skill.years_experience,
                "verified": emp_skill.verified,
            })
        return skills

    async def _get_person_capability_capacity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
        skill_id: str,
    ) -> Dict[str, Any]:
        """Get capacity detail for a person's specific capability."""
        # Get OrgCapability
        org_cap = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
                OrgCapability.skill_id == skill_id,
            )
        )
        org_cap = org_cap.scalars().first()
        
        if not org_cap:
            return {"skill_id": skill_id, "found": False}
        
        # Check if person is an expert for this capability
        expertise = await db.execute(
            select(ExpertiseState).where(
                ExpertiseState.organization_id == caller.organization_id,
                ExpertiseState.person_id == person_id,
                ExpertiseState.skill_id == skill_id,
            )
        )
        expertise = expertise.scalars().first()
        
        return {
            "skill_id": skill_id,
            "capability_name": org_cap.canonical_name,
            "is_expert": expertise is not None,
            "expertise_score": expertise.score if expertise else 0,
            "capacity_state": org_cap.capacity_state,
            "org_available": org_cap.capacity_available,
            "org_committed": org_cap.capacity_committed,
        }

    # ================================================================
    # TEAM CAPACITY
    # ================================================================

    async def _derive_team_capacity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        team_id: str,
    ) -> CapacityContext:
        """Derive capacity context for a team."""
        
        team = await db.get(Team, team_id)
        if not team or team.organization_id != caller.organization_id:
            raise ValueError("Team not found or cross-tenant access denied")
        
        # Get team members
        members = await self._get_team_members(db, caller, team_id)
        member_ids = [m["id"] for m in members]
        
        if not member_ids:
            return CapacityContext(
                organization_id=caller.organization_id,
                scope_type="team",
                scope_id=team_id,
                derived_from=["team_members"],
                derived_at=utcnow(),
            )
        
        # Aggregate workloads
        workloads_result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.employee_id.in_(member_ids),
            ).order_by(WorkloadSnapshot.period_start.desc())
        )
        workloads = workloads_result.scalars().all()
        
        # Get latest per person
        latest_workloads = {}
        for w in workloads:
            if w.employee_id not in latest_workloads:
                latest_workloads[w.employee_id] = w
        
        total_capacity = sum(w.capacity_hours for w in latest_workloads.values())
        total_allocated = sum(w.allocated_hours for w in latest_workloads.values())
        overloaded_count = sum(1 for w in latest_workloads.values() if w.is_overloaded)
        utilization = (total_allocated / total_capacity * 100) if total_capacity > 0 else 0
        
        # Get team responsibilities
        responsibilities = await self._get_team_responsibilities(db, caller, team_id)
        
        # Get team commitments
        commitments = await self._get_team_commitments(db, caller, team_id)
        
        # Capability-level details
        capability_details = await self._get_team_capability_details(db, caller, team_id, member_ids)
        
        # Determine team capacity state
        if overloaded_count >= len(member_ids) * 0.5:
            capacity_state = "constrained"
        elif overloaded_count >= 2:
            capacity_state = "stretched"
        else:
            capacity_state = "available"
        
        context = CapacityContext(
            organization_id=caller.organization_id,
            scope_type="team",
            scope_id=team_id,
            total_potential=int(total_capacity),
            total_committed=int(total_allocated),
            total_reserved=0,
            total_available=max(0, int(total_capacity - total_allocated)),
            capacity_state=capacity_state,
            utilization=round(utilization, 1),
            total_demand=len(commitments) + len(responsibilities),
            capability_details=capability_details,
            overloaded_capabilities=[
                c for c in capability_details 
                if c.get("capacity_state") in ("stretched", "constrained")
            ],
            derived_from=["workload_snapshots", "team_members", "responsibilities", "commitments", "capabilities"],
            derived_at=utcnow(),
        )
        
        return context

    async def _get_team_members(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        team_id: str,
    ) -> List[Dict[str, Any]]:
        """Get team members from TeamMember and Employee.team_id."""
        # TeamMember cross-memberships
        members_result = await db.execute(
            select(Employee).join(
                TeamMember, Employee.id == TeamMember.employee_id
            ).where(
                TeamMember.team_id == team_id,
                TeamMember.organization_id == caller.organization_id,
            )
        )
        members = [{"id": e.id, "name": e.full_name} for e in members_result.scalars().all()]
        
        # Direct team members
        direct_result = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.team_id == team_id,
            )
        )
        for e in direct_result.scalars().all():
            if not any(m["id"] == e.id for m in members):
                members.append({"id": e.id, "name": e.full_name})
        
        return members

    async def _get_team_responsibilities(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        team_id: str,
    ) -> List[OrganizationalResponsibility]:
        """Get responsibilities assigned to a team."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.team_id == team_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        return result.scalars().all()

    async def _get_team_commitments(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        team_id: str,
    ) -> List[CompanyCommitment]:
        """Get commitments scoped to a team."""
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.scope_type == "team",
                CompanyCommitment.scope_id == team_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            )
        )
        return result.scalars().all()

    async def _get_team_capability_details(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        team_id: str,
        member_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Get capability-level capacity details for a team."""
        # Get skills of team members
        skills_result = await db.execute(
            select(EmployeeSkill.skill_id, func.count(EmployeeSkill.employee_id).label("expert_count"))
            .where(
                EmployeeSkill.organization_id == caller.organization_id,
                EmployeeSkill.employee_id.in_(member_ids),
            )
            .group_by(EmployeeSkill.skill_id)
        )
        
        capability_details = []
        for skill_id, expert_count in skills_result.all():
            org_cap = await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == caller.organization_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
            org_cap = org_cap.scalars().first()
            
            if org_cap:
                capability_details.append({
                    "skill_id": skill_id,
                    "capability_name": org_cap.canonical_name,
                    "team_experts": expert_count,
                    "org_experts": org_cap.expert_count,
                    "capacity_state": org_cap.capacity_state,
                    "org_available": org_cap.capacity_available,
                    "org_committed": org_cap.capacity_committed,
                })
        
        return capability_details

    # ================================================================
    # DEPARTMENT CAPACITY
    # ================================================================

    async def _derive_department_capacity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        department_id: str,
    ) -> CapacityContext:
        """Derive capacity context for a department."""
        
        dept = await db.get(Department, department_id)
        if not dept or dept.organization_id != caller.organization_id:
            raise ValueError("Department not found or cross-tenant access denied")
        
        # Get department members
        members_result = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.department_id == department_id,
            )
        )
        members = members_result.scalars().all()
        member_ids = [m.id for m in members]
        
        if not member_ids:
            return CapacityContext(
                organization_id=caller.organization_id,
                scope_type="department",
                scope_id=department_id,
                derived_from=["department_members"],
                derived_at=utcnow(),
            )
        
        # Aggregate workloads
        workloads_result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.employee_id.in_(member_ids),
            ).order_by(WorkloadSnapshot.period_start.desc())
        )
        workloads = workloads_result.scalars().all()
        
        latest_workloads = {}
        for w in workloads:
            if w.employee_id not in latest_workloads:
                latest_workloads[w.employee_id] = w
        
        total_capacity = sum(w.capacity_hours for w in latest_workloads.values())
        total_allocated = sum(w.allocated_hours for w in latest_workloads.values())
        overloaded_count = sum(1 for w in latest_workloads.values() if w.is_overloaded)
        utilization = (total_allocated / total_capacity * 100) if total_capacity > 0 else 0
        
        # Get department commitments
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                or_(
                    and_(
                        CompanyCommitment.scope_type == "department",
                        CompanyCommitment.scope_id == department_id,
                    ),
                ),
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            )
        )
        commitments = commitments_result.scalars().all()
        
        # Capability details
        capability_details = await self._get_department_capability_details(db, caller, department_id, member_ids)
        
        if overloaded_count >= len(member_ids) * 0.4:
            capacity_state = "constrained"
        elif overloaded_count >= 3:
            capacity_state = "stretched"
        else:
            capacity_state = "available"
        
        context = CapacityContext(
            organization_id=caller.organization_id,
            scope_type="department",
            scope_id=department_id,
            total_potential=int(total_capacity),
            total_committed=int(total_allocated),
            total_reserved=0,
            total_available=max(0, int(total_capacity - total_allocated)),
            capacity_state=capacity_state,
            utilization=round(utilization, 1),
            total_demand=len(commitments),
            capability_details=capability_details,
            overloaded_capabilities=[
                c for c in capability_details 
                if c.get("capacity_state") in ("stretched", "constrained")
            ],
            derived_from=["workload_snapshots", "department_members", "commitments", "capabilities"],
            derived_at=utcnow(),
        )
        
        return context

    async def _get_department_capability_details(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        department_id: str,
        member_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Get capability-level capacity details for a department."""
        skills_result = await db.execute(
            select(EmployeeSkill.skill_id, func.count(EmployeeSkill.employee_id).label("expert_count"))
            .where(
                EmployeeSkill.organization_id == caller.organization_id,
                EmployeeSkill.employee_id.in_(member_ids),
            )
            .group_by(EmployeeSkill.skill_id)
        )
        
        capability_details = []
        for skill_id, expert_count in skills_result.all():
            org_cap = await db.execute(
                select(OrgCapability).where(
                    OrgCapability.organization_id == caller.organization_id,
                    OrgCapability.skill_id == skill_id,
                )
            )
            org_cap = org_cap.scalars().first()
            
            if org_cap:
                capability_details.append({
                    "skill_id": skill_id,
                    "capability_name": org_cap.canonical_name,
                    "dept_experts": expert_count,
                    "org_experts": org_cap.expert_count,
                    "capacity_state": org_cap.capacity_state,
                    "org_available": org_cap.capacity_available,
                    "org_committed": org_cap.capacity_committed,
                })
        
        return capability_details

    # ================================================================
    # ORGANIZATION CAPACITY
    # ================================================================

    async def _derive_organization_capacity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> CapacityContext:
        """Derive organization-wide capacity context."""
        
        # Get all OrgCapability rows
        caps_result = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
            ).order_by(OrgCapability.evidence_count.desc())
        )
        capabilities = caps_result.scalars().all()
        
        total_potential = sum(c.capacity_potential for c in capabilities)
        total_committed = sum(c.capacity_committed for c in capabilities)
        total_reserved = sum(c.capacity_reserved for c in capabilities)
        total_available = sum(c.capacity_available for c in capabilities)
        total_demand = sum(c.demand_count for c in capabilities)
        
        utilization = (total_committed / total_potential * 100) if total_potential > 0 else 0
        
        # Overall capacity state
        constrained_count = sum(1 for c in capabilities if c.capacity_state == "constrained")
        stretched_count = sum(1 for c in capabilities if c.capacity_state == "stretched")
        
        if constrained_count > 0:
            capacity_state = "constrained"
        elif stretched_count > 0:
            capacity_state = "stretched"
        else:
            capacity_state = "available"
        
        # Capability details
        capability_details = []
        for c in capabilities:
            capability_details.append({
                "skill_id": c.skill_id,
                "capability_name": c.canonical_name,
                "category": c.category,
                "lifecycle": c.lifecycle,
                "confidence": c.confidence,
                "expert_count": c.expert_count,
                "strong_expert_count": c.strong_expert_count,
                "evidence_count": c.evidence_count,
                "capacity_potential": c.capacity_potential,
                "capacity_committed": c.capacity_committed,
                "capacity_reserved": c.capacity_reserved,
                "capacity_available": c.capacity_available,
                "capacity_state": c.capacity_state,
                "demand_count": c.demand_count,
                "demand_state": c.demand_state,
                "concentration_share": c.concentration_share,
                "concentration_warning": c.concentration_share >= 0.6,
                "explain": c.explain,
            })
        
        # Overloaded and underutilized
        overloaded = [c for c in capability_details if c["capacity_state"] in ("stretched", "constrained")]
        underutilized = [c for c in capability_details if c["capacity_state"] == "available" and c["capacity_available"] > c["capacity_potential"] * 0.5]
        
        context = CapacityContext(
            organization_id=caller.organization_id,
            scope_type="organization",
            total_potential=total_potential,
            total_committed=total_committed,
            total_reserved=total_reserved,
            total_available=total_available,
            capacity_state=capacity_state,
            utilization=round(utilization, 1),
            total_demand=total_demand,
            capability_details=capability_details,
            overloaded_capabilities=overloaded,
            underutilized_capabilities=underutilized,
            derived_from=["org_capabilities", "capability_project_links", "allocation_demands", "capacity_allocations"],
            derived_at=utcnow(),
        )
        
        return context

    # ================================================================
    # CONFLICT DETECTION
    # ================================================================

    async def _detect_person_capacity_deficits(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect person-level capacity deficits."""
        conflicts = []
        
        workloads_result = await db.execute(
            select(WorkloadSnapshot, Employee).join(Employee).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.is_overloaded == True,
                WorkloadSnapshot.period_end >= utcnow(),
            ).limit(50)
        )
        
        for workload, employee in workloads_result.all():
            severity = "critical" if workload.utilization > 150 else "high"
            if workload.utilization > 120:
                severity = "critical"
            elif workload.utilization > 100:
                severity = "high"
            else:
                severity = "medium"
            
            # Get responsibilities to find affected commitments
            responsibilities = await self._get_person_responsibilities(db, caller, employee.id)
            commitment_ids = [r.commitment_id for r in responsibilities if r.commitment_id]
            commitments = await self._get_commitments(db, caller, commitment_ids)
            
            conflicts.append(CapacityConflict(
                id=f"person-capacity-deficit-{workload.id}",
                kind="capacity_deficit",
                severity=severity,
                title=f"Person capacity deficit: {employee.full_name}",
                description=f"Employee {employee.full_name} at {workload.utilization:.0f}% utilization ({workload.allocated_hours:.0f}h/{workload.capacity_hours:.0f}h)",
                scope_type="person",
                scope_id=employee.id,
                required=int(workload.allocated_hours),
                available=int(workload.capacity_hours),
                deficit=int(workload.allocated_hours - workload.capacity_hours),
                affected_commitments=[c.id for c in commitments],
                affected_objectives=[c.objective_id for c in commitments if c.objective_id],
                affected_people=[employee.id],
                source_entities=[{
                    "type": "workload_snapshot",
                    "id": workload.id,
                    "employee_id": employee.id,
                    "utilization": workload.utilization,
                }],
                affected_entities=[{
                    "type": "employee",
                    "id": employee.id,
                    "name": employee.full_name,
                }],
                risk_factors=["overloaded", "capacity_exceeded"],
                provenance={
                    "derived_from": "workload_snapshot",
                    "workload_id": workload.id,
                    "utilization": workload.utilization,
                    "derived_at": utcnow().isoformat(),
                },
                derived_at=utcnow(),
            ))
        
        return conflicts

    async def _detect_team_capacity_overload(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect team-level capacity overload."""
        conflicts = []
        
        # Get teams with overloaded members
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
            ).limit(20)
        )
        
        for row in team_workloads.all():
            severity = "critical" if row.avg_utilization > 150 else "high"
            
            conflicts.append(CapacityConflict(
                id=f"team-capacity-overload-{row.team_id}",
                kind="capacity_deficit",
                severity=severity,
                title=f"Team capacity overload: {row.team_name}",
                description=f"Team '{row.team_name}' has {row.overloaded_count} overloaded members (avg {row.avg_utilization:.0f}% utilization)",
                scope_type="team",
                scope_id=row.team_id,
                required=int(row.avg_utilization * row.overloaded_count),
                available=100 * row.overloaded_count,
                deficit=int((row.avg_utilization - 100) * row.overloaded_count),
                source_entities=[{
                    "type": "team",
                    "id": row.team_id,
                    "name": row.team_name,
                    "overloaded_count": row.overloaded_count,
                }],
                affected_entities=[{
                    "type": "team",
                    "id": row.team_id,
                    "name": row.team_name,
                }],
                risk_factors=["team_overload", "capacity_concentration"],
                provenance={
                    "derived_from": "team_workload_aggregation",
                    "team_id": row.team_id,
                    "overloaded_count": row.overloaded_count,
                    "avg_utilization": row.avg_utilization,
                    "derived_at": utcnow().isoformat(),
                },
                derived_at=utcnow(),
            ))
        
        return conflicts

    async def _detect_department_capacity_strain(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect department-level capacity strain."""
        conflicts = []
        
        dept_workloads = await db.execute(
            select(
                Department.id.label("dept_id"),
                Department.name.label("dept_name"),
                func.avg(WorkloadSnapshot.utilization).label("avg_utilization"),
                func.count(WorkloadSnapshot.id).label("overloaded_count"),
            ).join(
                Employee, Employee.department_id == Department.id
            ).join(
                WorkloadSnapshot, WorkloadSnapshot.employee_id == Employee.id
            ).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.is_overloaded == True,
            ).group_by(Department.id, Department.name).having(
                func.count(WorkloadSnapshot.id) >= 3
            ).limit(20)
        )
        
        for row in dept_workloads.all():
            severity = "critical" if row.avg_utilization > 130 else "high"
            
            conflicts.append(CapacityConflict(
                id=f"dept-capacity-strain-{row.dept_id}",
                kind="capacity_deficit",
                severity=severity,
                title=f"Department capacity strain: {row.dept_name}",
                description=f"Department '{row.dept_name}' has {row.overloaded_count} overloaded members (avg {row.avg_utilization:.0f}% utilization)",
                scope_type="department",
                scope_id=row.dept_id,
                source_entities=[{
                    "type": "department",
                    "id": row.dept_id,
                    "name": row.dept_name,
                    "overloaded_count": row.overloaded_count,
                }],
                affected_entities=[{
                    "type": "department",
                    "id": row.dept_id,
                    "name": row.dept_name,
                }],
                risk_factors=["department_overload", "capacity_concentration"],
                provenance={
                    "derived_from": "department_workload_aggregation",
                    "department_id": row.dept_id,
                    "overloaded_count": row.overloaded_count,
                    "avg_utilization": row.avg_utilization,
                    "derived_at": utcnow().isoformat(),
                },
                derived_at=utcnow(),
            ))
        
        return conflicts

    async def _detect_capability_gaps(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect capability gaps (demand > supply)."""
        conflicts = []
        
        caps_result = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
                OrgCapability.demand_count > 0,
                OrgCapability.capacity_available == 0,
            ).limit(30)
        )
        
        for cap in caps_result.scalars().all():
            conflicts.append(CapacityConflict(
                id=f"capability-gap-{cap.skill_id}",
                kind="capability_gap",
                severity="high",
                title=f"Capability gap: {cap.canonical_name}",
                description=f"{cap.demand_count} active project(s) demand '{cap.canonical_name}' but no expert is free ({cap.capacity_available} available)",
                scope_type="organization",
                scope_id=caller.organization_id,
                capability=cap.canonical_name,
                required=cap.demand_count,
                available=cap.capacity_available,
                deficit=cap.demand_count - cap.capacity_available,
                source_entities=[{
                    "type": "org_capability",
                    "skill_id": cap.skill_id,
                    "capability_name": cap.canonical_name,
                    "demand_count": cap.demand_count,
                    "capacity_available": cap.capacity_available,
                }],
                affected_entities=[{
                    "type": "org_capability",
                    "skill_id": cap.skill_id,
                    "capability_name": cap.canonical_name,
                }],
                risk_factors=["capability_gap", "demand_exceeds_supply"],
                provenance={
                    "derived_from": "org_capability",
                    "skill_id": cap.skill_id,
                    "demand_count": cap.demand_count,
                    "capacity_available": cap.capacity_available,
                    "derived_at": utcnow().isoformat(),
                },
                derived_at=utcnow(),
            ))
        
        return conflicts

    async def _detect_concentration_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect concentration risks (single-person dependencies)."""
        conflicts = []
        
        caps_result = await db.execute(
            select(OrgCapability).where(
                OrgCapability.organization_id == caller.organization_id,
                OrgCapability.expert_count >= 1,
                OrgCapability.concentration_share >= 0.6,
            ).limit(30)
        )
        
        for cap in caps_result.scalars().all():
            severity = "critical" if cap.concentration_share >= 0.7 else "high"
            
            conflicts.append(CapacityConflict(
                id=f"concentration-risk-{cap.skill_id}",
                kind="concentration_risk",
                severity=severity,
                title=f"Concentration risk: {cap.canonical_name}",
                description=f"{cap.concentration_share:.0%} of '{cap.canonical_name}' evidence comes from one person (next expert {cap.second_share:.0%})",
                scope_type="organization",
                scope_id=caller.organization_id,
                capability=cap.canonical_name,
                required=1,
                available=cap.expert_count,
                deficit=0,
                source_entities=[{
                    "type": "org_capability",
                    "skill_id": cap.skill_id,
                    "capability_name": cap.canonical_name,
                    "concentration_share": cap.concentration_share,
                    "second_share": cap.second_share,
                }],
                affected_entities=[{
                    "type": "org_capability",
                    "skill_id": cap.skill_id,
                    "capability_name": cap.canonical_name,
                }],
                risk_factors=["concentration", "single_point_of_failure"],
                provenance={
                    "derived_from": "org_capability_concentration",
                    "skill_id": cap.skill_id,
                    "concentration_share": cap.concentration_share,
                    "derived_at": utcnow().isoformat(),
                },
                derived_at=utcnow(),
            ))
        
        return conflicts

    async def _detect_overcommitment(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect overcommitment (commitments exceed available capacity)."""
        conflicts = []
        
        # Get active commitments
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            ).limit(100)
        )
        commitments = commitments_result.scalars().all()
        
        # Group by person via responsibilities
        person_commitments = defaultdict(list)
        for commitment in commitments:
            resp_result = await db.execute(
                select(OrganizationalResponsibility).where(
                    OrganizationalResponsibility.organization_id == caller.organization_id,
                    OrganizationalResponsibility.commitment_id == commitment.id,
                    OrganizationalResponsibility.state == "active",
                )
            )
            responsibilities = resp_result.scalars().all()
            for resp in responsibilities:
                if resp.person_id:
                    person_commitments[resp.person_id].append(commitment)
        
        # Check each person's commitment load
        for person_id, person_comms in person_commitments.items():
            if len(person_comms) > 5:  # Threshold for overcommitment
                person = await db.get(Employee, person_id)
                if not person:
                    continue
                
                workload = await self._get_current_workload(db, caller.organization_id, person_id)
                utilization = workload.utilization if workload else 0
                
                severity = "critical" if len(person_comms) > 10 else "high"
                
                conflicts.append(CapacityConflict(
                    id=f"overcommitment-{person_id}",
                    kind="overcommitment",
                    severity=severity,
                    title=f"Overcommitment: {person.full_name}",
                    description=f"Employee {person.full_name} has {len(person_comms)} active commitments",
                    scope_type="person",
                    scope_id=person_id,
                    required=len(person_comms),
                    available=5,  # Baseline threshold
                    deficit=len(person_comms) - 5,
                    affected_commitments=[c.id for c in person_comms],
                    affected_objectives=[c.objective_id for c in person_comms if c.objective_id],
                    affected_people=[person_id],
                    source_entities=[{
                        "type": "employee",
                        "id": person_id,
                        "name": person.full_name,
                        "commitment_count": len(person_comms),
                    }],
                    affected_entities=[{
                        "type": "employee",
                        "id": person_id,
                        "name": person.full_name,
                    }],
                    risk_factors=["overcommitment", "responsibility_overload"],
                    provenance={
                        "derived_from": "commitment_responsibility_aggregation",
                        "employee_id": person_id,
                        "commitment_count": len(person_comms),
                        "derived_at": utcnow().isoformat(),
                    },
                    derived_at=utcnow(),
                ))
        
        return conflicts

    async def _detect_allocation_gaps(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[CapacityConflict]:
        """Detect allocation gaps (demands not met by allocations)."""
        conflicts = []
        
        # Get demands without matching allocations
        demands_result = await db.execute(
            select(AllocationDemand).where(
                AllocationDemand.organization_id == caller.organization_id,
            ).limit(50)
        )
        
        for demand in demands_result.scalars().all():
            # Check if there's an allocation for this demand
            alloc_result = await db.execute(
                select(CapacityAllocation).where(
                    CapacityAllocation.organization_id == caller.organization_id,
                    CapacityAllocation.project_id == demand.project_id,
                    CapacityAllocation.capability == demand.capability,
                    CapacityAllocation.window_start == demand.window_start,
                    CapacityAllocation.window_end == demand.window_end,
                )
            )
            allocation = alloc_result.scalars().first()
            
            if not allocation:
                conflicts.append(CapacityConflict(
                    id=f"allocation-gap-{demand.id}",
                    kind="capability_gap",
                    severity="medium",
                    title=f"Unallocated demand: {demand.capability} for project {demand.project_id}",
                    description=f"Project {demand.project_id} demands {demand.units} units of {demand.capability} ({demand.window_start} to {demand.window_end}) but no allocation exists",
                    scope_type="project",
                    scope_id=demand.project_id,
                    capability=demand.capability,
                    required=demand.units,
                    available=0,
                    deficit=demand.units,
                    source_entities=[{
                        "type": "allocation_demand",
                        "id": demand.id,
                        "project_id": demand.project_id,
                        "capability": demand.capability,
                        "units": demand.units,
                    }],
                    affected_entities=[{
                        "type": "allocation_demand",
                        "id": demand.id,
                    }],
                    risk_factors=["unallocated_demand", "resource_shortage"],
                    provenance={
                        "derived_from": "allocation_demand",
                        "demand_id": demand.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    derived_at=utcnow(),
                ))
        
        return conflicts

    # ================================================================
    # HELPER METHODS
    # ================================================================

    async def _get_commitments(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        commitment_ids: List[str],
    ) -> List[CompanyCommitment]:
        if not commitment_ids:
            return []
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.id.in_(commitment_ids),
            )
        )
        return result.scalars().all()

    async def _get_objectives(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        objective_ids: List[str],
    ) -> List[CompanyObjective]:
        if not objective_ids:
            return []
        result = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
                CompanyObjective.id.in_(objective_ids),
            )
        )
        return result.scalars().all()

    async def _get_initiatives_for_objective(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        objective_id: str,
    ) -> List[CompanyInitiative]:
        result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
                CompanyInitiative.objective_id == objective_id,
                CompanyInitiative.status == "active",
            )
        )
        return result.scalars().all()

    async def _get_initiatives(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        initiative_ids: List[str],
    ) -> List[CompanyInitiative]:
        if not initiative_ids:
            return []
        result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
                CompanyInitiative.id.in_(initiative_ids),
            )
        )
        return result.scalars().all()

    async def _get_actions_for_commitment(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        commitment_id: str,
    ) -> List[CompanyAction]:
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.source_commitment_id == commitment_id,
            )
        )
        return result.scalars().all()

    async def _get_actions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        action_ids: List[str],
    ) -> List[CompanyAction]:
        if not action_ids:
            return []
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.id.in_(action_ids),
            )
        )
        return result.scalars().all()

    async def _get_tasks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        task_ids: List[str],
    ) -> List[Task]:
        if not task_ids:
            return []
        result = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.id.in_(task_ids),
            )
        )
        return result.scalars().all()

    async def _get_capability_experts(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        skill_id: str,
    ) -> List[Dict[str, Any]]:
        """Get experts for a capability with details."""
        expert_rows = await db.execute(
            select(
                ExpertiseState.person_id,
                ExpertiseState.score,
                ExpertiseState.evidence_count,
                ExpertiseState.lifecycle,
                ExpertiseState.last_observed,
            ).where(
                ExpertiseState.organization_id == caller.organization_id,
                ExpertiseState.skill_id == skill_id,
                ExpertiseState.score > 0,
            ).order_by(
                ExpertiseState.score.desc(),
                ExpertiseState.evidence_count.desc(),
            ).limit(20)
        )
        
        experts = []
        for row in expert_rows.all():
            person = await db.get(Employee, row.person_id)
            if person:
                experts.append({
                    "person_id": row.person_id,
                    "name": person.full_name,
                    "score": row.score,
                    "evidence_count": row.evidence_count,
                    "lifecycle": row.lifecycle,
                    "last_observed": row.last_observed.isoformat() if row.last_observed else None,
                })
        return experts

    async def _get_active_project_links(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        skill_id: str,
    ) -> List[Dict[str, Any]]:
        """Get active project links for a capability."""
        links_result = await db.execute(
            select(CapabilityProjectLink).where(
                CapabilityProjectLink.organization_id == caller.organization_id,
                CapabilityProjectLink.skill_id == skill_id,
                CapabilityProjectLink.status == "active",
            ).limit(50)
        )
        links = []
        for link in links_result.scalars().all():
            links.append({
                "project_id": link.project_id,
                "project_name": link.project_name,
                "status": link.status,
                "first_seen": link.first_seen.isoformat() if link.first_seen else None,
                "last_seen": link.last_seen.isoformat() if link.last_seen else None,
            })
        return links

    async def _get_allocation_demands(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        capability_name: str,
    ) -> List[Dict[str, Any]]:
        """Get allocation demands for a capability."""
        demands_result = await db.execute(
            select(AllocationDemand).where(
                AllocationDemand.organization_id == caller.organization_id,
                AllocationDemand.capability == capability_name,
            ).limit(50)
        )
        demands = []
        for demand in demands_result.scalars().all():
            demands.append({
                "id": demand.id,
                "project_id": demand.project_id,
                "units": demand.units,
                "window_start": demand.window_start.isoformat() if demand.window_start else None,
                "window_end": demand.window_end.isoformat() if demand.window_end else None,
                "proficiency": demand.proficiency,
            })
        return demands

    async def _get_capacity_allocations(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        capability_name: str,
    ) -> List[Dict[str, Any]]:
        """Get capacity allocations for a capability."""
        allocs_result = await db.execute(
            select(CapacityAllocation).where(
                CapacityAllocation.organization_id == caller.organization_id,
                CapacityAllocation.capability == capability_name,
                CapacityAllocation.status == "active",
            ).limit(50)
        )
        allocations = []
        for alloc in allocs_result.scalars().all():
            allocations.append({
                "id": alloc.id,
                "project_id": alloc.project_id,
                "project_label": alloc.project_label,
                "units": alloc.units,
                "window_start": alloc.window_start.isoformat() if alloc.window_start else None,
                "window_end": alloc.window_end.isoformat() if alloc.window_end else None,
                "status": alloc.status,
                "outcome": alloc.outcome,
            })
        return allocations

    async def _get_capability_signals(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        skill_id: str,
    ) -> List[Dict[str, Any]]:
        """Get capability signals."""
        signals_result = await db.execute(
            select(CapabilitySignal).where(
                CapabilitySignal.organization_id == caller.organization_id,
                CapabilitySignal.skill_id == skill_id,
                CapabilitySignal.status.in_(("open", "acknowledged")),
            ).limit(20)
        )
        signals = []
        for signal in signals_result.scalars().all():
            signals.append({
                "id": signal.id,
                "kind": signal.kind,
                "severity": signal.severity,
                "detail": signal.detail,
                "status": signal.status,
            })
        return signals

    async def _get_capability_history(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        skill_id: str,
    ) -> List[Dict[str, Any]]:
        """Get capability history."""
        history_result = await db.execute(
            select(CapabilityHistory).where(
                CapabilityHistory.organization_id == caller.organization_id,
                CapabilityHistory.skill_id == skill_id,
            ).order_by(CapabilityHistory.month_key.desc()).limit(12)
        )
        history = []
        for h in history_result.scalars().all():
            history.append({
                "month": h.month_key,
                "lifecycle": h.lifecycle,
                "expert_count": h.expert_count,
                "strong_expert_count": h.strong_expert_count,
                "evidence_count": h.evidence_count,
                "capacity_committed": h.capacity_committed,
                "demand_count": h.demand_count,
                "points": h.points,
            })
        return history


# Global instance
organizational_capacity_service = OrganizationalCapacityService()