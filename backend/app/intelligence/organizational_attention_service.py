"""Organizational Attention Service — Gate 8.5.

Extends the OperatingAttentionService with organizational-specific attention items:
- responsibility gaps
- organizational bottlenecks
- capacity concentration
- dependency concentration
- critical-person dependency
- responsibility gaps
- orphaned commitments
- objective execution drift
- verification failures
- unresolved contradictions
"""

import logging
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, or_, func
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
    CompanyCommitment,
    CompanyAuthorization,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.meeting import Meeting, MeetingParticipant
from app.models.workload import WorkloadSnapshot
from app.models.execution_strategy import ObjectiveContradiction
from app.models.company_operating import CompanyDecisionContradiction
from app.models.employee import Employee
from app.models.workload import WorkloadSnapshot
from app.models.company_operating import CompanyDecisionContradiction
from app.models.execution_strategy import ObjectiveContradiction
from app.intelligence.company_context import CallerAccess
from app.intelligence.cross_domain_impact_service import cross_domain_impact_service
from app.people.operating_context_service import operating_context_service

logger = logging.getLogger("vcos.intelligence.organizational_attention")


class OrganizationalAttentionService:
    """Service for deriving organizational attention from canonical reality.
    
    Extends OperatingAttentionService with organizational-specific attention items:
    - responsibility gaps
    - organizational bottlenecks
    - capacity concentration
    - dependency concentration
    - critical-person dependency
    - responsibility gaps
    - orphaned commitments
    - objective execution drift
    - verification failures
    - unresolved contradictions
    """

    def __init__(self):
        pass

    async def derive_organizational_attention(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[Dict[str, Any]]:
        """Derive all organizational attention items for the organization."""
        attention_items = []
        
        # 1. Capacity conflicts (from workload)
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
        
        # 6. Verification failures
        verification_failures = await self._derive_verification_failures(db, caller)
        attention_items.extend(verification_failures)
        
        # 7. Unresolved contradictions
        contradictions = await self._derive_unresolved_contradictions(db, caller)
        attention_items.extend(contradictions)
        
        # 8. Organizational bottlenecks (NEW for 8.5)
        bottlenecks = await self._derive_organizational_bottlenecks(db, caller)
        attention_items.extend(bottlenecks)
        
        # 9. Responsibility concentration (NEW for 8.5)
        resp_concentration = await self._derive_responsibility_concentration(db, caller)
        attention_items.extend(resp_concentration)
        
        # 10. Dependency concentration (NEW for 8.5)
        dep_concentration = await self._derive_dependency_concentration(db, caller)
        attention_items.extend(dep_concentration)
        
        # 11. Critical person dependency (NEW for 8.5)
        critical_person = await self._derive_critical_person_dependency(db, caller)
        attention_items.extend(critical_person)
        
        # 12. Orphaned commitments (NEW for 8.5)
        orphaned = await self._derive_orphaned_commitments(db, caller)
        attention_items.extend(orphaned)
        
        # 13. Objective execution drift (NEW for 8.5)
        obj_drift = await self._derive_objective_execution_drift(db, caller)
        attention_items.extend(obj_drift)
        
        # 14. Orphaned responsibilities (NEW for 8.5)
        orphaned_resp = await self._derive_orphaned_responsibilities(db, caller)
        attention_items.extend(orphaned_resp)
        
        # Sort by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        attention_items.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))
        
        logger.info(f"Derived {len(attention_items)} organizational attention items for org {caller.organization_id}")
        return attention_items

    # ============================================================
    # Private derivation methods
    # ============================================================

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
                    "commitment_id": commitment.id,
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

    async def _derive_objective_drift(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive objective execution drift attention (NEW for 8.5)."""
        from app.models.execution_strategy import CompanyObjective, CompanyInitiative, CompanyCommitment
        from app.models.company_actions import CompanyAction
        
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
                # No initiatives for active objective
                attention.append({
                    "id": f"obj-drift-no-init-{objective.id}",
                    "kind": "objective_execution_drift",
                    "severity": "high",
                    "title": f"Objective without initiatives: {objective.title}",
                    "description": f"Active objective '{objective.title}' has no active initiatives",
                    "source_entities": [{
                        "type": "objective",
                        "id": objective.id,
                        "title": objective.title,
                    }],
                    "affected_entities": [{
                        "type": "objective",
                        "id": objective.id,
                    }],
                    "risk_factors": ["no_initiatives", "execution_gap"],
                    "provenance": {
                        "derived_from": "objective_initiative_check",
                        "objective_id": objective.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": objective.id,
                })
                continue
            
            # Check if any initiative is behind
            for initiative in initiatives:
                if initiative.expected_outcome and objective.current_value is not None:
                    target = initiative.expected_outcome.get("target_value")
                    if target and objective.current_value is not None:
                        progress = objective.current_value / target
                        if progress < 0.3:  # Less than 30% progress
                            attention.append({
                                "id": f"obj-drift-{objective.id}-{initiative.id}",
                                "kind": "objective_execution_drift",
                                "severity": "high" if progress < 0.15 else "medium",
                                "title": f"Objective execution drift: {objective.title}",
                                "description": f"Initiative '{initiative.title}' at {progress:.0%} progress (target: {target})",
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

    async def _derive_organizational_bottlenecks(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive organizational bottleneck attention (NEW for 8.5)."""
        from app.models.workload import WorkloadSnapshot
        from app.models.employee import Employee
        from app.models.team import Team
        from app.models.department import Department
        from sqlalchemy import func
        
        attention = []
        
        # Team-level bottlenecks
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
            attention.append({
                "id": f"bottleneck-team-{row.team_id}",
                "kind": "organizational_bottleneck",
                "severity": "high" if row.avg_utilization > 150 else "medium",
                "title": f"Team bottleneck: {row.team_name}",
                "description": f"Team '{row.team_name}' has {row.overloaded_count} overloaded members (avg {row.avg_utilization:.0f}% utilization)",
                "source_entities": [{
                    "type": "team",
                    "id": row.team_id,
                    "name": row.team_name,
                    "overloaded_count": row.overloaded_count,
                }],
                "affected_entities": [{
                    "type": "team",
                    "id": row.team_id,
                    "name": row.team_name,
                }],
                "risk_factors": ["team_overload", "capacity_concentration"],
                "provenance": {
                    "derived_from": "team_workload_aggregation",
                    "team_id": row.team_id,
                    "overloaded_count": row.overloaded_count,
                    "avg_utilization": row.avg_utilization,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        # Department-level bottlenecks
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
            ).limit(10)
        )
        
        for row in dept_workloads.all():
            attention.append({
                "id": f"bottleneck-dept-{row.dept_id}",
                "kind": "organizational_bottleneck",
                "severity": "high" if row.avg_utilization > 130 else "medium",
                "title": f"Department bottleneck: {row.dept_name}",
                "description": f"Department '{row.dept_name}' has {row.overloaded_count} overloaded members (avg {row.avg_utilization:.0f}% utilization)",
                "source_entities": [{
                    "type": "department",
                    "id": row.dept_id,
                    "name": row.dept_name,
                    "overloaded_count": row.overloaded_count,
                }],
                "affected_entities": [{
                    "type": "department",
                    "id": row.dept_id,
                    "name": row.dept_name,
                }],
                "risk_factors": ["department_overload", "capacity_concentration"],
                "provenance": {
                    "derived_from": "department_workload_aggregation",
                    "department_id": row.dept_id,
                    "overloaded_count": row.overloaded_count,
                    "avg_utilization": row.avg_utilization,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        return attention

    async def _derive_responsibility_concentration(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive responsibility concentration attention (NEW for 8.5)."""
        from app.models.execution_strategy import OrganizationalResponsibility
        from app.models.employee import Employee
        from sqlalchemy import func
        
        attention = []
        
        # Find people with too many responsibilities
        resp_counts = await db.execute(
            select(
                OrganizationalResponsibility.person_id,
                func.count(OrganizationalResponsibility.id).label("resp_count"),
            ).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.state == "active",
            ).group_by(OrganizationalResponsibility.person_id).having(
                func.count(OrganizationalResponsibility.id) > 3
            ).limit(20)
        )
        
        for row in resp_counts.all():
            employee = await db.get(Employee, row.person_id)
            if not employee:
                continue
            
            severity = "critical" if row.resp_count > 7 else "high" if row.resp_count > 5 else "medium"
            
            attention.append({
                "id": f"resp-concentration-{row.person_id}",
                "kind": "responsibility_concentration",
                "severity": severity,
                "title": f"Responsibility concentration: {employee.full_name}",
                "description": f"Employee {employee.full_name} holds {row.resp_count} active responsibilities",
                "source_entities": [{
                    "type": "employee",
                    "id": row.person_id,
                    "name": employee.full_name,
                    "responsibility_count": row.resp_count,
                }],
                "affected_entities": [{
                    "type": "employee",
                    "id": row.person_id,
                    "name": employee.full_name,
                }],
                "risk_factors": ["responsibility_overload", "single_point_of_failure"],
                "provenance": {
                    "derived_from": "responsibility_count_aggregation",
                    "employee_id": row.person_id,
                    "responsibility_count": row.resp_count,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        return attention

    async def _derive_dependency_concentration(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive dependency concentration attention (NEW for 8.5)."""
        from app.models.task import Task, TaskDependency
        from app.models.project import Project
        from app.models.company_actions import CompanyAction
        from sqlalchemy import func
        
        attention = []
        
        # Task dependency concentration
        dep_counts = await db.execute(
            select(
                TaskDependency.depends_on_task_id,
                func.count(TaskDependency.id).label("dep_count"),
            ).select_from(
                TaskDependency
            ).join(
                Task, Task.id == TaskDependency.task_id
            ).where(
                TaskDependency.organization_id == caller.organization_id,
                Task.status.in_(("todo", "in_progress")),
            ).group_by(TaskDependency.depends_on_task_id).having(
                func.count(TaskDependency.id) >= 3
            ).limit(15)
        )
        
        for row in dep_counts.all():
            blocking_task = await db.get(Task, row.depends_on_task_id)
            if not blocking_task:
                continue
            
            severity = "critical" if row.dep_count >= 5 else "high"
            
            attention.append({
                "id": f"dep-concentration-{blocking_task.id}",
                "kind": "dependency_concentration",
                "severity": severity,
                "title": f"Dependency concentration: {blocking_task.title}",
                "description": f"Task '{blocking_task.title}' blocks {row.dep_count} other tasks",
                "source_entities": [{
                    "type": "task",
                    "id": blocking_task.id,
                    "title": blocking_task.title,
                    "blocked_count": row.dep_count,
                }],
                "affected_entities": [{
                    "type": "task",
                    "id": blocking_task.id,
                    "title": blocking_task.title,
                }],
                "risk_factors": ["dependency_concentration", "critical_path_risk"],
                "provenance": {
                    "derived_from": "task_dependency_aggregation",
                    "task_id": blocking_task.id,
                    "dependent_count": row.dep_count,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": blocking_task.project_id,
            })
        
        return attention

    async def _derive_critical_person_dependency(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive critical person dependency attention (NEW for 8.5)."""
        from app.models.employee import Employee
        from app.models.workload import WorkloadSnapshot
        from app.models.execution_strategy import OrganizationalResponsibility
        from app.models.company_actions import CompanyAction
        from app.models.task import Task, TaskDependency
        from app.models.execution_strategy import CompanyCommitment, OrganizationalResponsibility
        from sqlalchemy import func
        
        attention = []
        
        # Find people who are critical paths for multiple commitments
        # Check: person with responsibilities on multiple commitments + high workload + blocking many tasks
        
        # Get people with high responsibility count AND high workload
        from app.models.execution_strategy import OrganizationalResponsibility
        from app.models.workload import WorkloadSnapshot
        from app.models.employee import Employee
        
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
            employee = await db.get(Employee, row.person_id)
            if not employee:
                continue
            
            # Check workload
            workload = await db.execute(
                select(WorkloadSnapshot).where(
                    WorkloadSnapshot.organization_id == caller.organization_id,
                    WorkloadSnapshot.employee_id == row.person_id,
                ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
            )
            workload = workload.scalars().first()
            
            # Check blocked tasks
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
            
            # Calculate criticality score
            criticality = row.resp_count * 2
            if workload and workload.utilization > 100:
                criticality += 5
            criticality += blocked_count
            
            if criticality >= 10:
                severity = "critical"
            elif criticality >= 7:
                severity = "high"
            elif criticality >= 4:
                severity = "medium"
            else:
                continue  # Skip low criticality
            
            employee = await db.get(Employee, row.person_id)
            if not employee:
                continue
            
            attention.append({
                "id": f"critical-person-{row.person_id}",
                "kind": "critical_person_dependency",
                "severity": severity,
                "title": f"Critical person dependency: {employee.full_name}",
                "description": f"Employee {employee.full_name} is a critical dependency: {row.resp_count} responsibilities, {blocked_count} blocking dependencies",
                "source_entities": [{
                    "type": "employee",
                    "id": row.person_id,
                    "name": employee.full_name,
                    "responsibility_count": row.resp_count,
                }],
                "affected_entities": [{
                    "type": "employee",
                    "id": row.person_id,
                    "name": employee.full_name,
                }],
                "risk_factors": [
                    "responsibility_concentration",
                    "capacity_overload" if workload and workload.utilization > 100 else None,
                    "dependency_hub" if blocked_count >= 3 else None,
                ],
                "provenance": {
                    "derived_from": "critical_person_analysis",
                    "employee_id": row.person_id,
                    "responsibility_count": row.resp_count,
                    "workload_utilization": workload.utilization if workload else None,
                    "blocked_tasks": blocked_count,
                    "criticality_score": criticality,
                    "derived_at": utcnow().isoformat(),
                },
                "derived_at": utcnow(),
                "scope_id": None,
            })
        
        return attention

    async def _derive_orphaned_commitments(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive orphaned commitments attention (NEW for 8.5)."""
        from app.models.execution_strategy import CompanyCommitment, OrganizationalResponsibility
        
        attention = []
        
        # Find commitments without any active responsibilities
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
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
                    "id": f"orphaned-commitment-{commitment.id}",
                    "kind": "orphaned_commitment",
                    "severity": "high",
                    "title": f"Orphaned commitment: {commitment.title}",
                    "description": f"Commitment '{commitment.title}' has no assigned responsibilities",
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
                    "risk_factors": ["orphaned_commitment", "no_accountability"],
                    "provenance": {
                        "derived_from": "commitment_responsibility_check",
                        "commitment_id": commitment.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": commitment.scope_id,
                })
        
        return attention

    async def _derive_objective_execution_drift(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive objective execution drift attention (NEW for 8.5)."""
        from app.models.execution_strategy import CompanyObjective, CompanyInitiative, CompanyCommitment
        from app.models.company_actions import CompanyAction
        
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
                # No initiatives for active objective
                attention.append({
                    "id": f"obj-drift-no-init-{objective.id}",
                    "kind": "objective_execution_drift",
                    "severity": "high",
                    "title": f"Objective without initiatives: {objective.title}",
                    "description": f"Active objective '{objective.title}' has no active initiatives",
                    "source_entities": [{
                        "type": "objective",
                        "id": objective.id,
                        "title": objective.title,
                    }],
                    "affected_entities": [{
                        "type": "objective",
                        "id": objective.id,
                    }],
                    "risk_factors": ["no_initiatives", "execution_gap"],
                    "provenance": {
                        "derived_from": "objective_initiative_check",
                        "objective_id": objective.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": objective.id,
                })
                continue
            
            # Check if any initiative is behind
            for initiative in initiatives:
                if initiative.expected_outcome and initiative.current_value is not None:
                    target = initiative.expected_outcome.get("target_value")
                    if target and initiative.current_value is not None:
                        progress = initiative.current_value / target
                        if progress < 0.3:  # Less than 30% progress
                            attention.append({
                                "id": f"obj-drift-{objective.id}-{initiative.id}",
                                "kind": "objective_execution_drift",
                                "severity": "high" if progress < 0.15 else "medium",
                                "title": f"Objective execution drift: {objective.title}",
                                "description": f"Initiative '{initiative.title}' at {progress:.0%} progress (target: {target})",
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
                                "risk_factors": ["execution_drift", "objective_at_risk"],
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

    async def _derive_orphaned_responsibilities(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive orphaned responsibilities attention (NEW for 8.5)."""
        from app.models.execution_strategy import OrganizationalResponsibility
        from app.models.execution_strategy import CompanyCommitment
        
        attention = []
        
        # Find responsibilities linked to non-existent or inactive commitments
        responsibilities_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.state == "active",
            ).limit(100)
        )
        
        for resp in responsibilities_result.scalars().all():
            if resp.commitment_id:
                commitment = await db.get(CompanyCommitment, resp.commitment_id)
                if not commitment or commitment.state in ("expired", "rejected", "cancelled"):
                    attention.append({
                        "id": f"orphaned-resp-{resp.id}",
                        "kind": "orphaned_responsibility",
                        "severity": "high",
                        "title": f"Orphaned responsibility: {resp.title or resp.id}",
                        "description": f"Responsibility '{resp.title or resp.id}' linked to invalid commitment",
                        "source_entities": [{
                            "type": "responsibility",
                            "id": resp.id,
                            "title": resp.title,
                        }],
                        "affected_entities": [{
                            "type": "responsibility",
                            "id": resp.id,
                        }],
                        "risk_factors": ["orphaned_responsibility", "invalid_commitment_link"],
                        "provenance": {
                            "derived_from": "responsibility_commitment_check",
                            "responsibility_id": resp.id,
                            "commitment_id": resp.commitment_id,
                            "derived_at": utcnow().isoformat(),
                        },
                        "derived_at": utcnow(),
                        "scope_id": resp.scope_id,
                    })
        
        return attention

    async def _derive_objective_execution_drift(
        self, db: AsyncSession, caller: Any
    ) -> List[Dict[str, Any]]:
        """Derive objective execution drift attention (NEW for 8.5)."""
        from app.models.execution_strategy import CompanyObjective, CompanyInitiative
        from app.models.company_actions import CompanyAction, CompanyActionOutcome
        
        attention = []
        
        objectives_result = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
                CompanyObjective.status == "active",
            ).limit(30)
        )
        
        for objective in objectives_result.scalars().all():
            # Get commitments for this objective
            commitments_result = await db.execute(
                select(CompanyCommitment).where(
                    CompanyCommitment.organization_id == caller.organization_id,
                    CompanyCommitment.objective_id == objective.id,
                    CompanyCommitment.state.in_(("authorized", "active")),
                )
            )
            commitments = commitments_result.scalars().all()
            
            if not commitments:
                attention.append({
                    "id": f"obj-drift-no-commit-{objective.id}",
                    "kind": "objective_execution_drift",
                    "severity": "medium",
                    "title": f"Objective without commitments: {objective.title}",
                    "description": f"Active objective '{objective.title}' has no active commitments",
                    "source_entities": [{
                        "type": "objective",
                        "id": objective.id,
                        "title": objective.title,
                    }],
                    "affected_entities": [{
                        "type": "objective",
                        "id": objective.id,
                    }],
                    "risk_factors": ["no_commitments", "execution_gap"],
                    "provenance": {
                        "derived_from": "objective_commitment_check",
                        "objective_id": objective.id,
                        "derived_at": utcnow().isoformat(),
                    },
                    "derived_at": utcnow(),
                    "scope_id": objective.id,
                })
                continue
            
            # Check if commitments have actions with outcomes
            for commitment in commitments:
                actions_result = await db.execute(
                    select(CompanyAction).where(
                        CompanyAction.organization_id == caller.organization_id,
                        CompanyAction.source_commitment_id == commitment.id,
                    )
                )
                actions = actions_result.scalars().all()
                
                if not actions:
                    continue
                
                # Check outcomes
                action_ids = [a.id for a in actions]
                outcomes_result = await db.execute(
                    select(CompanyActionOutcome).where(
                        CompanyActionOutcome.organization_id == caller.organization_id,
                        CompanyActionOutcome.action_id.in_(action_ids),
                    )
                )
                outcomes = outcomes_result.scalars().all()
                
                if not outcomes:
                    attention.append({
                        "id": f"obj-drift-no-outcome-{commitment.id}",
                        "kind": "objective_execution_drift",
                        "severity": "medium",
                        "title": f"Commitment without outcomes: {commitment.title}",
                        "description": f"Commitment '{commitment.title}' has actions but no recorded outcomes",
                        "source_entities": [{
                            "type": "commitment",
                            "id": commitment.id,
                            "title": commitment.title,
                        }],
                        "affected_entities": [{
                            "type": "commitment",
                            "id": commitment.id,
                        }],
                        "risk_factors": ["no_outcomes", "execution_gap"],
                        "provenance": {
                            "derived_from": "commitment_outcome_check",
                            "commitment_id": commitment.id,
                            "derived_at": utcnow().isoformat(),
                        },
                        "derived_at": utcnow(),
                        "scope_id": commitment.scope_id,
                    })
        
        return attention

    # Global instance
organizational_attention_service = OrganizationalAttentionService()