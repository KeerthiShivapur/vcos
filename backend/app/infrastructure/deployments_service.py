"""Zero-downtime deployments: rolling, blue-green, canary, rollback (Phase 16.19)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import DeploymentRecord
from app.models.organization import gen_uuid

STRATEGIES = ("blue_green", "canary", "rolling", "rollback", "validate")


class DeploymentsService:
    """Deployment history with safe release strategies."""

    async def list_deployments(
        self, db: AsyncSession, *, service: Optional[str] = None, status: Optional[str] = None, limit: int = 100
    ) -> list[DeploymentRecord]:
        query = select(DeploymentRecord)
        if service:
            query = query.where(DeploymentRecord.service == service)
        if status:
            query = query.where(DeploymentRecord.status == status)
        result = await db.execute(query.order_by(DeploymentRecord.started_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_deployment(self, db: AsyncSession, deployment_id: str) -> Optional[DeploymentRecord]:
        return await db.get(DeploymentRecord, deployment_id)

    async def start(
        self,
        db: AsyncSession,
        *,
        version: str,
        service: str,
        strategy: str = "rolling",
        region: Optional[str] = None,
        commit_sha: Optional[str] = None,
        old_replicas: int = 3,
        new_replicas: int = 3,
        canary_percentage: int = 10,
        reason: Optional[str] = None,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> DeploymentRecord:
        if not version.strip() or not service.strip():
            raise ValueError("Version and service are required")
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{strategy}', expected one of {', '.join(STRATEGIES)}")
        if strategy == "canary":
            canary_percentage = max(0, min(100, canary_percentage))
        deployment = DeploymentRecord(
            id=gen_uuid(),
            version=version.strip(),
            service=service.strip(),
            region=region,
            strategy=strategy,
            status="started",
            commit_sha=commit_sha,
            old_replicas=old_replicas,
            new_replicas=new_replicas,
            canary_percentage=canary_percentage,
            started_at=utcnow(),
            reason=reason,
            actor_id=actor_id,
        )
        db.add(deployment)
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="deployment.started",
            actor_id=actor_id,
            payload={"deployment_id": deployment.id, "service": deployment.service, "version": deployment.version, "strategy": deployment.strategy},
        )
        return deployment

    async def complete(
        self,
        db: AsyncSession,
        *,
        deployment_id: str,
        status: str = "completed",
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[DeploymentRecord]:
        deployment = await self.get_deployment(db, deployment_id)
        if deployment is None:
            return None
        if status not in ("completed", "failed", "rolled_back", "promoted"):
            raise ValueError("status must be completed, promoted, failed or rolled_back")
        deployment.status = status
        deployment.completed_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name=f"deployment.{status}",
            actor_id=actor_id,
            payload={"deployment_id": deployment.id, "service": deployment.service, "version": deployment.version},
        )
        return deployment

    async def promote_canary(self, db: AsyncSession, *, deployment_id: str, organization_id: Optional[str] = None, actor_id: Optional[str] = None) -> Optional[DeploymentRecord]:
        deployment = await self.get_deployment(db, deployment_id)
        if deployment is None:
            return None
        if deployment.strategy != "canary":
            raise ValueError("only canary deployments can be promoted")
        deployment.canary_percentage = 100
        deployment.status = "promoted"
        deployment.completed_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="deployment.completed",
            actor_id=actor_id,
            payload={"deployment_id": deployment.id, "service": deployment.service, "version": deployment.version, "promoted": True},
        )
        return deployment

    async def rollback(self, db: AsyncSession, *, deployment_id: str, organization_id: Optional[str] = None, actor_id: Optional[str] = None) -> Optional[DeploymentRecord]:
        deployment = await self.get_deployment(db, deployment_id)
        if deployment is None:
            return None
        deployment.status = "rolled_back"
        deployment.completed_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="deployment.rolled_back",
            actor_id=actor_id,
            payload={"deployment_id": deployment.id, "service": deployment.service, "version": deployment.version},
        )
        return deployment

    async def validate(self, db: AsyncSession, *, version: str, service: str, strategy: str = "blue_green") -> dict[str, Any]:
        """Dry-run validation: check version format and strategy fit."""
        problems: list[str] = []
        if not version.strip():
            problems.append("version is empty")
        elif len(version) > 30:
            problems.append("version exceeds 30 characters")
        if not service.strip():
            problems.append("service is empty")
        if strategy not in STRATEGIES:
            problems.append(f"unknown strategy '{strategy}'")
        return {
            "valid": len(problems) == 0,
            "version": version,
            "service": service,
            "strategy": strategy,
            "problems": problems,
        }


deployments_service = DeploymentsService()
