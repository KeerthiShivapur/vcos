"""Synchronization worker (Gate 24) — drains queued sync runs and processes external events.

Runs:
- Scheduled incremental syncs
- Full syncs
- External event processing
- Webhook event processing
- Retry failed operations

Run standalone: python -m app.workers.sync_worker
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from app.intelligence.synchronization_service import synchronization_service
from app.intelligence.company_context import CallerAccess
from app.db.database import SessionLocal

logger = logging.getLogger("vcos.workers.sync")


_MAX_SYNC_RUNS_PER_PASS = 10
_MAX_EVENTS_PER_PASS = 100
_MAX_OPERATIONS_PER_PASS = 50


def _system_caller(organization_id: str) -> CallerAccess:
    """Build a system-level caller identity for background execution."""
    return CallerAccess(
        organization_id=organization_id,
        user_id="system",
        employee_id=None,
        org_wide=True,
    )


async def run_once(db=None) -> int:
    """Process one batch of sync work."""
    owns_session = db is None
    total_processed = 0
    
    async def _work(session) -> int:
        processed = 0
        
        from sqlalchemy import select
        from app.models.canonical_integration import (
            SyncRun,
            ConnectorInstance,
            ExternalEvent,
            ExternalOperation,
        )
        from app.services.sync_worker import create_sync_worker
        from app.services.external_operation_service import external_operation_service
        
        sync_worker = create_sync_worker()
        
        # 1. Process pending sync runs
        sync_runs = (
            await session.execute(
                select(SyncRun).where(
                    SyncRun.state == "pending",
                ).order_by(SyncRun.started_at.asc(), SyncRun.id.asc()).limit(_MAX_SYNC_RUNS_PER_PASS)
            )
        ).scalars().all()
        
        for sync_run in sync_runs:
            try:
                started = await synchronization_service.start_sync_run(session, sync_run.id)
                if started is None:
                    continue
                
                result = await sync_worker.execute_sync_run(session, sync_run)
                
                if result.error:
                    state = "failed" if result.entities_processed == 0 else "partial"
                elif result.entities_failed:
                    state = "partial"
                else:
                    state = "completed"
                
                await synchronization_service.complete_sync_run(
                    session,
                    sync_run.id,
                    state=state,
                    error=result.error,
                    entities_processed=result.entities_processed,
                    entities_created=result.entities_created,
                    entities_updated=result.entities_updated,
                    entities_deleted=result.entities_deleted,
                    entities_failed=result.entities_failed,
                    conflicts_detected=result.conflicts_detected,
                )
                processed += 1
                
            except Exception as exc:
                logger.exception("Sync run %s failed: %s", sync_run.id, exc)
                await synchronization_service.complete_sync_run(
                    session, sync_run.id, state="failed", error=str(exc)
                )
        
        # 2. Process pending external events
        pending_events = (
            await session.execute(
                select(ExternalEvent).where(
                    ExternalEvent.state == "pending",
                ).order_by(ExternalEvent.received_at.asc()).limit(_MAX_EVENTS_PER_PASS)
            )
        ).scalars().all()
        
        for event in pending_events:
            try:
                await synchronization_service.process_external_event(
                    session, event.id, _default_event_processor
                )
                processed += 1
            except Exception as exc:
                logger.exception("Event %s processing failed: %s", event.id, exc)
        
        # 3. Execute pending, governance-verified external operations
        pending_ops = (
            await session.execute(
                select(ExternalOperation).where(
                    ExternalOperation.state == "pending",
                    ExternalOperation.governance_verified.is_(True),
                ).order_by(ExternalOperation.created_at.asc()).limit(_MAX_OPERATIONS_PER_PASS)
            )
        ).scalars().all()
        
        for operation in pending_ops:
            try:
                await external_operation_service.execute_operation(
                    session, operation.id, _system_caller(operation.organization_id)
                )
                processed += 1
            except Exception as exc:
                logger.warning("Operation %s execution failed: %s", operation.id, exc)
        
        return processed
    
    if owns_session:
        async with SessionLocal() as session:
            total_processed = await _work(session)
            await session.commit()
    else:
        total_processed = await _work(db)
    
    return total_processed


async def _default_event_processor(db, event) -> Dict[str, Any]:
    """Default external event processor: resolve referenced identities (governed).

    Externally observed events never mutate canonical entities directly; the
    governed identity mapping is the only canonical-adjacent write.
    """
    from app.services.external_identity_service import external_identity_service
    
    external_id = None
    if event.source_type in ("person", "user", "member") and event.source_id:
        external_id = event.source_id
    elif event.external_actor_id:
        external_id = event.external_actor_id
    
    if not external_id:
        return {"processing": "no_identity_reference"}
    
    payload = event.payload or {}
    display_name = payload.get("display_name") or payload.get("name")
    if isinstance(display_name, dict):
        display_name = display_name.get("fullName") or display_name.get("displayName")
    
    mapping = await external_identity_service.resolve_identity(
        db=db,
        organization_id=event.organization_id,
        connector_instance_id=event.connector_instance_id,
        external_id=external_id,
        external_email=payload.get("email") or payload.get("primaryEmail"),
        external_display_name=display_name,
        external_metadata={"source": "event_worker", "event_id": event.id},
        source_event_id=event.id,
    )
    
    return {
        "processing": "identity_resolved",
        "mapping_id": mapping.id,
        "mapping_state": mapping.mapping_state,
    }


async def run_forever(interval_seconds: int = 30) -> None:
    """Run the sync worker continuously."""
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("sync worker processed %s items", processed)
        except Exception as exc:
            logger.exception("sync worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())