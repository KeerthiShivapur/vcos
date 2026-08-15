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
from app.models.people_intelligence import MEMBERSHIP_STATUSES, PeopleTimeline
from app.models.team import Team

logger = logging.getLogger("vcos.events.handlers")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _resolve_employee(
    db: AsyncSession, organization_id: str, payload: dict[str, Any]
) -> Optional[Employee]:
    for key in ("assignee_id", "owner_id", "author_id", "editor_id", "recipient_id", "actor_id", "employee_id", "approver_id", "decision_maker_id"):
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
    points: float | None = None, source_type: Optional[str] = None,
    source_id: Optional[str] = None, source_title: Optional[str] = None,
) -> None:
    """Feed the canonical expertise pipeline (Slice 4F.2). Source lineage is
    passed where the payload carries a real canonical id; otherwise the
    engine falls back to the event id itself (always a canonical source)."""
    from app.intelligence.expertise_engine import expertise_engine

    await expertise_engine.record_activity(
        db, organization_id=organization_id, employee_id=employee.id,
        event_name=event_name, tokens=tokens, reason=describe(event_name),
        event_id=event_id, points=points, source_type=source_type,
        source_id=source_id, source_title=source_title,
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
        await _evolve_expertise(
            db, org_id, "task.completed", employee, tokens, event.id,
            source_type="task", source_id=payload.get("task_id") or payload.get("id") or event.id,
            source_title=payload.get("title"),
        )
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


@on("task.completed")
async def handle_task_completed_unblocks(db, event, payload):
    """Propagate completion: blocked dependents whose blockers are all done unblock."""
    org_id = payload.get("organization_id") or event.organization_id
    completed_id = payload.get("task_id") or payload.get("id")
    if not completed_id:
        return
    from app.models.task import Task, TaskDependency

    dependents = (
        await db.execute(
            select(Task).join(TaskDependency, TaskDependency.task_id == Task.id).where(
                TaskDependency.organization_id == org_id,
                TaskDependency.depends_on_task_id == completed_id,
                TaskDependency.kind.in_(("blocking", "finish_to_start")),
                Task.status == "blocked",
            )
        )
    ).scalars().all()
    from app.work.dependency_service import dependency_service

    for dependent in dependents:
        remaining = await dependency_service.unsatisfied_blockers(
            db, organization_id=org_id, task_id=dependent.id
        )
        if remaining:
            continue
        from app.core.timeutils import utcnow

        dependent.status = "todo"
        dependent.updated_at = utcnow()
        await db.flush()
        from app.services.event_service import event_service

        await event_service.emit(
            db, name="task.unblocked", actor_id=event.actor_id,
            organization_id=org_id,
            payload={"task_id": dependent.id, "title": dependent.title, "assignee_id": dependent.assignee_id},
        )
        from app.services.work_audit import record

        await record(
            db, organization_id=org_id, action="task.unblocked",
            actor=None, ip_address=None,
            resource_type="task", resource_id=dependent.id,
            details={"title": dependent.title, "status": "todo", "trigger": "task.completed"},
        )
        if dependent.assignee_id:
            from app.services.work_alerts import notify_employee

            await notify_employee(
                db, organization_id=org_id,
                employee_id=dependent.assignee_id,
                type="task.unblocked",
                title=f"Task unblocked: {dependent.title}",
                body="All blocking dependencies are now complete.",
                actor_id=event.actor_id,
                entity_type="task", entity_id=dependent.id,
                link=f"/tasks/{dependent.id}",
            )


@on("project.started")
async def handle_project_started(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    project_id = payload.get("project_id") or payload.get("id")
    if not project_id:
        return
    from app.models.project import ProjectMember
    from app.services.work_alerts import notify_employees

    member_ids = list(
        (await db.execute(
            select(ProjectMember.employee_id).where(
                ProjectMember.organization_id == org_id, ProjectMember.project_id == project_id
            )
        )).scalars().all()
    )
    if member_ids:
        await notify_employees(
            db, organization_id=org_id, employee_ids=member_ids,
            type="project.started",
            title=f"Project started: {payload.get('name', '')[:80]}",
            body="The project is now in active execution.",
            actor_id=event.actor_id,
            entity_type="project", entity_id=project_id,
            link=f"/projects/{project_id}",
        )


@on("project.completed")
async def handle_project_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    project_id = payload.get("project_id") or payload.get("id")
    if not project_id:
        return
    from app.models.project import ProjectMember
    from app.services.work_alerts import notify_employees

    member_ids = list(
        (await db.execute(
            select(ProjectMember.employee_id).where(
                ProjectMember.organization_id == org_id, ProjectMember.project_id == project_id
            )
        )).scalars().all()
    )
    if member_ids:
        await notify_employees(
            db, organization_id=org_id, employee_ids=member_ids,
            type="project.completed",
            title=f"Project completed: {payload.get('name', '')[:80]}",
            body="The project has been completed. Well done!",
            actor_id=event.actor_id,
            priority="high",
            entity_type="project", entity_id=project_id,
            link=f"/projects/{project_id}",
        )


@on("project.cancelled")
async def handle_project_cancelled(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    project_id = payload.get("project_id") or payload.get("id")
    if not project_id:
        return
    from app.models.project import Project
    from app.services.work_alerts import notify_employee

    project = await db.get(Project, project_id)
    if project is not None and project.owner_id:
        await notify_employee(
            db, organization_id=org_id,
            employee_id=project.owner_id,
            type="project.cancelled",
            title=f"Project cancelled: {payload.get('name', '')[:80]}",
            body="The project has been cancelled.",
            actor_id=event.actor_id,
            entity_type="project", entity_id=project_id,
            link=f"/projects/{project_id}",
        )


@on("roadmap.started")
async def handle_roadmap_started(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    roadmap_id = payload.get("roadmap_id") or payload.get("id")
    if not roadmap_id:
        return
    from app.services.work_alerts import notify_employee

    owner_id = payload.get("owner_id")
    if owner_id:
        await notify_employee(
            db, organization_id=org_id, employee_id=owner_id,
            type="roadmap.started",
            title=f"Roadmap activated: {payload.get('name', '')[:80]}",
            body="Your roadmap is now active.",
            actor_id=event.actor_id,
            entity_type="roadmap", entity_id=roadmap_id,
            link=f"/roadmaps/{roadmap_id}",
        )


@on("roadmap.completed")
async def handle_roadmap_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    roadmap_id = payload.get("roadmap_id") or payload.get("id")
    if not roadmap_id:
        return
    from app.services.work_alerts import notify_employee

    owner_id = payload.get("owner_id")
    if owner_id:
        await notify_employee(
            db, organization_id=org_id, employee_id=owner_id,
            type="roadmap.completed",
            title=f"Roadmap completed: {payload.get('name', '')[:80]}",
            body="Your roadmap has been completed.",
            actor_id=event.actor_id,
            priority="high",
            entity_type="roadmap", entity_id=roadmap_id,
            link=f"/roadmaps/{roadmap_id}",
        )


@on("task.completed")
async def handle_task_progress_rollup(db, event, payload):
    """Keep project/epic/milestone/roadmap progress in sync with execution."""
    org_id = payload.get("organization_id") or event.organization_id
    task_id = payload.get("task_id") or payload.get("id")
    if not task_id:
        return
    from app.work.progress_rollup import rollup_for_task, rollup_roadmap_of_project

    await rollup_for_task(db, organization_id=org_id, task_id=task_id)
    project_id = payload.get("project_id")
    if project_id:
        await rollup_roadmap_of_project(db, organization_id=org_id, project_id=project_id)


@on("task.transitioned")
async def handle_task_transition_progress_rollup(db, event, payload):
    """Parent progress follows subtask status (any transition, not just completion)."""
    org_id = payload.get("organization_id") or event.organization_id
    task_id = payload.get("task_id") or payload.get("id")
    if not task_id:
        return
    from app.work.progress_rollup import rollup_for_task

    await rollup_for_task(db, organization_id=org_id, task_id=task_id)


@on("task.created")
async def handle_task_created_parent_rollup(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    parent_id = payload.get("parent_task_id")
    sprint_id = payload.get("sprint_id")
    from app.work.progress_rollup import rollup_parent, rollup_sprint

    if parent_id:
        await rollup_parent(db, organization_id=org_id, parent_id=parent_id)
    if sprint_id:
        await rollup_sprint(db, organization_id=org_id, sprint_id=sprint_id)


@on("milestone.completed")
async def handle_milestone_progress_rollup(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    from app.work.progress_rollup import rollup_project

    project_id = payload.get("project_id")
    if project_id:
        await rollup_project(db, organization_id=org_id, project_id=project_id)


@on("task.blocked")
async def handle_task_blocked(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("assignee_id"):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db, organization_id=org_id,
            employee_id=payload["assignee_id"],
            type="task.blocked",
            title=f"Task blocked: {payload.get('title', '')[:80]}",
            body="The task is blocked by an uncompleted dependency and needs attention.",
            actor_id=event.actor_id,
            priority="high",
            entity_type="task", entity_id=payload.get("task_id"),
            link=f"/tasks/{payload.get('task_id', '')}",
            metadata={"status": "blocked"},
        )
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
        await _evolve_expertise(
            db, org_id, "milestone.completed", employee,
            _tokens(payload.get("title"), payload.get("project_name")), event.id,
            source_type="milestone", source_id=payload.get("milestone_id") or event.id,
            source_title=payload.get("title"),
        )
    if payload.get("project_id"):
        await _graph_link(
            db, org_id, "milestone.completed", "project", payload["project_id"],
            "milestone", payload.get("milestone_id"),
            evidence=f"Milestone completed: {payload.get('title', '')[:120]}",
        )
        from app.models.project import Project
        from app.services.work_alerts import notify_employee

        project = await db.get(Project, payload["project_id"])
        if project is not None and project.owner_id:
            await notify_employee(
                db, organization_id=org_id,
                employee_id=project.owner_id,
                type="milestone.completed",
                title=f"Milestone completed: {payload.get('title', payload.get('name', ''))[:80]}",
                body=f"Milestone '{payload.get('title', payload.get('name', ''))[:80]}' in '{project.name}' was completed.",
                actor_id=event.actor_id,
                entity_type="milestone", entity_id=payload.get("milestone_id"),
                link=f"/projects/{project.id}",
            )


@on("milestone.created")
async def handle_milestone_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("project_id") and payload.get("milestone_id"):
        await _graph_link(
            db, org_id, "milestone.created", "project", payload["project_id"],
            "milestone", payload["milestone_id"],
            evidence=f"Milestone planned: {payload.get('name', '')[:120]}",
        )


@on("epic.created")
async def handle_epic_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("project_id") and payload.get("epic_id"):
        await _graph_link(
            db, org_id, "epic.created", "project", payload["project_id"],
            "epic", payload["epic_id"],
            evidence=f"Epic planned: {payload.get('name', '')[:120]}",
        )


@on("roadmap.created")
async def handle_roadmap_created(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("owner_id") and payload.get("roadmap_id"):
        await _graph_link(
            db, org_id, "roadmap.created", "employee", payload["owner_id"],
            "roadmap", payload["roadmap_id"],
            evidence=f"Owns roadmap: {payload.get('name', '')[:120]}",
        )


@on("task.deleted")
async def handle_task_deleted(db, event, payload):
    """Deleted tasks should not linger in the organization graph."""
    org_id = payload.get("organization_id") or event.organization_id
    task_id = payload.get("task_id") or payload.get("id")
    if not task_id:
        return
    from app.intelligence.graph_engine import graph_engine
    from app.models.intelligence import OrgGraphEdge
    from sqlalchemy import or_

    edges = (
        await db.execute(
            select(OrgGraphEdge).where(
                OrgGraphEdge.organization_id == org_id,
                OrgGraphEdge.active.is_(True),
                or_(
                    (OrgGraphEdge.source_type == "task") & (OrgGraphEdge.source_id == task_id),
                    (OrgGraphEdge.target_type == "task") & (OrgGraphEdge.target_id == task_id),
                ),
            )
        )
    ).scalars().all()
    for edge in edges:
        await graph_engine.deactivate_edge(db, organization_id=org_id, edge_id=edge.id)


@on("dependency.added")
async def handle_dependency_added(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Dependency added: {payload.get('task_id', '')[:40]} → {payload.get('depends_on_task_id', '')[:40]}",
        detail=f"A {payload.get('kind') or 'finish_to_start'} dependency was linked between tasks.",
        lesson="Explicit dependencies make blocking patterns visible before they bite.",
        entity_type="task", entity_id=payload.get("task_id"),
        tags=_tokens(payload.get("kind"), "dependency"),
    )


@on("dependency.removed")
async def handle_dependency_removed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Dependency removed: {payload.get('task_id', '')[:40]} → {payload.get('depends_on_task_id', '')[:40]}",
        detail="A task dependency was removed.",
        lesson="Frequent dependency churn can signal unstable task boundaries.",
        entity_type="task", entity_id=payload.get("task_id"),
        tags=_tokens("dependency", "churn"),
    )


@on("sprint.started")
async def handle_sprint_started(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("project_id"):
        from app.models.project import Project
        from app.services.work_alerts import notify_employee

        project = await db.get(Project, payload["project_id"])
        if project is not None and project.owner_id:
            await notify_employee(
                db, organization_id=org_id,
                employee_id=project.owner_id,
                type="sprint.started",
                title=f"Sprint started: {payload.get('name', '')[:80]}",
                body=f"Sprint '{payload.get('name', '')[:80]}' in '{project.name}' is now active.",
                actor_id=event.actor_id,
                entity_type="sprint", entity_id=payload.get("sprint_id"),
                link=f"/projects/{project.id}",
            )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Sprint started: {payload.get('name', '')[:100]}",
        detail="A sprint began execution.",
        lesson="Sprints with a clear goal and sized backlog tend to complete cleaner.",
        entity_type="sprint", entity_id=payload.get("sprint_id"),
        tags=_tokens(payload.get("name"), "sprint"),
    )


@on("sprint.completed")
async def handle_sprint_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("project_id"):
        from app.models.project import Project
        from app.services.work_alerts import notify_employee

        project = await db.get(Project, payload["project_id"])
        if project is not None and project.owner_id:
            await notify_employee(
                db, organization_id=org_id,
                employee_id=project.owner_id,
                type="sprint.completed",
                title=f"Sprint completed: {payload.get('name', '')[:80]}",
                body=f"Sprint '{payload.get('name', '')[:80]}' in '{project.name}' was completed.",
                actor_id=event.actor_id,
                entity_type="sprint", entity_id=payload.get("sprint_id"),
                link=f"/projects/{project.id}",
            )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Sprint completed: {payload.get('name', '')[:100]}",
        detail="A sprint finished its execution cycle.",
        lesson="Compare planned vs completed scope to tune sprint capacity estimates.",
        entity_type="sprint", entity_id=payload.get("sprint_id"),
        tags=_tokens(payload.get("name"), "sprint", "velocity"),
    )


@on("risk.closed")
async def handle_risk_closed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("owner_id"):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db, organization_id=org_id,
            employee_id=payload["owner_id"],
            type="risk.closed",
            title=f"Risk closed: {payload.get('title', '')[:80]}",
            body="A risk assigned to you was closed.",
            actor_id=event.actor_id,
            entity_type="risk", entity_id=payload.get("risk_id"),
            link="/analytics",
        )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="lesson",
        title=f"Risk closed: {payload.get('title', '')[:100]}",
        detail=f"A risk (score {payload.get('risk_score') or 0}) was closed.",
        lesson="Closed risks reveal which mitigations worked — reuse them early.",
        entity_type="risk", entity_id=payload.get("risk_id"),
        tags=_tokens(payload.get("title"), "risk"),
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
    entity_type = event.name.split(".")[0]
    entity_id = (payload.get("document_id") or payload.get("wiki_id")
                 or payload.get("entity_id") or payload.get("id") or event.id)
    # Live events carry only {entity_type, entity_id, title}: authorship must
    # come from the entity itself, never from a mangled payload.
    author = payload.get("author_id") or payload.get("owner_id")
    if not author:
        author = await _knowledge_entity_author(db, org_id, entity_type, entity_id)
    employee = None
    if author:
        employee = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == org_id, Employee.id == author
                )
            )
        ).scalar_one_or_none()
    if employee is not None:
        await _evolve_expertise(
            db, org_id, event.name, employee,
            _tokens(payload.get("title"), payload.get("category"), payload.get("keywords")),
            event.id,
            source_type=entity_type,
            source_id=entity_id,
            source_title=payload.get("title"),
        )
    if author:
        await _graph_link(
            db, org_id, event.name, "employee", author,
            entity_type, entity_id,
            evidence=f"Authored {entity_type}: {payload.get('title', '')[:120]}",
        )


async def _knowledge_entity_author(
    db: AsyncSession, organization_id: str, entity_type: str, entity_id: str,
) -> Optional[str]:
    """The accountable author of a knowledge entity (owner first — the person
    formally accountable — then the recorded author)."""
    if entity_type not in ("document", "wiki"):
        return None
    from app.models.knowledge import Document, WikiPage

    model = Document if entity_type == "document" else WikiPage
    row = await db.get(model, entity_id)
    if row is None or getattr(row, "organization_id", None) != organization_id:
        return None
    return getattr(row, "owner_id", None) or getattr(row, "author_id", None)


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
    decision_id = payload.get("decision_id") or payload.get("entity_id")
    if employee is not None:
        await _evolve_expertise(
            db, org_id, "decision.made", employee,
            _tokens(payload.get("title"), payload.get("summary")), event.id,
            source_type="decision", source_id=decision_id or event.id,
            source_title=payload.get("title"),
        )
        await _graph_link(
            db, org_id, "decision.made", "employee", employee.id,
            "decision", decision_id,
            evidence=f"Made decision: {payload.get('title', '')[:120]}",
        )
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="decision",
        title=f"Decision: {payload.get('title', '')[:100]}",
        detail=payload.get("summary") or "A decision was recorded.",
        lesson="Decisions should be linked to measurable outcomes so the org can learn.",
        entity_type="decision", entity_id=decision_id,
        tags=_tokens(payload.get("title"), payload.get("category")),
    )


