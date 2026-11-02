"""Company Operating Slice Service — Gate 8.4.

This service provides governed company operating slice queries that can answer:
- What is happening with this objective?
- What is happening with this commitment?
- What is happening with this project?
- What is happening with this team?
- What is happening with this person?

All answers must derive from canonical reality.
"""

from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import CompanyDecision
from app.models.meeting import Meeting, MeetingAttendee, MeetingAgendaItem, MeetingActionItem
from app.models.communication import (
    CanonicalCommunicationThread,
    CanonicalMessage,
    CanonicalCommunicationThreadMember,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.execution_strategy import CompanyGoal
from app.models.meeting import Meeting, MeetingAttendee
from sqlalchemy import select, and_, or_

logger = logging.getLogger("vcos.intelligence.company_operating_slice")


@dataclass
class CompanyOperatingSlice:
    """Canonical company operating slice — a cross-domain view of an entity."""

    # The entity being sliced
    entity_type: str  # "objective", "commitment", "project", "team", "person"
    entity_id: str
    
    # Core entity info
    title: str
    status: str
    
    # Cross-domain relationships
    objectives: List[Dict[str, Any]] = field(default_factory=list)
    initiatives: List[Dict[str, Any]] = field(default_factory=list)
    commitments: List[Dict[str, Any]] = field(default_factory=list)
    authorizations: List[Dict[str, Any]] = field(default_factory=list)
    responsibilities: List[Dict[str, Any]] = field(default_factory=list)
    accountability_links: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    action_outcomes: List[Dict[str, Any]] = field(default_factory=list)
    projects: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    task_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    meetings: List[Dict[str, Any]] = field(default_factory=list)
    communication_threads: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class CompanyOperatingSliceService:
    """Canonical service for company operating slice queries."""

    def __init__(self):
        pass

    async def get_objective_slice(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        objective_id: str,
    ) -> Dict[str, Any]:
        """Get operating slice for an objective."""
        # Get objective
        objective = await db.get(CompanyObjective, objective_id)
        if not objective or objective.organization_id != caller.organization_id:
            raise ValueError(f"Objective not found: {objective_id}")
        
        # Check governance
        if not caller.org_wide and objective.id not in caller.visible_scope_ids:
            # Check if objective is in visible scope
            pass
        
        # Get initiatives for this objective
        initiatives_result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
                CompanyInitiative.objective_id == objective_id,
                CompanyInitiative.status == "active",
            )
        )
        initiatives = []
        for i in initiatives_result.scalars().all():
            initiatives.append({
                "id": i.id,
                "title": i.title,
                "description": i.description,
                "kind": i.kind,
                "status": i.status,
                "expected_outcome": i.expected_outcome,
                "owner_person_id": i.owner_person_id,
                "owner_label": i.owner_label,
                "fingerprint": i.fingerprint,
                "version": i.version,
            })
        
        # Get commitments for this objective
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.objective_id == objective_id,
                CompanyCommitment.state.in_(("authorized", "active", "paused")),
            )
        )
        commitments = []
        for c in commitments_result.scalars().all():
            commitments.append({
                "id": c.id,
                "commitment_type": c.commitment_type,
                "title": c.title,
                "state": c.state,
                "scope_type": c.scope_type,
                "scope_id": c.scope_id,
                "objective_id": c.objective_id,
                "initiative_id": c.initiative_id,
                "decision_id": c.decision_id,
                "authorization_id": c.authorization_id,
                "fingerprint": c.fingerprint,
                "version": c.version,
            })
        
        # Get responsibilities
        responsibilities = await self._get_responsibilities_for_objective(
            db, caller.organization_id, objective_id
        )
        
        # Get actions
        actions = await self._get_actions_for_objective(db, caller.organization_id, objective_id)
        
        # Get projects
        projects = await self._get_projects_for_objective(db, caller.organization_id, objective_id)
        
        # Get tasks
        tasks = await self._get_tasks_for_objective(db, caller.organization_id, objective_id)
        
        # Get meetings
        meetings = await self._get_meetings_for_objective(db, caller.organization_id, objective_id)
        
        return {
            "objective_id": objective_id,
            "title": objective.title,
            "kind": objective.kind,
            "status": objective.status,
            "initiatives": initiatives,
            "commitments": commitments,
            "responsibilities": responsibilities,
            "actions": actions,
            "projects": projects,
            "tasks": tasks,
            "meetings": meetings,
        }

    async def get_commitment_slice(
        self,
        db: AsyncSession,
        *,
        caller: Any,
        commitment_id: str,
    ) -> Dict[str, Any]:
        """Get operating slice for a commitment."""
        commitment = await db.get(CompanyCommitment, commitment_id)
        if not commitment or commitment.organization_id != caller.organization_id:
            raise ValueError(f"Commitment not found: {commitment_id}")
        
        # Get authorization
        authorization = None
        if commitment.authorization_id:
            auth = await db.get(CompanyAuthorization, commitment.authorization_id)
            if auth:
                authorization = {
                    "id": auth.id,
                    "authorization_type": auth.authorization_type,
                    "title": auth.title,
                    "state": auth.state,
                    "scope_type": auth.scope_type,
                    "scope_id": auth.scope_id,
                }
        
        # Get responsibilities
        responsibilities = await self._get_responsibilities_for_commitment(
            db, caller.organization_id, commitment_id
        )
        
        # Get accountability links
        links_result = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == caller.organization_id,
                AccountabilityLink.commitment_id == commitment_id,
            )
        )
        accountability_links = []
        for link in links_result.scalars().all():
            accountability_links.append({
                "id": link.id,
                "commitment_id": link.commitment_id,
                "authorization_id": link.authorization_id,
                "responsibility_id": link.responsibility_id,
                "accountability_type": link.accountability_type,
                "valid_from": link.valid_from,
                "valid_to": link.valid_to,
            })
        
        # Get actions
        actions_result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.source_commitment_id == commitment_id,
            )
        )
        actions = []
        for a in actions_result.scalars().all():
            actions.append({
                "id": a.id,
                "action_type": a.action_type,
                "title": a.title,
                "state": a.state,
                "scope_type": a.scope_type,
                "scope_id": a.scope_id,
                "source_responsibility_id": a.source_responsibility_id,
                "assignee_id": a.assignee_id,
                "fingerprint": a.fingerprint,
                "version": a.version,
            })
        
        # Get action outcomes
        action_outcomes = []
        for action in actions_result.scalars().all():
            outcome = await db.execute(
                select(CompanyActionOutcome).where(
                    CompanyActionOutcome.action_id == action.id,
                )
            )
            for o in outcome.scalars().all():
                action_outcomes.append({
                    "id": o.id,
                    "action_id": o.action_id,
                    "outcome_type": o.outcome_type,
                    "verdict": o.verdict,
                    "effectiveness": o.effectiveness,
                    "evidence_json": o.evidence_json,
                    "recorded_by": o.recorded_by,
                    "measured_at": o.measured_at,
                })
        
        # Get meetings
        meetings_result = await db.execute(
            select(Meeting).where(
                Meeting.organization_id == caller.organization_id,
                Meeting.decision_id == commitment.decision_id,
            )
        )
        meetings = []
        for m in meetings_result.scalars().all():
            meetings.append({
                "id": m.id,
                "title": m.title,
                "meeting_type": m.meeting_type,
                "status": m.status,
                "start_at": m.start_at,
                "end_at": m.end_at,
            })
        
        # Get communication threads
        threads_result = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.organization_id == caller.organization_id,
                CanonicalCommunicationThread.meeting_id.in_(
                    select(Meeting.id).where(Meeting.decision_id == commitment.decision_id)
                ),
            )
        )
        communication_threads = []
        for t in threads_result.scalars().all():
            communication_threads.append({
                "id": t.id,
                "thread_type": t.thread_type,
                "title": t.title,
                "meeting_id": t.meeting_id,
            })
        
        return {
            "commitment_id": commitment_id,
            "title": commitment.title,
            "commitment_type": commitment.commitment_type,
            "state": commitment.state,
            "scope_type": commitment.scope_type,
            "scope_id": commitment.scope_id,
            "decision_id": commitment.decision_id,
            "objective_id": commitment.objective_id,
            "initiative_id": commitment.initiative_id,
            "project_id": commitment.project_id,
            "authorization": authorization,
            "responsibilities": await self._get_responsibilities_for_commitment(
                db, caller.organization_id, commitment_id
            ),
            "accountability_links": accountability_links,
            "actions": actions,
            "action_outcomes": action_outcomes,
            "meetings": meetings,
            "communication_threads": communication_threads,
        }

    async def _get_responsibilities_for_objective(
        self, db: AsyncSession, org_id: str, objective_id: str
    ) -> List[Dict[str, Any]]:
        """Get responsibilities linked to an objective."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == org_id,
                OrganizationalResponsibility.objective_id == objective_id,
                OrganizationalResponsibility.state == "active",
            )
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
                "person_id": r.person_id,
                "commitment_id": r.commitment_id,
                "authorization_id": r.authorization_id,
            })
        return responsibilities

    async def _get_responsibilities_for_commitment(
        self, db: AsyncSession, org_id: str, commitment_id: str
    ) -> List[Dict[str, Any]]:
        """Get responsibilities linked to a commitment."""
        result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == org_id,
                OrganizationalResponsibility.commitment_id == commitment_id,
                OrganizationalResponsibility.state == "active",
            )
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
                "person_id": r.person_id,
                "commitment_id": r.commitment_id,
                "authorization_id": r.authorization_id,
            })
        return responsibilities

    async def _get_actions_for_objective(
        self, db: AsyncSession, org_id: str, objective_id: str
    ) -> List[Dict[str, Any]]:
        """Get actions linked to an objective through commitments."""
        # Get commitments for this objective
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == org_id,
                CompanyCommitment.objective_id == objective_id,
            )
        )
        commitment_ids = [c.id for c in commitments_result.scalars().all()]
        
        if not commitment_ids:
            return []
        
        actions_result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == org_id,
                CompanyAction.source_commitment_id.in_(commitment_ids),
            )
        )
        actions = []
        for a in actions_result.scalars().all():
            actions.append({
                "id": a.id,
                "action_type": a.action_type,
                "title": a.title,
                "state": a.state,
                "scope_type": a.scope_type,
                "scope_id": a.scope_id,
                "source_commitment_id": a.source_commitment_id,
                "source_responsibility_id": a.source_responsibility_id,
                "assignee_id": a.assignee_id,
                "fingerprint": a.fingerprint,
                "version": a.version,
            })
        return actions

    async def _get_projects_for_objective(
        self, db: AsyncSession, org_id: str, objective_id: str
    ) -> List[Dict[str, Any]]:
        """Get projects linked to an objective through commitments."""
        # Get commitments with project_id
        commitments_result = await db.execute(
            select(CompanyCommitment.id, CompanyCommitment.project_id).where(
                CompanyCommitment.organization_id == org_id,
                CompanyCommitment.objective_id == objective_id,
                CompanyCommitment.project_id.is_not(None),
            )
        )
        project_ids = [c.project_id for c in commitments_result if c.project_id]
        
        # Also check commitments with scope_type="project" and scope_id set
        commitments_result2 = await db.execute(
            select(CompanyCommitment.id, CompanyCommitment.scope_id).where(
                CompanyCommitment.organization_id == org_id,
                CompanyCommitment.objective_id == objective_id,
                CompanyCommitment.scope_type == "project",
                CompanyCommitment.scope_id.is_not(None),
                CompanyCommitment.project_id.is_(None),
            )
        )
        for c in commitments_result2:
            if c.scope_id and c.scope_id not in project_ids:
                project_ids.append(c.scope_id)
        
        if not project_ids:
            return []
        
        projects_result = await db.execute(
            select(Project).where(
                Project.organization_id == org_id,
                Project.id.in_(project_ids),
            )
        )
        projects = []
        for p in projects_result.scalars().all():
            projects.append({
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "status": p.status,
                "progress": p.progress,
            })
        return projects

    async def _get_tasks_for_objective(
        self, db: AsyncSession, org_id: str, objective_id: str
    ) -> List[Dict[str, Any]]:
        """Get tasks linked to an objective through commitments/actions."""
        # Get commitments for this objective
        commitments_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == org_id,
                CompanyCommitment.objective_id == objective_id,
            )
        )
        commitment_ids = [c.id for c in commitments_result.scalars().all()]
        
        if not commitment_ids:
            return []
        
        # Get actions for these commitments
        actions_result = await db.execute(
            select(CompanyAction.id, CompanyAction.target_id).where(
                CompanyAction.organization_id == org_id,
                CompanyAction.source_commitment_id.in_(commitment_ids),
                CompanyAction.target_type == "task",
                CompanyAction.target_id.is_not(None),
            )
        )
        task_ids = [a.target_id for a in actions_result if a.target_id]
        
        if not task_ids:
            return []
        
        tasks_result = await db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.id.in_(task_ids),
            )
        )
        tasks = []
        for t in tasks_result.scalars().all():
            tasks.append({
                "id": t.id,
                "project_id": t.project_id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "assignee_id": t.assignee_id,
            })
        return tasks

    async def _get_meetings_for_objective(
        self, db: AsyncSession, org_id: str, objective_id: str
    ) -> List[Dict[str, Any]]:
        """Get meetings linked to an objective through commitments/decisions."""
        commitments_result = await db.execute(
            select(CompanyCommitment.decision_id).where(
                CompanyCommitment.organization_id == org_id,
                CompanyCommitment.objective_id == objective_id,
                CompanyCommitment.decision_id.is_not(None),
            )
        )
        decision_ids = [c.decision_id for c in commitments_result if c.decision_id]
        
        if not decision_ids:
            return []
        
        meetings_result = await db.execute(
            select(Meeting).where(
                Meeting.organization_id == org_id,
                Meeting.decision_id.in_(decision_ids),
            )
        )
        meetings = []
        for m in meetings_result.scalars().all():
            meetings.append({
                "id": m.id,
                "title": m.title,
                "meeting_type": m.meeting_type,
                "status": m.status,
                "decision_id": m.decision_id,
                "start_at": m.start_at,
                "end_at": m.end_at,
            })
        return meetings


# Global instance
company_operating_slice_service = CompanyOperatingSliceService()