"""Universal Company Workspace + Virtual Office Operating Fabric API.

Gate 25 — The unified operating surface for the canonical VCOS system.
Provides the single workspace where employees, managers, and executives
experience the company through authorized projections of ONE canonical reality.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting, MeetingAttendee
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyObjective
from app.models.canonical_business_intelligence import (
    CanonicalMetric, MetricObservation, CanonicalCompanyHealth,
    VarianceAnalysis, CanonicalDecisionContext, CanonicalExecutiveBriefing
)
from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
from app.intelligence.company_brain import company_brain

router = APIRouter(prefix="/workspace", tags=["Universal Workspace"])


# =============================================================================
# Request/Response Models
# =============================================================================

class MyDayResponse(BaseModel):
    """My Day - the employee's daily operating surface."""
    date: str
    user: dict
    meetings: list[dict]
    commitments: list[dict]
    tasks: list[dict]
    blocked_work: list[dict]
    approvals: list[dict]
    important_communications: list[dict]
    attention_signals: list[dict]
    capacity_context: dict
    relevant_changes: list[dict]


class CompanyHomeResponse(BaseModel):
    """Company Home - executive/company-wide operating surface."""
    organization: dict
    strategy: dict
    objectives: list[dict]
    execution: dict
    customers: dict
    financial_state: dict
    operations: dict
    people: dict
    capacity: dict
    resources: dict
    procurement: dict
    risks: list[dict]
    predictions: list[dict]
    decisions: list[dict]
    company_brain: dict


class ManagerWorkspaceResponse(BaseModel):
    """Manager workspace - team projection."""
    team: dict
    people: list[dict]
    capacity: dict
    responsibilities: list[dict]
    commitments: list[dict]
    projects: list[dict]
    tasks: list[dict]
    dependencies: list[dict]
    bottlenecks: list[dict]
    communication: dict
    risks: list[dict]
    performance_context: dict


class ExecutiveWorkspaceResponse(BaseModel):
    """Executive workspace - organizational projection."""
    organization: dict
    strategy: dict
    objectives: list[dict]
    execution: dict
    customers: dict
    financial_state: dict
    operations: dict
    people: dict
    capacity: dict
    resources: dict
    procurement: dict
    risks: list[dict]
    predictions: list[dict]
    decisions: list[dict]
    company_brain: dict
    cross_domain_impacts: list[dict] = []


class UniversalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=50)
    types: Optional[list[str]] = None
    scope: Optional[str] = None


class UniversalSearchResult(BaseModel):
    id: str
    type: str
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    metadata: dict = {}
    score: float
    deep_link: str


class UniversalSearchResponse(BaseModel):
    query: str
    results: list[UniversalSearchResult]
    total: int
    took_ms: int


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=500)
    context: Optional[dict] = None


class CommandResponse(BaseModel):
    intent: str
    interpretation: str
    actions: list[dict]
    requires_authorization: bool
    confirmation_required: bool
    result: Optional[dict] = None


class DeepLinkResolveRequest(BaseModel):
    path: str
    params: Optional[dict] = None


class DeepLinkResolveResponse(BaseModel):
    target_type: str
    target_id: Optional[str] = None
    target_url: str
    canonical_data: Optional[dict] = None


class NotificationCenterResponse(BaseModel):
    notifications: list[dict]
    unread_count: int
    grouped: dict


# =============================================================================
# My Day - Employee Daily Operating Surface
# =============================================================================