@on("decision.executed")
async def handle_decision_executed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    decision_id = payload.get("decision_id") or payload.get("entity_id")
    task_id = payload.get("task_id")
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "decision.executed", employee,
                                _tokens(payload.get("title"), payload.get("action")), event.id,
                                points=1.0)
    if decision_id and task_id:
        await _graph_link(
            db, org_id, "decision.executed", "decision", decision_id,
            "task", task_id,
            evidence=f"Follow-up action became task: {payload.get('task_title', '')[:120]}",
        )


@on("decision.implemented")
async def handle_decision_implemented(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "decision.implemented", employee,
                                _tokens(payload.get("title")), event.id, points=2.0)
    await _learning_from_event(
        db, org_id, event, payload,
        event_type="decision",
        title=f"Decision implemented: {payload.get('title', '')[:100]}",
        detail="Every follow-up task from this decision is complete.",
        lesson="Track decision-to-outcome so the org learns what actually got done.",
        entity_type="decision", entity_id=payload.get("decision_id") or payload.get("entity_id"),
        tags=_tokens(payload.get("title"), "implemented"),
    )


@on("approval.approved")
async def handle_approval_approved(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "approval.approved", employee,
                                _tokens(payload.get("title")), event.id, points=0.5)
    if payload.get("requester_id"):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db, organization_id=org_id,
            employee_id=payload["requester_id"],
            type="approval.decided",
            title=f"Approval granted: {payload.get('title', '')[:80]}",
            body="Your approval request was approved.",
            actor_id=event.actor_id,
            entity_type="approval", entity_id=payload.get("approval_id"),
            link="/approvals",
        )


