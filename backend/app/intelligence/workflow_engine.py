"""Phase 9.12 — Workflow intelligence engine.

Observes workflow execution to find:
    - slow approvals / approval bottlenecks
    - duplicate work signals
    - manual work / automation opportunities

Produces WorkflowInsight rows with concrete recommendations.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.approval import Approval
from app.models.intelligence import WorkflowInsight

logger = logging.getLogger("vcos.intelligence.workflow")

SLOW_APPROVAL_HOURS = 48


class WorkflowEngine:
    async def scan(self, db: AsyncSession, *, organization_id: str) -> int:
        created = 0
        created += await self._slow_approvals(db, organization_id=organization_id)
        created += await self._approval_volume(db, organization_id=organization_id)
        if created:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="workflow.optimized",
                organization_id=organization_id,
                payload={"new_insights": created},
            )
        return created

    async def _upsert(
        self, db: AsyncSession, *, organization_id: str, insight_type: str,
        entity_type: Optional[str], entity_id: Optional[str],
        title: str, detail: Optional[str], severity: str, recommendation: Optional[str],
    ) -> int:
        existing = (
            await db.execute(
                select(WorkflowInsight).where(
                    WorkflowInsight.organization_id == organization_id,
                    WorkflowInsight.insight_type == insight_type,
                    WorkflowInsight.entity_type == entity_type,
                    WorkflowInsight.entity_id == entity_id,
                    WorkflowInsight.status == "open",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return 0
        db.add(
            WorkflowInsight(
                organization_id=organization_id,
                insight_type=insight_type,
                entity_type=entity_type,
                entity_id=entity_id,
                title=title,
                detail=detail,
                severity=severity,
                status="open",
                recommendation=recommendation,
            )
        )
        return 1

    async def _slow_approvals(self, db: AsyncSession, *, organization_id: str) -> int:
        cutoff = utcnow() - timedelta(hours=SLOW_APPROVAL_HOURS)
        rows = (
            await db.execute(
                select(Approval)
                .where(
                    Approval.organization_id == organization_id,
                    Approval.status == "pending",
                    Approval.created_at < cutoff,
                )
                .order_by(Approval.created_at.asc())
                .limit(20)
            )
        ).scalars().all()
        created = 0
        for approval in rows:
            hours = (utcnow() - ensure_aware(approval.created_at)).total_seconds() / 3600
            created += await self._upsert(
                db, organization_id=organization_id,
                insight_type="slow_approval",
                entity_type="approval", entity_id=approval.id,
                title=f"Slow approval: {approval.title[:160]}",
                detail=f"Pending for {hours:.0f} hours.",
                severity="warning" if hours > SLOW_APPROVAL_HOURS * 2 else "info",
                recommendation="Escalate or remind the approver.",
            )
        return created

    async def _approval_volume(self, db: AsyncSession, *, organization_id: str) -> int:
        """Many approvals in a short window = workflow automation opportunity."""
        from app.models.approval import Approval as ApprovalModel

        window_start = utcnow() - timedelta(days=30)
        total = (
            await db.execute(
                select(func.count(ApprovalModel.id)).where(
                    ApprovalModel.organization_id == organization_id,
                    ApprovalModel.created_at >= window_start,
                )
            )
        ).scalar() or 0
        if total < 20:
            return 0
        return await self._upsert(
            db, organization_id=organization_id,
            insight_type="automation",
            entity_type=None, entity_id=None,
            title="Approval automation opportunity",
            detail=f"{total} approval requests in the last 30 days.",
            severity="info",
            recommendation="Consider routing rules or pre-approvals for low-risk requests.",
        )

    async def list_insights(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50,
        status: Optional[str] = "open",
    ) -> list[dict[str, Any]]:
        filters = [WorkflowInsight.organization_id == organization_id]
        if status:
            filters.append(WorkflowInsight.status == status)
        rows = (
            await db.execute(
                select(WorkflowInsight).where(*filters)
                .order_by(WorkflowInsight.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "insight_type": r.insight_type,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "title": r.title,
                "detail": r.detail,
                "severity": r.severity,
                "status": r.status,
                "recommendation": r.recommendation,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def set_status(self, db: AsyncSession, *, organization_id: str, insight_id: str, status: str) -> Optional[dict[str, Any]]:
        row = await db.get(WorkflowInsight, insight_id)
        if row is None or row.organization_id != organization_id:
            return None
        row.status = status
        return {"id": row.id, "status": row.status}


workflow_engine = WorkflowEngine()
