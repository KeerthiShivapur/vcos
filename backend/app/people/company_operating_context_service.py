"""Company Operating Context Service — Gate 8.4.

This service derives the company-wide operating context from canonical company reality.
It is a READ/DERIVATION layer — not a second source of truth.
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
from app.models.task import Task, TaskDependency
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
from app.intelligence.company_context import resolve_caller_access, CallerAccess

logger = logging.getLogger("vcos.people.company_operating_context")


@dataclass
class CompanyOperatingContext:
    """Canonical company operating context — derived from canonical reality."""
    
    # Organization
    organization_id: str
    organization_name: str
    
    # Objectives
    objectives: List[Dict[str, Any]] = field(default_factory=list)
    
    # Initiatives
    initiatives: List[Dict[str, Any]] = field(default_factory=list)
    
    # Commitments
    commitments: List[Dict[str, Any]] = field(default_factory=list)
    
    # Authorizations
    authorizations: List[Dict[str, Any]] = field(default_factory=list)
    
    # Responsibilities
    responsibilities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Accountability links
    accountability_links: List[Dict[str, Any]] = field(default_factory=list)
    
    # Actions
    actions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Action outcomes
    action_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    
    # Projects
    projects: List[Dict[str, Any]] = field(default_factory=list)
    
    # Tasks
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Task dependencies
    task_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    
    # Meetings
    meetings: List[Dict[str, Any]] = field(default_factory=list)
    
    # Communication threads
    communication_threads: List[Dict[str, Any]] = field(default_factory=list)
    
    # Messages
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Workload
    workload: List[Dict[str, Any]] = field(default_factory=list)
    
    # Attention
    attention: List[Dict[str, Any]] = field(default_factory=list)
    
    # Governance
    governance_scopes: List[Dict[str, Any]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    org_wide: bool = False
    
    # Metadata
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class CompanyOperatingContextService:
    """Canonical service for deriving company operating context from canonical reality.
    
    This is a READ/DERIVATION layer — it must not become a second source of truth.
    All data is derived from canonical PostgreSQL reality through canonical models.
    """

    def __init__(self):
        pass

    async def derive_company_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> CompanyOperatingContext:
        """Derive company operating context from canonical reality.

        Args:
            db: Database session
            caller: Caller access context (governance)

        Returns:
            Derived company operating context
        """
        # Get organization
        org = await db.get(Organization, caller.organization_id)

        # Get objectives
        objectives = await self._get_active_objectives(db, caller)

        # Get initiatives
        initiatives = await self._get_active_initiatives(db, caller)

        # Get commitments
        commitments = await self._get_active_commitments(db, caller)

        # Get authorizations
        authorizations = await self._get_active_authorizations(db, caller)

        # Get responsibilities
        responsibilities = await self._get_active_responsibilities(db, caller)

        # Get accountability links
        accountability_links = await self._get_accountability_links(db, caller)

        # Get actions
        actions = await self._get_active_actions(db, caller)

        # Get action outcomes
        action_outcomes = await self._get_action_outcomes(db, caller)

        # Get projects
        projects = await self._get_active_projects(db, caller)

        # Get tasks
        tasks = await self._get_active_tasks(db, caller)

        # Get task dependencies
        task_dependencies = await self._get_task_dependencies(db, caller)

        # Get meetings
        meetings = await self._get_upcoming_meetings(db, caller)

        # Get communication threads
        communication_threads = await self._get_active_threads(db, caller)

        # Get messages
        messages = await self._get_recent_messages(db, caller)

        # Get workload
        workload = await self._get_workload(db, caller)

        # Get attention
        attention = await self._get_attention(db, caller)

        # Get governance scopes
        governance_scopes = await self._get_governance_scopes(db, caller)

        # Get permissions
        permissions = await caller.get_permissions(db)

        # Build company operating context
        context = CompanyOperatingContext(
            organization_id=caller.organization_id,
            organization_name=org.name if org else "",
            objectives=objectives,
            initiatives=initiatives,
            commitments=commitments,
            authorizations=authorizations,
            responsibilities=responsibilities,
            accountability_links=accountability_links,
            actions=actions,
            action_outcomes=action_outcomes,
            projects=projects,
            tasks=tasks,
            task_dependencies=task_dependencies,
            meetings=meetings,
            communication_threads=communication_threads,
            messages=messages,
            workload=workload,
            attention=attention,
            governance_scopes=governance_scopes,
            permissions=list(permissions),
            org_wide=caller.org_wide,
        )

        logger.info(f"Derived company operating context for org {caller.organization_id}")
        return context

    # Private helper methods for data retrieval

    async def _get_active_objectives(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active objectives."""
        result = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
                CompanyObjective.status == "active",
            ).order_by(CompanyObjective.updated_at.desc())
        )
        objectives = []
        for obj in result.scalars().all():
            objectives.append({
                "id": obj.id,
                "goal_id": obj.goal_id,
                "intent_id": obj.intent_id,
                "title": obj.title,
                "description": obj.description,
                "kind": obj.kind,
                "status": obj.status,
                "required_capabilities": obj.required_capabilities,
                "owner_person_id": obj.owner_person_id,
                "owner_label": obj.owner_label,
                "current_value": obj.current_value,
                "target_value": obj.target_value,
                "actual_outcome_state": obj.actual_outcome_state,
                "measurement_quality": obj.measurement_quality,
                "fingerprint": obj.fingerprint,
                "version": obj.version,
            })
        return objectives

    async def _get_active_initiatives(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active initiatives."""
        result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
                CompanyInitiative.status == "active",
            ).order_by(CompanyInitiative.updated_at.desc())
        )
        initiatives = []
        for init in result.scalars().all():
            initiatives.append({
                "id": init.id,
                "objective_id": init.objective_id,
                "title": init.title,
                "description": init.description,
                "kind": init.kind,
                "status": init.status,
                "required_capabilities": init.required_capabilities,
                "customer_commitments": init.customer_commitments,
                "expected_outcome": init.expected_outcome,
                "owner_person_id": init.owner_person_id,
                "owner_label": init.owner_label,
                "fingerprint": init.fingerprint,
                "version": init.version,
            })
        return initiatives

    async def _get_active_commitments(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active commitments."""
        result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            ).order_by(CompanyCommitment.updated_at.desc())
        )
        commitments = []
        for c in result.scalars().all():
            commitments.append({
                "id": c.id,
                "commitment_type": c.commitment_type,
                "title": c.title,
                "description": c.description,
                "rationale": c.rationale,
                "state": c.state,
                "commitment_type": c.commitment_type,
                "scope_type": c.scope_type,
                "scope_id": c.scope_id,
                "intent_id": c.intent_id,
                "objective_id": c.objective_id,
                "initiative_id": c.initiative_id,
                "project_id": c.project_id,
                "decision_id": c.decision_id,
                "authorization_id": c.authorization_id,
                "budget_allocated": c.budget_allocated,
                "budget_currency": c.budget_currency,
                "resource_requirements": c.resource_requirements,
                "resource_constraints": c.resource_constraints,
                "start_date": c.start_date,
                "target_date": c.target_date,
                "conditions": c.conditions,
                "risk_assessment": c.risk_assessment,
                "risk_mitigations": c.risk_mitigations,
                "evidence_fingerprints": c.evidence_fingerprints,
                "supporting_pattern_ids": c.supporting_pattern_ids,
                "supporting_lesson_fingerprints": c.supporting_lesson_fingerprints,
                "contradicting_evidence_fingerprints": c.contradicting_evidence_fingerprints,
                "contradicting_pattern_ids": c.contradicting_pattern_ids,
                "contradicting_lesson_fingerprints": c.contradicting_lesson_fingerprints,
                "contradiction_ids": c.contradiction_ids,
                "decision_intelligence_context_id": c.decision_intelligence_context_id,
                "decision_alternative_ids": c.decision_alternative_ids,
                "action_ids": c.action_ids,
                "state": c.state,
                "authorized_at": c.authorized_at,
                "authorized_by": c.authorized_by,
                "fulfilled_at": c.fulfilled_at,
                "fulfilled_by": c.fulfilled_by,
                "supersedes_id": c.supersedes_id,
                "superseded_by_id": c.superseded_by_id,
                "source_event_id": c.source_event_id,
                "source_decision_id": c.source_decision_id,
                "source_scenario_id": c.source_scenario_id,
                "fingerprint": c.fingerprint,
                "version": c.version,
            })
        return commitments

    async def _get_active_authorizations(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active authorizations."""
        result = await db.execute(
            select(CompanyAuthorization).where(
                CompanyAuthorization.organization_id == caller.organization_id,
                CompanyAuthorization.state.in_(("approved", "conditional")),
            ).order_by(CompanyAuthorization.updated_at.desc())
        )
        authorizations = []
        for auth in result.scalars().all():
            authorizations.append({
                "id": auth.id,
                "authorization_type": auth.authorization_type,
                "title": auth.title,
                "description": auth.description,
                "rationale": auth.rationale,
                "scope_type": auth.scope_type,
                "scope_id": auth.scope_id,
                "decision_intelligence_context_id": auth.decision_intelligence_context_id,
                "decision_id": auth.decision_id,
                "commitment_id": auth.commitment_id,
                "policy_id": auth.policy_id,
                "conditions": auth.conditions,
                "constraints": auth.constraints,
                "budget_ceiling": auth.budget_ceiling,
                "budget_currency": auth.budget_currency,
                "valid_from": auth.valid_from,
                "valid_until": auth.valid_until,
                "state": auth.state,
                "requested_by": auth.requested_by,
                "requested_at": auth.requested_at,
                "approved_by": auth.approved_by,
                "approved_at": auth.approved_at,
                "rejected_by": auth.rejected_by,
                "rejected_at": auth.rejected_at,
                "evidence_fingerprints": auth.evidence_fingerprints,
                "supporting_pattern_ids": auth.supporting_pattern_ids,
                "supporting_lesson_fingerprints": auth.supporting_lesson_fingerprints,
                "contradicting_evidence_fingerprints": auth.contradicting_evidence_fingerprints,
                "contradicting_pattern_ids": auth.contradicting_pattern_ids,
                "contradicting_lesson_fingerprints": auth.contradicting_lesson_fingerprints,
                "contradiction_ids": auth.contradiction_ids,
                "decision_alternative_ids": auth.decision_alternative_ids,
                "decision_evidence_fingerprints": auth.decision_evidence_fingerprints,
                "decision_precedent_ids": auth.decision_precedent_ids,
                "risk_assessment": auth.risk_assessment,
                "lesson_fingerprints": auth.lesson_fingerprints,
                "pattern_ids": auth.pattern_ids,
                "source_event_id": auth.source_event_id,
                "source_decision_id": auth.source_decision_id,
                "source_scenario_id": auth.source_scenario_id,
                "fingerprint": auth.fingerprint,
                "version": auth.version,
            })
        return authorizations

    async def _get_active_responsibilities(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active responsibilities."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.state == "active",
            ).order_by(OrganizationalResponsibility.valid_from.desc())
        )
        responsibilities = []
        for r in result.scalars().all():
            responsibilities.append({
                "id": r.id,
                "responsibility_type": r.responsibility_type,
                "title": r.title,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "raci_accountable": r.raci_accountable,
                "raci_responsible": r.raci_responsible,
                "raci_consulted": r.raci_consulted,
                "raci_informed": r.raci_informed,
                "person_id": r.person_id,
                "role_id": r.role_id,
                "team_id": r.team_id,
                "department_id": r.department_id,
                "objective_id": r.objective_id,
                "initiative_id": r.initiative_id,
                "project_id": r.project_id,
                "commitment_id": r.commitment_id,
                "authorization_id": r.authorization_id,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "supersedes_id": r.supersedes_id,
                "superseded_by_id": r.superseded_by_id,
                "delegated_from_id": r.delegated_from_id,
                "delegation_depth": r.delegation_depth,
                "state": r.state,
                "source_event_id": r.source_event_id,
                "created_by": r.created_by,
                "fingerprint": r.fingerprint,
                "version": r.version,
            })
        return responsibilities

    async def _get_accountability_links(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get accountability links."""
        result = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == caller.organization_id,
            ).order_by(AccountabilityLink.valid_from.desc())
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
                "source_event_id": link.source_event_id,
                "created_by": link.created_by,
                "fingerprint": link.fingerprint,
                "version": link.version,
            })
        return links

    async def _get_active_actions(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active actions."""
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.state.in_(("proposed", "approved", "ready", "in_progress")),
            ).order_by(CompanyAction.updated_at.desc()).limit(50)
        )
        actions = []
        for a in result.scalars().all():
            actions.append({
                "id": a.id,
                "action_type": a.action_type,
                "title": a.title,
                "description": a.description,
                "state": a.state,
                "risk": a.risk,
                "priority_score": a.priority_score,
                "scope_type": a.scope_type,
                "scope_id": a.scope_id,
                "fingerprint": a.fingerprint,
                "target_label": a.target_label,
                "source_problem": a.source_problem,
                "why": a.why,
                "source_recommendation_id": a.source_recommendation_id,
                "source_insight_id": a.source_insight_id,
                "source_event_id": a.source_event_id,
                "source_claim_ids_json": a.source_claim_ids_json,
                "source_company_decision_id": a.source_company_decision_id,
                "source_scenario_id": a.source_scenario_id,
                "source_commitment_id": a.source_commitment_id,
                "source_scenario_id": a.source_scenario_id,
                "source_responsibility_id": a.source_responsibility_id,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "policy": a.policy,
                "approval_required": a.approval_required,
                "approver_id": a.approver_id,
                "approved_by": a.approved_by,
                "approved_at": a.approved_at,
                "approval_note": a.approval_note,
                "rejected_reason": a.rejected_reason,
                "assignee_type": a.assignee_type,
                "assignee_id": a.assignee_id,
                "assigned_at": a.assigned_at,
                "due_at": a.due_at,
                "dependencies_json": a.dependencies_json,
                "escalation_level": a.escalation_level,
                "started_at": a.started_at,
                "blocked_at": a.blocked_at,
                "blocked_reason": a.blocked_reason,
                "completed_at": a.completed_at,
                "completed_by": a.completed_by,
                "verified_at": a.verified_at,
                "verified_by": a.verified_by,
                "verification_note": a.verification_note,
                "outcome_id": a.outcome_id,
                "fail_reason": a.fail_reason,
                "cancel_reason": a.cancel_reason,
                "expired_at": a.expired_at,
                "supersedes_id": a.supersedes_id,
                "superseded_by_id": a.superseded_by_id,
                "version": a.version,
                "created_by": a.created_by,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            })
        return actions

    async def _get_action_outcomes(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get action outcomes."""
        result = await db.execute(
            select(CompanyActionOutcome).where(
                CompanyActionOutcome.organization_id == caller.organization_id,
            ).order_by(CompanyActionOutcome.measured_at.desc()).limit(50)
        )
        outcomes = []
        for o in result.scalars().all():
            outcomes.append({
                "id": o.id,
                "organization_id": o.organization_id,
                "action_id": o.action_id,
                "outcome_type": o.outcome_type,
                "verdict": o.verdict,
                "effectiveness": o.effectiveness,
                "evidence_json": o.evidence_json,
                "notes": o.notes,
                "recorded_by": o.recorded_by,
                "measured_at": o.measured_at,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            })
        return outcomes

    async def _get_active_projects(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active projects."""
        result = await db.execute(
            select(Project).where(
                Project.organization_id == caller.organization_id,
                Project.status == "active",
            ).order_by(Project.updated_at.desc()).limit(20)
        )
        projects = []
        for p in result.scalars().all():
            # Load owner name if owner_id exists
            owner_name = None
            if p.owner_id:
                from app.models.employee import Employee
                owner = await db.get(Employee, p.owner_id)
                if owner:
                    owner_name = owner.full_name
            
            # Load department name
            department_name = None
            if p.department_id:
                from app.models.department import Department
                dept = await db.get(Department, p.department_id)
                if dept:
                    department_name = dept.name
            
            # Load team name
            team_name = None
            if p.team_id:
                from app.models.team import Team
                team = await db.get(Team, p.team_id)
                if team:
                    team_name = team.name
            
            projects.append({
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "priority": p.priority,
                "progress": p.progress,
                "health": p.health,
                "owner_id": p.owner_id,
                "owner_name": owner_name,
                "department_id": p.department_id,
                "department_name": department_name,
                "team_id": p.team_id,
                "team_name": team_name,
                "roadmap_id": p.roadmap_id,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "budget": p.budget,
                "tags": p.tags,
                "ai_summary": p.ai_summary,
                "members_count": 0,  # Would need separate query
                "tasks_count": 0,  # Would need separate query
                "completed_count": 0,  # Would need separate query
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            })
        return projects

    async def _get_active_tasks(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active tasks."""
        result = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.status.in_(("todo", "in_progress", "review")),
            ).order_by(Task.updated_at.desc()).limit(50)
        )
        tasks = []
        for t in result.scalars().all():
            tasks.append({
                "id": t.id,
                "project_id": t.project_id,
                "epic_id": t.epic_id,
                "milestone_id": t.milestone_id,
                "sprint_id": t.sprint_id,
                "parent_task_id": t.parent_task_id,
                "decision_id": t.decision_id,
                "goal_id": t.goal_id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "assignee_id": t.assignee_id,
                "reporter_id": t.reporter_id,
                "estimate_hours": t.estimate_hours,
                "spent_hours": t.spent_hours,
                "start_date": t.start_date,
                "due_date": t.due_date,
                "completed_at": t.completed_at,
                "progress": t.progress,
                "tags": t.tags,
                "ai_summary": t.ai_summary,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            })
        return tasks

    async def _get_task_dependencies(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get task dependencies."""
        result = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == caller.organization_id,
            ).order_by(TaskDependency.created_at.desc()).limit(100)
        )
        deps = []
        for dep in result.scalars().all():
            deps.append({
                "id": dep.id,
                "task_id": dep.task_id,
                "depends_on_task_id": dep.depends_on_task_id,
                "kind": dep.kind,
                "created_at": dep.created_at,
            })
        return deps

    async def _get_upcoming_meetings(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get upcoming meetings."""
        now = utcnow()
        result = await db.execute(
            select(Meeting).where(
                Meeting.organization_id == caller.organization_id,
                Meeting.start_at >= now,
                Meeting.status.in_(("scheduled", "in_progress")),
            ).order_by(Meeting.start_at).limit(20)
        )
        meetings = []
        for m in result.scalars().all():
            meetings.append({
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "meeting_type": m.meeting_type,
                "status": m.status,
                "organizer_id": m.organizer_id,
                "organizer_name": getattr(m, "organizer_name", None),
                "project_id": m.project_id,
                "goal_id": m.goal_id,
                "department_id": m.department_id,
                "team_id": m.team_id,
                "calendar_event_id": m.calendar_event_id,
                "room_id": m.room_id,
                "meeting_code": m.meeting_code,
                "timezone": m.timezone,
                "duration_minutes": m.duration_minutes,
                "start_at": m.start_at,
                "end_at": m.end_at,
                "location": m.location,
                "meeting_link": m.meeting_link,
                "transcript_summary": m.transcript_summary,
                "ai_summary": m.ai_summary,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            })
        return meetings

    async def _get_active_threads(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get active communication threads."""
        result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.organization_id == caller.organization_id,
                CanonicalCommunicationThread.status == "active",
            ).order_by(CanonicalCommunicationThread.last_message_at.desc()).limit(20)
        )
        threads = []
        for t in result.scalars().all():
            threads.append({
                "id": t.id,
                "organization_id": t.organization_id,
                "thread_type": t.thread_type,
                "title": t.title,
                "description": t.description,
                "objective_id": t.objective_id,
                "commitment_id": t.commitment_id,
                "responsibility_id": t.responsibility_id,
                "decision_id": t.decision_id,
                "project_id": t.project_id,
                "meeting_id": t.meeting_id,
                "scope_type": t.scope_type,
                "scope_id": t.scope_id,
                "status": t.status,
                "valid_from": t.valid_from,
                "valid_to": t.valid_to,
                "version": t.version,
                "fingerprint": t.fingerprint,
                "supersedes_id": t.supersedes_id,
                "thread_metadata": t.thread_metadata,
                "source_event_id": t.source_event_id,
                "actor_id": t.actor_id,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            })
        return threads

    async def _get_recent_messages(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get recent messages."""
        result = await db.execute(
            select(CanonicalMessage).where(
                CanonicalMessage.organization_id == caller.organization_id,
            ).order_by(CanonicalMessage.valid_from.desc()).limit(50)
        )
        messages = []
        for m in result.scalars().all():
            messages.append({
                "id": m.id,
                "organization_id": m.organization_id,
                "thread_id": m.thread_id,
                "sender_id": m.sender_id,
                "content": m.content,
                "message_type": m.message_type,
                "reply_to": m.reply_to,
                "decision_id": m.decision_id,
                "commitment_id": m.commitment_id,
                "action_id": m.action_id,
                "objective_id": m.objective_id,
                "responsibility_id": m.responsibility_id,
                "attachments": m.attachments,
                "mentions": m.mentions,
                "valid_from": m.valid_from,
                "valid_to": m.valid_to,
                "version": m.version,
                "fingerprint": m.fingerprint,
                "supersedes_id": m.supersedes_id,
                "edited": m.edited,
                "edited_at": m.edited_at,
                "deleted": m.deleted,
                "deleted_at": m.deleted_at,
                "reaction_count": m.reaction_count,
                "source_event_id": m.source_event_id,
                "actor_id": m.actor_id,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            })
        return messages

    async def _get_workload(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get workload snapshots."""
        from app.models.workload import WorkloadSnapshot
        result = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
            ).order_by(WorkloadSnapshot.period_start.desc()).limit(20)
        )
        workloads = []
        for w in result.scalars().all():
            workloads.append({
                "id": w.id,
                "employee_id": w.employee_id,
                "period_start": w.period_start,
                "period_end": w.period_end,
                "capacity_hours": w.capacity_hours,
                "allocated_hours": w.allocated_hours,
                "utilization": w.utilization,
                "tasks_count": w.tasks_count,
                "meetings_hours": w.meetings_hours,
                "is_overloaded": w.is_overloaded,
                "created_at": w.created_at,
            })
        return workloads

    async def _get_attention(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[Dict[str, Any]]:
        """Get operating attention items."""
        # This would derive attention from cross-domain analysis
        # For now, return empty list - actual derivation in operating_attention_service
        return []

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


# Global instance
company_operating_context_service = CompanyOperatingContextService()


# Global instance
company_operating_context_service = CompanyOperatingContextService()