"""Workflow lifecycle service (Phase 14) — CRUD, graph editing, validation.

Workflows are stored as typed nodes + edges. Saving validates the graph
(cycle detection, node types, required action configs) and bumps the version,
snapshotting the previous definition into WorkflowVersion for auditability.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    Workflow,
    WorkflowAction,
    WorkflowEdge,
    WorkflowLog,
    WorkflowNode,
    WorkflowVersion,
)

logger = logging.getLogger("vcos.automation.workflows")

VALID_NODE_TYPES = {
    "start", "trigger", "end", "condition", "ai_decision", "delay",
    "approval", "task", "meeting", "project", "notification",
    "approval_action", "onboarding", "integration", "webhook",
    "ai_summarize", "script", "parallel_split", "parallel_join",
}

ACTION_TYPES = {
    "task": "create_task", "meeting": "create_meeting", "project": "create_project",
    "notification": "send_notification", "approval_action": "create_approval",
    "onboarding": "create_onboarding", "integration": "integration",
    "webhook": "webhook", "ai_summarize": "ai_summarize",
}


class WorkflowService:
    # ------------------------------------------------------------------ CRUD

    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        created_by: Optional[str] = None,
    ) -> Workflow:
        workflow = Workflow(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            category=data.get("category", "general"),
            status="draft",
            trigger_type=data.get("trigger_type", "manual"),
            trigger_config=data.get("trigger_config") or {},
            icon=data.get("icon"),
            color=data.get("color"),
            created_by=created_by,
        )
        db.add(workflow)
        await db.flush()
        if data.get("nodes") is not None:
            await self.save_graph(db, workflow, nodes=data["nodes"], edges=data.get("edges", []))
        return workflow

    async def save_graph(
        self, db: AsyncSession, workflow: Workflow, *,
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
        actor_id: Optional[str] = None,
    ) -> Workflow:
        """Replace the graph, validating it first. Bumps the version."""
        self._validate_graph(workflow, nodes, edges)

        existing_nodes = (
            await db.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id))
        ).scalars().all()
        existing_edges = (
            await db.execute(select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow.id))
        ).scalars().all()
        existing_actions = (
            await db.execute(select(WorkflowAction).where(WorkflowAction.workflow_id == workflow.id))
        ).scalars().all()

        for row in [*existing_nodes, *existing_edges, *existing_actions]:
            await db.delete(row)
        await db.flush()

        node_keys: set[str] = set()
        for node in nodes:
            key = node["key"]
            if key in node_keys:
                raise ValueError(f"Duplicate node key: {key}")
            node_keys.add(key)
            node_type = node.get("type") or node.get("node_type", "script")
            if node_type not in VALID_NODE_TYPES:
                raise ValueError(f"Unsupported node type: {node_type}")
            db.add(
                WorkflowNode(
                    workflow_id=workflow.id,
                    node_key=key,
                    node_type=node_type,
                    name=node.get("name", key),
                    config=node.get("config") or {},
                    position=node.get("position") or {},
                )
            )
            action_type = ACTION_TYPES.get(node_type)
            if action_type and node.get("config"):
                db.add(
                    WorkflowAction(
                        organization_id=workflow.organization_id,
                        workflow_id=workflow.id,
                        node_key=key,
                        action_type=action_type,
                        config=node["config"],
                        enabled=node.get("enabled", True),
                    )
                )

        for edge in edges:
            if edge["source"] not in node_keys or edge["target"] not in node_keys:
                raise ValueError("Edge references an unknown node")
            db.add(
                WorkflowEdge(
                    workflow_id=workflow.id,
                    source_key=edge["source"],
                    target_key=edge["target"],
                    condition=edge.get("condition") or {},
                )
            )

        workflow.version += 1
        db.add(
            WorkflowVersion(
                workflow_id=workflow.id,
                version=workflow.version,
                definition={"nodes": nodes, "edges": edges},
                created_by=actor_id,
            )
        )
        if workflow.status == "active":
            workflow.status = "draft"  # edits require re-activation
        await db.flush()
        return workflow

    def _validate_graph(
        self, workflow: Workflow, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> None:
        if not nodes:
            raise ValueError("Workflow must contain at least one node")
        keys = {node.get("key") for node in nodes if node.get("key")}
        for edge in edges:
            if edge.get("source") not in keys or edge.get("target") not in keys:
                raise ValueError("Edge references an unknown node")
        # cycle detection (Kahn's algorithm)
        indegree = {key: 0 for key in keys}
        adjacency = {key: [] for key in keys}
        for edge in edges:
            adjacency[edge["source"]].append(edge["target"])
            indegree[edge["target"]] += 1
        queue = [key for key, deg in indegree.items() if deg == 0]
        visited = 0
        while queue:
            current = queue.pop(0)
            visited += 1
            for nxt in adjacency[current]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if visited != len(keys):
            raise ValueError("Workflow graph contains a cycle")

    async def update(self, db: AsyncSession, workflow: Workflow, data: dict[str, Any]) -> Workflow:
        for field in ("name", "description", "category", "trigger_type",
                      "trigger_config", "icon", "color", "attributes"):
            if field in data:
                setattr(workflow, field, data[field])
        await db.flush()
        return workflow

    async def transition(self, db: AsyncSession, workflow: Workflow, status: str) -> Workflow:
        if status not in ("draft", "active", "paused", "archived"):
            raise ValueError(f"Invalid workflow status: {status}")
        if status == "active" and workflow.status == "draft":
            self._validate_graph(
                workflow,
                [
                    {"key": n.node_key}
                    for n in (
                        await db.execute(
                            select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id)
                        )
                    ).scalars().all()
                ],
                [
                    {"source": e.source_key, "target": e.target_key}
                    for e in (
                        await db.execute(
                            select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow.id)
                        )
                    ).scalars().all()
                ],
            )
        workflow.status = status
        await db.flush()
        return workflow

    async def duplicate(self, db: AsyncSession, workflow: Workflow, *, name: str) -> Workflow:
        copy = Workflow(
            organization_id=workflow.organization_id,
            name=name,
            description=workflow.description,
            category=workflow.category,
            status="draft",
            trigger_type=workflow.trigger_type,
            trigger_config=workflow.trigger_config,
            icon=workflow.icon,
            color=workflow.color,
            created_by=workflow.created_by,
        )
        db.add(copy)
        await db.flush()
        nodes = (
            await db.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id))
        ).scalars().all()
        edges = (
            await db.execute(select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow.id))
        ).scalars().all()
        for node in nodes:
            db.add(
                WorkflowNode(
                    workflow_id=copy.id,
                    node_key=node.node_key,
                    node_type=node.node_type,
                    name=node.name,
                    config=dict(node.config or {}),
                    position=dict(node.position or {}),
                )
            )
            action_type = ACTION_TYPES.get(node.node_type)
            if action_type:
                db.add(
                    WorkflowAction(
                        organization_id=copy.organization_id,
                        workflow_id=copy.id,
                        node_key=node.node_key,
                        action_type=action_type,
                        config=dict(node.config or {}),
                    )
                )
        for edge in edges:
            db.add(
                WorkflowEdge(
                    workflow_id=copy.id,
                    source_key=edge.source_key,
                    target_key=edge.target_key,
                    condition=dict(edge.condition or {}),
                )
            )
        await db.flush()
        return copy

    # ------------------------------------------------------------- queries

    async def payload(self, db: AsyncSession, workflow: Workflow, *, include_graph: bool = True) -> dict[str, Any]:
        nodes = (
            await db.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id))
        ).scalars().all()
        edges = (
            await db.execute(select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow.id))
        ).scalars().all()
        from app.models.workflow import WorkflowExecution

        runs = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.workflow_id == workflow.id
                )
            )
        ).scalars().all()
        result = {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "category": workflow.category,
            "status": workflow.status,
            "version": workflow.version,
            "trigger_type": workflow.trigger_type,
            "trigger_config": workflow.trigger_config,
            "icon": workflow.icon,
            "color": workflow.color,
            "created_by": workflow.created_by,
            "run_count": workflow.run_count,
            "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
            "attributes": workflow.attributes,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        }
        if include_graph:
            result["nodes"] = [
                {"key": n.node_key, "type": n.node_type, "name": n.name,
                 "config": n.config, "position": n.position} for n in nodes
            ]
            result["edges"] = [
                {"source": e.source_key, "target": e.target_key, "condition": e.condition}
                for e in edges
            ]
        result["run_summary"] = {
            "total": len(runs),
            "completed": sum(1 for r in runs if r.status == "completed"),
            "failed": sum(1 for r in runs if r.status == "failed"),
            "waiting": sum(1 for r in runs if r.status == "waiting"),
        }
        return result

    async def list(self, db: AsyncSession, *, organization_id: str,
                   status: Optional[str] = None, category: Optional[str] = None,
                   search: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(Workflow).where(Workflow.organization_id == organization_id)
        if status:
            query = query.where(Workflow.status == status)
        if category:
            query = query.where(Workflow.category == category)
        if search:
            query = query.where(Workflow.name.ilike(f"%{search}%"))
        rows = (await db.execute(query.order_by(Workflow.updated_at.desc()))).scalars().all()
        result = []
        for workflow in rows:
            payload = await self.payload(db, workflow, include_graph=False)
            result.append(payload)
        return result

    async def log(self, db: AsyncSession, *, organization_id: str, level: str,
                  message: str, workflow_id: Optional[str] = None,
                  execution_id: Optional[str] = None, data: Optional[dict] = None) -> None:
        db.add(
            WorkflowLog(
                organization_id=organization_id,
                workflow_id=workflow_id,
                execution_id=execution_id,
                level=level,
                message=message[:2000],
                data=data or {},
            )
        )
        await db.flush()


workflow_service = WorkflowService()
