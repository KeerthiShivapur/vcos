"""Cross-Domain Impact Service — Gate 8.4.

This service derives cross-domain impact analysis from canonical reality.
It detects how changes in one domain affect others.
"""

import logging
from datetime import datetime
from typing import Any, Optional, List, Dict
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
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
from app.models.company_operating import CompanyDecision
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.workload import WorkloadSnapshot
from app.models.meeting import Meeting, MeetingAttendee
from app.models.communication import (
    CanonicalCommunicationThread,
    CanonicalMessage,
)

logger = logging.getLogger("vcos.intelligence.cross_domain_impact")


@dataclass
class ImpactAnalysis:
    """Cross-domain impact analysis result."""
    impact_type: str
    source_entity_type: str
    source_entity_id: str
    affected_entities: List[Dict[str, Any]]
    risk_factors: List[str]
    severity: str  # "low", "medium", "high", "critical"
    derived_at: datetime
    provenance: Dict[str, Any]


class CrossDomainImpactService:
    """Service for deriving cross-domain impact from canonical reality."""

    def __init__(self):
        pass

    async def derive_capacity_impact(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        employee_id: str,
    ) -> Dict[str, Any]:
        """Derive capacity impact for an employee across commitments."""
        from app.models.workload import WorkloadSnapshot
        
        # Get workload
        workload_result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.employee_id == employee_id,
            ).order_by(WorkloadSnapshot.period_start.desc())
        )
        workloads = workload_result.scalars().all()
        
        is_overloaded = any(w.is_overloaded for w in workloads)
        max_utilization = max((w.utilization for w in workloads), default=0)
        
        # Get responsibilities for this employee
        from app.models.execution_strategy import OrganizationalResponsibility
        responsibilities_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.person_id == employee_id,
                OrganizationalResponsibility.state == "active",
            )
        )
        responsibilities = responsibilities_result.scalars().all()
        
        # Get commitments for these responsibilities
        from app.models.execution_strategy import CompanyCommitment
        commitment_ids = [r.commitment_id for r in responsibilities if r.commitment_id]
        
        affected_commitments = []
        if commitment_ids:
            commitments_result = await db.execute(
                select(CompanyCommitment).where(
                    CompanyCommitment.organization_id == caller.organization_id,
                    CompanyCommitment.id.in_(commitment_ids),
                )
            )
            for c in commitments_result.scalars().all():
                affected_commitments.append({
                    "commitment_id": c.id,
                    "title": c.title,
                    "state": c.state,
                    "scope_type": c.scope_type,
                    "scope_id": c.scope_id,
                })
        
        # Get actions
        from app.models.company_actions import CompanyAction
        actions_result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.assignee_id == employee_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            )
        )
        actions = actions_result.scalars().all()
        
        risk_factors = []
        if is_overloaded:
            risk_factors.append("capacity_shortage")
        if len(responsibilities) > 3:
            risk_factors.append("responsibility_concentration")
        if max_utilization > 120:
            risk_factors.append("critical_overload")
        elif max_utilization > 100:
            risk_factors.append("overload")
        
        return {
            "employee_id": employee_id,
            "is_overloaded": is_overloaded,
            "utilization": max_utilization,
            "max_utilization": max_utilization,
            "active_responsibilities": len(responsibilities),
            "active_actions": len([a for a in workloads if a.allocated_hours > 0]),
            "affected_commitments": affected_commitments,
            "risk_factors": risk_factors,
        }

    async def derive_commitment_risk(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        commitment_id: str,
    ) -> Dict[str, Any]:
        """Derive commitment risk from outcomes and execution."""
        from app.models.execution_strategy import CompanyCommitment
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment:
            raise ValueError(f"Commitment not found: {commitment_id}")
        
        # Get actions for this commitment
        actions_result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == commitment.organization_id,
                CompanyAction.source_commitment_id == commitment_id,
            )
        )
        actions = actions_result.scalars().all()
        
        # Get outcomes for these actions
        action_ids = [a.id for a in actions]
        outcomes = []
        if action_ids:
            outcomes_result = await db.execute(
                select(CompanyActionOutcome).where(
                    CompanyActionOutcome.organization_id == commitment.organization_id,
                    CompanyActionOutcome.action_id.in_(action_ids),
                )
            )
            outcomes = outcomes_result.scalars().all()
        
        # Calculate risk
        total_actions = len(actions)
        completed_actions = len([a for a in actions if a.state == "completed"])
        failed_outcomes = len([o for o in outcomes if o.outcome_type == "failed"])
        partial_outcomes = len([o for o in outcomes if o.outcome_type == "partial"])
        
        avg_effectiveness = sum(o.effectiveness for o in outcomes) / len(outcomes) if outcomes else 0
        
        # Determine risk level
        risk_level = "low"
        if failed_outcomes > 0:
            risk_level = "critical"
        elif partial_outcomes > total_actions * 0.3:
            risk_level = "high"
        elif avg_effectiveness < 0.6:
            risk_level = "high"
        elif completed_actions < len(actions) * 0.5:
            risk_level = "medium"
        
        return {
            "commitment_id": commitment_id,
            "title": commitment.title,
            "state": commitment.state,
            "total_actions": len(actions),
            "completed_actions": completed_actions,
            "failed_outcomes": failed_outcomes,
            "partial_outcomes": partial_outcomes,
            "outcome_effectiveness": avg_effectiveness,
            "risk_level": risk_level,
            "risk_factors": self._derive_risk_factors(actions, outcomes),
        }

    def _derive_risk_factors(
        self, actions: List, outcomes: List
    ) -> List[str]:
        """Derive risk factors from actions and outcomes."""
        factors = []
        if not actions:
            factors.append("no_actions")
        else:
            incomplete = [a for a in actions if a.state != "completed"]
            if incomplete:
                factors.append("incomplete_actions")
        
        if outcomes:
            failed = [o for o in outcomes if o.outcome_type == "failed"]
            if failed:
                factors.append("failed_outcomes")
            partial = [o for o in outcomes if o.outcome_type == "partial"]
            if len(partial) > len(outcomes) * 0.3:
                factors.append("partial_outcomes")
            low_eff = [o for o in outcomes if o.effectiveness < 0.5]
            if low_eff:
                factors.append("low_effectiveness")
        
        return factors

    async def derive_dependency_impact(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        task_id: str,
    ) -> Dict[str, Any]:
        """Derive impact of a blocked task on downstream work."""
        from app.models.task import Task, TaskDependency
        
        task = await db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        
        # Find tasks that depend on this task
        dependents_result = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == task.organization_id,
                TaskDependency.depends_on_task_id == task_id,
            )
        )
        dependents = dependents_result.scalars().all()
        
        affected_tasks = []
        for dep in dependents:
            dependent_task = await db.get(Task, dep.task_id)
            if dependent_task:
                affected_tasks.append({
                    "task_id": dependent_task.id,
                    "title": dependent_task.title,
                    "status": dependent_task.status,
                    "dependency_kind": dep.kind,
                })
        
        # Check for cascading impact
        cascading = []
        for affected in affected_tasks:
            if affected["status"] in ("todo", "in_progress"):
                # Recursively check further dependencies
                sub_impact = await self.derive_dependency_impact(db, caller=caller, task_id=affected["task_id"])
                cascading.extend(sub_impact.get("affected_tasks", []))
        
        return {
            "source_task_id": task_id,
            "source_task_title": task.title,
            "source_task_status": task.status,
            "directly_affected": len(affected_tasks),
            "affected_tasks": affected_tasks,
            "cascading_impact": len(cascading),
        }

    async def derive_decision_impact(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        decision_id: str,
    ) -> Dict[str, Any]:
        """Derive impact of a decision on commitments and execution."""
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        
        decision = await db.get(CompanyDecision, decision_id)
        if not decision:
            raise ValueError(f"Decision not found: {decision_id}")
        
        # Find commitments from this decision
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == decision.organization_id,
                CompanyCommitment.decision_id == decision.decision_id,
            )
        )
        commitments = commitments_result.scalars().all()
        
        # Find authorizations from this decision
        auths_result = await db.execute(
            select(CompanyAuthorization).where(
                CompanyAuthorization.organization_id == decision.organization_id,
                CompanyAuthorization.decision_id == decision.decision_id,
            )
        )
        authorizations = auths_result.scalars().all()
        
        return {
            "decision_id": decision.decision_id,
            "decision_title": decision.title,
            "decision_state": decision.state,
            "derived_commitments": len(commitments),
            "derived_authorizations": len(authorizations),
            "commitments": [
                {
                    "id": c.id,
                    "title": c.title,
                    "state": c.state,
                } for c in commitments
            ],
            "authorizations": [
                {
                    "id": a.id,
                    "title": a.title,
                    "state": a.state,
                } for a in authorizations
            ],
        }


# Global instance
cross_domain_impact_service = CrossDomainImpactService()