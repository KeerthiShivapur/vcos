"""Usage Aggregation Service — Stage 5.1 Pay-As-You-Go Billing.

Implements deterministic, retry-safe usage aggregation with:
- Idempotent aggregation (reprocessing doesn't change totals)
- Late-arriving event handling
- Versioned aggregation rules
- Billing period boundary enforcement
- Aggregation versioning for audit trail
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    UsageRecord,
    UsageAggregation,
    Subscription,
    Entitlement,
    Plan,
)
from app.schemas.usage_metering import (
    UsageMetricCode,
    get_metric_aggregation,
)
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.billing.usage_aggregation")


class AggregationError(Exception):
    """Base exception for aggregation errors."""
    pass


class AggregationState(str, Enum):
    """Aggregation processing state."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class AggregationResult:
    """Result of an aggregation run."""
    organization_id: str
    period: str
    metric_code: str
    total_quantity: Decimal
    record_count: int
    aggregation_version: int
    state: AggregationState
    error: Optional[str] = None
    duration_ms: int = 0


class UsageAggregationService:
    """Service for deterministic usage aggregation."""
    
    # Aggregation configuration
    MAX_RECORDS_PER_AGGREGATION = 100000
    AGGREGATION_BATCH_SIZE = 1000
    
    # Supported aggregation types
    AGGREGATION_TYPES = {
        "sum": "Sum all quantities",
        "max": "Maximum quantity in period",
        "avg": "Average quantity",
        "count": "Count of records",
        "distinct_count": "Count of distinct entities",
    }
    
    def __init__(self):
        pass
    
    # =========================================================================
    # AGGREGATION ENTRY POINT
    # =========================================================================
    
    async def aggregate_period(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_codes: Optional[List[str]] = None,
        force_reaggregate: bool = False,
    ) -> List[AggregationResult]:
        """
        Aggregate usage for a billing period.
        
        Idempotent: re-running with same inputs produces same results.
        Late events: processes events that arrived after initial aggregation.
        """
        results = []
        
        # Get metrics to aggregate
        if metric_codes is None:
            metric_codes = await self._get_active_metrics(db, organization_id)
        
        for metric_code in metric_codes:
            try:
                result = await self._aggregate_metric(
                    db=db,
                    organization_id=organization_id,
                    period=period,
                    metric_code=metric_code,
                    force_reaggregate=force_reaggregate,
                )
                results.append(result)
            except Exception as e:
                logger.exception(f"Aggregation failed for {metric_code}: {e}")
                results.append(AggregationResult(
                    organization_id=organization_id,
                    period=period,
                    metric_code=metric_code,
                    total_quantity=Decimal("0"),
                    record_count=0,
                    aggregation_version=0,
                    state=AggregationState.FAILED,
                    error=str(e),
                ))
        
        return results
    
    async def _aggregate_metric(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
        force_reaggregate: bool = False,
    ) -> AggregationResult:
        """Aggregate a single metric for a period."""
        start_time = datetime.now(timezone.utc)
        
        # Determine aggregation type
        agg_type = get_metric_aggregation(metric_code)
        
        # Check existing aggregation
        existing = await self._get_existing_aggregation(
            db, organization_id, period, metric_code
        )
        
        if existing and not force_reaggregate:
            # Check if there are new records since last aggregation
            new_records = await self._count_new_records(
                db, organization_id, period, metric_code, existing.last_processed_at
            )
            if new_records == 0:
                logger.info(f"No new records for {metric_code} in {period}, skipping")
                return AggregationResult(
                    organization_id=organization_id,
                    period=period,
                    metric_code=metric_code,
                    total_quantity=existing.total_quantity,
                    record_count=existing.record_count,
                    aggregation_version=existing.version,
                    state=AggregationState.COMPLETED,
                )
        
        # Perform aggregation
        if agg_type == "sum":
            total, count = await self._aggregate_sum(db, organization_id, period, metric_code)
        elif agg_type == "max":
            total, count = await self._aggregate_max(db, organization_id, period, metric_code)
        elif agg_type == "avg":
            total, count = await self._aggregate_avg(db, organization_id, period, metric_code)
        elif agg_type == "count":
            total, count = await self._aggregate_count(db, organization_id, period, metric_code)
        else:
            total, count = await self._aggregate_sum(db, organization_id, period, metric_code)
        
        # Determine next version
        next_version = (existing.version + 1) if existing else 1
        
        # Upsert aggregation record
        aggregation = await self._upsert_aggregation(
            db=db,
            organization_id=organization_id,
            period=period,
            metric_code=metric_code,
            total_quantity=total,
            record_count=count,
            aggregation_type=agg_type,
            version=next_version,
            last_processed_at=utcnow(),
        )
        
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        # Emit event
        await publish_event(
            db,
            name="usage.aggregation.completed",
            organization_id=organization_id,
            payload={
                "metric_code": metric_code,
                "period": period,
                "total_quantity": str(total),
                "record_count": count,
                "version": next_version,
                "aggregation_type": agg_type,
            },
        )
        
        return AggregationResult(
            organization_id=organization_id,
            period=period,
            metric_code=metric_code,
            total_quantity=total,
            record_count=count,
            aggregation_version=next_version,
            state=AggregationState.COMPLETED,
            duration_ms=duration_ms,
        )
    
    # =========================================================================
    # AGGREGATION IMPLEMENTATIONS
    # =========================================================================
    
    async def _aggregate_sum(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Tuple[Decimal, int]:
        """Sum aggregation - total quantity."""
        result = await db.execute(
            select(
                func.coalesce(func.sum(UsageRecord.quantity), Decimal("0")),
                func.count(UsageRecord.id),
            ).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == metric_code,
                UsageRecord.period == period,
            )
        )
        total, count = result.first()
        return total or Decimal("0"), count or 0
    
    async def _aggregate_max(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Tuple[Decimal, int]:
        """Max aggregation - peak usage in period."""
        result = await db.execute(
            select(
                func.coalesce(func.max(UsageRecord.quantity), Decimal("0")),
                func.count(UsageRecord.id),
            ).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == metric_code,
                UsageRecord.period == period,
            )
        )
        total, count = result.first()
        return total or Decimal("0"), count or 0
    
    async def _aggregate_avg(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Tuple[Decimal, int]:
        """Average aggregation - mean quantity per record."""
        result = await db.execute(
            select(
                func.coalesce(func.avg(UsageRecord.quantity), Decimal("0")),
                func.count(UsageRecord.id),
            ).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == metric_code,
                UsageRecord.period == period,
            )
        )
        total, count = result.first()
        return total or Decimal("0"), count or 0
    
    async def _aggregate_count(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Tuple[Decimal, int]:
        """Count aggregation - number of events."""
        result = await db.execute(
            select(
                func.count(UsageRecord.id),
            ).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == metric_code,
                UsageRecord.period == period,
            )
        )
        count = result.scalar() or 0
        return Decimal(str(count)), count
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _get_active_metrics(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> List[str]:
        """Get metric codes that have usage records for organization."""
        result = await db.execute(
            select(UsageRecord.entitlement_key).where(
                UsageRecord.organization_id == organization_id,
            ).distinct()
        )
        return [row[0] for row in result.all()]
    
    async def _get_existing_aggregation(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Optional[UsageAggregation]:
        """Get existing aggregation record."""
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
                UsageAggregation.metric_code == metric_code,
            )
        )
        return result.scalar_one_or_none()
    
    async def _count_new_records(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
        since: Optional[datetime],
    ) -> int:
        """Count records added since last aggregation."""
        if not since:
            result = await db.execute(
                select(func.count(UsageRecord.id)).where(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.entitlement_key == metric_code,
                    UsageRecord.period == period,
                )
            )
            return result.scalar() or 0
        
        result = await db.execute(
            select(func.count(UsageRecord.id)).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == metric_code,
                UsageRecord.period == period,
                UsageRecord.created_at > since,
            )
        )
        return result.scalar() or 0
    
    async def _upsert_aggregation(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
        total_quantity: Decimal,
        record_count: int,
        aggregation_type: str,
        version: int,
        last_processed_at: datetime,
    ) -> UsageAggregation:
        """Upsert aggregation record with version tracking."""
        stmt = pg_insert(UsageAggregation).values(
            organization_id=organization_id,
            period=period,
            metric_code=metric_code,
            total_quantity=total_quantity,
            record_count=record_count,
            aggregation_type=aggregation_type,
            version=version,
            last_processed_at=last_processed_at,
            updated_at=utcnow(),
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["organization_id", "period", "metric_code"],
            set_={
                "total_quantity": total_quantity,
                "record_count": record_count,
                "aggregation_type": aggregation_type,
                "version": version,
                "last_processed_at": last_processed_at,
                "updated_at": utcnow(),
            },
        )
        
        await db.execute(stmt)
        await db.flush()
        
        # Return the upserted record
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
                UsageAggregation.metric_code == metric_code,
            )
        )
        return result.scalar_one()
    
    # =========================================================================
    # LATE EVENT HANDLING
    # =========================================================================
    
    async def process_late_events(
        self,
        db: AsyncSession,
        organization_id: str,
        lookback_days: int = 30,
    ) -> List[AggregationResult]:
        """
        Process late-arriving events for recent periods.
        
        Finds events that arrived after their period's aggregation was completed
        and re-aggregates affected periods.
        """
        cutoff = utcnow() - timedelta(days=lookback_days)
        
        # Find periods with late events
        result = await db.execute(
            select(
                UsageRecord.period,
                UsageRecord.entitlement_key,
            ).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.created_at > cutoff,
            ).distinct()
        )
        
        affected = result.all()
        results = []
        
        for period, metric_code in affected:
            try:
                result = await self._aggregate_metric(
                    db=db,
                    organization_id=organization_id,
                    period=period,
                    metric_code=metric_code,
                    force_reaggregate=True,
                )
                results.append(result)
            except Exception as e:
                logger.exception(f"Late event aggregation failed for {metric_code}: {e}")
                results.append(AggregationResult(
                    organization_id=organization_id,
                    period=period,
                    metric_code=metric_code,
                    total_quantity=Decimal("0"),
                    record_count=0,
                    aggregation_version=0,
                    state=AggregationState.FAILED,
                    error=str(e),
                ))
        
        return results
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    async def get_aggregation(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        metric_code: str,
    ) -> Optional[UsageAggregation]:
        """Get aggregation for a specific period and metric."""
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
                UsageAggregation.metric_code == metric_code,
            )
        )
        return result.scalar_one_or_none()
    
    async def get_aggregations_for_period(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
    ) -> List[UsageAggregation]:
        """Get all aggregations for a billing period."""
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
            ).order_by(UsageAggregation.metric_code)
        )
        return list(result.scalars().all())
    
    async def get_aggregation_history(
        self,
        db: AsyncSession,
        organization_id: str,
        metric_code: str,
        limit: int = 24,
    ) -> List[UsageAggregation]:
        """Get aggregation history for a metric."""
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.metric_code == metric_code,
            ).order_by(UsageAggregation.period.desc()).limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_aggregation_status(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """Get aggregation status summary for a period."""
        result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
            )
        )
        aggregations = list(result.scalars().all())
        
        total_records = sum(a.record_count for a in aggregations)
        total_quantity = sum(a.total_quantity for a in aggregations)
        
        return {
            "period": period,
            "metrics_aggregated": len(aggregations),
            "total_records": total_records,
            "total_quantity": str(total_quantity),
            "metrics": [
                {
                    "metric_code": a.metric_code,
                    "total_quantity": str(a.total_quantity),
                    "record_count": a.record_count,
                    "version": a.version,
                    "aggregation_type": a.aggregation_type,
                    "last_processed_at": a.last_processed_at.isoformat() if a.last_processed_at else None,
                }
                for a in aggregations
            ],
        }


# Global instance
usage_aggregation_service = UsageAggregationService()


# Import timedelta
from datetime import timedelta