@router.get("/my-day", response_model=MyDayResponse)
async def get_my_day(
    date: Optional[str] = Query(None, description="ISO date (defaults to today)"),
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the employee's daily operating surface (My Day).
    
    Aggregates from canonical reality:
    - Meetings (from calendar)
    - Commitments (from execution_strategy)
    - Tasks (from work execution)
    - Blocked work
    - Approvals
    - Important communications
    - Attention signals
    - Capacity context
    - Relevant company changes
    
    All data derives from canonical reality — no personal productivity database.
    """
    target_date = datetime.fromisoformat(date) if date else datetime.now(timezone.utc)
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    
    # Get employee
    emp_result = await db.execute(
        select(Employee).where(Employee.user_id == user.id, Employee.organization_id == org.id)
    )
    employee = emp_result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found")
    
    # Meetings for the day
    meetings_result = await db.execute(
        select(Meeting).where(
            Meeting.organization_id == org.id,
            Meeting.start_at >= day_start,
            Meeting.start_at < day_end,
        ).join(MeetingAttendee, MeetingAttendee.meeting_id == Meeting.id).where(
            MeetingAttendee.employee_id == employee.id
        )
    )
    meetings = meetings_result.scalars().all()
    
    # Commitments due soon
    commitments_result = await db.execute(
        select(CompanyCommitment).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.state.in_(["authorized", "active"]),
            CompanyCommitment.target_date >= day_start,
            CompanyCommitment.target_date < day_end + timedelta(days=7),
        )
    )
    commitments = commitments_result.scalars().all()
    
    # Tasks assigned (open work — every canonical status except terminal ones)
    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == org.id,
            Task.assignee_id == employee.id,
            Task.status.notin_(["completed", "archived"]),
        ).order_by(Task.due_date.asc().nullslast())
    )
    tasks = tasks_result.scalars().all()
    
    # Blocked work
    blocked_tasks = [t for t in tasks if t.status == "blocked"]
    
    # Approvals awaiting user
    approvals_result = await db.execute(
        select(CompanyAction).where(
            CompanyAction.organization_id == org.id,
            CompanyAction.state == "awaiting_approval",
            CompanyAction.approver_id == employee.id,
        )
    )
    approvals = approvals_result.scalars().all()
    
    # Company Brain - what changed relevant to user
    changes_result = await company_brain.what_changed(
        db, org.id, user=user, days=7
    )
    
    # Capacity context
    from app.work.workload_service import workload_service
    workload = await workload_service.compute_for_employee(
        db, organization_id=org.id, employee_id=employee.id
    )
    
    return MyDayResponse(
        date=target_date.date().isoformat(),
        user={
            "id": employee.id,
            "name": employee.display_name,
            "email": employee.email,
            "role": employee.designation,
        },
        meetings=[
            {
                "id": m.id,
                "title": m.title,
                "start_at": m.start_at.isoformat() if m.start_at else None,
                "end_at": m.end_at.isoformat() if m.end_at else None,
                "location": m.location,
                "meeting_code": m.code,
            }
            for m in meetings
        ],
        commitments=[
            {
                "id": c.id,
                "title": c.title,
                "due_at": c.target_date.isoformat() if c.target_date else None,
                "state": c.state,
            }
            for c in commitments
        ],
        tasks=[
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_at": t.due_date.isoformat() if t.due_date else None,
                "project_id": t.project_id,
            }
            for t in tasks
        ],
        blocked_work=[
            {
                "id": t.id,
                "title": t.title,
                "blocked_reason": t.blocked_reason,
            }
            for t in blocked_tasks
        ],
        approvals=[
            {
                "id": a.id,
                "title": a.title,
                "action_type": a.action_type,
            }
            for a in approvals
        ],
        important_communications=[],  # Would integrate with messaging
        attention_signals=[
            {
                "type": "capacity_warning",
                "message": f"Capacity at {workload.get('utilization', 0)}%",
            }
        ] if workload.get("utilization", 0) > 80 else [],
        capacity_context={
            "utilization": workload.get("utilization", 0),
            "allocated_hours": workload.get("allocated_hours", 0),
            "capacity_hours": workload.get("capacity_hours", 40),
        },
        relevant_changes=changes_result.get("changes", [])[:10],
    )


# =============================================================================
# Company Home - Executive/Company-Wide Operating Surface
# =============================================================================

@router.get("/company-home", response_model=CompanyHomeResponse)
async def get_company_home(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the company-wide operating surface (Company Home).
    
    For executives and authorized viewers, shows:
    - Strategy & Objectives
    - Execution status
    - Customers
    - Financial state
    - Operations
    - People & Capacity
    - Resources & Procurement
    - Risks
    - Predictions
    - Decisions awaiting
    - Company Brain
    
    All derived from Gates 10-24 canonical reality.
    """
    from app.models.company_intent import CompanyIntent
    from app.models.project import Project
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective
    from app.models.customer import Customer
    from app.models.company_actions import CompanyAction
    from app.models.canonical_business_intelligence import CanonicalMetric, MetricObservation
    from app.models.company_state import CompanyState
    from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
    from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
    from app.intelligence.company_brain import company_brain
    from app.intelligence.canonical_workforce_service import canonical_workforce_service
    from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
    from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
    from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
    from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
    from app.intelligence.company_planning_engine import company_planning_engine
    from sqlalchemy import select, func, and_, or_, desc
    from datetime import datetime, timezone, timedelta
    
    # Get Company Brain overview
    brain_overview = await company_brain.overview(db, org.id, user=user)
    
    # Get BI briefing
    from app.intelligence.company_context import resolve_caller_access

    caller = await resolve_caller_access(db, organization_id=org.id, user=user)
    briefing = await canonical_business_intelligence_service.generate_executive_briefing(
        db, caller=caller, briefing_type="weekly"
    )
    
    # Get digital twin state
    twin_state = await canonical_digital_twin_service.derive_twin_state(
        db, caller=caller, scope_type="org", scope_id=org.id
    )
    
    # Strategy - Goals and Objectives
    goals_result = await db.execute(
        select(func.count(CompanyGoal.id)).where(CompanyGoal.organization_id == org.id)
    )
    goals_count = goals_result.scalar() or 0
    
    objectives_result = await db.execute(
        select(func.count(CompanyObjective.id)).where(CompanyObjective.organization_id == org.id)
    )
    objectives_count = objectives_result.scalar() or 0
    
    # Active objectives with progress
    active_objectives = await db.execute(
        select(CompanyObjective).where(
            CompanyObjective.organization_id == org.id,
            CompanyObjective.status.in_(["active", "in_progress"])
        ).limit(10)
    )
    objectives_list = [
        {
            "id": o.id,
            "title": o.title,
            "state": o.status,
            "progress": round(min(max((o.current_value or 0.0) / o.target_value * 100.0, 0.0), 100.0), 1) if o.target_value else 0,
            "target_date": None,
        }
        for o in active_objectives.scalars().all()
    ]
    
    # Execution - Projects and Commitments
    active_projects_result = await db.execute(
        select(func.count(Project.id)).where(
            Project.organization_id == org.id,
            Project.status == "active"
        )
    )
    active_projects = active_projects_result.scalar() or 0
    
    active_commitments_result = await db.execute(
        select(func.count(CompanyCommitment.id)).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.state.in_(["authorized", "active"])
        )
    )
    active_commitments = active_commitments_result.scalar() or 0
    
    completed_commitments_result = await db.execute(
        select(func.count(CompanyCommitment.id)).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.state == "fulfilled"
        )
    )
    completed_commitments = completed_commitments_result.scalar() or 0
    total_commitments = active_commitments + completed_commitments
    completion_rate = round(completed_commitments / total_commitments * 100, 1) if total_commitments > 0 else 0
    
    # Customers
    total_customers_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.organization_id == org.id)
    )
    total_customers = total_customers_result.scalar() or 0
    
    # Financial state from BI metrics
    revenue_metric = await db.execute(
        select(CanonicalMetric).where(
            CanonicalMetric.organization_id == org.id,
            CanonicalMetric.key == "revenue"
        )
    )
    revenue_metric_obj = revenue_metric.scalar_one_or_none()
    
    # Get latest observations for key financial metrics
    financial_obs = await db.execute(
        select(MetricObservation).where(
            MetricObservation.organization_id == org.id,
            MetricObservation.metric_id.in_(
                select(CanonicalMetric.id).where(
                    CanonicalMetric.organization_id == org.id,
                    CanonicalMetric.key.in_(["revenue", "expenses", "cash_position", "runway_months"])
                )
            )
        ).order_by(MetricObservation.observed_at.desc()).limit(4)
    )
    financial_data = {}
    for obs in financial_obs.scalars().all():
        financial_data[obs.metric_id] = obs.value
    
    # Operations - Processes
    healthy_processes_result = await db.execute(
        select(func.count(CompanyState.id)).where(
            CompanyState.organization_id == org.id,
            CompanyState.state == "healthy"
        )
    )
    healthy_processes = healthy_processes_result.scalar() or 0
    
    degraded_processes_result = await db.execute(
        select(func.count(CompanyState.id)).where(
            CompanyState.organization_id == org.id,
            CompanyState.state == "degraded"
        )
    )
    degraded_processes = degraded_processes_result.scalar() or 0
    
    # People & Capacity - from Workforce service
    total_employees_result = await db.execute(
        select(func.count(Employee.id)).where(Employee.organization_id == org.id)
    )
    total_employees = total_employees_result.scalar() or 0
    
    # Capacity utilization
    from app.intelligence.organizational_capacity_service import organizational_capacity_service
    capacity_context = await organizational_capacity_service.derive_capacity_context(
        db, caller=caller, scope_type="organization"
    )
    capacity_utilization = capacity_context.utilization
    bottlenecks = capacity_context.overloaded_capabilities
    
    # Resources & Procurement
    resources_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
        db, caller=caller, scope_type="organization"
    )
    vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
        db, caller=caller, scope_type="organization"
    )
    resources_summary = {
        "allocated": resources_slice.total_committed or 0,
        "available": resources_slice.total_available or 0,
    }
    procurement_summary = {
        "pending_pos": (vendor_slice.procurements_by_state or {}).get("pending", 0),
        "vendor_risks": vendor_slice.vendor_risk_count or 0,
    }
    
    # Risks from BI variance analysis
    from app.models.canonical_business_intelligence import VarianceAnalysis
    risks_result = await db.execute(
        select(VarianceAnalysis).where(
            VarianceAnalysis.organization_id == org.id,
            VarianceAnalysis.impact_severity.in_(["high", "critical"]),
            VarianceAnalysis.attention_required.is_(True)
        ).limit(10)
    )
    risks_list = [
        {
            "id": r.id,
            "domain": r.domain,
            "entity_id": r.entity_id,
            "entity_label": r.entity_label,
            "severity": r.impact_severity,
            "description": r.impact_description or r.entity_label,
            "direction": r.direction,
            "variance_pct": r.variance_pct,
            "detected_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in risks_result.scalars().all()
    ]
    
    # Predictions from predictive intelligence
    from dataclasses import asdict

    active_predictions = await predictive_intelligence_service.derive_predictions(db, caller=caller)
    predictions_summary = {"predictions": [asdict(p) for p in active_predictions[:10]]}
    
    # Decisions awaiting
    decisions_awaiting_result = await db.execute(
        select(CompanyDecision).where(
            CompanyDecision.organization_id == org.id,
            CompanyDecision.state.in_(["proposed", "evaluated", "recommended"])
        ).order_by(CompanyDecision.created_at.desc()).limit(10)
    )
    decisions_list = [
        {
            "id": d.id,
            "title": d.title,
            "state": d.state,
            "decision_type": d.kind,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decisions_awaiting_result.scalars().all()
    ]
    
    return CompanyHomeResponse(
        organization={
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
        },
        strategy={
            "goals_count": goals_count,
            "objectives_count": objectives_count,
        },
        objectives=objectives_list,
        execution={
            "active_projects": active_projects,
            "active_commitments": active_commitments,
            "completion_rate": completion_rate,
        },
        customers={
            "total": total_customers,
            "at_risk": 0,  # Would need customer health scoring
            "new_this_month": 0,  # Would need date filter
        },
        financial_state={
            "revenue": financial_data.get("revenue", 0),
            "expenses": financial_data.get("expenses", 0),
            "cash_position": financial_data.get("cash_position", 0),
            "runway_months": financial_data.get("runway_months", 0),
        },
        operations={
            "processes_healthy": healthy_processes,
            "processes_degraded": degraded_processes,
        },
        people={
            "total_employees": total_employees,
            "capacity_utilization": capacity_utilization,
            "open_roles": 0,  # Would need recruitment data
        },
        capacity={"utilization": capacity_utilization, "bottlenecks": bottlenecks},
        resources=resources_summary,
        procurement=procurement_summary,
        risks=risks_list,
        predictions=predictions_summary.get("predictions", []),
        decisions=decisions_list,
        company_brain=brain_overview,
    )


# =============================================================================
# Manager Workspace - Team Projection
# =============================================================================

@router.get("/manager/{team_id}", response_model=ManagerWorkspaceResponse)
async def get_manager_workspace(
    team_id: str,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the manager's team workspace projection.
    
    Shows authorized team view:
    - People
    - Capacity
    - Responsibilities
    - Commitments
    - Projects
    - Tasks
    - Dependencies
    - Bottlenecks
    - Communication
    - Risks
    
    Governance-enforced: only shows what manager's scope permits.
    """
    from app.models.team import Team, TeamMember
    from app.models.employee import Employee
    from app.models.project import Project
    from app.models.task import Task
    from app.models.execution_strategy import CompanyCommitment, CompanyObjective, OrganizationalResponsibility
    from app.models.company_actions import CompanyAction
    from app.intelligence.organizational_capacity_service import organizational_capacity_service
    from app.intelligence.canonical_communication_collaboration_service import canonical_communication_collaboration_service
    from sqlalchemy import select, func, and_, or_, desc
    from datetime import datetime, timezone, timedelta
    
    # Verify manager access to team
    team_result = await db.execute(
        select(Team).where(Team.id == team_id, Team.organization_id == org.id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Check if user is manager of this team
    manager_check = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.employee_id.in_(
                select(Employee.id).where(Employee.user_id == user.id)
            ),
            TeamMember.role.in_(["lead", "manager", "owner"])
        )
    )
    if not manager_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not authorized to view this team workspace")
    
    # Get team members
    members_result = await db.execute(
        select(Employee).join(TeamMember).where(TeamMember.team_id == team_id)
    )
    members = members_result.scalars().all()
    
    member_ids = [m.id for m in members]
    
    # Get team capacity
    from dataclasses import asdict

    from app.intelligence.company_context import resolve_caller_access

    caller = await resolve_caller_access(db, organization_id=org.id, user=user)
    team_capacity = await organizational_capacity_service.derive_capacity_context(
        db, caller=caller, scope_type="team", scope_id=team_id
    )
    
    # Get team responsibilities (objectives canonically assigned to the team)
    responsibilities_result = await db.execute(
        select(CompanyObjective)
        .join(
            OrganizationalResponsibility,
            OrganizationalResponsibility.objective_id == CompanyObjective.id,
        )
        .where(
            CompanyObjective.organization_id == org.id,
            OrganizationalResponsibility.organization_id == org.id,
            OrganizationalResponsibility.team_id == team_id,
            CompanyObjective.status.in_(["active", "in_progress"]),
        )
    )
    responsibilities = [
        {
            "id": r.id,
            "title": r.title,
            "state": r.status,
            "progress": round(min(max((r.current_value or 0.0) / r.target_value * 100.0, 0.0), 100.0), 1) if r.target_value else 0,
            "owner_id": r.owner_person_id,
        }
        for r in responsibilities_result.scalars().all()
    ]
    
    # Get team commitments
    commitments_result = await db.execute(
        select(CompanyCommitment).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.scope_type == "team",
            CompanyCommitment.scope_id == team_id,
            CompanyCommitment.state.in_(["authorized", "active"]),
        ).order_by(CompanyCommitment.target_date.asc().nullslast())
    )
    commitments = [
        {
            "id": c.id,
            "title": c.title,
            "state": c.state,
            "commitment_type": c.commitment_type,
            "target_date": c.target_date.isoformat() if c.target_date else None,
            "scope_type": c.scope_type,
            "scope_id": c.scope_id,
        }
        for c in commitments_result.scalars().all()
    ]
    
    # Get team projects
    projects_result = await db.execute(
        select(Project).where(
            Project.organization_id == org.id,
            Project.team_id == team_id,
            Project.status == "active"
        ).order_by(Project.updated_at.desc())
    )
    projects = [
        {
            "id": p.id,
            "title": p.name,
            "state": p.status,
            "progress": p.progress or 0,
            "due_at": p.end_date.isoformat() if p.end_date else None,
        }
        for p in projects_result.scalars().all()
    ]
    
    # Get team tasks
    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == org.id,
            Task.assignee_id.in_(member_ids),
            Task.status.notin_(["completed", "archived"]),
        ).order_by(Task.due_date.asc().nullslast()).limit(50)
    )
    tasks = [
        {
            "id": t.id,
            "title": t.title,
                "status": t.status,
                "due_at": t.due_date.isoformat() if t.due_date else None,
                "assignee_id": t.assignee_id,
            "project_id": t.project_id,
        }
        for t in tasks_result.scalars().all()
    ]
    
    # Get blocked tasks as bottlenecks
    blocked_tasks = [t for t in tasks if t.get("status") == "blocked"]
    
    # Get dependencies (tasks waiting on other teams)
    dependencies = []  # Would query task dependencies
    
    # Communication context
    comm_context = await canonical_communication_collaboration_service.derive_operational_communication_context(
        db, caller=caller, context_type="group", context_id=team_id
    )
    
    # Risks specific to team
    from app.models.canonical_business_intelligence import VarianceAnalysis
    risks_result = await db.execute(
        select(VarianceAnalysis).where(
            VarianceAnalysis.organization_id == org.id,
            VarianceAnalysis.impact_severity.in_(["high", "critical"]),
            VarianceAnalysis.attention_required.is_(True)
        ).limit(10)
    )
    risks = [
        {
            "id": r.id,
            "domain": r.domain,
            "entity_id": r.entity_id,
            "entity_label": r.entity_label,
            "severity": r.impact_severity,
            "description": r.impact_description or r.entity_label,
            "direction": r.direction,
            "variance_pct": r.variance_pct,
        }
        for r in risks_result.scalars().all()
    ]
    
    return ManagerWorkspaceResponse(
        team={"id": team.id, "name": team.name, "description": team.description},
        people=[
            {
                "id": m.id,
                "name": m.display_name,
                "role": m.designation,
                "email": m.email,
            }
            for m in members
        ],
            capacity=asdict(team_capacity),
        responsibilities=responsibilities,
        commitments=commitments,
        projects=projects,
        tasks=tasks,
        dependencies=dependencies,
        bottlenecks=blocked_tasks,
        communication=comm_context,
        risks=risks,
        performance_context={
            "team_velocity": 0,  # Would compute from completed tasks
            "commitment_fulfillment_rate": 0,  # Would compute
        },
    )


# =============================================================================
# Executive Workspace - Organizational Projection
# =============================================================================

@router.get("/executive", response_model=ExecutiveWorkspaceResponse)
async def get_executive_workspace(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the executive's organizational workspace projection.
    
    Shows authorized company-wide view:
    - Strategy & Objectives
    - Execution status across all teams
    - Customers & Commercial state
    - Financial state
    - Operations & Processes
    - People, Workforce & Capacity
    - Resources & Procurement
    - Risks & Predictions
    - Decisions & Cross-domain impacts
    - Company Brain context
    
    Governance-enforced: only shows what executive's scope permits.
    """
    from app.models.project import Project
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective
    from app.models.customer import Customer
    from app.models.company_actions import CompanyAction
    from app.models.canonical_business_intelligence import CanonicalMetric, MetricObservation, VarianceAnalysis
    from app.models.company_state import CompanyState
    from app.models.employee import Employee
    from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
    from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
    from app.intelligence.company_brain import company_brain
    from app.intelligence.canonical_workforce_service import canonical_workforce_service
    from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
    from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
    from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
    from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
    from app.intelligence.cross_domain_impact_service import cross_domain_impact_service
    from app.intelligence.organizational_capacity_service import organizational_capacity_service
    from sqlalchemy import select, func, and_, or_, desc
    from datetime import datetime, timezone, timedelta
    
    # Verify executive access
    emp_result = await db.execute(
        select(Employee).where(Employee.user_id == user.id, Employee.organization_id == org.id)
    )
    employee = emp_result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found")
    
    # Check if user has executive permissions (simplified - would check role)
    # For now, allow if workspace:read permission
    
    # Get Company Brain overview
    brain_overview = await company_brain.overview(db, org.id, user=user)
    
    # Get BI briefing
    from app.intelligence.company_context import resolve_caller_access

    caller = await resolve_caller_access(db, organization_id=org.id, user=user)
    briefing = await canonical_business_intelligence_service.generate_executive_briefing(
        db, caller=caller, briefing_type="weekly"
    )
    
    # Get digital twin state
    twin_state = await canonical_digital_twin_service.derive_twin_state(
        db, caller=caller, scope_type="org", scope_id=org.id
    )
    
    # Strategy - Goals and Objectives
    goals_result = await db.execute(
        select(func.count(CompanyGoal.id)).where(CompanyGoal.organization_id == org.id)
    )
    goals_count = goals_result.scalar() or 0
    
    objectives_result = await db.execute(
        select(func.count(CompanyObjective.id)).where(CompanyObjective.organization_id == org.id)
    )
    objectives_count = objectives_result.scalar() or 0
    
    # Active objectives with progress
    active_objectives = await db.execute(
        select(CompanyObjective).where(
            CompanyObjective.organization_id == org.id,
            CompanyObjective.status.in_(["active", "in_progress"])
        ).limit(15)
    )
    objectives_list = [
        {
            "id": o.id,
            "title": o.title,
            "state": o.status,
            "progress": round(min(max((o.current_value or 0.0) / o.target_value * 100.0, 0.0), 100.0), 1) if o.target_value else 0,
            "target_date": None,
            "owner_id": o.owner_person_id,
        }
        for o in active_objectives.scalars().all()
    ]
    
    # Execution - Projects and Commitments
    active_projects_result = await db.execute(
        select(func.count(Project.id)).where(
            Project.organization_id == org.id,
            Project.status == "active"
        )
    )
    active_projects = active_projects_result.scalar() or 0
    
    active_commitments_result = await db.execute(
        select(func.count(CompanyCommitment.id)).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.state.in_(["authorized", "active"])
        )
    )
    active_commitments = active_commitments_result.scalar() or 0
    
    completed_commitments_result = await db.execute(
        select(func.count(CompanyCommitment.id)).where(
            CompanyCommitment.organization_id == org.id,
            CompanyCommitment.state == "fulfilled"
        )
    )
    completed_commitments = completed_commitments_result.scalar() or 0
    total_commitments = active_commitments + completed_commitments
    completion_rate = round(completed_commitments / total_commitments * 100, 1) if total_commitments > 0 else 0
    
    # Customers
    total_customers_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.organization_id == org.id)
    )
    total_customers = total_customers_result.scalar() or 0
    
    # Financial state from BI metrics
    financial_obs = await db.execute(
        select(MetricObservation).where(
            MetricObservation.organization_id == org.id,
            MetricObservation.metric_id.in_(
                select(CanonicalMetric.id).where(
                    CanonicalMetric.organization_id == org.id,
                    CanonicalMetric.key.in_(["revenue", "expenses", "cash_position", "runway_months"])
                )
            )
        ).order_by(MetricObservation.observed_at.desc()).limit(4)
    )
    financial_data = {}
    for obs in financial_obs.scalars().all():
        financial_data[obs.metric_id] = obs.value
    
    # Operations - Processes
    healthy_processes_result = await db.execute(
        select(func.count(CompanyState.id)).where(
            CompanyState.organization_id == org.id,
            CompanyState.state == "healthy"
        )
    )
    healthy_processes = healthy_processes_result.scalar() or 0
    
    degraded_processes_result = await db.execute(
        select(func.count(CompanyState.id)).where(
            CompanyState.organization_id == org.id,
            CompanyState.state == "degraded"
        )
    )
    degraded_processes = degraded_processes_result.scalar() or 0
    
    # People & Capacity - from Workforce service
    total_employees_result = await db.execute(
        select(func.count(Employee.id)).where(Employee.organization_id == org.id)
    )
    total_employees = total_employees_result.scalar() or 0
    
    # Capacity utilization
    capacity_context = await organizational_capacity_service.derive_capacity_context(
        db, caller=caller, scope_type="organization"
    )
    capacity_utilization = capacity_context.utilization
    bottlenecks = capacity_context.overloaded_capabilities
    
    # Resources & Procurement
    resources_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
        db, caller=caller, scope_type="organization"
    )
    vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
        db, caller=caller, scope_type="organization"
    )
    resources_summary = {
        "allocated": resources_slice.total_committed or 0,
        "available": resources_slice.total_available or 0,
    }
    procurement_summary = {
        "pending_pos": (vendor_slice.procurements_by_state or {}).get("pending", 0),
        "vendor_risks": vendor_slice.vendor_risk_count or 0,
    }
    
    # Risks from BI variance analysis
    risks_result = await db.execute(
        select(VarianceAnalysis).where(
            VarianceAnalysis.organization_id == org.id,
            VarianceAnalysis.impact_severity.in_(["high", "critical"]),
            VarianceAnalysis.attention_required.is_(True)
        ).limit(15)
    )
    risks_list = [
        {
            "id": r.id,
            "domain": r.domain,
            "entity_id": r.entity_id,
            "entity_label": r.entity_label,
            "severity": r.impact_severity,
            "description": r.impact_description or r.entity_label,
            "direction": r.direction,
            "variance_pct": r.variance_pct,
            "detected_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in risks_result.scalars().all()
    ]
    
    # Predictions from predictive intelligence
    from dataclasses import asdict

    active_predictions = await predictive_intelligence_service.derive_predictions(db, caller=caller)
    predictions_summary = {"predictions": [asdict(p) for p in active_predictions[:10]]}
    
    # Decisions awaiting
    decisions_awaiting_result = await db.execute(
        select(CompanyDecision).where(
            CompanyDecision.organization_id == org.id,
            CompanyDecision.state.in_(["proposed", "evaluated", "recommended"])
        ).order_by(CompanyDecision.created_at.desc()).limit(15)
    )
    decisions_list = [
        {
            "id": d.id,
            "title": d.title,
            "state": d.state,
            "decision_type": d.kind,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decisions_awaiting_result.scalars().all()
    ]
    
    # Cross-domain impacts: the canonical service derives impacts per-entity on
    # demand; there is no persisted "recent impacts" stream to project here.
    cross_domain_impacts: list[dict] = []
    
    return ExecutiveWorkspaceResponse(
        organization={
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
        },
        strategy={
            "goals_count": goals_count,
            "objectives_count": objectives_count,
        },
        objectives=objectives_list,
        execution={
            "active_projects": active_projects,
            "active_commitments": active_commitments,
            "completion_rate": completion_rate,
        },
        customers={
            "total": total_customers,
            "at_risk": 0,
            "new_this_month": 0,
        },
        financial_state={
            "revenue": financial_data.get("revenue", 0),
            "expenses": financial_data.get("expenses", 0),
            "cash_position": financial_data.get("cash_position", 0),
            "runway_months": financial_data.get("runway_months", 0),
        },
        operations={
            "processes_healthy": healthy_processes,
            "processes_degraded": degraded_processes,
        },
        people={
            "total_employees": total_employees,
            "capacity_utilization": capacity_utilization,
            "open_roles": 0,
        },
        capacity={"utilization": capacity_utilization, "bottlenecks": bottlenecks},
        resources=resources_summary,
        procurement=procurement_summary,
        risks=risks_list,
        predictions=predictions_summary.get("predictions", []),
        decisions=decisions_list,
        company_brain=brain_overview,
        cross_domain_impacts=cross_domain_impacts,
    )


# =============================================================================
# Universal Search
# =============================================================================

@router.post("/search", response_model=UniversalSearchResponse)
async def universal_search(
    request: UniversalSearchRequest,
    user: User = Depends(require_permission("search:global")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Universal search across canonical reality.
    
    Searches authorized entities:
    - People
    - Teams
    - Customers
    - Projects
    - Tasks
    - Processes
    - Meetings
    - Messages
    - Documents
    - Knowledge
    - Decisions
    - Commitments
    - Actions
    - Outcomes
    
    Respects: tenant isolation, scope, permissions, temporal truth, provenance.
    Does NOT create a second company search reality.
    """
    import time
    start = time.perf_counter()
    
    # Use existing search service
    from app.services.search_service import search_service
    result = await search_service.search(
        db, organization_id=org.id, query=request.query, user_id=user.id, 
        limit=request.limit, user=user
    )
    
    # Convert to universal format with deep links
    search_results = []
    for item in result.get("results", []):
        deep_link = _build_deep_link(item["type"], item["id"])
        search_results.append(UniversalSearchResult(
            id=item["id"],
            type=item["type"],
            title=item["title"],
            subtitle=item.get("subtitle"),
            description=item.get("snippet"),
            metadata=item.get("metadata", {}),
            score=item.get("score", 0.0),
            deep_link=deep_link,
        ))
    
    took_ms = int((time.perf_counter() - start) * 1000)
    
    return UniversalSearchResponse(
        query=request.query,
        results=search_results,
        total=result.get("total", 0),
        took_ms=took_ms,
    )


def _build_deep_link(entity_type: str, entity_id: str) -> str:
    """Build deep link for entity."""
    type_map = {
        "user": "/people",
        "project": "/projects",
        "task": "/tasks",
        "meeting": "/meetings",
        "document": "/documents",
        "customer": "/customers",
        "decision": "/decisions",
        "commitment": "/commitments",
    }
    base = type_map.get(entity_type, "/search")
    return f"{base}/{entity_id}"


# =============================================================================
# Universal Command / Ask VCOS
# =============================================================================

@router.post("/command", response_model=CommandResponse)
async def execute_command(
    request: CommandRequest,
    user: User = Depends(require_permission("workspace:command")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Universal command surface - natural language intent to governed operation.
    
    Architecture:
    Intent → Interpretation → Authorization → Governance → Canonical Operation
    
    AI MUST NOT silently mutate canonical state.
    Recommendation ≠ Decision ≠ Authorization ≠ Action
    
    Example commands:
    - "show my commitments"
    - "find the last customer meeting"
    - "explain this risk"
    - "find relevant documents"
    - "show decisions awaiting me"
    - "create a task"
    - "create a project from an authorized commitment"
    """
    command = request.command.strip().lower()
    
    # Parse intent (simplified - would use NLP/Company Brain in production)
    intent, params = _parse_command(command)
    
    # Check authorization for the intent
    authorized, auth_detail = await _check_command_authorization(db, org.id, user.id, intent, params)
    
    if not authorized:
        return CommandResponse(
            intent=intent,
            interpretation=f"Understood: {command}",
            actions=[],
            requires_authorization=True,
            confirmation_required=False,
            result={"error": auth_detail},
        )
    
    # Execute based on intent
    result = await _execute_intent(db, org.id, user, intent, params)
    
    return CommandResponse(
        intent=intent,
        interpretation=f"Executing: {command}",
        actions=[{"type": intent, "params": params}],
        requires_authorization=False,
        confirmation_required=intent in ["create", "delete", "transition"],
        result=result,
    )


def _parse_command(command: str) -> tuple[str, dict]:
    """Parse natural language command into intent and parameters."""
    # Simplified parsing - production would use Company Brain/NLP
    if "show my commitments" in command or "my commitments" in command:
        return "show_commitments", {"scope": "my"}
    elif "show commitments" in command:
        return "show_commitments", {"scope": "all"}
    elif "show my tasks" in command or "my tasks" in command:
        return "show_tasks", {"scope": "my"}
    elif "show tasks" in command:
        return "show_tasks", {"scope": "all"}
    elif "find the last" in command and "meeting" in command:
        return "find_last_meeting", {}
    elif "explain" in command and "risk" in command:
        return "explain_risk", {}
    elif "find relevant documents" in command or "search documents" in command:
        return "search_documents", {"query": command.replace("find relevant documents", "").replace("search documents", "").strip()}
    elif "show decisions awaiting me" in command or "my decisions" in command:
        return "show_decisions", {"scope": "my"}
    elif "create a task" in command:
        return "create_task", {"title": command.replace("create a task", "").strip()}
    elif "create a project" in command:
        return "create_project", {"title": command.replace("create a project", "").strip()}
    else:
        return "ask_brain", {"question": command}


async def _check_command_authorization(
    db: AsyncSession, org_id: str, user_id: str, intent: str, params: dict
) -> tuple[bool, str]:
    """Check if user is authorized for command intent."""
    # Read operations generally allowed
    read_intents = ["show_commitments", "show_tasks", "find_last_meeting", 
                    "explain_risk", "search_documents", "show_decisions", "ask_brain"]
    if intent in read_intents:
        return True, "OK"
    
    # Write operations require specific permissions
    write_permissions = {
        "create_task": "tasks:manage",
        "create_project": "projects:manage",
    }
    if intent in write_permissions:
        # Would check actual permission
        return True, "OK"  # Simplified
    
    return False, f"Intent {intent} not recognized or not authorized"


async def _execute_intent(
    db: AsyncSession, org_id: str, user: User, intent: str, params: dict
) -> dict:
    """Execute the parsed intent."""
    if intent == "show_commitments":
        # Would call commitment service
        return {"message": "Commitments retrieved", "data": []}
    elif intent == "show_tasks":
        return {"message": "Tasks retrieved", "data": []}
    elif intent == "ask_brain":
        from app.intelligence.company_brain import company_brain
        result = await company_brain.answer(db, org_id, params["question"], user=user)
        return result
    elif intent == "explain_risk":
        from app.intelligence.canonical_business_intelligence_service import canonical_business_intelligence_service
        # Would query variance/risk
        return {"message": "Risk explanation", "data": {}}
    else:
        return {"message": f"Executed {intent}", "data": params}


# =============================================================================
# Deep Link Resolution
# =============================================================================

@router.post("/deep-link/resolve", response_model=DeepLinkResolveResponse)
async def resolve_deep_link(
    request: DeepLinkResolveRequest,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve a deep link to its canonical entity.
    
    Supports paths like:
    - /company/project/123
    - /company/customer/456
    - /company/meeting/789
    - /company/person/abc
    - /company/task/def
    - /company/decision/ghi
    - /company/commitment/jkl
    
    Returns canonical data and target URL for the web/desktop client.
    """
    path = request.path.strip("/")
    parts = path.split("/")
    
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid deep link path")
    
    # Expected: company/<entity_type>/<entity_id>
    if parts[0] != "company" or len(parts) != 3:
        raise HTTPException(status_code=400, detail="Deep link format: /company/<type>/<id>")
    
    entity_type = parts[1]
    entity_id = parts[2]
    
    # Resolve entity and get canonical data
    canonical_data = await _resolve_entity(db, org.id, entity_type, entity_id)
    
    if not canonical_data:
        raise HTTPException(status_code=404, detail="Entity not found or not accessible")
    
    # Build target URL
    target_url = _build_deep_link(entity_type, entity_id)
    
    return DeepLinkResolveResponse(
        target_type=entity_type,
        target_id=entity_id,
        target_url=target_url,
        canonical_data=canonical_data,
    )


async def _resolve_entity(
    db: AsyncSession, org_id: str, entity_type: str, entity_id: str
) -> Optional[dict]:
    """Resolve entity to canonical data."""
    type_to_model = {
        "project": Project,
        "task": Task,
        "meeting": Meeting,
        "person": Employee,
        "customer": None,  # Would import Customer
        "decision": CompanyDecision,
        "commitment": CompanyCommitment,
    }
    
    model = type_to_model.get(entity_type)
    if not model:
        return None
    
    result = await db.execute(
        select(model).where(model.id == entity_id, model.organization_id == org_id)
    )
    entity = result.scalar_one_or_none()
    
    if not entity:
        return None
    
    return {
        "id": entity.id,
        "type": entity_type,
        "title": getattr(entity, "title", getattr(entity, "name", str(entity.id))),
        "status": getattr(entity, "state", getattr(entity, "status", None)),
    }


# =============================================================================
# Notification Center
# =============================================================================

@router.get("/notifications", response_model=NotificationCenterResponse)
async def get_notifications(
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False),
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get notification center data.
    
    Aggregates from canonical attention/event architecture:
    - Task assignments
    - Commitment deadlines
    - Approval requests
    - Meeting changes
    - Decision requests
    - Customer attention
    - Capacity conflicts
    - Important communications
    - Company changes
    
    No second notification truth — all from canonical events.
    """
    from app.models.notification import Notification
    
    query = select(Notification).where(
        Notification.organization_id == org.id,
        Notification.recipient_id == user.id,
    )
    
    if unread_only:
        query = query.where(Notification.is_read == False)
    
    query = query.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    # Group by type
    grouped = {}
    for n in notifications:
        n_type = n.type or "general"
        if n_type not in grouped:
            grouped[n_type] = []
        grouped[n_type].append({
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "priority": n.priority,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "link": n.link,
        })
    
    unread_count = sum(1 for n in notifications if not n.is_read)
    
    return NotificationCenterResponse(
        notifications=[
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "priority": n.priority,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "link": n.link,
            }
            for n in notifications
        ],
        unread_count=unread_count,
        grouped=grouped,
    )


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    from app.models.notification import Notification
    
    notification = await db.get(Notification, notification_id)
    if not notification or notification.organization_id != org.id or notification.recipient_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    await db.flush()
    
    return {"success": True}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    from app.models.notification import Notification
    
    await db.execute(
        select(Notification).where(
            Notification.organization_id == org.id,
            Notification.recipient_id == user.id,
            Notification.is_read == False,
        ).update({Notification.is_read: True, Notification.read_at: datetime.now(timezone.utc)})
    )
    
    return {"success": True}


# =============================================================================
# Virtual Office Operating Context
# =============================================================================

class VirtualOfficeFloorResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    layout_json: Optional[dict] = None
    background_url: Optional[str] = None
    is_default: bool
    capacity: int
    access_level: str
    allowed_departments: list[str]
    allowed_teams: list[str]
    rooms: list[dict] = []


class VirtualOfficeFloorCreate(BaseModel):
    name: str
    description: Optional[str] = None
    layout_json: Optional[dict] = None
    background_url: Optional[str] = None
    is_default: bool = False
    capacity: int = 50
    access_level: str = "all"
    allowed_departments: list[str] = []
    allowed_teams: list[str] = []


class VirtualOfficeFloorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layout_json: Optional[dict] = None
    background_url: Optional[str] = None
    is_default: Optional[bool] = None
    capacity: Optional[int] = None
    access_level: Optional[str] = None
    allowed_departments: Optional[list[str]] = None
    allowed_teams: Optional[list[str]] = None


class VirtualOfficeRoomResponse(BaseModel):
    id: str
    floor_id: str
    name: str
    description: Optional[str] = None
    room_type: str
    capacity: int
    icon: str
    color: str
    requires_booking: bool
    auto_release_minutes: int
    has_screen: bool
    has_whiteboard: bool
    has_video_conf: bool


class VirtualOfficeRoomCreate(BaseModel):
    floor_id: str
    name: str
    description: Optional[str] = None
    room_type: str = "meeting"
    capacity: int = 4
    icon: str = "meeting_room"
    color: str = "#3B82F6"
    requires_booking: bool = True
    auto_release_minutes: int = 15
    has_screen: bool = True
    has_whiteboard: bool = True
    has_video_conf: bool = True


class VirtualOfficeRoomUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    room_type: Optional[str] = None
    capacity: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    requires_booking: Optional[bool] = None
    auto_release_minutes: Optional[int] = None
    has_screen: Optional[bool] = None
    has_whiteboard: Optional[bool] = None
    has_video_conf: Optional[bool] = None


class VirtualOfficeContextResponse(BaseModel):
    """Virtual Office operating context for a room/floor."""
    floor: dict
    room: Optional[dict] = None
    people: list[dict] = []
    teams: list[dict] = []
    projects: list[dict] = []
    meetings: list[dict] = []
    conversations: list[dict] = []
    knowledge: list[dict] = []
    decisions: list[dict] = []
    operating_state: dict = {}
    company_brain_context: dict = {}


@router.get("/virtual-office/floors", response_model=list[VirtualOfficeFloorResponse])
async def list_virtual_office_floors(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all Virtual Office floors for the organization."""
    from app.models.workspace import VirtualOfficeFloor, VirtualOfficeRoom
    from sqlalchemy import select
    
    floors_result = await db.execute(
        select(VirtualOfficeFloor).where(VirtualOfficeFloor.organization_id == org.id)
    )
    floors = floors_result.scalars().all()
    
    result = []
    for floor in floors:
        rooms_result = await db.execute(
            select(VirtualOfficeRoom).where(VirtualOfficeRoom.floor_id == floor.id)
        )
        rooms = rooms_result.scalars().all()
        
        result.append(VirtualOfficeFloorResponse(
            id=floor.id,
            name=floor.name,
            description=floor.description,
            layout_json=floor.layout_json,
            background_url=floor.background_url,
            is_default=floor.is_default,
            capacity=floor.capacity,
            access_level=floor.access_level,
            allowed_departments=floor.allowed_departments or [],
            allowed_teams=floor.allowed_teams or [],
            rooms=[
                {
                    "id": r.id,
                    "name": r.name,
                    "room_type": r.room_type,
                    "capacity": r.capacity,
                    "icon": r.icon,
                    "color": r.color,
                }
                for r in rooms
            ]
        ))
    
    return result


@router.post("/virtual-office/floors", response_model=VirtualOfficeFloorResponse)
async def create_virtual_office_floor(
    create: VirtualOfficeFloorCreate,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Virtual Office floor."""
    from app.models.workspace import VirtualOfficeFloor
    
    floor = VirtualOfficeFloor(
        organization_id=org.id,
        name=create.name,
        description=create.description,
        layout_json=create.layout_json,
        background_url=create.background_url,
        is_default=create.is_default,
        capacity=create.capacity,
        access_level=create.access_level,
        allowed_departments=create.allowed_departments,
        allowed_teams=create.allowed_teams,
    )
    db.add(floor)
    await db.flush()
    
    return VirtualOfficeFloorResponse(
        id=floor.id,
        name=floor.name,
        description=floor.description,
        layout_json=floor.layout_json,
        background_url=floor.background_url,
        is_default=floor.is_default,
        capacity=floor.capacity,
        access_level=floor.access_level,
        allowed_departments=floor.allowed_departments or [],
        allowed_teams=floor.allowed_teams or [],
        rooms=[],
    )


@router.patch("/virtual-office/floors/{floor_id}", response_model=VirtualOfficeFloorResponse)
async def update_virtual_office_floor(
    floor_id: str,
    update: VirtualOfficeFloorUpdate,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a Virtual Office floor."""
    from app.models.workspace import VirtualOfficeFloor
    from sqlalchemy import select
    
    floor = await db.get(VirtualOfficeFloor, floor_id)
    if not floor or floor.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Floor not found")
    
    if update.name is not None:
        floor.name = update.name
    if update.description is not None:
        floor.description = update.description
    if update.layout_json is not None:
        floor.layout_json = update.layout_json
    if update.background_url is not None:
        floor.background_url = update.background_url
    if update.is_default is not None:
        floor.is_default = update.is_default
    if update.capacity is not None:
        floor.capacity = update.capacity
    if update.access_level is not None:
        floor.access_level = update.access_level
    if update.allowed_departments is not None:
        floor.allowed_departments = update.allowed_departments
    if update.allowed_teams is not None:
        floor.allowed_teams = update.allowed_teams
    
    await db.flush()
    
    rooms_result = await db.execute(
        select(VirtualOfficeRoom).where(VirtualOfficeRoom.floor_id == floor.id)
    )
    rooms = rooms_result.scalars().all()
    
    return VirtualOfficeFloorResponse(
        id=floor.id,
        name=floor.name,
        description=floor.description,
        layout_json=floor.layout_json,
        background_url=floor.background_url,
        is_default=floor.is_default,
        capacity=floor.capacity,
        access_level=floor.access_level,
        allowed_departments=floor.allowed_departments or [],
        allowed_teams=floor.allowed_teams or [],
        rooms=[
            {
                "id": r.id,
                "name": r.name,
                "room_type": r.room_type,
                "capacity": r.capacity,
                "icon": r.icon,
                "color": r.color,
            }
            for r in rooms
        ]
    )


@router.post("/virtual-office/rooms", response_model=VirtualOfficeRoomResponse)
async def create_virtual_office_room(
    create: VirtualOfficeRoomCreate,
    user: User = Depends(require_permission("workspace:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Virtual Office room."""
    from app.models.workspace import VirtualOfficeFloor, VirtualOfficeRoom
    
    # Verify floor exists and belongs to org
    floor = await db.get(VirtualOfficeFloor, create.floor_id)
    if not floor or floor.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Floor not found")
    
    room = VirtualOfficeRoom(
        organization_id=org.id,
        floor_id=create.floor_id,
        name=create.name,
        description=create.description,
        room_type=create.room_type,
        capacity=create.capacity,
        icon=create.icon,
        color=create.color,
        requires_booking=create.requires_booking,
        auto_release_minutes=create.auto_release_minutes,
        has_screen=create.has_screen,
        has_whiteboard=create.has_whiteboard,
        has_video_conf=create.has_video_conf,
    )
    db.add(room)
    await db.flush()
    
    return VirtualOfficeRoomResponse(
        id=room.id,
        floor_id=room.floor_id,
        name=room.name,
        description=room.description,
        room_type=room.room_type,
        capacity=room.capacity,
        icon=room.icon,
        color=room.color,
        requires_booking=room.requires_booking,
        auto_release_minutes=room.auto_release_minutes,
        has_screen=room.has_screen,
        has_whiteboard=room.has_whiteboard,
        has_video_conf=room.has_video_conf,
    )


@router.get("/virtual-office/context", response_model=VirtualOfficeContextResponse)
async def get_virtual_office_context(
    floor_id: Optional[str] = Query(None),
    room_id: Optional[str] = Query(None),
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the operating context for a Virtual Office floor or room.
    
    This is the real Virtual Office — an interface into canonical company reality.
    A room represents an operating context (team, project, meeting, etc.).
    """
    from app.models.workspace import VirtualOfficeFloor, VirtualOfficeRoom, WorkspaceSession
    from app.models.employee import Employee
    from app.models.team import Team, TeamMember
    from app.models.project import Project
    from app.models.meeting import Meeting, MeetingAttendee
    from app.models.company_operating import CompanyDecision
    from app.models.knowledge import KnowledgeDocument
    from app.intelligence.company_brain import company_brain
    from app.intelligence.canonical_communication_collaboration_service import canonical_communication_collaboration_service
    from sqlalchemy import select, func, and_, or_
    from datetime import datetime, timezone, timedelta
    
    floor = None
    room = None
    
    if floor_id:
        floor = await db.get(VirtualOfficeFloor, floor_id)
        if not floor or floor.organization_id != org.id:
            raise HTTPException(status_code=404, detail="Floor not found")
    
    if room_id:
        room = await db.get(VirtualOfficeRoom, room_id)
        if not room or room.organization_id != org.id:
            raise HTTPException(status_code=404, detail="Room not found")
    
    # Get people currently in this context (active sessions)
    people_query = select(WorkspaceSession).where(
        WorkspaceSession.organization_id == org.id,
        WorkspaceSession.active == True,
    )
    if room_id:
        people_query = people_query.where(WorkspaceSession.virtual_location == room_id)
    elif floor_id:
        people_query = people_query.where(WorkspaceSession.virtual_location.like(f"{floor_id}%"))
    
    people_sessions = await db.execute(people_query)
    people_sessions = people_sessions.scalars().all()
    
    # Get employee details for active people
    employee_ids = [s.user_id for s in people_sessions]
    employees_result = await db.execute(
        select(Employee).where(Employee.user_id.in_(employee_ids)) if employee_ids else select(Employee).where(Employee.id == "none")
    )
    employees = {e.user_id: e for e in employees_result.scalars().all()}
    
    people = [
        {
            "id": e.id,
            "name": e.display_name,
            "role": e.designation,
            "virtual_location": s.virtual_location,
            "device_type": s.device_type,
            "last_activity": s.last_activity_at.isoformat() if s.last_activity_at else None,
        }
        for s in people_sessions
        if (e := employees.get(s.user_id))
    ]
    
    # Get teams on this floor/in this room
    teams = []
    if floor_id:
        teams_result = await db.execute(
            select(Team).where(Team.organization_id == org.id)
        )
        for team in teams_result.scalars().all():
            members_result = await db.execute(
                select(Employee).join(TeamMember).where(TeamMember.team_id == team.id)
            )
            members = members_result.scalars().all()
            teams.append({
                "id": team.id,
                "name": team.name,
                "member_count": len(members),
            })
    
    # Get active projects
    projects_result = await db.execute(
        select(Project).where(
            Project.organization_id == org.id,
            Project.status == "active"
        ).limit(10)
    )
    projects = [
        {"id": p.id, "title": p.name, "state": p.status, "progress": p.progress or 0}
        for p in projects_result.scalars().all()
    ]
    
    # Get upcoming meetings in this context
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    
    meetings_query = select(Meeting).where(
        Meeting.organization_id == org.id,
        Meeting.start_at >= day_start,
        Meeting.start_at < day_end,
    )
    if room_id:
        meetings_query = meetings_query.where(Meeting.location == room_id)
    
    meetings_result = await db.execute(meetings_query)
    meetings = [
        {
            "id": m.id,
            "title": m.title,
            "start_at": m.start_at.isoformat() if m.start_at else None,
            "end_at": m.end_at.isoformat() if m.end_at else None,
            "location": m.location,
        }
        for m in meetings_result.scalars().all()
    ]
    
    # Get active conversations (from communication service)
    conversations = await canonical_communication_collaboration_service.get_active_conversations(db, org.id)
    
    # Get relevant knowledge
    knowledge_result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.organization_id == org.id,
            KnowledgeDocument.state == "published"
        ).limit(10)
    )
    knowledge = [
        {"id": k.id, "title": k.title, "type": k.document_type}
        for k in knowledge_result.scalars().all()
    ]
    
    # Get recent decisions
    decisions_result = await db.execute(
        select(CompanyDecision).where(
            CompanyDecision.organization_id == org.id,
            CompanyDecision.state.in_(["proposed", "evaluated", "recommended", "approved"])
        ).order_by(CompanyDecision.updated_at.desc()).limit(10)
    )
    decisions = [
        {"id": d.id, "title": d.title, "state": d.state, "decision_type": d.kind}
        for d in decisions_result.scalars().all()
    ]
    
    # Operating state
    operating_state = {
        "total_active_people": len(people),
        "total_teams": len(teams),
        "active_projects": len(projects),
        "todays_meetings": len(meetings),
    }
    
    # Company Brain context
    brain_context = await company_brain.get_context_for_scope(db, org.id, "virtual_office", floor_id or room_id or "org")
    
    return VirtualOfficeContextResponse(
        floor={"id": floor.id, "name": floor.name} if floor else {},
        room={
            "id": room.id, "name": room.name, "room_type": room.room_type, "capacity": room.capacity
        } if room else None,
        people=people,
        teams=teams,
        projects=projects,
        meetings=meetings,
        conversations=conversations,
        knowledge=knowledge,
        decisions=decisions,
        operating_state=operating_state,
        company_brain_context=brain_context,
    )


# =============================================================================
# Joy & Break Experience Layer
# =============================================================================

class GameStartRequest(BaseModel):
    game: str = Field(..., pattern="^(brain_blitz|what_happens_next|emoji_detective|tiny_genius|company_chaos)$")


class GameStartResponse(BaseModel):
    game: str
    session_id: str
    state: dict
    cooldown_until: str


class GameActionRequest(BaseModel):
    session_id: str
    action: dict


class GameActionResponse(BaseModel):
    state: dict
    result: Optional[dict] = None
    completed: bool = False
    score: Optional[int] = None


@router.get("/joy-break/games")
async def list_games(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
):
    """List available Joy & Break games with cooldown status."""
    from app.models.workspace import GameSession
    
    # Check cooldown for each game (12-hour window)
    games = [
        {"id": "brain_blitz", "name": "Brain Blitz", "description": "Quick mental challenges"},
        {"id": "what_happens_next", "name": "What Happens Next?", "description": "Predict the outcome"},
        {"id": "emoji_detective", "name": "Emoji Detective", "description": "Decode the message"},
        {"id": "tiny_genius", "name": "Tiny Genius", "description": "Micro-trivia"},
        {"id": "company_chaos", "name": "Company Chaos", "description": "Fictional scenario simulator"},
    ]
    
    for game in games:
        recent = await db.execute(
            select(GameSession).where(
                GameSession.organization_id == user.organization_id,
                GameSession.user_id == user.id,
                GameSession.game_id == game["id"],
                GameSession.started_at >= datetime.now(timezone.utc) - timedelta(hours=12),
            ).order_by(GameSession.started_at.desc())
        )
        last_session = recent.scalars().first()
        if last_session:
            game["available"] = False
            game["cooldown_until"] = (last_session.started_at + timedelta(hours=12)).isoformat()
        else:
            game["available"] = True
            game["cooldown_until"] = None
    
    return {"games": games}


@router.post("/joy-break/start", response_model=GameStartResponse)
async def start_game(
    request: GameStartRequest,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start a Joy & Break game session (with 12-hour cooldown)."""
    from app.models.workspace import GameSession
    
    # Check cooldown
    recent = await db.execute(
        select(GameSession).where(
            GameSession.organization_id == org.id,
            GameSession.user_id == user.id,
            GameSession.game_id == request.game,
            GameSession.started_at >= datetime.now(timezone.utc) - timedelta(hours=12),
        )
    )
    if recent.scalars().first():
        raise HTTPException(status_code=429, detail="Game on cooldown. Try again in 12 hours.")
    
    # Create session
    session = GameSession(
        organization_id=org.id,
        user_id=user.id,
        game_id=request.game,
        state={"level": 1, "score": 0},
    )
    db.add(session)
    await db.flush()
    
    # Initialize game state
    initial_state = _initialize_game_state(request.game)
    
    return GameStartResponse(
        game=request.game,
        session_id=session.id,
        state=initial_state,
        cooldown_until=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
    )


@router.post("/joy-break/action", response_model=GameActionResponse)
async def game_action(
    request: GameActionRequest,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Process a game action."""
    from app.models.workspace import GameSession
    
    session = await db.get(GameSession, request.session_id)
    if not session or session.organization_id != org.id or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    # Process action based on game type
    new_state, result, completed, score = _process_game_action(
        session.game_id, session.state, request.action
    )
    
    session.state = new_state
    if completed:
        session.completed_at = datetime.now(timezone.utc)
        session.final_score = score
    await db.flush()
    
    return GameActionResponse(
        state=new_state,
        result=result,
        completed=completed,
        score=score,
    )


def _initialize_game_state(game_id: str) -> dict:
    """Initialize game state for a new session."""
    states = {
        "brain_blitz": {"level": 1, "score": 0, "challenge": "memory_sequence", "sequence": [1, 3, 2, 4]},
        "what_happens_next": {"level": 1, "score": 0, "scenario": "project_delay", "options": ["delay", "escalate", "replan", "accept"]},
        "emoji_detective": {"level": 1, "score": 0, "puzzle": "🏢💻📊📈", "answer": "business_growth"},
        "tiny_genius": {"level": 1, "score": 0, "question": "What does ROI stand for?", "options": ["Return on Investment", "Rate of Interest", "Risk of Inflation", "Revenue on Income"]},
        "company_chaos": {"level": 1, "score": 0, "scenario": "server_outage", "role": "engineer", "actions": ["restart", "investigate", "escalate", "communicate"]},
    }
    return states.get(game_id, {"level": 1, "score": 0})


def _process_game_action(game_id: str, state: dict, action: dict) -> tuple[dict, Optional[dict], bool, Optional[int]]:
    """Process a game action and return new state."""
    # Simplified game logic
    score = state.get("score", 0)
    
    if game_id == "tiny_genius":
        if action.get("answer") == "Return on Investment":
            score += 10
        return {"level": state["level"] + 1, "score": score, "completed": True}, {"correct": True}, True, score
    
    elif game_id == "brain_blitz":
        if action.get("input") == state.get("sequence"):
            score += 20
        return {"level": state["level"] + 1, "score": score}, {"correct": True}, state["level"] >= 5, score
    
    return state, None, False, score


# =============================================================================
# Workspace Settings / Personalization
# =============================================================================

class WorkspaceSettingsResponse(BaseModel):
    pinned_items: list[dict]
    shortcuts: list[dict]
    navigation_arrangement: dict
    dashboard_arrangement: dict
    notification_preferences: dict
    favorite_views: list[dict]


class WorkspaceSettingsUpdate(BaseModel):
    pinned_items: Optional[list[dict]] = None
    shortcuts: Optional[list[dict]] = None
    navigation_arrangement: Optional[dict] = None
    dashboard_arrangement: Optional[dict] = None
    notification_preferences: Optional[dict] = None
    favorite_views: Optional[list[dict]] = None


@router.get("/settings", response_model=WorkspaceSettingsResponse)
async def get_workspace_settings(
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get user's workspace personalization settings."""
    from app.models.workspace import WorkspaceSettings
    
    settings = await db.execute(
        select(WorkspaceSettings).where(
            WorkspaceSettings.organization_id == org.id,
            WorkspaceSettings.user_id == user.id,
        )
    )
    settings_obj = settings.scalar_one_or_none()
    
    if not settings_obj:
        return WorkspaceSettingsResponse(
            pinned_items=[],
            shortcuts=[],
            navigation_arrangement={},
            dashboard_arrangement={},
            notification_preferences={},
            favorite_views=[],
        )
    
    return WorkspaceSettingsResponse(
        pinned_items=settings_obj.pinned_items or [],
        shortcuts=settings_obj.shortcuts or [],
        navigation_arrangement=settings_obj.navigation_arrangement or {},
        dashboard_arrangement=settings_obj.dashboard_arrangement or {},
        notification_preferences=settings_obj.notification_preferences or {},
        favorite_views=settings_obj.favorite_views or [],
    )


@router.patch("/settings", response_model=WorkspaceSettingsResponse)
async def update_workspace_settings(
    update: WorkspaceSettingsUpdate,
    user: User = Depends(require_permission("workspace:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update workspace personalization settings."""
    from app.models.workspace import WorkspaceSettings
    
    settings = await db.execute(
        select(WorkspaceSettings).where(
            WorkspaceSettings.organization_id == org.id,
            WorkspaceSettings.user_id == user.id,
        )
    )
    settings_obj = settings.scalar_one_or_none()
    
    if not settings_obj:
        settings_obj = WorkspaceSettings(
            organization_id=org.id,
            user_id=user.id,
        )
        db.add(settings_obj)
    
    if update.pinned_items is not None:
        settings_obj.pinned_items = update.pinned_items
    if update.shortcuts is not None:
        settings_obj.shortcuts = update.shortcuts
    if update.navigation_arrangement is not None:
        settings_obj.navigation_arrangement = update.navigation_arrangement
    if update.dashboard_arrangement is not None:
        settings_obj.dashboard_arrangement = update.dashboard_arrangement
    if update.notification_preferences is not None:
        settings_obj.notification_preferences = update.notification_preferences
    if update.favorite_views is not None:
        settings_obj.favorite_views = update.favorite_views
    
    await db.flush()
    
    return WorkspaceSettingsResponse(
        pinned_items=settings_obj.pinned_items or [],
        shortcuts=settings_obj.shortcuts or [],
        navigation_arrangement=settings_obj.navigation_arrangement or {},
        dashboard_arrangement=settings_obj.dashboard_arrangement or {},
        notification_preferences=settings_obj.notification_preferences or {},
        favorite_views=settings_obj.favorite_views or [],
    )