@on("approval.rejected")
async def handle_approval_rejected(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    if payload.get("requester_id"):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db, organization_id=org_id,
            employee_id=payload["requester_id"],
            type="approval.decided",
            title=f"Approval rejected: {payload.get('title', '')[:80]}",
            body="Your approval request was rejected.",
            actor_id=event.actor_id,
            priority="high",
            entity_type="approval", entity_id=payload.get("approval_id"),
            link="/approvals",
        )


@on("goal.completed")
async def handle_goal_completed(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(db, org_id, "goal.updated", employee,
                                _tokens(payload.get("name"), payload.get("title")), event.id, points=2.0)
    if payload.get("owner_id"):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db, organization_id=org_id,
            employee_id=payload["owner_id"],
            type="goal.completed",
            title=f"Goal completed: {payload.get('name', '')[:80]}",
            body="All key results are complete — the goal was achieved.",
            actor_id=event.actor_id,
            entity_type="goal", entity_id=payload.get("goal_id"),
            link="/goals",
        )
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
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(
            db, org_id, "course.completed", employee,
            _tokens(payload.get("course_title"), payload.get("category"),
                    payload.get("skill_name"), payload.get("tags")),
            event.id,
            source_type="course", source_id=payload.get("course_id") or event.id,
            source_title=payload.get("course_title"),
        )


