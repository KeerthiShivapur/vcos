"""Enterprise AI service (Phase 15).

Model routing gated by license entitlements, data-residency/consent policy,
usage accounting (tokens, requests) and an audit trail of AI usage so
organizations can demonstrate governed AI adoption.
"""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.enterprise.licensing_service import PLANS, licensing_service
from app.events.publisher import publish_event
from app.models.enterprise import ObservabilityLog, SystemMetric
from app.models.workspace import AITenantMemory

# model -> (minimum plan tier, data residency)
MODEL_CATALOG: dict[str, dict[str, Any]] = {
    "gpt-4o": {"tier": "professional", "residency": "us-east", "modality": "chat"},
    "gpt-4o-mini": {"tier": "starter", "residency": "us-east", "modality": "chat"},
    "claude-sonnet": {"tier": "professional", "residency": "eu-west", "modality": "chat"},
    "embedding-small": {"tier": "starter", "residency": "us-east", "modality": "embedding"},
    "vision-standard": {"tier": "enterprise", "residency": "us-east", "modality": "vision"},
}

CONSENT_SCOPES = ("model_training", "data_sharing", "memory_retention")


class AiService:
    async def models(self, db: AsyncSession, organization_id: str) -> list[dict[str, Any]]:
        allowed_tiers = ("starter", "professional", "enterprise", "custom")
        license_row = await licensing_service.get_license(db, organization_id)
        tier = license_row.plan if license_row.plan in allowed_tiers else "starter"
        plan = PLANS.get(license_row.plan, PLANS["starter"])
        features = set(license_row.features or plan["features"])
        out = []
        for model, meta in MODEL_CATALOG.items():
            tiers = ("starter", "professional", "enterprise", "custom")
            idx = tiers.index(tier) if tier in tiers else 0
            required = meta["tier"]
            available = (idx >= tiers.index(required)) or "ai" in features
            out.append({**meta, "model": model, "available": available})
        return out

    async def record_usage(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        model: str,
        tokens: int,
        actor_id: Optional[str] = None,
    ) -> None:
        db.add(
            SystemMetric(
                organization_id=organization_id,
                name="ai_tokens",
                value=float(tokens),
                unit="tokens",
                tags={"model": model},
                recorded_at=utcnow(),
            )
        )
        db.add(
            SystemMetric(
                organization_id=organization_id,
                name="ai_requests",
                value=1.0,
                unit="requests",
                tags={"model": model},
                recorded_at=utcnow(),
            )
        )
        await publish_event(
            db,
            name="ai.usage.recorded",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"model": model, "tokens": tokens},
        )

    async def usage(
        self, db: AsyncSession, *, organization_id: str
    ) -> dict[str, Any]:
        tokens = (
            await db.execute(
                select(func.sum(SystemMetric.value)).where(
                    SystemMetric.organization_id == organization_id,
                    SystemMetric.name == "ai_tokens",
                )
            )
        ).scalar_one() or 0
        requests = (
            await db.execute(
                select(func.sum(SystemMetric.value)).where(
                    SystemMetric.organization_id == organization_id,
                    SystemMetric.name == "ai_requests",
                )
            )
        ).scalar_one() or 0
        return {
            "tokens_used": float(tokens),
            "requests": float(requests),
            "window": "all_time",
        }

    async def set_consent(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        actor_id: str,
        scope: str,
        granted: bool,
    ) -> dict[str, Any]:
        if scope not in CONSENT_SCOPES:
            raise ValueError(f"unknown consent scope: {scope}")
        db.add(
            ObservabilityLog(
                organization_id=organization_id,
                level="info",
                source="ai",
                message=f"AI consent {'granted' if granted else 'revoked'} for {scope}",
                details={"scope": scope, "granted": granted, "actor": actor_id},
                recorded_at=utcnow(),
            )
        )
        await publish_event(
            db,
            name="ai.consent.changed",
            organization_id=organization_id,
            actor_id=actor_id,
            payload={"scope": scope, "granted": granted},
        )
        return {"scope": scope, "granted": granted, "actor_id": actor_id}

    async def memory_settings(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        count = (
            await db.execute(
                select(func.count(AITenantMemory.id)).where(
                    AITenantMemory.organization_id == organization_id
                )
            )
        ).scalar_one()
        return {
            "memory_records": int(count),
            "consent_scopes": CONSENT_SCOPES,
            "residencies": sorted({meta["residency"] for meta in MODEL_CATALOG.values()}),
        }


ai_service = AiService()
