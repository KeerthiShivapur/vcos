"""Gate 24 — Integration Health Service.

Implements operational visibility for administrators:
- Connection status
- Last synchronization
- Sync lag
- Events processed/failed
- Authentication status
- Rate limits
- Conflicts & mapping problems
- Data freshness
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    IntegrationHealth,
    ConnectorInstance,
    Connector,
    SyncRun,
    ExternalEvent,
    ExternalConflict,
    ExternalIdentityMapping,
)

logger = logging.getLogger("vcos.integration.health")


class IntegrationHealthService:
    """Service for monitoring integration health."""
    
    # ------------------------------------------------------------ Health Calculation
    
    async def calculate_health(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
    ) -> IntegrationHealth:
        """Calculate and update health for a connector instance."""
        
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if instance is None or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Get or create health record
        result = await db.execute(
            select(IntegrationHealth).where(
                IntegrationHealth.connector_instance_id == connector_instance_id
            )
        )
        health = result.scalar_one_or_none()
        
        if health is None:
            health = IntegrationHealth(
                organization_id=organization_id,
                connector_instance_id=connector_instance_id,
            )
            db.add(health)
        
        # Connection status
        health.connection_status = instance.state
        health.last_connection_check = utcnow()
        
        # Authentication
        if instance.credentials_expires_at:
            health.credentials_expire_at = instance.credentials_expires_at
            if instance.credentials_expires_at < utcnow():
                health.auth_status = "expired"
            else:
                health.auth_status = "valid"
        else:
            health.auth_status = "unknown"
        
        # Synchronization
        last_sync = await db.execute(
            select(SyncRun).where(
                SyncRun.connector_instance_id == connector_instance_id,
                SyncRun.state == "completed",
            ).order_by(desc(SyncRun.completed_at)).limit(1)
        )
        last_completed = last_sync.scalar_one_or_none()
        
        if last_completed:
            health.last_successful_sync = last_completed.completed_at
            if health.last_successful_sync:
                health.sync_lag_seconds = int((utcnow() - health.last_successful_sync).total_seconds())
        
        last_attempt = await db.execute(
            select(SyncRun).where(
                SyncRun.connector_instance_id == connector_instance_id,
            ).order_by(desc(SyncRun.started_at)).limit(1)
        )
        last_run = last_attempt.scalar_one_or_none()
        
        if last_run:
            health.last_sync_attempt = last_run.started_at
            health.last_sync_state = last_run.state
        
        # Sync success rate (last 10 runs)
        recent_runs = await db.execute(
            select(SyncRun).where(
                SyncRun.connector_instance_id == connector_instance_id,
                SyncRun.state.in_(["completed", "failed", "partial"]),
            ).order_by(desc(SyncRun.started_at)).limit(10)
        )
        runs = list(recent_runs.scalars().all())
        if runs:
            completed = sum(1 for r in runs if r.state == "completed")
            health.sync_success_rate = completed / len(runs)
        
        # Events (last 24h)
        since_24h = utcnow() - timedelta(hours=24)
        events_24h = await db.execute(
            select(ExternalEvent).where(
                ExternalEvent.organization_id == organization_id,
                ExternalEvent.connector_instance_id == connector_instance_id,
                ExternalEvent.received_at >= since_24h,
            )
        )
        events = list(events_24h.scalars().all())
        
        health.events_processed_24h = sum(1 for e in events if e.state == "processed")
        health.events_failed_24h = sum(1 for e in events if e.state == "failed")
        health.events_pending = sum(1 for e in events if e.state == "pending")
        
        # Oldest pending event
        pending_events = [e for e in events if e.state == "pending"]
        if pending_events:
            oldest = min(pending_events, key=lambda e: e.received_at)
            health.oldest_pending_event_age_seconds = int((utcnow() - oldest.received_at).total_seconds())
        
        # Conflicts & mappings
        conflicts = await db.execute(
            select(ExternalConflict).where(
                ExternalConflict.organization_id == organization_id,
                or_(
                    ExternalConflict.source_a_instance_id == connector_instance_id,
                    ExternalConflict.source_b_instance_id == connector_instance_id,
                ),
                ExternalConflict.resolution_state == "open",
            )
        )
        health.active_conflicts = len(list(conflicts.scalars().all()))
        
        pending_mappings = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.mapping_state == "pending",
            )
        )
        health.pending_mappings = len(list(pending_mappings.scalars().all()))
        
        mapping_conflicts = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.mapping_state == "conflict",
            )
        )
        health.mapping_conflicts = len(list(mapping_conflicts.scalars().all()))
        
        # Data freshness
        if health.last_successful_sync:
            hours_since_sync = (utcnow() - health.last_successful_sync).total_seconds() / 3600
            # Freshness decays over 24 hours
            health.data_freshness_score = max(0.0, 1.0 - (hours_since_sync / 24.0))
        
        # Overall status
        health.overall_status = self._calculate_overall_status(health, instance)
        
        health.last_calculated_at = utcnow()
        health.updated_at = utcnow()
        
        await db.flush()
        return health
    
    def _calculate_overall_status(
        self, health: IntegrationHealth, instance: ConnectorInstance
    ) -> str:
        """Calculate overall health status."""
        
        if instance.state in ("error", "revoked", "reauthorization_required"):
            return "error"
        
        if instance.state == "paused":
            return "degraded"
        
        if health.auth_status == "expired":
            return "reauth_required"
        
        if health.auth_status == "invalid":
            return "error"
        
        if health.active_conflicts > 0 or health.mapping_conflicts > 0:
            return "degraded"
        
        if health.events_failed_24h > 10:
            return "degraded"
        
        if health.events_pending > 100:
            return "degraded"
        
        if health.sync_success_rate is not None and health.sync_success_rate < 0.8:
            return "degraded"
        
        if health.sync_lag_seconds is not None and health.sync_lag_seconds > 3600:
            return "degraded"
        
        if health.data_freshness_score is not None and health.data_freshness_score < 0.5:
            return "degraded"
        
        return "healthy"
    
    async def refresh_all_health(
        self, db: AsyncSession, organization_id: str
    ) -> list[IntegrationHealth]:
        """Refresh health for all connector instances in an organization."""
        
        instances = await db.execute(
            select(ConnectorInstance).where(
                ConnectorInstance.organization_id == organization_id
            )
        )
        
        health_records = []
        for instance in instances.scalars().all():
            health = await self.calculate_health(db, organization_id, instance.id)
            health_records.append(health)
        
        await db.flush()
        return health_records
    
    # ------------------------------------------------------------ Health Queries
    
    async def get_health(
        self, db: AsyncSession, connector_instance_id: str
    ) -> Optional[IntegrationHealth]:
        """Get health for a connector instance."""
        result = await db.execute(
            select(IntegrationHealth).where(
                IntegrationHealth.connector_instance_id == connector_instance_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_health(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        overall_status: Optional[str] = None,
    ) -> list[IntegrationHealth]:
        """List health records for an organization."""
        query = select(IntegrationHealth).where(
            IntegrationHealth.organization_id == organization_id
        )
        if overall_status:
            query = query.where(IntegrationHealth.overall_status == overall_status)
        query = query.order_by(IntegrationHealth.overall_status, IntegrationHealth.last_calculated_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_unhealthy_integrations(
        self, db: AsyncSession, organization_id: str
    ) -> list[IntegrationHealth]:
        """Get integrations that are not healthy."""
        return await self.list_health(
            db, organization_id, overall_status="error"
        ) + await self.list_health(
            db, organization_id, overall_status="degraded"
        ) + await self.list_health(
            db, organization_id, overall_status="reauth_required"
        )
    
    async def get_health_summary(
        self, db: AsyncSession, organization_id: str
    ) -> dict[str, Any]:
        """Get a summary of integration health."""
        
        health_records = await self.list_health(db, organization_id)
        
        summary = {
            "total": len(health_records),
            "healthy": sum(1 for h in health_records if h.overall_status == "healthy"),
            "degraded": sum(1 for h in health_records if h.overall_status == "degraded"),
            "error": sum(1 for h in health_records if h.overall_status == "error"),
            "reauth_required": sum(1 for h in health_records if h.overall_status == "reauth_required"),
            "unknown": sum(1 for h in health_records if h.overall_status == "unknown"),
            "by_provider": {},
        }
        
        # Group by provider
        for health in health_records:
            instance = await db.get(ConnectorInstance, health.connector_instance_id)
            if instance:
                connector = await db.get(Connector, instance.connector_id)
                if connector:
                    provider = connector.provider
                    if provider not in summary["by_provider"]:
                        summary["by_provider"][provider] = {
                            "healthy": 0, "degraded": 0, "error": 0, "total": 0
                        }
                    summary["by_provider"][provider]["total"] += 1
                    summary["by_provider"][provider][health.overall_status] += 1
        
        return summary


integration_health_service = IntegrationHealthService()