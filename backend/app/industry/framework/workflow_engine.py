"""Industry workflow engine (Phase 17.12).

Every industry pack ships ready-made workflow templates (patient admission,
tender -> completion, order fulfillment...). Activating one creates an
IndustryWorkflow instance whose steps come from the pack's template AND a
core Phase 14 Workflow row, so industry workflows participate in the
universal workflow engine — approvals, schedules, automation and analytics.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.industry.framework.registry import pack_workflow, pack_workflows
from app.models.industry_configuration import IndustryWorkflow
from app.models.organization import gen_uuid
from app.models.workflow import Workflow

_INDUSTRY_WORKFLOW_CATEGORY = "general"


class IndustryWorkflowEngine:
    async def activate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        industry_key: str,
        template_key: str,
        actor_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> IndustryWorkflow:
        template = pack_workflow(industry_key, template_key)
        name = template["name"]
        existing = (
            await db.execute(
                select(IndustryWorkflow).where(
                    IndustryWorkflow.organization_id == organization_id,
                    IndustryWorkflow.industry_key == industry_key,
                    IndustryWorkflow.template_key == template_key,
                    IndustryWorkflow.status.in_(("draft", "active", "paused")),
                )
            )
        ).scalars().first()
        if existing is not None:
            raise ValueError(
                f"workflow '{template_key}' is already active for {industry_key}"
            )

        steps = [
            {
                "key": step["key"],
                "name": step["name"],
                "status": "pending",
                "assignee_role": step.get("assignee_role"),
            }
            for step in template.get("steps", [])
        ]
        workflow = IndustryWorkflow(
            id=gen_uuid(),
            organization_id=organization_id,
            industry_key=industry_key,
            template_key=template_key,
            name=name,
            description=template.get("description"),
            status="active",
            steps=steps,
            current_step=steps[0]["key"] if steps else None,
            progress=0.0,
            assignee_id=actor_id,
            started_at=utcnow(),
            context=context or {},
        )
        db.add(workflow)
        await db.flush()

        # Link into the core Phase 14 workflow engine so the industry flow is
        # visible and runnable from the universal automation console.
        core_workflow = Workflow(
            id=gen_uuid(),
            organization_id=organization_id,
            name=f"[{industry_key}] {name}",
            description=template.get("description"),
            category=_INDUSTRY_WORKFLOW_CATEGORY,
            status="active",
            trigger_type="manual",
            attributes={
                "industry": industry_key,
                "industry_workflow_id": workflow.id,
                "template_key": template_key,
                "pack_workflow": True,
            },
            created_by=actor_id,
        )
        db.add(core_workflow)
        await db.flush()
        workflow.source_workflow_id = core_workflow.id
        await db.flush()

        await publish_event(
            db,
            name="industry.workflow.created",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={
                "industry_key": industry_key,
                "workflow_id": workflow.id,
                "template_key": template_key,
                "source_workflow_id": core_workflow.id,
                "steps": len(steps),
            },
        )
        return workflow

    async def list_workflows(
        self,
        db: AsyncSession,
        organization_id: str,
        industry_key: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[IndustryWorkflow]:
        query = select(IndustryWorkflow).where(
            IndustryWorkflow.organization_id == organization_id
        )
        if industry_key:
            query = query.where(IndustryWorkflow.industry_key == industry_key)
        if status:
            query = query.where(IndustryWorkflow.status == status)
        result = await db.execute(query.order_by(IndustryWorkflow.created_at.desc()))
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, organization_id: str, workflow_id: str) -> Optional[IndustryWorkflow]:
        workflow = await db.get(IndustryWorkflow, workflow_id)
        if workflow is None or workflow.organization_id != organization_id:
            return None
        return workflow

    async def advance(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        workflow_id: str,
        step_key: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[IndustryWorkflow]:
        workflow = await self.get(db, organization_id, workflow_id)
        if workflow is None:
            return None
        if workflow.status != "active":
            raise ValueError(f"workflow is not active (status={workflow.status})")
        steps = list(workflow.steps or [])
        if not steps:
            raise ValueError("workflow has no steps")
        current = step_key or workflow.current_step
        target = next((step for step in steps if step["key"] == current), None)
        if target is None:
            raise ValueError(f"unknown step '{current}'")
        target["status"] = "completed"
        idx = steps.index(target)
        if idx + 1 < len(steps):
            steps[idx + 1]["status"] = "in_progress"
            workflow.current_step = steps[idx + 1]["key"]
        else:
            workflow.status = "completed"
            workflow.current_step = target["key"]
            workflow.completed_at = utcnow()
        workflow.steps = steps
        workflow.progress = round(100 * (idx + 1) / len(steps), 1)
        if workflow.status == "completed":
            await publish_event(
                db,
                name="industry.workflow.completed",
                organization_id=organization_id,
                actor_id=actor_id,
                payload={
                    "industry_key": workflow.industry_key,
                    "workflow_id": workflow.id,
                    "template_key": workflow.template_key,
                },
            )
        return workflow

    async def pause(self, db: AsyncSession, *, organization_id: str, workflow_id: str) -> Optional[IndustryWorkflow]:
        workflow = await self.get(db, organization_id, workflow_id)
        if workflow is None:
            return None
        if workflow.status == "active":
            workflow.status = "paused"
        return workflow

    async def resume(self, db: AsyncSession, *, organization_id: str, workflow_id: str) -> Optional[IndustryWorkflow]:
        workflow = await self.get(db, organization_id, workflow_id)
        if workflow is None:
            return None
        if workflow.status == "paused":
            workflow.status = "active"
        return workflow

    async def cancel(self, db: AsyncSession, *, organization_id: str, workflow_id: str) -> Optional[IndustryWorkflow]:
        workflow = await self.get(db, organization_id, workflow_id)
        if workflow is None:
            return None
        if workflow.status in ("active", "paused", "draft"):
            workflow.status = "cancelled"
        return workflow

    async def available_templates(self, industry_key: str) -> list[dict[str, Any]]:
        return pack_workflows(industry_key)


industry_workflow_engine = IndustryWorkflowEngine()
