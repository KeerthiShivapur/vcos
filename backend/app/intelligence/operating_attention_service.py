"""Operating Attention Service — Gate 8.4.

This service derives operating attention items from cross-domain canonical reality.
Attention items are derived findings that surface risks, conflicts, and important
patterns in the company's operating reality.
"""

import logging
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    CompanyObjective,
    CompanyInitiative,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.meeting import Meeting, MeetingAttendee
from app.models.workload import WorkloadSnapshot
from app.models.execution_strategy import ObjectiveContradiction
from app.models.company_operating import CompanyDecisionContradiction
from datetime import datetime, timezone, timedelta
from app.intelligence.company_context import CallerAccess
from app.intelligence.cross_domain_impact_service import cross_domain_impact_service

logger = logging.getLogger("vcos.intelligence.operating_attention")


@dataclass
class OperatingAttention:
    """Operating attention item — a derived finding from cross-domain analysis."""
    id: str
    kind: str  # commitment_at_risk, capacity_conflict, blocked_work, responsibility_gap, etc.
    severity: str  # low, medium, high, critical
    title: str
    description: str
    source_entities: List[Dict[str, Any]]  # Entities that triggered this attention
    affected_entities: List[Dict[str, Any]]  # Entities affected
    risk_factors: List[str]
    provenance: Dict[str, Any]  # How this was derived
    derived_at: datetime
    scope_id: Optional[str] = None


