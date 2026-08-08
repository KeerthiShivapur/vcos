"""Autoscaling: metric-driven scale decisions (Phase 16.22)."""

import math
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import AutoscalingEvent
from app.models.organization import gen_uuid

RESOURCES = ("api", "workers", "meeting", "search", "ai", "db_replicas", "cache", "storage")
MIN_CAPACITY = 1
MAX_CAPACITY = 20


class AutoscalingService:
    """Evaluate utilization, scale up/down, record every decision."""

    async def list_events(
        self, db: AsyncSession, *, resource: Optional[str] = None, status: Optional[str] = None, limit: int = 100
    ) -> list[AutoscalingEvent]:
        query = select(AutoscalingEvent)
        if resource:
            query = query.where(AutoscalingEvent.resource == resource)
        if status:
            query = query.where(AutoscalingEvent.status == status)
        result = await db.execute(query.order_by(AutoscalingEvent.triggered_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_event(self, db: AsyncSession, event_id: str) -> Optional[AutoscalingEvent]:
        return await db.get(AutoscalingEvent, event_id)

    async def record(
        self,
        db: AsyncSession,
        *,
        resource: str,
        region: Optional[str] = None,
        direction: str = "scale_up",
        from_capacity: int = 1,
        to_capacity: int = 1,
        metric: str = "cpu_percent",
        threshold: float = 70.0,
        observed: float = 0.0,
        reason: Optional[str] = None,
        status: str = "triggered",
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> AutoscalingEvent:
        if resource not in RESOURCES:
            raise ValueError(f"Unknown resource '{resource}', expected one of {', '.join(RESOURCES)}")
        if direction not in ("scale_up", "scale_down"):
            raise ValueError("direction must be scale_up or scale_down")
        event = AutoscalingEvent(
            id=gen_uuid(),
            resource=resource,
            region=region,
            direction=direction,
            from_capacity=max(1, from_capacity),
            to_capacity=max(MIN_CAPACITY, min(MAX_CAPACITY, to_capacity)),
            metric=metric,
            threshold=threshold,
            observed=observed,
            reason=reason or f"{metric} at {observed}",
            status=status,
            triggered_at=utcnow(),
            actor_id=actor_id,
        )
        db.add(event)
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="autoscaling.triggered",
            actor_id=actor_id,
            payload={
                "event_id": event.id,
                "resource": event.resource,
                "region": event.region,
                "direction": event.direction,
                "from_capacity": event.from_capacity,
                "to_capacity": event.to_capacity,
            },
        )
        return event

    async def apply(self, db: AsyncSession, *, event_id: str, status: str = "applied") -> Optional[AutoscalingEvent]:
        event = await self.get_event(db, event_id)
        if event is None:
            return None
        if status not in ("applied", "reverted", "completed"):
            raise ValueError("status must be applied, reverted or completed")
        event.status = status
        await db.flush()
        return event

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        resource: str = "api",
        region: Optional[str] = None,
        cpu_percent: float = 0.0,
        requests_per_second: float = 0.0,
        latency_ms: float = 0.0,
        current_capacity: int = 2,
        scale_out_at: float = 70.0,
        scale_in_at: float = 30.0,
        cooldown_minutes: int = 5,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> AutoscalingEvent:
        """Decide on the dominant metric; respect cooldown and capacity bounds."""
        if cpu_percent > 0:
            metric, observed = "cpu_percent", cpu_percent
        elif requests_per_second > 0:
            metric, observed = "requests_per_second", requests_per_second
        else:
            metric, observed = "latency_ms", latency_ms

        recent = await self.list_events(db, resource=resource, limit=1)
        if recent:
            last = recent[0]
            elapsed = (utcnow() - last.triggered_at).total_seconds() / 60
            if elapsed < cooldown_minutes:
                return await self.record(
                    db,
                    resource=resource,
                    region=region,
                    organization_id=organization_id,
                    direction="scale_up",
                    from_capacity=current_capacity,
                    to_capacity=current_capacity,
                    metric=metric,
                    threshold=scale_out_at,
                    observed=observed,
                    reason="cooldown active",
                    actor_id=actor_id,
                )

        if observed >= scale_out_at and current_capacity < MAX_CAPACITY:
            desired = min(MAX_CAPACITY, math.ceil(current_capacity * 2))
            return await self.record(
                db,
                resource=resource,
                region=region,
                organization_id=organization_id,
                direction="scale_up",
                from_capacity=current_capacity,
                to_capacity=desired,
                metric=metric,
                threshold=scale_out_at,
                observed=observed,
                reason=f"{metric} {observed} >= high threshold {scale_out_at}",
                actor_id=actor_id,
            )
        if observed <= scale_in_at and current_capacity > MIN_CAPACITY:
            desired = max(MIN_CAPACITY, math.floor(current_capacity / 2))
            return await self.record(
                db,
                resource=resource,
                region=region,
                organization_id=organization_id,
                direction="scale_down",
                from_capacity=current_capacity,
                to_capacity=desired,
                metric=metric,
                threshold=scale_in_at,
                observed=observed,
                reason=f"{metric} {observed} <= low threshold {scale_in_at}",
                actor_id=actor_id,
            )
        return await self.record(
            db,
            resource=resource,
            region=region,
            organization_id=organization_id,
            direction="scale_up",
            from_capacity=current_capacity,
            to_capacity=current_capacity,
            metric=metric,
            threshold=scale_out_at,
            observed=observed,
            reason="within thresholds, no scaling needed",
            actor_id=actor_id,
        )


autoscaling_service = AutoscalingService()
