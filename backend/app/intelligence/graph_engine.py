"""Phase 9.4 — Organization graph engine.

Every relationship updates automatically. The graph is stored as typed,
weighted edges (OrgGraphEdge) with evidence, so queries can find:

    - experts (employee->skill/document clusters)
    - mentors / collaboration paths
    - dependencies and bottlenecks
    - who-knows-who and cross-team collaboration

The graph worker rebuilds structural edges (reports_to, member_of, works_on)
in bulk; event handlers add activity edges in real time.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.communication import Conversation, Message
from app.models.employee import Employee
from app.models.governance import GovernanceScope
from app.models.intelligence import GraphUpdate, OrgGraphEdge
from app.models.knowledge import Decision
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.intelligence.company_context import resolve_caller_access, resolve_accessible_ids, CallerAccess

logger = logging.getLogger("vcos.intelligence.graph")

STRUCTURAL_RELATIONS = ("reports_to", "member_of", "works_on", "manages", "owns")


class GraphEngine:
    # ------------------------------------------------------------------ mutations

    async def upsert_edge(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relation: str,
        weight: float = 1.0,
        evidence: Optional[str] = None,
        record_update: bool = True,
    ) -> OrgGraphEdge:
        row = (
            await db.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == organization_id,
                    OrgGraphEdge.source_type == source_type,
                    OrgGraphEdge.source_id == source_id,
                    OrgGraphEdge.target_type == target_type,
                    OrgGraphEdge.target_id == target_id,
                    OrgGraphEdge.relation == relation,
                )
            )
        ).scalar_one_or_none()
        now = utcnow()
        if row is None:
            from sqlalchemy.exc import IntegrityError

            row = OrgGraphEdge(
                organization_id=organization_id,
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                target_id=target_id,
                relation=relation,
                weight=weight,
                evidence=evidence,
                active=True,
            )
            db.add(row)
            try:
                async with db.begin_nested():
                    await db.flush()
            except IntegrityError:
                # concurrent workers can both pass the select above for the
                # same edge; re-read the committed row and update it instead.
                row = (
                    await db.execute(
                        select(OrgGraphEdge).where(
                            OrgGraphEdge.organization_id == organization_id,
                            OrgGraphEdge.source_type == source_type,
                            OrgGraphEdge.source_id == source_id,
                            OrgGraphEdge.target_type == target_type,
                            OrgGraphEdge.target_id == target_id,
                            OrgGraphEdge.relation == relation,
                        )
                    )
                ).scalar_one()
                row.weight = max(row.weight, weight)
                row.evidence = evidence or row.evidence
                row.active = True
                row.updated_at = now
                change = "edge_updated"
            else:
                change = "edge_added"
        else:
            row.weight = max(row.weight, weight)
            row.evidence = evidence or row.evidence
            row.active = True
            row.updated_at = now
            change = "edge_updated"
        if record_update:
            db.add(
                GraphUpdate(
                    organization_id=organization_id,
                    change_type=change,
                    relation=relation,
                    source_type=source_type, source_id=source_id,
                    target_type=target_type, target_id=target_id,
                    detail=evidence,
                )
            )
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="graph.updated",
                organization_id=organization_id,
                payload={
                    "change": change,
                    "relation": relation,
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_type": target_type,
                    "target_id": target_id,
                },
            )
        return row

    async def deactivate_edge(self, db: AsyncSession, *, organization_id: str, edge_id: str) -> bool:
        edge = await db.get(OrgGraphEdge, edge_id)
        if edge is None or edge.organization_id != organization_id:
            return False
        edge.active = False
        edge.updated_at = utcnow()
        db.add(
            GraphUpdate(
                organization_id=organization_id,
                change_type="edge_deactivated",
                relation=edge.relation,
                source_type=edge.source_type, source_id=edge.source_id,
                target_type=edge.target_type, target_id=edge.target_id,
            )
        )
        from app.events.publisher import publish_background_event

        await publish_background_event(
            db,
            name="graph.updated",
            organization_id=organization_id,
            payload={
                "change": "edge_deactivated",
                "relation": edge.relation,
                "edge_id": edge_id,
            },
        )
        return True

    async def rebuild_structural(
        self, db: AsyncSession, *, organization_id: str,
    ) -> int:
        """Bulk rebuild of structural edges: reports_to, member_of, works_on."""
        employees = (
            await db.execute(
                select(Employee).where(Employee.organization_id == organization_id)
            )
        ).scalars().all()
        count = 0
        for employee in employees:
            if employee.manager_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="employee", source_id=employee.id,
                    target_type="employee", target_id=employee.manager_id,
                    relation="reports_to", weight=1.0, evidence="Org structure",
                    record_update=False,
                )
                count += 1
            if employee.department_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="employee", source_id=employee.id,
                    target_type="department", target_id=employee.department_id,
                    relation="member_of", weight=1.0, evidence="Department membership",
                    record_update=False,
                )
                count += 1
            if employee.team_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="employee", source_id=employee.id,
                    target_type="team", target_id=employee.team_id,
                    relation="member_of", weight=1.0, evidence="Team membership",
                    record_update=False,
                )
                count += 1

        members = (
            await db.execute(
                select(ProjectMember).where(ProjectMember.organization_id == organization_id)
            )
        ).scalars().all()
        for member in members:
            await self.upsert_edge(
                db, organization_id=organization_id,
                source_type="employee", source_id=member.employee_id,
                target_type="project", target_id=member.project_id,
                relation="works_on", weight=1.0, evidence="Project member",
                record_update=False,
            )
            count += 1

        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id)
            )
        ).scalars().all()
        for project in projects:
            if project.owner_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="employee", source_id=project.owner_id,
                    target_type="project", target_id=project.id,
                    relation="owns", weight=1.0, evidence="Project owner",
                    record_update=False,
                )
                count += 1

        tasks = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.assignee_id.isnot(None),
                )
            )
        ).scalars().all()
        for task in tasks:
            await self.upsert_edge(
                db, organization_id=organization_id,
                source_type="employee", source_id=task.assignee_id,
                target_type="task", target_id=task.id,
                relation="assigned_to", weight=1.0, evidence="Task assignment",
                record_update=False,
            )
            count += 1
        if count:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="graph.updated",
                organization_id=organization_id,
                payload={"change": "structural_rebuild", "edges": count},
            )
        return count

    # ------------------------------------------- Slice 4D.1 relationship edges

    async def sync_entity_edges(
        self, db: AsyncSession, *, organization_id: str, entity_type: str, entity_id: str,
    ) -> int:
        """Upsert the relationship edges of one entity (bounded, indexed).

        Change-driven: callers (event handlers / the company intel worker)
        invoke this for the exact entity a change touched — never a scan.
          task -> project        : belongs_to
          decision -> scope      : governed_by (via the project a scope wraps)
          conversation -> message: contains
        """
        count = 0
        if entity_type == "task":
            task = await db.get(Task, entity_id)
            if task and task.organization_id == organization_id and task.project_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="task", source_id=task.id,
                    target_type="project", target_id=task.project_id,
                    relation="belongs_to", weight=1.0, evidence="Task project relationship",
                    record_update=False,
                )
                count += 1
        elif entity_type == "decision":
            decision = await db.get(Decision, entity_id)
            if decision and decision.organization_id == organization_id and decision.project_id:
                scope = (
                    await db.execute(
                        select(GovernanceScope.id).where(
                            GovernanceScope.organization_id == organization_id,
                            GovernanceScope.scope_type == "project",
                            GovernanceScope.entity_id == decision.project_id,
                        )
                    )
                ).scalars().first()
                if scope:
                    await self.upsert_edge(
                        db, organization_id=organization_id,
                        source_type="decision", source_id=decision.id,
                        target_type="scope", target_id=scope,
                        relation="governed_by", weight=1.0, evidence="Decision under project scope",
                        record_update=False,
                    )
                    count += 1
        elif entity_type == "conversation":
            conversation = await db.get(Conversation, entity_id)
            if conversation and conversation.organization_id == organization_id:
                recent = (
                    await db.execute(
                        select(Message.id).where(
                            Message.organization_id == organization_id,
                            Message.conversation_id == conversation.id,
                        ).order_by(Message.created_at.desc()).limit(5)
                    )
                ).scalars().all()
                for message_id in recent:
                    await self.upsert_edge(
                        db, organization_id=organization_id,
                        source_type="conversation", source_id=conversation.id,
                        target_type="message", target_id=message_id,
                        relation="contains", weight=1.0, evidence="Conversation message",
                        record_update=False,
                    )
                    count += 1
        elif entity_type == "message":
            message = await db.get(Message, entity_id)
            if message and message.organization_id == organization_id:
                await self.upsert_edge(
                    db, organization_id=organization_id,
                    source_type="conversation", source_id=message.conversation_id,
                    target_type="message", target_id=message.id,
                    relation="contains", weight=1.0, evidence="Conversation message",
                    record_update=False,
                )
                count += 1
        return count

    async def sync_recent_relationships(
        self, db: AsyncSession, *, organization_id: str, each: int = 5,
    ) -> int:
        """Bounded recent-relationship sync used by the company intel worker."""
        count = 0
        task_ids = (
            await db.execute(
                select(Task.id)
                .where(Task.organization_id == organization_id, Task.project_id.isnot(None))
                .order_by(Task.updated_at.desc())
                .limit(each)
            )
        ).scalars().all()
        for task_id in task_ids:
            count += await self.sync_entity_edges(db, organization_id=organization_id, entity_type="task", entity_id=task_id)
        decision_ids = (
            await db.execute(
                select(Decision.id)
                .where(Decision.organization_id == organization_id, Decision.project_id.isnot(None))
                .order_by(Decision.updated_at.desc())
                .limit(each)
            )
        ).scalars().all()
        for decision_id in decision_ids:
            count += await self.sync_entity_edges(db, organization_id=organization_id, entity_type="decision", entity_id=decision_id)
        conversation_ids = (
            await db.execute(
                select(Conversation.id)
                .where(Conversation.organization_id == organization_id)
                .order_by(Conversation.updated_at.desc())
                .limit(each)
            )
        ).scalars().all()
        for conversation_id in conversation_ids:
            count += await self.sync_entity_edges(db, organization_id=organization_id, entity_type="conversation", entity_id=conversation_id)
        return count

    async def traverse(
        self, db: AsyncSession, *, organization_id: str, start_type: str, start_id: str,
        max_depth: int = 3, max_nodes: int = 64, max_edges: int = 128,
    ) -> dict[str, Any]:
        """Bounded BFS traversal of the org graph from one node.

        Never loads the whole graph: each hop is an indexed edge lookup on
        (organization_id, source/target_type, source/target_id), stopped by
        hard caps on depth, nodes and edges.
        """
        nodes: list[dict[str, str]] = [{"type": start_type, "id": start_id}]
        edges: list[dict[str, Any]] = []
        visited: set[tuple[str, str]] = {(start_type, start_id)}
        frontier: list[tuple[str, str, int]] = [(start_type, start_id, 0)]
        edge_seen: set[str] = set()
        truncated = False
        while frontier:
            ntype, nid, depth = frontier.pop(0)
            if depth + 1 > max_depth or len(nodes) >= max_nodes or len(edges) >= max_edges:
                continue
            out = (
                await db.execute(
                    select(OrgGraphEdge).where(
                        OrgGraphEdge.organization_id == organization_id,
                        OrgGraphEdge.active.is_(True),
                        OrgGraphEdge.source_type == ntype,
                        OrgGraphEdge.source_id == nid,
                    ).limit(max_edges)
                )
            ).scalars().all()
            incoming = (
                await db.execute(
                    select(OrgGraphEdge).where(
                        OrgGraphEdge.organization_id == organization_id,
                        OrgGraphEdge.active.is_(True),
                        OrgGraphEdge.target_type == ntype,
                        OrgGraphEdge.target_id == nid,
                    ).limit(max_edges)
                )
            ).scalars().all()
            for edge in list(out) + list(incoming):
                if len(edges) >= max_edges:
                    truncated = True
                    continue
                key = edge.id
                if key in edge_seen:
                    continue
                edge_seen.add(key)
                a = (edge.source_type, edge.source_id)
                b = (edge.target_type, edge.target_id)
                edges.append({"source_type": edge.source_type, "source_id": edge.source_id,
                              "target_type": edge.target_type, "target_id": edge.target_id,
                              "relation": edge.relation})
                for node in (a, b):
                    if node not in visited and len(nodes) < max_nodes:
                        visited.add(node)
                        nodes.append({"type": node[0], "id": node[1]})
                        frontier.append((node[0], node[1], depth + 1))
        return {"nodes": nodes, "edges": edges, "truncated": truncated,
                "limits": {"max_depth": max_depth, "max_nodes": max_nodes, "max_edges": max_edges}}

    # ------------------------------------------------------------------ queries

    async def edges(
        self, db: AsyncSession, *, organization_id: str, limit: int = 100,
        relation: Optional[str] = None, entity_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Legacy unscoped query - use edges_visible for governance-scoped access."""
        filters = [OrgGraphEdge.organization_id == organization_id, OrgGraphEdge.active.is_(True)]
        if relation:
            filters.append(OrgGraphEdge.relation == relation)
        if entity_type:
            filters.append(
                or_(
                    OrgGraphEdge.source_type == entity_type,
                    OrgGraphEdge.target_type == entity_type,
                )
            )
        rows = (
            await db.execute(
                select(OrgGraphEdge).where(*filters).order_by(OrgGraphEdge.weight.desc()).limit(limit)
            )
        ).scalars().all()
        return [self._edge_dict(r) for r in rows]

    async def edges_visible(
        self, db: AsyncSession, *, organization_id: str, access: CallerAccess, limit: int = 100,
        relation: Optional[str] = None, entity_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Governance-scoped edges: only returns edges the caller may access."""
        filters = [OrgGraphEdge.organization_id == organization_id, OrgGraphEdge.active.is_(True)]
        if relation:
            filters.append(OrgGraphEdge.relation == relation)
        if entity_type:
            filters.append(
                or_(
                    OrgGraphEdge.source_type == entity_type,
                    OrgGraphEdge.target_type == entity_type,
                )
            )
        # Apply scope filtering for non-org-wide callers
        if not access.org_wide:
            if not access.project_ids:
                return []
            # Filter to edges where source or target is in accessible projects
            project_edge_filter = or_(
                OrgGraphEdge.source_id.in_(access.project_ids),
                OrgGraphEdge.target_id.in_(access.project_ids),
            )
            filters.append(project_edge_filter)
        if relation:
            filters.append(OrgGraphEdge.relation == relation)
        if entity_type:
            filters.append(
                or_(
                    OrgGraphEdge.source_type == entity_type,
                    OrgGraphEdge.target_type == entity_type,
                )
            )
        rows = (
            await db.execute(
                select(OrgGraphEdge).where(*filters).order_by(OrgGraphEdge.weight.desc()).limit(limit)
            )
        ).scalars().all()
        return [self._edge_dict(r) for r in rows]

    def _edge_dict(self, row: OrgGraphEdge) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "relation": row.relation,
            "weight": row.weight,
            "evidence": row.evidence,
            "active": row.active,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def neighbors(
        self, db: AsyncSession, *, organization_id: str,
        entity_type: str, entity_id: str, relations: Optional[list[str]] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        filters = [OrgGraphEdge.organization_id == organization_id, OrgGraphEdge.active.is_(True)]
        if relations:
            filters.append(OrgGraphEdge.relation.in_(relations))
        rows = (
            await db.execute(
                select(OrgGraphEdge)
                .where(
                    *filters,
                    or_(
                        (OrgGraphEdge.source_type == entity_type) & (OrgGraphEdge.source_id == entity_id),
                        (OrgGraphEdge.target_type == entity_type) & (OrgGraphEdge.target_id == entity_id),
                    ),
                )
                .order_by(OrgGraphEdge.weight.desc())
                .limit(limit)
            )
        ).scalars().all()
        result = []
        for row in rows:
            is_source = row.source_type == entity_type and row.source_id == entity_id
            result.append({
                "edge_id": row.id,
                "relation": row.relation,
                "direction": "out" if is_source else "in",
                "neighbor_type": row.target_type if is_source else row.source_type,
                "neighbor_id": row.target_id if is_source else row.source_id,
                "weight": row.weight,
                "evidence": row.evidence,
            })
        return result

    async def collaboration_path(
        self, db: AsyncSession, *, organization_id: str,
        from_employee: str, to_employee: str, max_depth: int = 4,
    ) -> list[dict[str, Any]]:
        """BFS over employee-to-employee edges to find collaboration paths."""
        if from_employee == to_employee:
            return [{"path": [from_employee], "hops": 0}]

        adjacency: dict[str, list[tuple[str, str]]] = {}
        rows = (
            await db.execute(
                select(OrgGraphEdge).where(
                    OrgGraphEdge.organization_id == organization_id,
                    OrgGraphEdge.active.is_(True),
                    or_(
                        (OrgGraphEdge.source_type == "employee") & (OrgGraphEdge.target_type == "employee"),
                        (OrgGraphEdge.source_type == "employee") & (OrgGraphEdge.target_type.isnot(None)),
                    ),
                )
            )
        ).scalars().all()
        for row in rows:
            if row.source_type == "employee" and row.target_type == "employee":
                adjacency.setdefault(row.source_id, []).append((row.target_id, row.relation))
                adjacency.setdefault(row.target_id, []).append((row.source_id, row.relation))
            elif row.source_type == "employee":
                adjacency.setdefault(row.source_id, []).append((row.target_id, row.relation))

        from collections import deque

        queue: deque[tuple[str, list[str], list[str]]] = deque([(from_employee, [from_employee], [])])
        visited = {from_employee}
        depth = 0
        while queue and depth < max_depth:
            level_size = len(queue)
            for _ in range(level_size):
                current, path, relations = queue.popleft()
                for neighbor, relation in adjacency.get(current, []):
                    if neighbor in visited:
                        continue
                    if neighbor == to_employee:
                        return [{
                            "path": path + [neighbor],
                            "hops": len(path),
                            "relations": relations + [relation],
                        }]
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor], relations + [relation]))
            depth += 1
        return []

    async def bottlenecks(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Employees with the most active graph connections (hub risk)."""
        rows = (
            await db.execute(
                select(OrgGraphEdge.source_id, func.count(OrgGraphEdge.id))
                .where(
                    OrgGraphEdge.organization_id == organization_id,
                    OrgGraphEdge.active.is_(True),
                    OrgGraphEdge.source_type == "employee",
                )
                .group_by(OrgGraphEdge.source_id)
                .order_by(func.count(OrgGraphEdge.id).desc())
                .limit(limit)
            )
        ).all()
        result = []
        for employee_id, edge_count in rows:
            employee = await db.get(Employee, employee_id)
            if employee is None:
                continue
            result.append({
                "employee_id": employee_id,
                "name": employee.display_name or f"{employee.first_name} {employee.last_name or ''}".strip(),
                "designation": employee.designation,
                "degree": edge_count,
            })
        return result

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        from sqlalchemy import func as sa_func

        total = (
            await db.execute(
                select(sa_func.count(OrgGraphEdge.id)).where(
                    OrgGraphEdge.organization_id == organization_id,
                    OrgGraphEdge.active.is_(True),
                )
            )
        ).scalar() or 0
        relations = (
            await db.execute(
                select(OrgGraphEdge.relation, sa_func.count(OrgGraphEdge.id))
                .where(
                    OrgGraphEdge.organization_id == organization_id,
                    OrgGraphEdge.active.is_(True),
                )
                .group_by(OrgGraphEdge.relation)
            )
        ).all()
        return {
            "edges": total,
            "relations": {r: c for r, c in relations},
            "employee_nodes": (
                await db.execute(
                    select(sa_func.count(sa_func.distinct(Employee.id))).where(
                        Employee.organization_id == organization_id
                    )
                )
            ).scalar() or 0,
        }


graph_engine = GraphEngine()