class OperatingAttentionService:
    """Service for deriving operating attention from canonical reality."""

    def __init__(self):
        pass

    async def derive_attention(
        self,
        db: AsyncSession,
        *,
        caller: Any,
    ) -> List[Dict[str, Any]]:
        """Derive all operating attention items for the organization."""
        attention_items = []
        
        # 1. Capacity conflicts
        capacity_attention = await self._derive_capacity_conflicts(db, caller)
        attention_items.extend(capacity_attention)
        
        # 2. Commitment at risk
        commitment_risk = await self._derive_commitment_at_risk(db, caller)
        attention_items.extend(commitment_risk)
        
        # 3. Blocked work
        blocked_work = await self._derive_blocked_work(db, caller)
        attention_items.extend(blocked_work)
        
        # 4. Responsibility gaps
        resp_gaps = await self._derive_responsibility_gaps(db, caller)
        attention_items.extend(resp_gaps)
        
        # 5. Objective execution drift
        obj_drift = await self._derive_objective_drift(db, caller)
        attention_items.extend(obj_drift)
        
        # 5. Verification failures
        verification_failures = await self._derive_verification_failures(db, caller)
        attention_items.extend(verification_failures)
        
        # 6. Unresolved contradictions
        contradictions = await self._derive_unresolved_contradictions(db, caller)
        attention_items.extend(contradictions)
        
        # Sort by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        attention_items.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))
        
        logger.info(f"Derived {len(attention_items)} attention items for org {caller.organization_id}")
        return attention_items

    # Private derivation methods

    async def _derive_capacity_conflicts(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive capacity conflict attention items."""
        from app.models.workload import WorkloadSnapshot
        from app.models.employee import Employee
        
        attention = []
        
        # Get overloaded workloads
        workloads_result = await db.execute(
            select(WorkloadSnapshot, Employee).join(Employee).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.is_overloaded == True,
                WorkloadSnapshot.period_end >= utcnow(),
            ).limit(20)
        )
        
        for workload, employee in workloads_result.all():
            severity = "critical" if workload.utilization > 150 else "high"
            if workload.utilization > 120:
                severity = "critical"
            elif workload.utilization > 100:
                severity = "high"
            else:
                severity = "medium"
            
            attention.append({
                "id": f"capacity-{workload.id}",
                "kind": "capacity_conflict",
                "severity": severity,
                "title": f"Capacity overload: {employee.full_name}",
                "description": f"Employee {employee.full_name} at {workload.utilization:.0f}% utilization ({workload.allocated_hours}h/{workload.capacity_hours}h)",
                "employee_id": employee.id,
                "utilization": workload.utilization,
                "source_entities": [{
                    "type": "workload_snapshot",
                    "id": workload.id,
                    "employee_id": employee.id,
                    "utilization": workload.utilization,
                }],
                "affected_entities": [{
                    "type": "employee",
                    "id": employee.id,
                    "name": employee.full_name,
                }],
                "risk_factors": ["overloaded", "capacity_exceeded"],
                "provenance": {
                    "derived_from": "workload_snapshot",
                    "workload_id": workload.id,
                    "utilization": workload.utilization,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        return attention

    async def _derive_commitment_at_risk(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive commitment at risk attention."""
        from app.models.execution_strategy import CompanyCommitment
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        
        attention = []
        
        # Get active commitments
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            ).limit(50)
        )
        
        for commitment in commitments_result.scalars().all():
            # Get actions for this commitment
            actions_result = await db.execute(
                select(CompanyAction).where(
                    CompanyAction.organization_id == caller.organization_id,
                    CompanyAction.source_commitment_id == commitment.id,
                )
            )
            actions = actions_result.scalars().all()
            
            if not actions:
                continue
            
            # Get outcomes for these actions
            action_ids = [a.id for a in actions]
            outcomes_result = await db.execute(
                select(CompanyActionOutcome).where(
                    CompanyActionOutcome.organization_id == caller.organization_id,
                    CompanyActionOutcome.action_id.in_(action_ids),
                )
            )
            outcomes = outcomes_result.scalars().all()
            
            if not outcomes:
                continue
            
            # Check for risk
            failed = [o for o in outcomes if o.outcome_type == "failed"]
            partial = [o for o in outcomes if o.outcome_type == "partial"]
            avg_effectiveness = sum(o.effectiveness for o in outcomes) / len(outcomes)
            
            risk_factors = []
            severity = "low"
            
            if len([o for o in outcomes if o.outcome_type == "failed"]) > 0:
                severity = "critical"
                risk_factors.append("failed_outcomes")
            elif len([o for o in outcomes if o.outcome_type == "partial"]) > len(outcomes) * 0.3:
                severity = "high"
                risk_factors.append("high_partial_rate")
            elif sum(o.effectiveness for o in outcomes) / len(outcomes) < 0.5:
                severity = "high"
                risk_factors.append("low_effectiveness")
            
            if severity in ("high", "critical"):
                attention.append({
                    "id": f"commitment-risk-{commitment.id}",
                    "kind": "commitment_at_risk",
                    "severity": severity,
                    "title": f"Commitment at risk: {commitment.title}",
                    "description": f"Commitment '{commitment.title}' has {len([o for o in outcomes if o.outcome_type in ('failed', 'partial')])} underperforming outcomes",
                    "source_entities": [{
                        "type": "commitment",
                        "id": commitment.id,
                        "title": commitment.title,
                        "state": commitment.state,
                    }],
                    "affected_entities": [{
                        "type": "commitment",
                        "id": commitment.id,
                    }],
                    "risk_factors": risk_factors,
                    "provenance": {
                        "derived_from": "action_outcomes",
                        "commitment_id": commitment.id,
                        "total_outcomes": len(outcomes),
                        "failed_count": len([o for o in outcomes if o.outcome_type == "failed"]),
                        "partial_count": len([o for o in outcomes if o.outcome_type == "partial"]),
                        "avg_effectiveness": sum(o.effectiveness for o in outcomes) / len(outcomes),
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": commitment.scope_id,
                })
        
        return attention

    async def _derive_blocked_work(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive blocked work attention."""
        from app.models.task import Task, TaskDependency
        
        attention = []
        
        # Find tasks that are blocked by dependencies
        from sqlalchemy.orm import aliased
        DependsOnTask = aliased(Task)
        
        blocked_query = await db.execute(
            select(Task).join(
                TaskDependency, Task.id == TaskDependency.task_id
            ).join(
                DependsOnTask, TaskDependency.depends_on_task_id == DependsOnTask.id
            ).where(
                TaskDependency.organization_id == caller.organization_id,
                DependsOnTask.status != "completed",
                Task.status.in_(("todo", "in_progress")),
            ).limit(20)
        )
        
        blocked_tasks = blocked_query.scalars().all()
        
        for task in blocked_tasks:
            # Get the blocking tasks
            deps = await db.execute(
                select(TaskDependency).where(
                    TaskDependency.organization_id == caller.organization_id,
                    TaskDependency.task_id == task.id,
                )
            )
            
            blocking_tasks = []
            for dep in deps.scalars().all():
                blocking_task = await db.get(Task, dep.depends_on_task_id)
                if blocking_task and blocking_task.status != "completed":
                    blocking_tasks.append({
                        "task_id": blocking_task.id,
                        "title": blocking_task.title,
                        "status": blocking_task.status,
                        "dependency_kind": dep.kind,
                    })
            
            if blocking_tasks:
                attention.append({
                    "id": f"blocked-{task.id}",
                    "kind": "blocked_work",
                    "severity": "high",
                    "title": f"Blocked work: {task.title}",
                    "description": f"Task '{task.title}' is blocked by {len(blocking_tasks)} incomplete dependencies",
                    "source_entities": [{
                        "type": "task",
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                    }],
                    "affected_entities": [{
                        "type": "task",
                        "id": task.id,
                    }] + [{"type": "task", **bt} for bt in blocking_tasks],
                    "risk_factors": ["dependency_blocked", "schedule_risk"],
                    "provenance": {
                        "derived_from": "task_dependencies",
                        "task_id": task.id,
                        "blocking_count": len(blocking_tasks),
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": task.project_id,
                })
        
        return attention

    async def _derive_responsibility_gaps(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive responsibility gap attention."""
        from app.models.execution_strategy import CompanyCommitment, OrganizationalResponsibility
        
        attention = []
        
        # Find commitments without responsibilities
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.state.in_(("authorized", "active")),
            ).limit(50)
        )
        
        for commitment in commitments_result.scalars().all():
            resp_result = await db.execute(
                select(OrganizationalResponsibility).where(
                    OrganizationalResponsibility.organization_id == caller.organization_id,
                    OrganizationalResponsibility.commitment_id == commitment.id,
                    OrganizationalResponsibility.state == "active",
                )
            )
            responsibilities = resp_result.scalars().all()
            
            if not responsibilities:
                attention.append({
                    "id": f"resp-gap-{commitment.id}",
                    "kind": "responsibility_gap",
                    "severity": "high",
                    "title": f"Commitment without responsibility: {commitment.title}",
                    "description": f"Commitment '{commitment.title}' has no assigned responsibilities",
                    "source_entities": [{
                        "type": "commitment",
                        "id": commitment.id,
                        "title": commitment.title,
                    }],
                    "affected_entities": [{
                        "type": "commitment",
                        "id": commitment.id,
                    }],
                    "risk_factors": ["no_accountability", "execution_risk"],
                    "provenance": {
                        "derived_from": "commitment_responsibility_check",
                        "commitment_id": commitment.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": commitment.scope_id,
                })
        
        return attention

    async def _derive_objective_drift(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive objective execution drift attention."""
        from app.models.execution_strategy import CompanyObjective, CompanyInitiative, CompanyCommitment
        
        attention = []
        
        objectives_result = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
                CompanyObjective.status == "active",
            ).limit(30)
        )
        
        for objective in objectives_result.scalars().all():
            # Get initiatives for this objective
            initiatives_result = await db.execute(
                select(CompanyInitiative).where(
                    CompanyInitiative.organization_id == caller.organization_id,
                    CompanyInitiative.objective_id == objective.id,
                    CompanyInitiative.status == "active",
                )
            )
            initiatives = initiatives_result.scalars().all()
            
            if not initiatives:
                continue
            
            # Check if any initiative is behind
            for initiative in initiatives:
                if initiative.expected_outcome and initiative.current_value is not None:
                    target = initiative.expected_outcome.get("target_value")
                    if target and initiative.current_value is not None:
                        progress = initiative.current_value / target
                        if progress < 0.5:  # Less than 50% progress
                            attention.append({
                                "id": f"obj-drift-{objective.id}-{initiative.id}",
                                "kind": "objective_drift",
                                "severity": "medium",
                                "title": f"Objective drift: {objective.title}",
                                "description": f"Initiative '{initiative.title}' at {progress:.0%} progress",
                                "source_entities": [{
                                    "type": "objective",
                                    "id": objective.id,
                                    "title": objective.title,
                                }, {
                                    "type": "initiative",
                                    "id": initiative.id,
                                    "title": initiative.title,
                                }],
                                "affected_entities": [{
                                    "type": "objective",
                                    "id": objective.id,
                                }, {
                                    "type": "initiative",
                                    "id": initiative.id,
                                }],
                                "risk_factors": ["slow_progress", "objective_at_risk"],
                                "provenance": {
                                    "derived_from": "objective_initiative_progress",
                                    "objective_id": objective.id,
                                    "initiative_id": initiative.id,
                                    "progress": progress,
                                    "derived_at": utcnow().isoformat(),
                                },
                                "derived_at": utcnow(),
                                "scope_id": objective.id,
                            })
        
        return attention

    async def _derive_verification_failures(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive verification failure attention."""
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        
        attention = []
        
        # Find actions with failed outcomes
        outcomes_result = await db.execute(
            select(CompanyActionOutcome).where(
                CompanyActionOutcome.organization_id == caller.organization_id,
                CompanyActionOutcome.outcome_type.in_(("failed", "partial")),
            ).limit(20)
        )
        
        for outcome in outcomes_result.scalars().all():
            action = await db.get(CompanyAction, outcome.action_id)
            if action:
                attention.append({
                    "id": f"verification-fail-{outcome.id}",
                    "kind": "verification_failure",
                    "severity": "high" if outcome.outcome_type == "failed" else "medium",
                    "title": f"Verification failure: {action.title}",
                    "description": f"Action '{action.title}' outcome: {outcome.verdict}",
                    "source_entities": [{
                        "type": "action",
                        "id": action.id,
                        "title": action.title,
                    }, {
                        "type": "action_outcome",
                        "id": outcome.id,
                        "type": outcome.outcome_type,
                    }],
                    "affected_entities": [{
                        "type": "action",
                        "id": action.id,
                    }],
                    "risk_factors": ["outcome_not_achieved", "verification_failed"],
                    "provenance": {
                        "derived_from": "action_outcome",
                        "action_id": action.id,
                        "outcome_id": outcome.id,
                        "outcome_type": outcome.outcome_type,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": action.scope_id,
                })
        
        return attention

    async def _derive_unresolved_contradictions(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive unresolved contradiction attention."""
        from app.models.company_operating import CompanyDecisionContradiction
        from app.models.execution_strategy import ObjectiveContradiction
        
        attention = []
        
        # Decision contradictions
        contradictions_result = await db.execute(
            select(CompanyDecisionContradiction).where(
                CompanyDecisionContradiction.organization_id == caller.organization_id,
                CompanyDecisionContradiction.status.in_(("open", "acknowledged")),
            ).limit(20)
        )
        
        for contradiction in contradictions_result.scalars().all():
            attention.append({
                "id": f"contradiction-dec-{contradiction.id}",
                "kind": "contradiction_unresolved",
                "severity": "high" if contradiction.status == "open" else "medium",
                "title": f"Unresolved contradiction: {contradiction.decision_id}",
                "description": f"Decision contradiction {contradiction.contradiction_key} remains {contradiction.status}",
                "source_entities": [{
                    "type": "decision_contradiction",
                    "id": contradiction.id,
                    "decision_id": contradiction.decision_id,
                }],
                "affected_entities": [{
                    "type": "decision",
                    "id": contradiction.decision_id,
                }],
                "risk_factors": ["unresolved_contradiction", "evidence_conflict"],
                "provenance": {
                    "derived_from": "decision_contradiction",
                    "contradiction_id": contradiction.id,
                    "status": contradiction.status,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        # Objective contradictions
        obj_contradictions_result = await db.execute(
            select(ObjectiveContradiction).where(
                ObjectiveContradiction.organization_id == caller.organization_id,
                ObjectiveContradiction.status.in_(("open", "acknowledged")),
            ).limit(20)
        )
        
        for contradiction in obj_contradictions_result.scalars().all():
            attention.append({
                "id": f"contradiction-obj-{contradiction.id}",
                "kind": "contradiction_unresolved",
                "severity": "high" if contradiction.status == "open" else "medium",
                "title": f"Unresolved objective contradiction: {contradiction.objective_id}",
                "description": f"Objective contradiction {contradiction.contradiction_key} remains {contradiction.status}",
                "source_entities": [{
                    "type": "objective_contradiction",
                    "id": contradiction.id,
                    "objective_id": contradiction.objective_id,
                }],
                "affected_entities": [{
                    "type": "objective",
                    "id": contradiction.objective_id,
                }],
                "risk_factors": ["unresolved_contradiction", "evidence_conflict"],
                "provenance": {
                    "derived_from": "objective_contradiction",
                    "contradiction_id": contradiction.id,
                    "status": contradiction.status,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        return attention


# Global instance
operating_attention_service = OperatingAttentionService()