@on("certificate.earned")
async def handle_certificate_earned(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(
            db, org_id, "certificate.earned", employee,
            _tokens(payload.get("certificate_name"), payload.get("certification_name"),
                    payload.get("skill_name"), payload.get("category")),
            event.id,
            source_type="certificate", source_id=payload.get("certificate_id") or event.id,
            source_title=payload.get("certificate_name") or payload.get("certification_name"),
        )


@on("assessment.finished")
async def handle_assessment_finished(db, event, payload):
    org_id = payload.get("organization_id") or event.organization_id
    await _refresh_learner(db, org_id, payload.get("employee_id"))
    employee = await _resolve_employee(db, org_id, payload)
    if employee is not None:
        await _evolve_expertise(
            db, org_id, "assessment.finished", employee,
            _tokens(payload.get("assessment_title"), payload.get("skill_name"),
                    payload.get("category")),
            event.id,
            source_type="assessment", source_id=payload.get("assessment_id") or event.id,
            source_title=payload.get("assessment_title"),
        )


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
        employee = await _resolve_employee(db, org_id, payload)
        if employee is not None:
            await _evolve_expertise(
                db, org_id, "learning.path.completed", employee,
                _tokens(payload.get("path_title"), payload.get("skill_name"),
                        payload.get("category")),
                event.id,
                source_type="learning_path", source_id=payload.get("path_id") or event.id,
                source_title=payload.get("path_title"),
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


# ---------------------------------------------------------------------------
# Slice 4B — Messaging operating loop
# ---------------------------------------------------------------------------
# These handlers drive the realtime leg of the messaging loop: they fan out
# live updates to the in-memory LiveHub personal channels and (for membership)
# notify the affected employee. Handlers never commit — the EventBus owns the
# transaction. The hub push performs no database work; if nobody is connected
# it is a no-op (clients keep the 30s polling fallback).


async def _conversation_member_ids(db: AsyncSession, org_id: str, conversation_id: str) -> list[str]:
    from app.models.communication import ConversationMember

    return list(
        (
            await db.execute(
                select(ConversationMember.employee_id).where(
                    ConversationMember.organization_id == org_id,
                    ConversationMember.conversation_id == conversation_id,
                )
            )
        ).scalars().all()
    )


async def _push_messaging(employee_ids: list[str], event_type: str, data: Optional[dict[str, Any]]) -> None:
    from app.collaboration.live import live_hub

    for employee_id in employee_ids:
        if not employee_id:
            continue
        try:
            await live_hub.send_personal(employee_id, event_type, data)
        except Exception:  # pragma: no cover - hub is defensive
            logger.warning("messaging push failed for %s", employee_id, exc_info=True)


async def _messaging_sender_name(db: AsyncSession, org_id: str, sender_id: Optional[str]) -> Optional[str]:
    if not sender_id:
        return None
    sender = await db.get(Employee, sender_id)
    if sender is None or sender.organization_id != org_id:
        return None
    return sender.display_name or " ".join(p for p in (sender.first_name, sender.last_name) if p) or sender_id


@on("messaging.message_sent")
async def handle_messaging_message_sent(db, event, payload):
    """Realtime: deliver the new message to every conversation member (except the sender)."""
    org_id = payload.get("organization_id") or event.organization_id
    message_id = payload.get("message_id")
    conversation_id = payload.get("conversation_id")
    if not message_id or not conversation_id:
        return
    from app.communication.message_service import message_service
    from app.communication.presenters import present_message

    message = await message_service.get_message(db, organization_id=org_id, message_id=message_id)
    if message is None or message.deleted:
        return
    presented = await present_message(
        message,
        sender_name=await _messaging_sender_name(db, org_id, message.sender_id),
    )
    members = await _conversation_member_ids(db, org_id, conversation_id)
    await _push_messaging(
        [m for m in members if m != message.sender_id],
        "messaging.message.sent",
        {"conversation_id": conversation_id, "message": presented},
    )


@on("messaging.message_updated")
async def handle_messaging_message_updated(db, event, payload):
    """Realtime: propagate an edit to the conversation so clients can patch in place."""
    org_id = payload.get("organization_id") or event.organization_id
    message_id = payload.get("message_id")
    if not message_id:
        return
    from app.communication.message_service import message_service
    from app.communication.presenters import present_message

    message = await message_service.get_message(db, organization_id=org_id, message_id=message_id)
    if message is None or message.deleted:
        return
    presented = await present_message(
        message,
        sender_name=await _messaging_sender_name(db, org_id, message.sender_id),
    )
    members = await _conversation_member_ids(db, org_id, message.conversation_id)
    await _push_messaging(
        members,
        "messaging.message.updated",
        {"conversation_id": message.conversation_id, "message": presented},
    )


@on("messaging.message_deleted")
async def handle_messaging_message_deleted(db, event, payload):
    """Realtime: tell clients to drop/replace the deleted message."""
    org_id = payload.get("organization_id") or event.organization_id
    message_id = payload.get("message_id")
    if not message_id:
        return
    from app.communication.message_service import message_service

    message = await message_service.get_message(db, organization_id=org_id, message_id=message_id)
    if message is None:
        return
    members = await _conversation_member_ids(db, org_id, message.conversation_id)
    await _push_messaging(
        members,
        "messaging.message.deleted",
        {"conversation_id": message.conversation_id, "message_id": message_id},
    )


@on("messaging.message_reaction_added")
@on("messaging.message_reaction_removed")
async def handle_messaging_message_reaction(db, event, payload):
    """Realtime: keep reaction state in sync without a refetch."""
    org_id = payload.get("organization_id") or event.organization_id
    message_id = payload.get("message_id")
    if not message_id:
        return
    from app.communication.message_service import message_service

    message = await message_service.get_message(db, organization_id=org_id, message_id=message_id)
    if message is None:
        return
    reacted = event.name.endswith("_added")
    members = await _conversation_member_ids(db, org_id, message.conversation_id)
    await _push_messaging(
        members,
        "messaging.message.reaction",
        {
            "conversation_id": message.conversation_id,
            "message_id": message_id,
            "emoji": payload.get("emoji"),
            "reacted": reacted,
        },
    )


@on("messaging.member_added")
async def handle_messaging_member_added(db, event, payload):
    """Membership: notify the added member and surface the conversation to everyone live."""
    org_id = payload.get("organization_id") or event.organization_id
    conversation_id = payload.get("conversation_id")
    employee_id = payload.get("employee_id")
    if not conversation_id or not employee_id:
        return
    from app.models.communication import Conversation

    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.organization_id != org_id:
        return
    member = await db.get(Employee, employee_id)
    if member is not None and member.organization_id == org_id:
        await _notify_user(
            db, org_id, _recipient_user_id(member), "messaging",
            f"Added to conversation: {conversation.title or 'New conversation'}",
            "You were added to a conversation and can now send messages.",
            entity_type="conversation", entity_id=conversation_id,
        )
    members = await _conversation_member_ids(db, org_id, conversation_id)
    await _push_messaging(
        members,
        "messaging.member.added",
        {"conversation_id": conversation_id, "employee_id": employee_id},
    )


# ---------------------------------------------------------------------------
# company intelligence (Slice 4D.1) — change-driven consumers
#
# These consumers reuse the durable event bus: on an operating event they
# perform a bounded, idempotent refresh of the affected entity's company
# evidence (graph edges + CompanyInsight freshness). They never commit, never
# fan out, and are safe to retry.
# ---------------------------------------------------------------------------


async def _company_intel_refresh(
    db: AsyncSession, org_id: str, entity_type: str, entity_id: Optional[str],
    message_id: Optional[str] = None, *, reason: str,
) -> bool:
    """Bounded context refresh for one affected entity.

    Validates the entity belongs to the org, syncs its graph edges (bounded),
    then asks the company-intel worker to bump/refresh the insight. Failures
    are logged by the dispatcher and never break sibling handlers.
    """
    if not entity_id:
        return False
    try:
        from app.intelligence.graph_engine import graph_engine
        from app.workers import company_intel_worker

        if entity_type == "conversation":
            from app.models.communication import Conversation

            row = await db.get(Conversation, entity_id)
            if row is None or row.organization_id != org_id:
                return False
        elif entity_type == "scope":
            from app.models.governance import GovernanceScope

            row = await db.get(GovernanceScope, entity_id)
            if row is None or row.organization_id != org_id:
                return False
        if entity_type in ("task", "decision", "conversation", "message"):
            await graph_engine.sync_entity_edges(
                db, organization_id=org_id, entity_type=entity_type, entity_id=entity_id
            )
        if message_id and entity_type == "conversation":
            await graph_engine.sync_entity_edges(
                db, organization_id=org_id, entity_type="message", entity_id=message_id
            )
        await company_intel_worker.refresh_entity(
            db, organization_id=org_id,
            entity_type=entity_type, entity_id=entity_id,
            reason=reason,
        )
        return True
    except Exception:  # noqa: BLE001 - defensive consumer
        logger.exception("company-intel refresh failed for %s:%s", entity_type, entity_id)
        return False


@on("messaging.message_sent")
@on("messaging.message_updated")
@on("messaging.message_deleted")
async def handle_company_intel_message_change(db, event, payload):
    """Change-driven: a message event refreshes the bounded context of its conversation."""
    org_id = payload.get("organization_id") or event.organization_id
    await _company_intel_refresh(
        db, org_id, "conversation", payload.get("conversation_id"),
        message_id=payload.get("message_id"), reason=event.name,
    )


@on("messaging.conversation_created")
@on("messaging.conversation_updated")
@on("messaging.conversation_archived")
@on("messaging.member_added")
@on("messaging.member_removed")
async def handle_company_intel_conversation_change(db, event, payload):
    """Change-driven: conversation/membership changes refresh that conversation's context."""
    org_id = payload.get("organization_id") or event.organization_id
    await _company_intel_refresh(
        db, org_id, "conversation", payload.get("conversation_id"), reason=event.name,
    )


@on("governance.scope.created")
@on("governance.scope.updated")
@on("governance.scope.deleted")
@on("governance.assignment.created")
@on("governance.assignment.removed")
@on("governance.delegation.created")
@on("governance.delegation.revoked")
async def handle_company_intel_governance_change(db, event, payload):
    """Change-driven: governance changes refresh the affected scope's context.

    Caller access is derived live from the scope table on each request, so the
    operator-facing refresh only keeps the bounded insight for the scope fresh.
    """
    org_id = payload.get("organization_id") or event.organization_id
    scope_id = payload.get("scope_id")
    if scope_id:
        await _company_intel_refresh(db, org_id, "scope", scope_id, reason=event.name)


@on("governance.policy.created")
@on("governance.policy.updated")
async def handle_company_intel_policy_change(db, event, payload):
    """Change-driven: approval-policy changes refresh their scope's context."""
    org_id = payload.get("organization_id") or event.organization_id
    scope_id = payload.get("scope_id")
    if not scope_id:
        from app.models.governance import ApprovalPolicy

        policy = await db.get(ApprovalPolicy, payload.get("policy_id"))
        scope_id = policy.scope_id if policy is not None else None
    if scope_id:
        await _company_intel_refresh(db, org_id, "scope", scope_id, reason=event.name)


# ---------------------------------------------------------------------------
# semantic knowledge indexing (Slice 4D.2) — change-driven consumers
#
# Every knowledge write (create / update / restore / status change) re-indexes
# the affected entity's chunk vectors; every delete or archive removes them so
# removed content can never resurface. Handlers never commit (the event bus
# owns the transaction) and each re-index is idempotent and bounded.
# ---------------------------------------------------------------------------

_KNOWLEDGE_KINDS = ("document", "wiki", "policy", "sop", "template", "decision")
_KNOWLEDGE_REINDEX_SUFFIXES = (
    "created", "updated", "restored",
    "published", "approved", "made", "implemented", "reviewed",
)
_KNOWLEDGE_DELETE_SUFFIXES = ("deleted", "archived")

_KNOWLEDGE_REINDEX_EVENTS = tuple(
    f"{kind}.{suffix}" for kind in _KNOWLEDGE_KINDS for suffix in _KNOWLEDGE_REINDEX_SUFFIXES
)
_KNOWLEDGE_DELETE_EVENTS = tuple(
    f"{kind}.{suffix}" for kind in _KNOWLEDGE_KINDS for suffix in _KNOWLEDGE_DELETE_SUFFIXES
)


async def handle_semantic_knowledge_reindex(db, event, payload):
    """Change-driven: knowledge writes re-index the affected entity's vectors."""
    org_id = payload.get("organization_id") or event.organization_id
    entity_id = payload.get("entity_id") or payload.get("id") or payload.get("document_id")
    entity_type = event.name.split(".")[0]
    if not org_id or not entity_id or entity_type not in _KNOWLEDGE_KINDS:
        return
    try:
        from app.knowledge import semantic_indexer

        await semantic_indexer.reindex_entity(
            db, organization_id=org_id, kind=entity_type, entity_id=entity_id
        )
    except Exception:  # noqa: BLE001 - per-event isolation
        logger.exception("semantic reindex failed for %s/%s", entity_type, entity_id)


for _event_name in _KNOWLEDGE_REINDEX_EVENTS:
    on(_event_name)(handle_semantic_knowledge_reindex)


async def handle_semantic_knowledge_delete(db, event, payload):
    """Change-driven: knowledge deletes/archives remove the entity's vectors."""
    org_id = payload.get("organization_id") or event.organization_id
    entity_id = payload.get("entity_id") or payload.get("id") or payload.get("document_id")
    entity_type = event.name.split(".")[0]
    if not org_id or not entity_id or entity_type not in _KNOWLEDGE_KINDS:
        return
    try:
        from app.knowledge import semantic_indexer

        await semantic_indexer.delete_entity(
            db, organization_id=org_id, kind=entity_type, entity_id=entity_id
        )
    except Exception:  # noqa: BLE001 - per-event isolation
        logger.exception("semantic delete failed for %s/%s", entity_type, entity_id)


for _event_name in _KNOWLEDGE_DELETE_EVENTS:
    on(_event_name)(handle_semantic_knowledge_delete)


# ---------------------------------------------------------------------------
# Slice 4D.3 — organizational memory automation (change-driven formation)
# ---------------------------------------------------------------------------


async def handle_memory_formation_enqueue(db, event, payload):
    """Significant events enqueue a durable memory-formation job.

    The job runs in the memory formation worker (bounded FIFO batches); the
    enqueue itself is idempotent under the (name, event_id) uniqueness
    constraint. This handler never writes memory directly — the pipeline runs
    in its own transaction, keeping the event dispatch transaction small.
    """
    org_id = payload.get("organization_id") or event.organization_id
    if not org_id:
        return
    try:
        from app.memory import formation

        await formation.enqueue_formation(
            db,
            organization_id=org_id,
            event_id=event.id,
            name=event.name,
        )
    except Exception:  # noqa: BLE001 - per-event isolation
        logger.exception("memory formation enqueue failed for %s", event.name)


for _event_name in (
    "task.blocked",
    "task.unblocked",
    "task.completed",
    "task.commented",
    "project.started",
    "project.paused",
    "project.completed",
    "project.cancelled",
    "milestone.completed",
    "decision.made",
    "decision.executed",
    "decision.implemented",
    "approval.approved",
    "approval.rejected",
    "policy.approved",
    "document.published",
    "wiki.published",
    "sop.published",
    "template.published",
    "ticket.escalated",
    "customer.renewed",
):
    on(_event_name)(handle_memory_formation_enqueue)


# ---------------------------------------------------------------------------
# Slice 4D.4 — universal organizational pattern intelligence (change-driven)
# ---------------------------------------------------------------------------


async def handle_pattern_evaluation_enqueue(db, event, payload):
    """Significant events enqueue a durable pattern-evaluation job.

    The job runs in the pattern worker (bounded FIFO batches); the enqueue
    itself is idempotent under the (name, event_id) uniqueness constraint.
    This handler never writes patterns directly — the evaluation pipeline
    runs in its own transaction, keeping the event dispatch transaction small.
    """
    org_id = payload.get("organization_id") or event.organization_id
    if not org_id:
        return
    try:
        from app.intelligence import pattern_pipeline

        await pattern_pipeline.enqueue_evaluation(
            db,
            organization_id=org_id,
            event_id=event.id,
            name=event.name,
        )
    except Exception:  # noqa: BLE001 - per-event isolation
        logger.exception("pattern evaluation enqueue failed for %s", event.name)


for _event_name in (
    "task.blocked",
    "task.unblocked",
    "task.transitioned",
    "task.completed",
    "task.commented",
    "task.updated",
    "project.started",
    "project.paused",
    "project.completed",
    "project.cancelled",
    "milestone.completed",
    "decision.made",
    "decision.updated",
    "decision.executed",
    "decision.implemented",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "governance.assignment.created",
    "governance.assignment.removed",
    "governance.delegation.created",
    "governance.delegation.revoked",
    "employee.transferred",
    "ticket.escalated",
):
    on(_event_name)(handle_pattern_evaluation_enqueue)


# ---------------------------------------------------------------------------
# Slice 4D.5 — universal company insight intelligence (change-driven)
# ---------------------------------------------------------------------------


async def handle_insight_evaluation_enqueue(db, event, payload):
    """Observable events enqueue one durable insight-evaluation job.

    The job runs in the insight worker (bounded FIFO batches, CAS claim); the
    enqueue is idempotent under the (name, event_id) uniqueness constraint.
    This handler never writes insights directly — composition runs in its own
    worker transaction.
    """
    org_id = payload.get("organization_id") or event.organization_id
    if not org_id:
        return
    try:
        from app.intelligence import insight_pipeline

        await insight_pipeline.enqueue_evaluation(
            db,
            organization_id=org_id,
            event_id=event.id,
            name=event.name,
        )
    except Exception:  # noqa: BLE001 - per-event isolation
        logger.exception("insight evaluation enqueue failed for %s", event.name)


for _event_name in (
    "pattern.detected",
    "pattern.updated",
    "pattern.confirmed",
    "pattern.faded",
    "pattern.resolved",
    "memory.recorded",
    "decision.made",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
):
    on(_event_name)(handle_insight_evaluation_enqueue)


# ---------------------------------------------------------------------------
# Slice 4E.1 � canonical knowledge ingestion (event-driven, exact-once)
# ---------------------------------------------------------------------------
# The universal ingestion contract reacts to existing durable events: every
# knowledge object mutation (create / update / restore / approve / decide)
# reconciles exactly one canonical KnowledgeSource row plus its claims,
# evidence and topics. Re-processing the same content is a no-op.
# ---------------------------------------------------------------------------


@on("document.created")
@on("document.updated")
@on("document.restored")
@on("document.published")
@on("wiki.created")
@on("wiki.updated")
@on("wiki.restored")
@on("wiki.published")
@on("policy.created")
@on("policy.updated")
@on("policy.restored")
@on("policy.approved")
@on("sop.created")
@on("sop.updated")
@on("sop.restored")
@on("sop.published")
@on("template.created")
@on("template.updated")
@on("template.restored")
@on("template.published")
@on("decision.created")
@on("decision.updated")
@on("decision.made")
async def handle_canonical_knowledge_ingest(db, event, payload):
    """Keep the canonical knowledge model in sync with the object it stores."""
    org_id = payload.get("organization_id") or event.organization_id
    entity_type = payload.get("entity_type")
    if entity_type not in ("document", "wiki", "policy", "sop", "template", "decision"):
        entity_type = event.name.split(".")[0]
        if entity_type not in ("document", "wiki", "policy", "sop", "template", "decision"):
            return
    entity_id = (
        payload.get("entity_id")
        or payload.get("id")
        or payload.get(f"{entity_type}_id")
    )
    if not entity_id:
        return
    from app.knowledge.canonical_service import canonical_engine

    await canonical_engine.ingest(
        db, organization_id=org_id,
        entity_type=entity_type, entity_id=entity_id,
        event_name=event.name,
    )


# ---------------------------------------------------------------------------
# Slice 4E.2 � universal knowledge ingestion (one contract for all activity)
# ---------------------------------------------------------------------------
# The canonical model is fed by the SAME durable events the rest of the org
# already emits � messages, tasks, meetings, memories and patterns speak one
# internal language via canonical_engine.ingest_event. One event, many
# consumers; no new emission sites. Noise never becomes knowledge; governance
# scope and source identity are preserved; replays are exact-once.
# ---------------------------------------------------------------------------


@on("messaging.message_sent")
@on("task.created")
@on("task.updated")
@on("task.transitioned")
@on("task.blocked")
@on("task.completed")
@on("task.unblocked")
@on("task.deleted")
@on("meeting.created")
@on("meeting.updated")
@on("meeting.started")
@on("meeting.ended")
@on("meeting.completed")
@on("memory.recorded")
@on("pattern.detected")
@on("pattern.updated")
@on("pattern.confirmed")
async def handle_universal_knowledge_ingest(db, event, payload):
    """Funnel meaningful company activity into the canonical knowledge model."""
    from app.knowledge.canonical_service import canonical_engine

    result = await canonical_engine.ingest_event(db, event=event, payload=payload)
    if result.get("status") != "ok":
        return
    # 4E.3 — keep the topics this source touched synthesized: bounded,
    # idempotent and inside the same transaction as the ingest.
    from app.knowledge.synthesis_engine import synthesis_engine

    await synthesis_engine.synthesize_for_source(
        db,
        organization_id=result.get("organization_id") or payload.get("organization_id") or event.organization_id,
        source_type=result["entity_type"],
        source_id=result["entity_id"],
    )


# ---------------------------------------------------------------------------
# Slice 4F.1 — Universal People Intelligence Foundation (event bridge)
# ---------------------------------------------------------------------------
# The people layer is event-driven from the SAME durable events the platform
# already emits (user.created, employee.joined, employee.offboarded,
# employee.promoted, user.status.updated, team.member.added/removed). Every
# handler is replay-safe: the human/journal row keyed by the durable event id
# makes a replay exact-once. Handlers never commit — the EventBus owns the
# transaction.
# ---------------------------------------------------------------------------


async def _people_person(
    db: AsyncSession, org_id: Optional[str], payload: dict[str, Any]
) -> Optional[Employee]:
    """Resolve the canonical person behind a people event payload."""
    org_id = payload.get("organization_id") or org_id
    if not org_id:
        return None
    person_id = payload.get("employee_id") or payload.get("person_id")
    if person_id:
        employee = await db.get(Employee, person_id)
        if employee is not None and employee.organization_id == org_id:
            return employee
        return None
    user_id = payload.get("user_id") or payload.get("id")
    if user_id:
        row = await db.execute(
            select(Employee).where(
                Employee.organization_id == org_id, Employee.user_id == user_id
            )
        )
        return row.scalar_one_or_none()
    return None


async def _people_applied(
    db: AsyncSession, org_id: str, person_id: str, event_id: str
) -> bool:
    """Exact-once guard: has this durable event already been applied to the
    person's timeline?"""
    row = (
        await db.execute(
            select(PeopleTimeline.id).where(
                PeopleTimeline.organization_id == org_id,
                PeopleTimeline.person_id == person_id,
                PeopleTimeline.event_id == event_id,
            )
        )
    ).scalars().first()
    return row is not None


@on("user.created")
async def handle_people_user_joined(db, event, payload):
    """A person joined: canonical sync + person.created evidence."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    await people_engine.ensure_person(db, organization_id=org_id, person_id=person.id)
    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.journal(
        db, org_id, person.id, kind="person.created",
        title=f"{person.full_name} joined the company",
        detail=person.designation or "New team member joined the organization.",
        meta={"employee_number": person.employee_number, "email": person.email},
        event_id=event.id,
    )


@on("employee.joined")
async def handle_people_employee_joined(db, event, payload):
    """Hire completed: canonical sync + person.created evidence."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    await people_engine.ensure_person(db, organization_id=org_id, person_id=person.id)
    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.journal(
        db, org_id, person.id, kind="person.created",
        title=f"{person.full_name} joined the company",
        detail="Employee joined through the recruitment pipeline.",
        meta={"employee_number": person.employee_number},
        event_id=event.id,
    )


@on("employee.offboarded")
async def handle_people_employee_offboarded(db, event, payload):
    """Departure: close the open membership window — history is retained."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.set_membership(
        db, organization_id=org_id, person_id=person.id,
        employment_status="departed",
        note=f"Offboarding: {payload.get('reason') or 'no reason recorded'}",
        source_type="event", source_id=event.id,
        actor_id=payload.get("actor_id"),
        event_id=event.id,
    )


@on("employee.promoted")
async def handle_people_employee_promoted(db, event, payload):
    """Promotion: open a new primary role window (demoting the previous
    primary) — the designation mirror follows."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    new_title = payload.get("new_designation") or person.designation
    if not new_title:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.assign_role(
        db, organization_id=org_id, person_id=person.id,
        role_title=new_title, role_type="functional", is_primary=True,
        source_type="event", source_id=event.id,
        actor_id=payload.get("actor_id"),
        event_id=event.id,
    )


@on("user.status.updated")
async def handle_people_user_status(db, event, payload):
    """User status changes open/close membership windows accordingly."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    status = (payload.get("status") or "").lower()
    mapping = {
        "active": "active",
        "inactive": "inactive",
        "suspended": "suspended",
        "pending": "invited",
        "invited": "invited",
    }
    membership_status = mapping.get(status)
    if membership_status is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.set_membership(
        db, organization_id=org_id, person_id=person.id,
        employment_status=membership_status,
        note=f"User account status changed to {status}.",
        source_type="event", source_id=event.id,
        actor_id=payload.get("actor_id"),
        event_id=event.id,
    )


@on("team.member.added")
async def handle_people_team_member_added(db, event, payload):
    """Evidence a team join in the people timeline."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    team = await db.get(Team, payload.get("team_id"))
    await people_engine.journal(
        db, org_id, person.id, kind="team.joined",
        title=f"Joined team: {team.name if team else payload.get('team_id')}",
        detail="Team membership recorded on the people timeline.",
        meta={"team_id": payload.get("team_id")},
        event_id=event.id,
    )


@on("team.member.removed")
async def handle_people_team_member_removed(db, event, payload):
    """Evidence a team leave in the people timeline."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    team = await db.get(Team, payload.get("team_id"))
    await people_engine.journal(
        db, org_id, person.id, kind="team.left",
        title=f"Left team: {team.name if team else payload.get('team_id')}",
        detail="Team membership removed.",
        meta={"team_id": payload.get("team_id")},
        event_id=event.id,
    )


@on("employee.created")
async def handle_people_employee_created(db, event, payload):
    """A person was created through the employee service: canonical sync +
    person.created evidence."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    await people_engine.ensure_person(db, organization_id=org_id, person_id=person.id)
    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.journal(
        db, org_id, person.id, kind="person.created",
        title=f"{person.full_name} joined the company",
        detail="Employee record created.",
        meta={"employee_number": person.employee_number, "email": person.email},
        event_id=event.id,
    )


@on("manager.changed")
async def handle_people_manager_changed(db, event, payload):
    """Reporting mirror: the manager change opens/closes the reports_to
    window."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.set_reporting(
        db, organization_id=org_id, person_id=person.id,
        relationship_type="reports_to",
        manager_person_id=payload.get("to"),
        note=f"Manager changed: now {'reports to ' + str(payload.get('to')) if payload.get('to') else 'reports to no one'}.",
        source_type="event", source_id=event.id,
        actor_id=payload.get("actor_id"),
        event_id=event.id,
    )


@on("employee.status.changed")
async def handle_people_employee_status_changed(db, event, payload):
    """Employment status transitions open/close membership windows."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    status = (payload.get("to") or person.status or "").lower()
    if status not in MEMBERSHIP_STATUSES:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.set_membership(
        db, organization_id=org_id, person_id=person.id,
        employment_status=status,
        note=f"Employment status changed to {status}.",
        source_type="event", source_id=event.id,
        actor_id=payload.get("actor_id"),
        event_id=event.id,
    )


@on("employee.transferred")
async def handle_people_employee_transferred(db, event, payload):
    """Evidence a department/team transfer in the people timeline."""
    org_id = payload.get("organization_id") or event.organization_id
    person = await _people_person(db, org_id, payload)
    if person is None:
        return
    from app.people.people_engine import people_engine

    if await _people_applied(db, org_id, person.id, event.id):
        return
    await people_engine.journal(
        db, org_id, person.id, kind="person.transferred",
        title="Moved between departments/teams",
        detail=(f"Transferred to department {payload.get('to_department')}"
                if payload.get("to_department") else "Transfer recorded."),
        meta={
            "from_department": payload.get("from_department"),
            "to_department": payload.get("to_department"),
        },
        event_id=event.id,
    )
