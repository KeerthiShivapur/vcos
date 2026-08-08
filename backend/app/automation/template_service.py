"""Workflow templates (Phase 14) — the automation marketplace.

System templates ship with the platform; orgs can add their own. Instantiating
a template clones its graph into a new draft workflow.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.workflow_service import workflow_service
from app.models.workflow import WorkflowTemplate

logger = logging.getLogger("vcos.automation.templates")


class TemplateService:
    # ------------------------------------------------------------- system

    def _system_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "New Employee Onboarding",
                "description": "Creates onboarding tasks and meetings when an employee joins.",
                "category": "hr",
                "icon": "person",
                "trigger_type": "event",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Employee joined",
                     "config": {}},
                    {"key": "assign_work", "type": "task", "name": "Assign workspace setup",
                     "config": {"title": "Set up workstation for {{employee_name}}",
                                "priority": "high", "status": "todo",
                                "assignee_ref": "{{employee_id}}"}},
                    {"key": "schedule_welcome", "type": "meeting", "name": "Welcome meeting",
                     "config": {"title": "Welcome {{employee_name}}",
                                "meeting_type": "onboarding"}},
                    {"key": "notify_hr", "type": "notification", "name": "Notify HR",
                     "config": {"title": "Onboarding started for {{employee_name}}",
                                "body": "Workflow automation created the onboarding tasks."}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "assign_work"},
                    {"source": "assign_work", "target": "schedule_welcome"},
                    {"source": "schedule_welcome", "target": "notify_hr"},
                    {"source": "notify_hr", "target": "done"},
                ],
            },
            {
                "name": "High Value Deal Approval",
                "description": "Route high-value opportunities through a finance approval gate.",
                "category": "crm",
                "icon": "approval",
                "trigger_type": "event",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Opportunity created",
                     "config": {}},
                    {"key": "check_value", "type": "condition", "name": "Is value above 50k?",
                     "config": {"field": "value", "operator": "gte", "value": 50000}},
                    {"key": "approve", "type": "approval", "name": "Finance approval",
                     "config": {"title": "Approve deal over $50k",
                                "approver_role": "finance"}},
                    {"key": "notify", "type": "notification", "name": "Notify sales team",
                     "config": {"title": "Deal approved", "body": "The high-value deal was approved."}},
                    {"key": "skip", "type": "end", "name": "Auto-accepted", "config": {}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "check_value"},
                    {"source": "check_value", "target": "approve", "condition": {"branch": "true"}},
                    {"source": "check_value", "target": "skip", "condition": {"branch": "false"}},
                    {"source": "approve", "target": "notify", "condition": {"branch": "approved"}},
                    {"source": "approve", "target": "done", "condition": {"branch": "rejected"}},
                ],
            },
            {
                "name": "Customer Onboarding",
                "description": "Kicks off tasks and a kickoff meeting when a customer signs.",
                "category": "crm",
                "icon": "customer",
                "trigger_type": "event",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Customer created",
                     "config": {}},
                    {"key": "account_task", "type": "task", "name": "Assign account setup",
                     "config": {"title": "Set up account for {{customer_name}}",
                                "priority": "high"}},
                    {"key": "kickoff", "type": "meeting", "name": "Kickoff meeting",
                     "config": {"title": "Customer kickoff: {{customer_name}}",
                                "meeting_type": "customer"}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "account_task"},
                    {"source": "account_task", "target": "kickoff"},
                    {"source": "kickoff", "target": "done"},
                ],
            },
            {
                "name": "Expense Overrun Alert",
                "description": "Notifies finance when an expense is flagged by policy.",
                "category": "finance",
                "icon": "alert",
                "trigger_type": "event",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Expense flagged",
                     "config": {}},
                    {"key": "notify", "type": "notification", "name": "Alert finance",
                     "config": {"title": "Expense flagged: {{title}}",
                                "body": "Policy check flagged this expense for review.",
                                "priority": "high"}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "notify"},
                    {"source": "notify", "target": "done"},
                ],
            },
            {
                "name": "Weekly Status Digest",
                "description": "Sends a weekly digest to the whole company via schedule.",
                "category": "general",
                "icon": "calendar",
                "trigger_type": "schedule",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Monday morning",
                     "config": {}},
                    {"key": "digest", "type": "notification", "name": "Broadcast digest",
                     "config": {"title": "Weekly status digest",
                                "body": "Here is what happened this week.", "broadcast": True}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "digest"},
                    {"source": "digest", "target": "done"},
                ],
            },
            {
                "name": "New Hire Task Distribution",
                "description": "Parallel tasks for IT and HR when an employee joins.",
                "category": "hr",
                "icon": "split",
                "trigger_type": "event",
                "nodes": [
                    {"key": "trigger", "type": "start", "name": "Employee joined",
                     "config": {}},
                    {"key": "split", "type": "parallel_split", "name": "Distribute",
                     "config": {}},
                    {"key": "it_task", "type": "task", "name": "IT setup",
                     "config": {"title": "Provision laptop for {{employee_name}}",
                                "priority": "high"}},
                    {"key": "hr_task", "type": "task", "name": "HR orientation",
                     "config": {"title": "Schedule orientation for {{employee_name}}",
                                "priority": "medium"}},
                    {"key": "join", "type": "parallel_join", "name": "All done",
                     "config": {}},
                    {"key": "done", "type": "end", "name": "Done", "config": {}},
                ],
                "edges": [
                    {"source": "trigger", "target": "split"},
                    {"source": "split", "target": "it_task"},
                    {"source": "split", "target": "hr_task"},
                    {"source": "it_task", "target": "join"},
                    {"source": "hr_task", "target": "join"},
                    {"source": "join", "target": "done"},
                ],
            },
        ]

    async def seed(self, db: AsyncSession) -> int:
        """Idempotently seed the system template catalog."""
        existing = {
            row.name
            for row in (await db.execute(select(WorkflowTemplate))).scalars().all()
        }
        created = 0
        for template in self._system_templates():
            if template["name"] in existing:
                continue
            db.add(
                WorkflowTemplate(
                    name=template["name"],
                    description=template["description"],
                    category=template["category"],
                    icon=template["icon"],
                    definition={
                        "trigger_type": template["trigger_type"],
                        "nodes": template["nodes"],
                        "edges": template["edges"],
                    },
                    is_system=True,
                )
            )
            created += 1
        await db.flush()
        return created

    async def list(self, db: AsyncSession, *, organization_id: Optional[str] = None,
                   category: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(WorkflowTemplate)
        if category:
            query = query.where(WorkflowTemplate.category == category)
        rows = (
            await db.execute(query.order_by(WorkflowTemplate.is_system.desc(), WorkflowTemplate.popularity.desc()))
        ).scalars().all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "icon": row.icon,
                "is_system": row.is_system,
                "popularity": row.popularity,
                "definition": row.definition,
            }
            for row in rows
        ]

    async def create_org_template(self, db: AsyncSession, *, data: dict[str, Any]) -> WorkflowTemplate:
        template = WorkflowTemplate(
            name=data["name"],
            description=data.get("description"),
            category=data.get("category", "general"),
            icon=data.get("icon"),
            definition={"trigger_type": data.get("trigger_type", "manual"),
                        "nodes": data.get("nodes", []), "edges": data.get("edges", [])},
            is_system=False,
            created_by=data.get("created_by"),
        )
        db.add(template)
        await db.flush()
        return template

    async def instantiate(self, db: AsyncSession, *, template_id: str,
                          organization_id: str, name: str,
                          created_by: Optional[str] = None) -> dict[str, Any]:
        template = await db.get(WorkflowTemplate, template_id)
        if template is None:
            raise ValueError("Template not found")
        definition = template.definition or {}
        workflow = await workflow_service.create(
            db,
            organization_id=organization_id,
            data={
                "name": name,
                "description": template.description,
                "category": template.category,
                "icon": template.icon,
                "trigger_type": definition.get("trigger_type", "manual"),
            },
            created_by=created_by,
        )
        await workflow_service.save_graph(
            db, workflow,
            nodes=definition.get("nodes", []),
            edges=definition.get("edges", []),
            actor_id=created_by,
        )
        template.popularity += 1
        await db.flush()
        return await workflow_service.payload(db, workflow)


template_service = TemplateService()
