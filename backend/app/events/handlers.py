"""Event handlers — react to organizational events by updating intelligence.

Handlers are registered with @on(...). They run inside the event worker
(or on-demand via event_bus.process_pending). Each handler is defensive:
a missing entity simply logs and skips. Handlers never commit — the caller
(EventBus) owns the transaction so a partial failure stays atomic.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.event_models import GRAPH_EVENTS, describe
from app.events.subscriber import on
from app.models.employee import Employee
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.events.handlers")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _resolve_employee(
    db: AsyncSession, organization_id: str, payload: dict[str, Any]
) -> Optional[Employee]:
    for key in ("assignee_id", "owner_id", "author_id", "editor_id", "recipient_id", "actor_id", "employee_id", "approver_id"):
        value = payload.get(key)
        if not value:
            continue
        row = await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id, Employee.id == value
            )
        )
        employee = row.scalar_one_or_none()
        if employee is not None:
            return employee
    return None


def _tokens(*parts: Any) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        text = str(part).lower().replace("_", " ").replace("-", " ")
        tokens.extend(t for t in text.split() if len(t) > 2)
    return tokens


async def _evolve_expertise(
    db: AsyncSession, organization_id: str, event_name: str,
    employee: Employee, tokens: list[str], event_id: Optional[str] = None,
    points: float | None = None,
) -> None:
    from app.intelligence.expertise_engine import expertise_engine

    await expertise_engine.record_activity(
        db, organization_id=organization_id, employee_id=employee.id,
        event_name=event_name, tokens=tokens, reason=describe(event_name),
        event_id=event_id, points=points,
    )


async def _graph_link(
    db: AsyncSession, organization_id: str, event_name: str,
    source_type: str, source_id: str,
    target_type: str, target_id: str,
    evidence: Optional[str] = None,
    relation: Optional[str] = None,
) -> None:
    from app.intelligence.graph_engine import graph_engine

    graph_relation = relation or GRAPH_EVENTS.get(event_name, "related_to")
    await graph_engine.upsert_edge(
        db, organization_id=organization_id,
        source_type=source_type, source_id=source_id,
        target_type=target_type, target_id=target_id,
        relation=graph_relation, evidence=evidence or describe(event_name),
    )


async def _learning_from_event(
    db: AsyncSession, organization_id: str, event: EventRow,
    payload: dict[str, Any], event_type: str, title: str,
    detail: str, lesson: str, entity_type: Optional[str] = None,
    entity_id: Optional[str] = None, tags: Optional[list[str]] = None,
) -> None:
    from app.intelligence.learning_engine import learning_engine

    await learning_engine.record(
        db, organization_id=organization_id, event_type=event_type,
        title=title, detail=detail, lesson=lesson,
        entity_type=entity_type, entity_id=entity_id, tags=tags,
    )


# ---------------------------------------------------------------------------
# work events
# ---------------------------------------------------------------------------


@on("task.created")
async def handle_task_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("assignee_id"):
        await _graph_link(
            db, org_id, "task.created", "employee", payload["assignee_id"],
            "task", payload.get("task_id") or payload.get("id"),
            evidence=f"Assigned task: {payload.get('title', '')[:120]}",
        )


@on("task.completed")
async def handle_task_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        tokens = _tokens(payload.get("title"), payload.get("project_name"), payload.get("tags"))
        await _evolve_expertise(db, org_id, "task.completed", employee, tokens, event.id)
    if payload.get("assignee_id"):
        await _graph_link(
            db, org_id, "task.completed", "employee", payload["assignee_id"],
            "task", payload.get("task_id") or payload.get("id"),
            evidence=f"Completed task: {payload.get('title', '')[:120]}",
        )
    if payload.get("project_id"):
        await _learning_from_event(
            db, org_id, event, payload,
            event_type="lesson",
            title=f"Task completed: {payload.get('title', '')[:100]}",
            detail="A task was completed in the background learning stream.",
            lesson="Track completion velocity per task type to improve estimates.",
            entity_type="task", entity_id=payload.get("task_id"),
            tags=_tokens(payload.get("title")),
        )


@on("task.blocked")
async def handle_task_blocked(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="incident",
        title=f"Task blocked: {payload.get('title', '')[:100]}",
        detail="A task was blocked and may need dependency review.",
        lesson="Repeated blocking patterns indicate missing dependencies or ownership.",
        entity_type="task", entity_id=payload.get("task_id"),
        tags=_tokens("blocked", payload.get("title")),
    )


@on("project.created")
async def handle_project_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("owner_id"):
        await _graph_link(
            db, org_id, "project.created", "employee", payload["owner_id"],
            "project", payload.get("project_id") or payload.get("id"),
            evidence=f"Owns project: {payload.get('name', payload.get('title', ''))[:120]}",
        )


@on("milestone.completed")
async def handle_milestone_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "milestone.completed", employee,
                                _tokens(payload.get("title"), payload.get("project_name")), event.id)
    if payload.get("project_id"):
        await _graph_link(
            db, org_id, "milestone.completed", "project", payload["project_id"],
            "milestone", payload.get("milestone_id"),
            evidence=f"Milestone completed: {payload.get('title', '')[:120]}",
        )


@on("meeting.ended")
async def handle_meeting_ended(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    meeting_id = payload.get("meeting_id") or payload.get("id")
    for attendee_id in (payload.get("attendees") or []):
        if not attendee_id:
            continue
        await _graph_link(
            db, org_id, "meeting.ended", "employee", attendee_id,
            "meeting", meeting_id,
            evidence=f"Attended meeting: {payload.get('title', '')[:120]}",
        )
        row = await db.execute(
            select(Employee).where(Employee.organization_id == org_id, Employee.id == attendee_id)
        )
        employee = row.scalar_one_or_none()
        if employee is not None:
            await _evolve_expertise(db, org_id, "meeting.ended", employee,
                                    _tokens(payload.get("title"), payload.get("agenda")), event.id,
                                    points=0.5)


# ---------------------------------------------------------------------------
# knowledge events
# ---------------------------------------------------------------------------


@on("document.created")
@on("wiki.created")
async def handle_knowledge_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    entity_type = event.name.split(".")[0]
    if employee is not None:
        await _evolve_expertise(db, org_id, event.name, employee,
                                _tokens(payload.get("title"), payload.get("category"), payload.get("keywords")),
                                event.id)
    author = payload.get("author_id") or payload.get("owner_id")
    if author:
        await _graph_link(
            db, org_id, event.name, "employee", author,
            entity_type, payload.get("document_id") or payload.get("id"),
            evidence=f"Authored {entity_type}: {payload.get('title', '')[:120]}",
        )


@on("document.updated")
@on("wiki.updated")
async def handle_knowledge_updated(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, event.name, employee,
                                _tokens(payload.get("title")), event.id, points=1.0)


@on("knowledge.duplicate_detected")
async def handle_duplicate_detected(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    from app.intelligence.knowledge_engine import knowledge_engine

    await knowledge_engine.ingest_duplicate_insight(db, organization_id=org_id, payload=payload)


@on("policy.approved")
async def handle_policy_approved(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "policy.approved", employee,
                                _tokens(payload.get("title"), payload.get("category")), event.id)


# ---------------------------------------------------------------------------
# goals / approvals / decisions
# ---------------------------------------------------------------------------


@on("decision.made")
async def handle_decision_made(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "decision.made", employee,
                                _tokens(payload.get("title"), payload.get("summary")), event.id)
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="decision",
        title=f"Decision: {payload.get('title', '')[:100]}",
        detail=payload.get("summary") or "A decision was recorded.",
        lesson="Decisions should be linked to measurable outcomes so the org can learn.",
        entity_type="decision", entity_id=payload.get("decision_id"),
        tags=_tokens(payload.get("title"), payload.get("category")),
    )


@on("approval.approved")
async def handle_approval_approved(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "approval.approved", employee,
                                _tokens(payload.get("title")), event.id, points=0.5)


@on("goal.completed")
async def handle_goal_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "goal.updated", employee,
                                _tokens(payload.get("name"), payload.get("title")), event.id, points=2.0)
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Goal completed: {payload.get('name', payload.get('title', ''))[:100]}",
        detail="A goal was completed.",
        lesson="Capture what made the goal succeed for future planning.",
        entity_type="goal", entity_id=payload.get("goal_id"),
        tags=_tokens(payload.get("name"), payload.get("title")),
    )


# ---------------------------------------------------------------------------
# people & community events
# ---------------------------------------------------------------------------


@on("community.posted")
async def handle_community_posted(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "community.posted", employee,
                                _tokens(payload.get("title"), payload.get("content"), payload.get("community_name")),
                                event.id)
    author = payload.get("author_id") or payload.get("creator_id")
    if author:
        await _graph_link(
            db, org_id, "community.posted", "employee", author,
            "community", payload.get("community_id"),
            evidence=f"Posted in community: {payload.get('community_name', '')[:120]}",
        )


@on("recognition.given")
async def handle_recognition_given(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    recipient = payload.get("recipient_id") or payload.get("receiver_id")
    row = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.id == recipient)
    )
    employee = row.scalar_one_or_none()
    if employee is not None:
        await _evolve_expertise(db, org_id, "recognition.given", employee,
                                _tokens(payload.get("reason"), payload.get("message")), event.id)
    if recipient:
        await _graph_link(
            db, org_id, "recognition.given", "employee", recipient,
            "employee", payload.get("giver_id") or payload.get("actor_id") or recipient,
            evidence=f"Recognition: {payload.get('reason', '')[:120]}",
        )


@on("team.member.added")
async def handle_team_member_added(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    member_id = payload.get("employee_id") or payload.get("member_id")
    if member_id and payload.get("team_id"):
        await _graph_link(
            db, org_id, "team.member.added", "employee", member_id,
            "team", payload["team_id"],
            evidence=f"Member of team: {payload.get('team_name', '')[:120]}",
        )


@on("innovation.submitted")
async def handle_innovation_submitted(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "innovation.submitted", employee,
                                _tokens(payload.get("title"), payload.get("description")), event.id)


@on("user.created")
async def handle_employee_joined(db, event, payload):
    """New member: seed the graph with their department/team membership."""
    org_id = payload.get("organization_id") or event.organization_id
    user_id = payload.get("user_id") or payload.get("id")
    if not user_id:
        return
    row = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.user_id == user_id)
    )
    employee = row.scalar_one_or_none()
    if employee is None:
        return
    if employee.department_id:
        await _graph_link(
            db, org_id, "user.created", "employee", employee.id,
            "department", employee.department_id, evidence="Joined department",
        )
    if employee.team_id:
        await _graph_link(
            db, org_id, "user.created", "employee", employee.id,
            "team", employee.team_id, evidence="Joined team",
        )
    if employee.manager_id:
        await _graph_link(
            db, org_id, "user.created", "employee", employee.id,
            "employee", employee.manager_id, relation="reports_to", evidence="Reports to manager",
        )


# ---------------------------------------------------------------------------
# Phase 10 — Learning & Growth Operating System
# ---------------------------------------------------------------------------


async def _refresh_learner(
    db: AsyncSession, organization_id: str, employee_id: Optional[str],
) -> None:
    """Close stale skill gaps and regenerate recommendations for a learner."""
    if not employee_id:
        return
    from app.learning.recommendation_service import recommendation_service
    from app.learning.skill_service import skill_service

    await skill_service.detect_gaps(
        db, organization_id=organization_id, employee_id=employee_id
    )
    await recommendation_service.refresh_for_employee(
        db, organization_id=organization_id, employee_id=employee_id
    )


@on("course.completed")
async def handle_course_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Course completed: {payload.get('course_title', '')[:100]}",
        detail="A learning course was completed in the background learning stream.",
        lesson="Completed courses signal mastery worth reusing in the organization.",
        entity_type="course", entity_id=payload.get("course_id"),
        tags=["course", "learning"],
    )


@on("certificate.earned")
async def handle_certificate_earned(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))


@on("assessment.finished")
async def handle_assessment_finished(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))


@on("learning.path.completed")
async def handle_path_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee_id = payload.get("employee_id")
    await _refresh_learner(db, org_id, employee_id)
    if employee_id:
        await _learning_from_event(
            db, org_id, event, payload,
            event_type="lesson",
            title=f"Learning path completed: {payload.get('path_title', '')[:100]}",
            detail="A full learning path was completed in the background learning stream.",
            lesson="Path completions indicate role-readiness worth recording.",
            entity_type="learning_path", entity_id=payload.get("path_id"),
            tags=["learning", "career"],
        )


@on("mentor.assigned")
async def handle_mentor_assigned(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("mentor_id"):
        await _graph_link(
            db, org_id, "mentor.assigned", "employee", payload["mentee_id"],
            "employee", payload["mentor_id"], relation="mentored_by",
            evidence=f"Mentorship on: {payload.get('topic', '')[:80]}",
        )


@on("mentorship.stalled")
async def handle_mentorship_stalled(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    from app.models.notification import Notification

    recipient_id = payload.get("mentor_id")
    if not recipient_id:
        return
    employee = await db.get(Employee, recipient_id)
    if employee is None:
        return
    db.add(
        Notification(
            organization_id=org_id,
            recipient_id=employee.user_id,
            actor_id=payload.get("mentee_id"),
            type="mentorship",
            title="Mentorship has stalled",
            body=f"No session recorded in 14+ days for '{payload.get('topic', 'mentorship')}'.",
            priority="normal",
            channel="in_app",
            entity_type="mentorship",
            entity_id=payload.get("mentorship_id"),
            delivered_at=None,
        )
    )


@on("onboarding.completed")
async def handle_onboarding_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))


# ---------------------------------------------------------------------------
# Slice 2 — People & Organization change notifications
# ---------------------------------------------------------------------------
# Handlers never commit: the EventBus owns the transaction. Recipients are
# resolved employee -> user_id using the established _notify_user pattern.


@on("manager.changed")
async def handle_manager_changed(db, event, payload):
    """Reporting relationship changed: refresh the graph edge, notify everyone involved."""
    org_id = payload.get("organization_id") or event.organization_id
    employee_id = payload.get("employee_id")
    new_manager_id = payload.get("to")
    old_manager_id = payload.get("from")
    if not employee_id:
        return
    from app.intelligence.graph_engine import graph_engine
    from app.models.intelligence import OrgGraphEdge

    stale = (
        await db.execute(
            select(OrgGraphEdge).where(
                OrgGraphEdge.organization_id == org_id,
                OrgGraphEdge.source_type == "employee",
                OrgGraphEdge.source_id == employee_id,
                OrgGraphEdge.relation == "reports_to",
                OrgGraphEdge.active.is_(True),
            )
        )
    ).scalars().all()
    for edge in stale:
        await graph_engine.deactivate_edge(db, organization_id=org_id, edge_id=edge.id)
    if new_manager_id:
        await graph_engine.upsert_edge(
            db, organization_id=org_id,
            source_type="employee", source_id=employee_id,
            target_type="employee", target_id=new_manager_id,
            relation="reports_to", evidence="Reports to manager",
        )

    employee = await db.get(Employee, employee_id)
    if employee is None:
        return
    new_manager = await db.get(Employee, new_manager_id) if new_manager_id else None
    old_manager = await db.get(Employee, old_manager_id) if old_manager_id else None
    manager_label = new_manager.full_name if new_manager else "no one"
    await _notify_user(
        db, org_id, _recipient_user_id(employee), "people",
        "Manager changed", f"You now report to {manager_label}.",
        entity_type="employee", entity_id=employee_id,
    )
    if new_manager is not None and new_manager.id != employee.id:
        await _notify_user(
            db, org_id, _recipient_user_id(new_manager), "people",
            "New direct report", f"{employee.full_name} now reports to you.",
            entity_type="employee", entity_id=employee_id,
        )
    if old_manager is not None and old_manager.id != employee.id:
        await _notify_user(
            db, org_id, _recipient_user_id(old_manager), "people",
            "Direct report changed", f"{employee.full_name} no longer reports to you.",
            entity_type="employee", entity_id=employee_id,
        )


@on("employee.transferred")
async def handle_employee_transferred(db, event, payload):
    """Department/team transfer: notify the employee and the new department head."""
    org_id = payload.get("organization_id") or event.organization_id
    employee_id = payload.get("employee_id")
    if not employee_id:
        return
    from app.models.department import Department

    employee = await db.get(Employee, employee_id)
    if employee is None:
        return
    new_dep = await db.get(Department, employee.department_id) if employee.department_id else None
    new_dep_label = new_dep.name if new_dep else "no department"
    await _notify_user(
        db, org_id, _recipient_user_id(employee), "people",
        "You were transferred", f"Your department is now {new_dep_label}.",
        entity_type="employee", entity_id=employee_id,
    )
    if new_dep is not None and new_dep.head_id and new_dep.head_id != employee.id:
        head = await db.get(Employee, new_dep.head_id)
        if head is not None:
            await _notify_user(
                db, org_id, _recipient_user_id(head), "people",
                "New department member", f"{employee.full_name} joined {new_dep.name}.",
                entity_type="employee", entity_id=employee_id,
            )


@on("team.member.added")
async def handle_team_member_added_notify(db, event, payload):
    """Team join: notify the employee and the team lead."""
    org_id = payload.get("organization_id") or event.organization_id
    employee_id = payload.get("employee_id")
    team_id = payload.get("team_id")
    if not employee_id or not team_id:
        return
    from app.models.team import Team

    employee = await db.get(Employee, employee_id)
    team = await db.get(Team, team_id)
    if employee is None or team is None:
        return
    await _notify_user(
        db, org_id, _recipient_user_id(employee), "people",
        f"Added to team {team.name}", f"You joined the {team.name} team.",
        entity_type="team", entity_id=team_id,
    )
    if team.lead_id and team.lead_id != employee.id:
        lead = await db.get(Employee, team.lead_id)
        if lead is not None:
            await _notify_user(
                db, org_id, _recipient_user_id(lead), "people",
                "Team member added", f"{employee.full_name} joined {team.name}.",
                entity_type="team", entity_id=team_id,
            )


@on("team.member.removed")
async def handle_team_member_removed(db, event, payload):
    """Team departure: notify the employee and the team lead."""
    org_id = payload.get("organization_id") or event.organization_id
    employee_id = payload.get("employee_id")
    team_id = payload.get("team_id")
    if not employee_id or not team_id:
        return
    from app.models.team import Team

    employee = await db.get(Employee, employee_id)
    team = await db.get(Team, team_id)
    if employee is None or team is None:
        return
    await _notify_user(
        db, org_id, _recipient_user_id(employee), "people",
        f"Removed from team {team.name}", f"You were removed from the {team.name} team.",
        entity_type="team", entity_id=team_id,
    )
    if team.lead_id and team.lead_id != employee.id:
        lead = await db.get(Employee, team.lead_id)
        if lead is not None:
            await _notify_user(
                db, org_id, _recipient_user_id(lead), "people",
                "Team member removed", f"{employee.full_name} left {team.name}.",
                entity_type="team", entity_id=team_id,
            )


# ---------------------------------------------------------------------------
# Phase 12 — Customers, CRM & External Relationships (CROS)
# ---------------------------------------------------------------------------


def _recipient_user_id(employee: Optional[Employee]) -> Optional[str]:
    return employee.user_id if employee is not None else None


async def _notify_user(
    db: AsyncSession, organization_id: str, recipient_user_id: Optional[str],
    type: str, title: str, body: str, entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> None:
    if not recipient_user_id:
        return
    from app.models.notification import Notification

    db.add(
        Notification(
            organization_id=organization_id,
            recipient_id=recipient_user_id,
            type=type, title=title, body=body,
            priority="high" if type == "escalation" else "normal",
            channel="in_app",
            entity_type=entity_type, entity_id=entity_id,
            delivered_at=None,
        )
    )


@on("customer.created")
async def handle_customer_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("owner_id"):
        await _graph_link(
            db, org_id, "customer.created", "employee", payload["owner_id"],
            "customer", payload.get("customer_id") or payload.get("id"),
            evidence=f"Owns account: {payload.get('company_name', '')[:120]}",
        )


@on("lead.qualified")
async def handle_lead_qualified(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Lead qualified: {payload.get('company_name', '')[:100]}",
        detail="A lead was qualified in the pipeline.",
        lesson="Track qualification velocity to tune lead scoring thresholds.",
        entity_type="lead", entity_id=payload.get("lead_id"),
        tags=["lead", "sales"],
    )


@on("opportunity.won")
async def handle_opportunity_won(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    owner = await _resolve_employee(db, org_id, payload)
    if owner is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(owner), "success",
            f"Deal won: {payload.get('title', '')[:80]}",
            f"Opportunity closed for ${payload.get('value') or 0:,.0f}.",
            entity_type="opportunity", entity_id=payload.get("opportunity_id"),
        )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Deal won: {payload.get('title', '')[:100]}",
        detail="A deal was won in the pipeline.",
        lesson="Won deals reveal which segments and sales motions drive revenue.",
        entity_type="opportunity", entity_id=payload.get("opportunity_id"),
        tags=["opportunity", "revenue"],
    )
    if payload.get("customer_id"):
        await _graph_link(
            db, org_id, "opportunity.won", "opportunity", payload["opportunity_id"],
            "customer", payload["customer_id"],
            evidence=f"Won deal: {payload.get('title', '')[:120]}",
        )


@on("contract.signed")
async def handle_contract_signed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Contract signed: {payload.get('title', '')[:100]}",
        detail="A contract was signed.",
        lesson="Track signature cycle time to remove friction in sales.",
        entity_type="contract", entity_id=payload.get("contract_id"),
        tags=["contract", "revenue"],
    )


@on("ticket.escalated")
async def handle_ticket_escalated(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    assignee = await _resolve_employee(db, org_id, payload)
    if assignee is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(assignee), "escalation",
            f"Ticket escalated: {payload.get('subject', '')[:80]}",
            "A support ticket was escalated and needs immediate attention.",
            entity_type="ticket", entity_id=payload.get("ticket_id"),
        )


@on("customer.renewed")
async def handle_customer_renewed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Renewal closed: {payload.get('title', '')[:100]}",
        detail="A customer contract was renewed.",
        lesson="Renewal wins depend on health, engagement and early outreach.",
        entity_type="contract", entity_id=payload.get("contract_id"),
        tags=["renewal", "retention"],
    )
    if payload.get("customer_id"):
        await _graph_link(
            db, org_id, "customer.renewed", "contract", payload["contract_id"],
            "customer", payload["customer_id"],
            evidence=f"Renewed: {payload.get('title', '')[:120]}",
        )


# ---------------------------------------------------------------------------
# Phase 13 — Finance & Business Operations
# ---------------------------------------------------------------------------


async def _create_finance_approval(
    db: AsyncSession, org_id: str, payload: dict[str, Any],
    *, approval_type: str, title: str, entity_type: str, entity_id: str,
    requester_id: Optional[str] = None, approver_id: Optional[str] = None,
    priority: str = "medium", description: Optional[str] = None,
) -> None:
    from app.models.approval import Approval

    existing = (
        await db.execute(
            select(Approval).where(
                Approval.organization_id == org_id,
                Approval.approval_type == approval_type,
                Approval.entity_type == entity_type,
                Approval.entity_id == entity_id,
                Approval.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Approval(
            organization_id=org_id,
            approval_type=approval_type,
            title=title,
            description=description,
            requester_id=requester_id,
            approver_id=approver_id,
            status="pending",
            priority=priority,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


@on("expense.submitted")
async def handle_expense_submitted(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if not payload.get("expense_id"):
        return
    await _create_finance_approval(
        db, org_id, payload,
        approval_type="expense",
        title=f"Expense approval: {payload.get('expense_type', 'expense')} — {payload.get('amount', 0):,.2f}",
        entity_type="expense", entity_id=payload["expense_id"],
        requester_id=payload.get("employee_id"),
        approver_id=payload.get("approver_id"),
        priority="medium",
        description="An expense was submitted and awaits approval.",
    )
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(requester), "success",
            "Expense submitted",
            f"{payload.get('expense_type', 'Expense')} of {payload.get('amount') or 0:,.2f} is pending approval.",
            entity_type="expense", entity_id=payload["expense_id"],
        )


@on("expense.approved")
async def handle_expense_approved(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("budget_id"):
        from app.finance.budget_service import budget_service
        budget = await budget_service.get(db, organization_id=org_id, budget_id=payload["budget_id"])
        if budget:
            await budget_service._refresh_usage(db, budget, organization_id=org_id)
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(requester), "success",
            "Expense approved",
            f"Your {payload.get('expense_type', 'expense')} of {payload.get('amount') or 0:,.2f} was approved.",
            entity_type="expense", entity_id=payload.get("expense_id"),
        )


@on("expense.rejected")
async def handle_expense_rejected(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(requester), "error",
            "Expense rejected",
            f"Your expense of {payload.get('amount') or 0:,.2f} was rejected.",
            entity_type="expense", entity_id=payload.get("expense_id"),
        )


@on("purchase.requested")
async def handle_purchase_requested(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if not payload.get("purchase_request_id"):
        return
    await _create_finance_approval(
        db, org_id, payload,
        approval_type="purchase",
        title=f"Purchase approval: {payload.get('title', '')[:120]} — {payload.get('estimated_cost', 0):,.2f}",
        entity_type="purchase_request", entity_id=payload["purchase_request_id"],
        requester_id=payload.get("employee_id"),
        approver_id=payload.get("approver_id"),
        priority="medium",
        description="A purchase request was submitted and awaits approval.",
    )
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _graph_link(
            db, org_id, "purchase.requested", "employee", requester.id,
            "purchase_request", payload["purchase_request_id"],
            evidence=f"Requested purchase: {payload.get('title', '')[:120]}",
        )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Purchase requested: {payload.get('title', '')[:100]}",
        detail="A purchase request entered the approval pipeline.",
        lesson="Faster purchase approvals shorten procurement cycles.",
        entity_type="purchase_request", entity_id=payload.get("purchase_request_id"),
        tags=["procurement", "finance"],
    )


@on("purchase.approved")
async def handle_purchase_approved(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(requester), "success",
            "Purchase approved",
            f"Your purchase '{payload.get('title', '')[:80]}' was approved.",
            entity_type="purchase_request", entity_id=payload.get("purchase_request_id"),
        )


@on("purchase.rejected")
async def handle_purchase_rejected(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    requester = await _resolve_employee(db, org_id, payload)
    if requester is not None:
        await _notify_user(
            db, org_id, _recipient_user_id(requester), "error",
            "Purchase rejected",
            f"Your purchase '{payload.get('title', '')[:80]}' was rejected.",
            entity_type="purchase_request", entity_id=payload.get("purchase_request_id"),
        )


@on("purchase.ordered")
async def handle_purchase_ordered(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Purchase order issued: {payload.get('po_number', '')[:40]}",
        detail="A purchase order was issued.",
        lesson="Orders that cite a budget are reconciled against it automatically.",
        entity_type="purchase_order", entity_id=payload.get("purchase_order_id"),
        tags=["procurement", "finance"],
    )


@on("budget.created")
async def handle_budget_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("owner_id"):
        await _graph_link(
            db, org_id, "budget.created", "employee", payload["owner_id"],
            "budget", payload.get("budget_id"),
            evidence=f"Owns budget: {payload.get('name', '')[:120]}",
        )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Budget created: {payload.get('name', '')[:100]}",
        detail="A new budget was established.",
        lesson="Budgets that track actuals early predict overruns sooner.",
        entity_type="budget", entity_id=payload.get("budget_id"),
        tags=["budget", "finance"],
    )


@on("vendor.created")
async def handle_vendor_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Vendor added: {payload.get('name', '')[:100]}",
        detail="A new vendor was added to the supplier network.",
        lesson="A curated vendor network concentrates spend and simplifies risk review.",
        entity_type="vendor", entity_id=payload.get("vendor_id"),
        tags=["vendor", "procurement"],
    )


@on("invoice.received")
async def handle_invoice_received(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Invoice received: {payload.get('title', '')[:100]}",
        detail="An invoice was received.",
        lesson="Track payable aging to avoid late fees and preserve supplier trust.",
        entity_type="invoice", entity_id=payload.get("invoice_id"),
        tags=["invoice", "finance"],
    )


@on("payment.completed")
async def handle_payment_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("vendor_id"):
        await _graph_link(
            db, org_id, "payment.completed", "payment", payload.get("payment_id"),
            "vendor", payload["vendor_id"],
            evidence=f"Paid {payload.get('amount') or 0:,.2f}",
        )
