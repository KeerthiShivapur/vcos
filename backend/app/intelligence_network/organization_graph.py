"""Unified enterprise graph — one connected view of the entire organization.

Builds nodes and edges for every major entity type and answers structural
questions: who works with whom, which project depends on what, shortest
connections between people and knowledge, community structure.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.communication import CommunityPost
from app.models.customer import Customer
from app.models.department import Department
from app.models.employee import Employee
from app.models.goal import Goal
from app.models.knowledge import Document, WikiPage
from app.models.meeting import Meeting, MeetingAttendee
from app.models.organization_edge import OrganizationEdge
from app.models.organization_node import OrganizationNode
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.team import Team


class OrganizationGraphService:
    async def rebuild(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> dict[str, Any]:
        """Rebuild the whole graph for an organization (idempotent)."""
        await db.execute(
            delete(OrganizationNode).where(OrganizationNode.organization_id == organization_id)
        )
        await db.execute(
            delete(OrganizationEdge).where(OrganizationEdge.organization_id == organization_id)
        )
        await db.flush()

        node_count = 0
        edge_count = 0
        now = utcnow()

        # ---- people
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        emp_by_user: dict[str, str] = {}
        for emp in employees:
            node_id = self._upsert(
                db, organization_id, "employee", emp.id, emp.full_name or emp.id,
                {"title": getattr(emp, "title", None), "department_id": getattr(emp, "department_id", None)},
                now,
            )
            node_count += 1
            if getattr(emp, "user_id", None):
                emp_by_user[str(emp.user_id)] = str(emp.id)

        departments = (
            await db.execute(
                select(Department).where(Department.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        for dep in departments:
            node_count += self._upsert(
                db, organization_id, "department", dep.id, dep.name or dep.id, {}, now
            )
        for emp in employees:
            if getattr(emp, "department_id", None):
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", emp.id, "department", str(emp.department_id),
                    "member_of", 1.0, {}, now,
                )
            manager_id = getattr(emp, "manager_id", None)
            if manager_id:
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", emp.id, "employee", str(manager_id),
                    "reports_to", 1.0, {}, now,
                )

        # ---- teams + membership
        teams = (
            await db.execute(
                select(Team).where(Team.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        for team in teams:
            node_count += self._upsert(
                db, organization_id, "team", team.id, team.name or team.id, {}, now
            )

        # ---- projects + tasks + members
        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        project_by_id: dict[str, str] = {}
        for project in projects:
            project_by_id[str(project.id)] = project.name or project.id
            node_count += self._upsert(
                db, organization_id, "project", project.id, project.name or project.id,
                {"status": getattr(project, "status", None)}, now,
            )
            owner = getattr(project, "owner_id", None)
            if owner:
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", str(owner), "project", str(project.id),
                    "owns", 1.0, {}, now,
                )
        members = (
            await db.execute(
                select(ProjectMember).where(ProjectMember.project_id.in_(project_by_id.keys())).limit(1000)
            )
        ).scalars().all()
        for member in members:
            edge_count += self._upsert_edge(
                db, organization_id, "employee", str(member.employee_id),
                "project", str(member.project_id), "works_on", 1.0, {}, now,
            )

        tasks = (
            await db.execute(
                select(Task).where(Task.organization_id == organization_id).limit(1000)
            )
        ).scalars().all()
        for task in tasks:
            node_count += self._upsert(
                db, organization_id, "task", task.id, task.title or task.id,
                {"status": getattr(task, "status", None), "project_id": getattr(task, "project_id", None)},
                now,
            )
            assignee = getattr(task, "assignee_id", None)
            if assignee:
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", str(assignee), "task", str(task.id),
                    "assigned_to", 1.0, {}, now,
                )
            pid = getattr(task, "project_id", None)
            if pid:
                edge_count += self._upsert_edge(
                    db, organization_id, "task", str(task.id), "project", str(pid),
                    "linked_to", 1.0, {}, now,
                )

        # ---- meetings + attendees
        meetings = (
            await db.execute(
                select(Meeting).where(Meeting.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        meeting_ids = [m.id for m in meetings]
        for meeting in meetings:
            node_count += self._upsert(
                db, organization_id, "meeting", meeting.id, meeting.title or meeting.id,
                {"start_at": meeting.start_at.isoformat() if getattr(meeting, "start_at", None) else None},
                now,
            )
        if meeting_ids:
            attendees = (
                await db.execute(
                    select(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids)).limit(2000)
                )
            ).scalars().all()
            for attendee in attendees:
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", str(attendee.employee_id),
                    "meeting", str(attendee.meeting_id), "attended", 1.0, {}, now,
                )

        # ---- knowledge
        documents = (
            await db.execute(
                select(Document).where(Document.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        for doc in documents:
            node_count += self._upsert(
                db, organization_id, "document", doc.id, doc.title or doc.id,
                {"category": getattr(doc, "category", None)}, now,
            )
            uploaded_by = getattr(doc, "uploaded_by", None)
            if uploaded_by:
                edge_count += self._upsert_edge(
                    db, organization_id, "employee", str(uploaded_by), "document", str(doc.id),
                    "created", 1.0, {}, now,
                )
            pid = getattr(doc, "project_id", None)
            if pid:
                edge_count += self._upsert_edge(
                    db, organization_id, "document", str(doc.id), "project", str(pid),
                    "linked_to", 1.0, {}, now,
                )
        wiki_pages = (
            await db.execute(
                select(WikiPage).where(WikiPage.organization_id == organization_id).limit(500)
            )
        ).scalars().all()
        for page in wiki_pages:
            node_count += self._upsert(
                db, organization_id, "knowledge", page.id, page.title or page.id,
                {"category": getattr(page, "category", None)}, now,
            )

        # ---- goals
        goals = (
            await db.execute(
                select(Goal).where(Goal.organization_id == organization_id).limit(200)
            )
        ).scalars().all()
        for goal in goals:
            node_count += self._upsert(
                db, organization_id, "goal", goal.id, goal.name or goal.id,
                {"status": getattr(goal, "status", None)}, now,
            )

        # ---- customers
        customers = (
            await db.execute(
                select(Customer).where(Customer.organization_id == organization_id).limit(300)
            )
        ).scalars().all()
        for customer in customers:
            node_count += self._upsert(
                db, organization_id, "customer", customer.id, customer.company_name or customer.id,
                {"industry": getattr(customer, "industry", None)}, now,
            )

        await db.flush()
        return {
            "organization_id": organization_id,
            "nodes": node_count,
            "edges": edge_count,
            "built_at": now.isoformat(),
        }

    def _upsert(
        self, db: AsyncSession, organization_id: str, node_type: str, external_id: str,
        name: str, properties: dict[str, Any], now: Any,
    ) -> int:
        db.add(
            OrganizationNode(
                organization_id=organization_id,
                node_type=node_type,
                external_id=str(external_id),
                name=name[:255],
                properties=properties,
                importance=1.0,
                last_seen_at=now,
            )
        )
        return 1

    def _upsert_edge(
        self, db: AsyncSession, organization_id: str, source_type: str, source_id: str,
        target_type: str, target_id: str, relation: str, weight: float,
        properties: dict[str, Any], now: Any,
    ) -> int:
        if str(source_id) == str(target_id):
            return 0
        db.add(
            OrganizationEdge(
                organization_id=organization_id,
                source_type=source_type,
                source_id=str(source_id),
                target_type=target_type,
                target_id=str(target_id),
                relation=relation,
                weight=weight,
                properties=properties,
            )
        )
        return 1

    async def stats(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        node_counts = (
            await db.execute(
                select(OrganizationNode.node_type, func.count(OrganizationNode.id))
                .where(OrganizationNode.organization_id == organization_id)
                .group_by(OrganizationNode.node_type)
            )
        ).all()
        edge_counts = (
            await db.execute(
                select(OrganizationEdge.relation, func.count(OrganizationEdge.id))
                .where(OrganizationEdge.organization_id == organization_id)
                .group_by(OrganizationEdge.relation)
            )
        ).all()
        return {
            "organization_id": organization_id,
            "total_nodes": sum(n for _, n in node_counts),
            "total_edges": sum(n for _, n in edge_counts),
            "nodes_by_type": {t: int(n) for t, n in node_counts},
            "edges_by_relation": {r: int(n) for r, n in edge_counts},
        }

    async def nodes(
        self, db: AsyncSession, organization_id: str, *, node_type: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        stmt = select(OrganizationNode).where(OrganizationNode.organization_id == organization_id)
        if node_type:
            stmt = stmt.where(OrganizationNode.node_type == node_type)
        rows = (
            await db.execute(stmt.order_by(OrganizationNode.name).limit(limit))
        ).scalars().all()
        return {
            "total": len(rows),
            "nodes": [
                {
                    "id": r.id, "node_type": r.node_type, "external_id": r.external_id,
                    "name": r.name, "properties": r.properties or {},
                }
                for r in rows
            ],
        }

    async def neighbors(
        self, db: AsyncSession, organization_id: str, node_type: str, node_id: str
    ) -> dict[str, Any]:
        edges = (
            await db.execute(
                select(OrganizationEdge)
                .where(
                    OrganizationEdge.organization_id == organization_id,
                    OrganizationEdge.source_type == node_type,
                    OrganizationEdge.source_id == node_id,
                )
                .limit(100)
            )
        ).scalars().all()
        return {
            "node": {"node_type": node_type, "node_id": node_id},
            "neighbors": [
                {
                    "id": e.id, "target_type": e.target_type, "target_id": e.target_id,
                    "relation": e.relation, "weight": e.weight,
                }
                for e in edges
            ],
        }

    async def path(
        self, db: AsyncSession, organization_id: str,
        start_type: str, start_id: str, end_type: str, end_id: str,
    ) -> dict[str, Any]:
        """BFS shortest path between two entities."""
        nodes = (
            await db.execute(
                select(OrganizationNode).where(OrganizationNode.organization_id == organization_id).limit(2000)
            )
        ).scalars().all()
        edges = (
            await db.execute(
                select(OrganizationEdge).where(OrganizationEdge.organization_id == organization_id).limit(8000)
            )
        ).scalars().all()
        node_key = {f"{n.node_type}:{n.external_id}": n for n in nodes}
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            key = f"{e.source_type}:{e.source_id}"
            adjacency.setdefault(key, []).append((f"{e.target_type}:{e.target_id}", e.relation))
            adjacency.setdefault(f"{e.target_type}:{e.target_id}", []).append((key, e.relation))
        start = f"{start_type}:{start_id}"
        end = f"{end_type}:{end_id}"
        if start not in adjacency or end not in adjacency:
            return {"path": [], "connected": False}
        from collections import deque

        queue: deque[list[tuple[str, str]]] = deque([[start]])
        visited = {start}
        while queue:
            current_path = queue.popleft()
            last = current_path[-1][0]
            for neighbor, relation in adjacency.get(last, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_path = current_path + [(neighbor, relation)]
                if neighbor == end:
                    return {
                        "connected": True,
                        "length": len(new_path) - 1,
                        "path": [
                            {
                                "node_type": key.split(":")[0],
                                "external_id": key.split(":")[1],
                                "name": node_key[key].name if key in node_key else key,
                                "relation": relation if i > 0 else None,
                            }
                            for i, (key, relation) in enumerate(new_path)
                        ],
                    }
                queue.append(new_path)
        return {"path": [], "connected": False}


organization_graph = OrganizationGraphService()
