"""Industry router factory (Phase 17.16).

One generic factory builds an identical router for every industry pack —
each mount exposes the pack's modules, templates, workflows, compliance, AI
profiles and analytics through the same service layer. Adding a new vertical
is a one-line registration, never new endpoint code.

Mounted under /industries/{key} so paths never collide with the core
/industry/* router (catalog, installed, selections, marketplace).
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.events.publisher import publish_event
from app.industry.framework.ai_router import industry_ai_router
from app.industry.framework.analytics_engine import industry_analytics_engine
from app.industry.framework.compliance_engine import industry_compliance_engine
from app.industry.framework.plugin_loader import industry_plugin_loader
from app.industry.framework.registry import (
    pack_compliance,
    pack_kpis,
    pack_modules,
    pack_navigation,
    pack_templates,
    pack_workflows,
)
from app.industry.framework.workflow_engine import industry_workflow_engine
from app.models.industry import IndustrySelection
from app.models.organization import Organization
from app.models.user import User

INDUSTRY_ROUTER_TAG = "Industry Packs"


def _http(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def build_industry_router(industry_key: str) -> APIRouter:
    """Generate a complete, self-contained router for one industry pack."""

    router = APIRouter(
        prefix=f"/industries/{industry_key}",
        tags=[INDUSTRY_ROUTER_TAG, f"{industry_key} pack"],
    )

    @router.get("")
    async def pack_overview(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
    ):
        config = await industry_plugin_loader.get_config(db, org.id, industry_key)
        selection = None
        if config is not None:
            selection = (
                await db.execute(
                    select(IndustrySelection).where(
                        IndustrySelection.organization_id == org.id,
                        IndustrySelection.industry_key == industry_key,
                    )
                )
            ).scalars().first()
        return {
            "industry_key": industry_key,
            "installed": config is not None and config.status not in ("uninstalled",),
            "status": config.status if config else "not_installed",
            "modules": pack_modules(industry_key),
            "workflows": pack_workflows(industry_key),
            "templates": pack_templates(industry_key),
            "compliance": pack_compliance(industry_key),
            "kpis": pack_kpis(industry_key),
            "navigation": pack_navigation(industry_key),
            "selection": (
                {
                    "business_type": selection.business_type,
                    "company_size": selection.company_size,
                    "country": selection.country,
                    "regulations": selection.regulations or [],
                }
                if selection is not None
                else None
            ),
        }

    @router.get("/modules")
    async def pack_modules_route(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
    ):
        config = await industry_plugin_loader.get_config(db, org.id, industry_key)
        enabled = set(config.modules_enabled or []) if config else set()
        return [
            {**module, "enabled": module["key"] in enabled}
            for module in pack_modules(industry_key)
        ]

    @router.get("/templates")
    async def pack_templates_route(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        kind: Optional[str] = Query(None),
    ):
        return pack_templates(industry_key, kind=kind)

    @router.post("/templates/{template_key}/apply")
    async def pack_template_apply(
        template_key: str,
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:manage")),
        db: AsyncSession = Depends(get_db),
    ):
        template = next(
            (t for t in pack_templates(industry_key) if t["key"] == template_key), None
        )
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        workflow_id: Optional[str] = None
        if template.get("kind") == "workflow" and template.get("workflow_key"):
            workflow = await industry_workflow_engine.activate(
                db,
                organization_id=org.id,
                industry_key=industry_key,
                template_key=template["workflow_key"],
                actor_id=user.id,
                context=payload.get("context") or {},
            )
            workflow_id = workflow.id
        await publish_event(
            db,
            name="industry.template.applied",
            organization_id=org.id,
            actor_id=user.id,
            payload={
                "industry_key": industry_key,
                "template_key": template_key,
                "kind": template.get("kind"),
                "workflow_id": workflow_id,
            },
        )
        await db.commit()
        return {
            "industry_key": industry_key,
            "template_key": template_key,
            "name": template["name"],
            "kind": template.get("kind"),
            "content": template.get("content", {}),
            "workflow_id": workflow_id,
        }

    @router.get("/workflows")
    async def pack_workflows_route(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
    ):
        return pack_workflows(industry_key)

    @router.get("/workflows/runs")
    async def pack_workflow_runs(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
        status: Optional[str] = Query(None),
    ):
        workflows = await industry_workflow_engine.list_workflows(
            db, organization_id=org.id, industry_key=industry_key, status=status
        )
        return [
            {
                "id": w.id,
                "template_key": w.template_key,
                "name": w.name,
                "status": w.status,
                "current_step": w.current_step,
                "progress": w.progress,
                "started_at": w.started_at,
            }
            for w in workflows
        ]

    @router.post("/workflows/activate")
    async def pack_workflow_activate(
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:manage")),
        db: AsyncSession = Depends(get_db),
    ):
        template_key = payload.get("template_key")
        if not template_key:
            raise HTTPException(status_code=400, detail="template_key is required")
        try:
            workflow = await industry_workflow_engine.activate(
                db,
                organization_id=org.id,
                industry_key=industry_key,
                template_key=template_key,
                actor_id=user.id,
                context=payload.get("context") or {},
            )
        except ValueError as exc:
            raise _http(exc)
        await db.commit()
        return {
            "id": workflow.id,
            "template_key": workflow.template_key,
            "name": workflow.name,
            "status": workflow.status,
            "steps": workflow.steps,
            "source_workflow_id": workflow.source_workflow_id,
        }

    @router.post("/workflows/{workflow_id}/advance")
    async def pack_workflow_advance(
        workflow_id: str,
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:manage")),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            workflow = await industry_workflow_engine.advance(
                db, organization_id=org.id, workflow_id=workflow_id,
                step_key=payload.get("step_key"), actor_id=user.id,
            )
        except ValueError as exc:
            raise _http(exc)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        await db.commit()
        return {"id": workflow.id, "status": workflow.status,
                "current_step": workflow.current_step, "progress": workflow.progress}

    @router.get("/compliance")
    async def pack_compliance_route(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
    ):
        policies, _config = await industry_compliance_engine.policies(
            db, organization_id=org.id, industry_key=industry_key
        )
        await db.commit()
        posture = await industry_compliance_engine.latest(
            db, organization_id=org.id, industry_key=industry_key
        )
        return {"rules": policies, "posture": posture}

    @router.post("/compliance/run")
    async def pack_compliance_run(
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:manage")),
        db: AsyncSession = Depends(get_db),
    ):
        result = await industry_compliance_engine.run(
            db,
            organization_id=org.id,
            industry_key=industry_key,
            actor_id=user.id,
            evidence=payload.get("evidence"),
            auto_status=payload.get("auto_status"),
        )
        await db.commit()
        return result

    @router.get("/ai")
    async def pack_ai_status(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
    ):
        status = await industry_ai_router.status(
            db, organization_id=org.id, industry_key=industry_key
        )
        await db.commit()
        return status

    @router.post("/ai/chat")
    async def pack_ai_chat(
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            model_key = payload.get("model_key")
            if not model_key:
                model_key = await industry_ai_router.default_model_key(
                    db, organization_id=org.id, industry_key=industry_key
                )
            result = await industry_ai_router.chat(
                db,
                organization_id=org.id,
                industry_key=industry_key,
                model_key=model_key,
                question=payload.get("question") or "",
                skill=payload.get("skill"),
                context=payload.get("context"),
                actor_id=user.id,
            )
        except ValueError as exc:
            raise _http(exc)
        await db.commit()
        return result

    @router.get("/analytics")
    async def pack_analytics(
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:read")),
        db: AsyncSession = Depends(get_db),
        days: int = Query(30),
    ):
        dashboard = await industry_analytics_engine.dashboard(
            db, organization_id=org.id, industry_key=industry_key, days=days
        )
        await db.commit()
        return dashboard

    @router.post("/analytics/record")
    async def pack_analytics_record(
        payload: dict[str, Any],
        org: Organization = Depends(get_current_organization),
        user: User = Depends(require_permission("industry:manage")),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            recorded = await industry_analytics_engine.record_many(
                db,
                organization_id=org.id,
                industry_key=industry_key,
                values=payload.get("values", []),
                period=payload.get("period", "daily"),
                actor_id=user.id,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise _http(exc)
        await db.commit()
        return {"recorded": len(recorded), "metric_keys": [m.metric_key for m in recorded]}

    # unique operation ids so generated routers never collide in OpenAPI
    for route in router.routes:
        if getattr(route, "operation_id", None):
            route.operation_id = f"{industry_key}_{route.operation_id}"

    return router
