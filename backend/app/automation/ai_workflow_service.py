"""AI workflow assistant (Phase 14) — natural language → validated workflows.

Uses the configured AI provider when available and falls back to a
deterministic intent parser (so tests and offline mode stay hermetic). The
parser understands common intents — onboarding, approvals, alerts,
digests, parallel distribution — and always produces a valid graph.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.execution_service import execution_engine
from app.automation.workflow_service import workflow_service, VALID_NODE_TYPES
from app.models.workflow import Workflow, WorkflowTemplate

logger = logging.getLogger("vcos.automation.ai")


class AIWorkflowService:
    async def generate(
        self, db: AsyncSession, *, organization_id: str, prompt: str,
        name: Optional[str] = None, category: Optional[str] = "general",
        created_by: Optional[str] = None, persist: bool = True,
    ) -> dict[str, Any]:
        """Generate a workflow definition from a natural language prompt."""
        definition = await self._from_provider(db, prompt, name or "AI-generated workflow", category)
        if definition is None:
            definition = self._from_intent(prompt, name or "AI-generated workflow", category)
        self._validate_definition(definition)
        result: dict[str, Any] = {"definition": definition, "valid": True}
        if persist:
            workflow = await workflow_service.create(
                db,
                organization_id=organization_id,
                data={
                    "name": definition["name"],
                    "description": definition.get("description") or prompt[:300],
                    "category": definition.get("category", category),
                    "trigger_type": definition.get("trigger_type", "manual"),
                },
                created_by=created_by,
            )
            await workflow_service.save_graph(
                db, workflow,
                nodes=definition["nodes"], edges=definition["edges"],
                actor_id=created_by,
            )
            result["workflow"] = await workflow_service.payload(db, workflow)
        return result

    async def _from_provider(self, db, prompt: str, name: str, category: str) -> Optional[dict[str, Any]]:
        from app.core.config import get_settings

        settings = get_settings()
        if settings.AI_PROVIDER in ("none", None):
            return None
        try:
            from app.services.ai_provider import get_ai_provider

            provider = get_ai_provider()
            if provider is None:
                return None
            schema_hint = (
                'Respond with JSON: {"name": str, "trigger_type": "manual|event|schedule", '
                '"nodes": [{"key", "type", "name", "config"}], "edges": [{"source", "target", "condition"?}]}. '
                "Node types allowed: start, condition, approval, task, meeting, notification, "
                "delay, integration, webhook, ai_decision, parallel_split, parallel_join, end."
            )
            text = await provider.complete(
                prompt=f"Design a business workflow. {schema_hint}\nRequest: {prompt}"
            )
            import json

            match = re.search(r"\{.*\}", text or "", re.DOTALL)
            if not match:
                return None
            return json.loads(match.group(0))
        except Exception as exc:  # pragma: no cover - provider dependent
            logger.warning("AI workflow generation unavailable: %s", exc)
            return None

    # ---------------------------------------------------- deterministic parser

    def _from_intent(self, prompt: str, name: str, category: str) -> dict[str, Any]:
        lowered = prompt.lower()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        trigger_type = "manual"

        if any(word in lowered for word in ("onboarding", "new hire", "new employee", "joining")):
            trigger_type = "event"
            nodes = [
                {"key": "trigger", "type": "start", "name": "Employee joins", "config": {}},
                {"key": "setup", "type": "task", "name": "Workspace setup",
                 "config": {"title": "Set up workspace for the new employee", "priority": "high"}},
                {"key": "welcome", "type": "meeting", "name": "Welcome meeting",
                 "config": {"title": "Welcome the new employee", "meeting_type": "onboarding"}},
                {"key": "notify", "type": "notification", "name": "Notify team",
                 "config": {"title": "New employee onboarded", "body": "Onboarding workflow completed."}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "setup"},
                {"source": "setup", "target": "welcome"},
                {"source": "welcome", "target": "notify"},
                {"source": "notify", "target": "end"},
            ]
        elif any(word in lowered for word in ("approval", "approve", "sign-off", "sign off")):
            nodes = [
                {"key": "trigger", "type": "start", "name": "Request", "config": {}},
                {"key": "approve", "type": "approval", "name": "Approval gate",
                 "config": {"title": "Approve the request", "approver_role": "manager",
                            "due_hours": 24}},
                {"key": "approved", "type": "notification", "name": "Notify requester",
                 "config": {"title": "Request approved", "body": "Your request was approved."}},
                {"key": "rejected", "type": "notification", "name": "Notify requester",
                 "config": {"title": "Request rejected", "body": "Your request was rejected."}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "approve"},
                {"source": "approve", "target": "approved", "condition": {"branch": "approved"}},
                {"source": "approve", "target": "rejected", "condition": {"branch": "rejected"}},
                {"source": "approved", "target": "end"},
                {"source": "rejected", "target": "end"},
            ]
        elif any(word in lowered for word in ("alert", "flag", "overrun", "monitor", "notify")):
            trigger_type = "event"
            nodes = [
                {"key": "trigger", "type": "start", "name": "Event", "config": {}},
                {"key": "alert", "type": "notification", "name": "Alert",
                 "config": {"title": "Alert from workflow", "priority": "high",
                            "body": "An event triggered this alert."}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "alert"},
                {"source": "alert", "target": "end"},
            ]
        elif any(word in lowered for word in ("digest", "report", "summary", "weekly", "daily")):
            trigger_type = "schedule"
            nodes = [
                {"key": "trigger", "type": "start", "name": "Scheduled run", "config": {}},
                {"key": "digest", "type": "notification", "name": "Digest",
                 "config": {"title": "Status digest", "broadcast": True,
                            "body": "Automated digest from the workflow."}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "digest"},
                {"source": "digest", "target": "end"},
            ]
        elif any(word in lowered for word in ("parallel", "distribute", "split")):
            nodes = [
                {"key": "trigger", "type": "start", "name": "Start", "config": {}},
                {"key": "split", "type": "parallel_split", "name": "Distribute", "config": {}},
                {"key": "a", "type": "task", "name": "Workstream A",
                 "config": {"title": "Workstream A task", "priority": "medium"}},
                {"key": "b", "type": "task", "name": "Workstream B",
                 "config": {"title": "Workstream B task", "priority": "medium"}},
                {"key": "join", "type": "parallel_join", "name": "Join", "config": {}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "split"},
                {"source": "split", "target": "a"},
                {"source": "split", "target": "b"},
                {"source": "a", "target": "join"},
                {"source": "b", "target": "join"},
                {"source": "join", "target": "end"},
            ]
        elif any(word in lowered for word in ("decision", "ai", "intelligent")):
            nodes = [
                {"key": "trigger", "type": "start", "name": "Start", "config": {}},
                {"key": "decide", "type": "ai_decision", "name": "AI decision",
                 "config": {"prompt": "Decide the next step for this request."}},
                {"key": "yes", "type": "notification", "name": "Yes branch",
                 "config": {"title": "AI decision: yes", "body": "Proceeding."}},
                {"key": "no", "type": "notification", "name": "No branch",
                 "config": {"title": "AI decision: no", "body": "Not proceeding."}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "decide"},
                {"source": "decide", "target": "yes", "condition": {"branch": "yes"}},
                {"source": "decide", "target": "no", "condition": {"branch": "no"}},
                {"source": "yes", "target": "end"},
                {"source": "no", "target": "end"},
            ]
        else:
            nodes = [
                {"key": "trigger", "type": "start", "name": "Start", "config": {}},
                {"key": "notify", "type": "notification", "name": "Notify",
                 "config": {"title": name, "body": prompt[:300]}},
                {"key": "end", "type": "end", "name": "Done", "config": {}},
            ]
            edges = [
                {"source": "trigger", "target": "notify"},
                {"source": "notify", "target": "end"},
            ]
        return {
            "name": name,
            "description": prompt[:500],
            "category": category,
            "trigger_type": trigger_type,
            "nodes": nodes,
            "edges": edges,
        }

    def _validate_definition(self, definition: dict[str, Any]) -> None:
        nodes = definition.get("nodes") or []
        edges = definition.get("edges") or []
        keys = {node.get("key") for node in nodes if node.get("key")}
        if not keys:
            raise ValueError("AI workflow definition has no nodes")
        for node in nodes:
            node_type = node.get("type")
            if node_type not in VALID_NODE_TYPES:
                node["type"] = "script"
        for edge in edges:
            if edge.get("source") not in keys or edge.get("target") not in keys:
                edge["source"] = list(keys)[0]
                edge["target"] = list(keys)[-1]
        # always ensure a terminal node
        if not any(node.get("type") == "end" for node in nodes):
            nodes.append({"key": "end", "type": "end", "name": "Done", "config": {}})
            for node in nodes:
                if node.get("type") != "end" and not any(
                    e.get("source") == node.get("key") for e in edges
                ):
                    edges.append({"source": node.get("key"), "target": "end"})
        definition["nodes"] = nodes
        definition["edges"] = edges

    # ------------------------------------------------------------ decisions

    async def decide(self, db: AsyncSession, *, organization_id: str,
                     prompt: str, context: dict[str, Any]) -> str:
        """AI branch decision used by ai_decision nodes (fallback: heuristic)."""
        lowered = (prompt + " " + str(context.get("trigger") or "")).lower()
        if any(word in lowered for word in ("high", "urgent", "critical", "large", "expensive", "important")):
            return "yes"
        if any(word in lowered for word in ("low", "small", "no", "false", "reject")):
            return "no"
        return "yes"

    async def suggest_rule(self, db: AsyncSession, *, organization_id: str,
                           prompt: str) -> dict[str, Any]:
        lowered = prompt.lower()
        if any(word in lowered for word in ("expense", "flagged", "policy")):
            return {
                "name": "Flagged expense alert",
                "event_name": "expense.flagged",
                "conditions": [{"field": "policy_flags", "operator": "truthy", "value": None}],
                "actions": [
                    {"action": "send_notification",
                     "config": {"title": "Expense flagged by policy",
                                "body": "An expense needs review.", "priority": "high"}}
                ],
                "enabled": True,
            }
        if any(word in lowered for word in ("ticket", "support", "sla")):
            return {
                "name": "Escalated ticket alert",
                "event_name": "ticket.escalated",
                "conditions": [],
                "actions": [
                    {"action": "send_notification",
                     "config": {"title": "Support ticket escalated",
                                "body": "A ticket was escalated by SLA policy."}}
                ],
                "enabled": True,
            }
        if any(word in lowered for word in ("lead", "qualified")):
            return {
                "name": "Qualified lead follow-up",
                "event_name": "lead.qualified",
                "conditions": [],
                "actions": [
                    {"action": "send_notification",
                     "config": {"title": "Lead qualified",
                                "body": "A lead was qualified; assign follow-up."}}
                ],
                "enabled": True,
            }
        return {
            "name": "Rule from prompt",
            "event_name": "task.created",
            "conditions": [{"field": "priority", "operator": "eq", "value": "high"}],
            "actions": [
                {"action": "send_notification",
                 "config": {"title": "High priority task created",
                            "body": "A high priority task was created."}}
            ],
            "enabled": True,
        }

    async def explain(self, db: AsyncSession, *, workflow_id: str,
                      organization_id: str) -> dict[str, Any]:
        workflow = await db.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            raise ValueError("Workflow not found")
        payload = await workflow_service.payload(db, workflow)
        node_count = len(payload.get("nodes", []))
        edge_count = len(payload.get("edges", []))
        summary = (
            f"{workflow.name} is an {workflow.trigger_type}-triggered workflow with "
            f"{node_count} steps connected by {edge_count} transitions. "
            f"Status: {workflow.status}, version {workflow.version}, "
            f"executed {workflow.run_count} times."
        )
        return {"workflow_id": workflow_id, "summary": summary,
                "node_count": node_count, "edge_count": edge_count}


ai_workflow_service = AIWorkflowService()
