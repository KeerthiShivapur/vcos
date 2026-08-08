"""Organization graph — nodes and edges for visualization (Phase 2)."""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeePresence
from app.schemas.people import GraphEdge, GraphNode, OrganizationGraph

logger = logging.getLogger("vcos.people")

ACTIVE_STATUSES = ("active", "probation", "notice")


class GraphService:
    async def build(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        include_locations: bool = True,
        include_teams: bool = True,
        include_work: bool = True,
    ) -> OrganizationGraph:
        from app.models.department import Department, Location
        from app.models.team import Team

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()

        employees = (
            await db.execute(
                select(Employee).where(
                    Employee.organization_id == organization_id,
                    Employee.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
        online_ids = set(
            (
                await db.execute(
                    select(EmployeePresence.employee_id).where(
                        EmployeePresence.organization_id == organization_id,
                        EmployeePresence.is_online.is_(True),
                    )
                )
            ).scalars().all()
        )
        for e in employees:
            nodes.append(
                GraphNode(
                    id=e.id,
                    label=e.full_name,
                    kind="employee",
                    designation=e.designation,
                    meta={"employee_number": e.employee_number, "is_online": e.id in online_ids},
                )
            )
            if e.manager_id:
                key = ("manages", e.manager_id, e.id)
                if key not in seen_edges:
                    edges.append(GraphEdge(source=e.manager_id, target=e.id, relation="manages"))
                    seen_edges.add(key)

        departments = (
            await db.execute(
                select(Department).where(Department.organization_id == organization_id)
            )
        ).scalars().all()
        dep_names = {d.id: d.name for d in departments}
        for d in departments:
            nodes.append(
                GraphNode(
                    id=f"dep:{d.id}", label=d.name, kind="department",
                    meta={"code": d.code},
                )
            )
            if d.head_id:
                key = ("head_of", d.head_id, f"dep:{d.id}")
                if key not in seen_edges:
                    edges.append(GraphEdge(source=d.head_id, target=f"dep:{d.id}", relation="head_of"))
                    seen_edges.add(key)
            if d.parent_id:
                key = ("child_of", f"dep:{d.parent_id}", f"dep:{d.id}")
                if key not in seen_edges:
                    edges.append(GraphEdge(source=f"dep:{d.parent_id}", target=f"dep:{d.id}", relation="head_of"))
                    seen_edges.add(key)

        teams: list[Team] = []
        if include_teams:
            teams = (
                await db.execute(
                    select(Team).where(Team.organization_id == organization_id)
                )
            ).scalars().all()
            for t in teams:
                nodes.append(
                    GraphNode(
                        id=f"team:{t.id}", label=t.name, kind="team",
                        meta={"code": t.code},
                    )
                )
                if t.lead_id:
                    key = ("leads", t.lead_id, f"team:{t.id}")
                    if key not in seen_edges:
                        edges.append(GraphEdge(source=t.lead_id, target=f"team:{t.id}", relation="leads"))
                        seen_edges.add(key)
                if t.department_id:
                    key = ("member_of", f"team:{t.id}", f"dep:{t.department_id}")
                    if key not in seen_edges:
                        edges.append(
                            GraphEdge(source=f"team:{t.id}", target=f"dep:{t.department_id}", relation="member_of")
                        )
                        seen_edges.add(key)

        locations: list[Location] = []
        if include_locations:
            locations = (
                await db.execute(
                    select(Location).where(Location.organization_id == organization_id)
                )
            ).scalars().all()
            for loc in locations:
                nodes.append(
                    GraphNode(
                        id=f"loc:{loc.id}", label=loc.name, kind="location",
                        meta={"city": loc.city, "country": loc.country},
                    )
                )
            loc_map = {l.id: f"loc:{l.id}" for l in locations}
            for e in employees:
                if e.location_id and e.location_id in loc_map:
                    key = ("located_at", e.id, loc_map[e.location_id])
                    if key not in seen_edges:
                        edges.append(GraphEdge(source=e.id, target=loc_map[e.location_id], relation="located_at"))
                        seen_edges.add(key)

        team_ids = {t.id for t in teams}
        for e in employees:
            if e.team_id and e.team_id in team_ids:
                key = ("member_of", e.id, f"team:{e.team_id}")
                if key not in seen_edges:
                    edges.append(GraphEdge(source=e.id, target=f"team:{e.team_id}", relation="member_of"))
                    seen_edges.add(key)
            if e.department_id and e.department_id in dep_names:
                key = ("member_of", e.id, f"dep:{e.department_id}")
                if key not in seen_edges:
                    edges.append(GraphEdge(source=e.id, target=f"dep:{e.department_id}", relation="member_of"))
                    seen_edges.add(key)

        if include_work:
            await self._add_work(db, organization_id, nodes, edges, seen_edges)

        return OrganizationGraph(nodes=nodes, edges=edges)

    async def _add_work(
        self,
        db: AsyncSession,
        organization_id: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        seen_edges: set[tuple[str, str, str]],
    ) -> None:
        """Phase 3 — work entities (projects, tasks, goals, meetings) join the graph."""
        from app.models.goal import Goal
        from app.models.meeting import Meeting, MeetingAttendee
        from app.models.project import Project, ProjectMember
        from app.models.task import Task

        def add_edge(source: str, target: str, relation: str) -> None:
            key = (relation, source, target)
            if key not in seen_edges:
                edges.append(GraphEdge(source=source, target=target, relation=relation))
                seen_edges.add(key)

        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id, Project.status != "cancelled"
                )
            )
        ).scalars().all()
        member_rows = (
            await db.execute(
                select(ProjectMember).where(ProjectMember.organization_id == organization_id)
            )
        ).scalars().all()
        members_by_project: dict[str, list[str]] = {}
        for row in member_rows:
            members_by_project.setdefault(row.project_id, []).append(row.employee_id)

        for project in projects:
            node_id = f"proj:{project.id}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=project.name,
                    kind="project",
                    meta={"status": project.status, "code": project.code, "progress": project.progress or 0},
                )
            )
            if project.owner_id:
                add_edge(project.owner_id, node_id, "owns")
            for member_id in members_by_project.get(project.id, []):
                add_edge(member_id, node_id, "works_on")

        active_tasks = (
            await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.status.notin_(("completed", "archived")),
                    Task.assignee_id.isnot(None),
                )
                .order_by(Task.updated_at.desc())
                .limit(200)
            )
        ).scalars().all()
        for task in active_tasks:
            node_id = f"task:{task.id}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=task.title,
                    kind="task",
                    meta={"status": task.status, "priority": task.priority},
                )
            )
            add_edge(task.assignee_id, node_id, "assigned_to")
            if task.project_id:
                add_edge(node_id, f"proj:{task.project_id}", "belongs_to")

        goals = (
            await db.execute(
                select(Goal).where(Goal.organization_id == organization_id, Goal.status != "completed")
            )
        ).scalars().all()
        for goal in goals:
            node_id = f"goal:{goal.id}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=goal.name,
                    kind="goal",
                    meta={"status": goal.status, "scope": goal.scope, "progress": goal.progress or 0},
                )
            )
            if goal.owner_id:
                add_edge(goal.owner_id, node_id, "owns")
            if goal.project_id:
                add_edge(node_id, f"proj:{goal.project_id}", "belongs_to")

        meetings = (
            await db.execute(
                select(Meeting)
                .where(
                    Meeting.organization_id == organization_id,
                    Meeting.status.in_(("scheduled", "in_progress")),
                )
                .order_by(Meeting.start_at.desc())
                .limit(100)
            )
        ).scalars().all()
        meeting_ids = [m.id for m in meetings]
        attendees_by_meeting: dict[str, list[str]] = {}
        if meeting_ids:
            rows = await db.execute(
                select(MeetingAttendee).where(
                    MeetingAttendee.organization_id == organization_id,
                    MeetingAttendee.meeting_id.in_(meeting_ids),
                )
            )
            for row in rows.scalars().all():
                attendees_by_meeting.setdefault(row.meeting_id, []).append(row.employee_id)
        for meeting in meetings:
            node_id = f"meeting:{meeting.id}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=meeting.title,
                    kind="meeting",
                    meta={"status": meeting.status, "meeting_type": meeting.meeting_type},
                )
            )
            for attendee_id in attendees_by_meeting.get(meeting.id, []):
                add_edge(attendee_id, node_id, "attends")
            if meeting.project_id:
                add_edge(node_id, f"proj:{meeting.project_id}", "belongs_to")

        await self._add_knowledge(db, organization_id, nodes, edges, seen_edges)

    async def _add_knowledge(
        self,
        db: AsyncSession,
        organization_id: str,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        seen_edges: set[tuple[str, str, str]],
    ) -> None:
        """Phase 4 — knowledge entities join the org graph, linked to their projects."""
        from app.knowledge import knowledge_base as kb

        def add_edge(source: str, target: str, relation: str) -> None:
            key = (relation, source, target)
            if key not in seen_edges:
                edges.append(GraphEdge(source=source, target=target, relation=relation))
                seen_edges.add(key)

        for kind, model in kb.KIND_MODELS.items():
            stmt = (
                select(model)
                .where(
                    model.organization_id == organization_id,
                    model.status.in_(kb.published_statuses(kind)),
                )
                .order_by(model.updated_at.desc())
                .limit(100)
            )
            rows = (await db.execute(stmt)).scalars().all()
            for row in rows:
                node_id = f"kb:{kind}:{row.id}"
                nodes.append(
                    GraphNode(
                        id=node_id,
                        label=row.title,
                        kind=kind,
                        meta={"url": kb.entity_url(kind, row.id), "status": row.status},
                    )
                )
                project_id = getattr(row, "project_id", None)
                if project_id:
                    add_edge(node_id, f"proj:{project_id}", "belongs_to")
                author_id = getattr(row, "author_id", None)
                if author_id:
                    add_edge(author_id, node_id, "authors")
                owner_id = getattr(row, "owner_id", None)
                if owner_id:
                    add_edge(owner_id, node_id, "owns")


graph_service = GraphService()
