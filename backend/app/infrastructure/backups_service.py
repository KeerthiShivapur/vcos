"""Backups, PITR and restore (Phase 16.20)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import BackupRecord
from app.models.organization import gen_uuid

BACKUP_KINDS = ("hourly", "daily", "weekly", "cross_region", "pitr")
BACKUP_TARGETS = ("postgres", "redis", "neo4j", "opensearch", "object_storage", "ai")
BACKUP_STATUSES = ("started", "completed", "failed", "restoring", "restored", "expired")


class BackupsService:
    """Automated backups with point-in-time recovery (PITR)."""

    async def list_backups(
        self, db: AsyncSession, *, status: Optional[str] = None, kind: Optional[str] = None, limit: int = 100
    ) -> list[BackupRecord]:
        query = select(BackupRecord)
        if status:
            query = query.where(BackupRecord.status == status)
        if kind:
            query = query.where(BackupRecord.kind == kind)
        result = await db.execute(query.order_by(BackupRecord.started_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_backup(self, db: AsyncSession, backup_id: str) -> Optional[BackupRecord]:
        return await db.get(BackupRecord, backup_id)

    async def create(
        self,
        db: AsyncSession,
        *,
        kind: str = "daily",
        target: str = "postgres",
        region: Optional[str] = None,
        retention_days: int = 30,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> BackupRecord:
        if kind not in BACKUP_KINDS:
            raise ValueError(f"Unknown backup kind '{kind}', expected one of {', '.join(BACKUP_KINDS)}")
        if target not in BACKUP_TARGETS:
            raise ValueError(f"Unknown backup target '{target}', expected one of {', '.join(BACKUP_TARGETS)}")
        record = BackupRecord(
            id=gen_uuid(),
            kind=kind,
            target=target,
            region=region,
            status="started",
            retention_days=max(1, retention_days),
            started_at=utcnow(),
            actor_id=actor_id,
        )
        db.add(record)
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="backup.started",
            actor_id=actor_id,
            payload={"backup_id": record.id, "kind": record.kind, "target": record.target},
        )
        return record

    async def complete(
        self,
        db: AsyncSession,
        *,
        backup_id: str,
        status: str = "completed",
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
        storage_key: Optional[str] = None,
        verified: bool = False,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[BackupRecord]:
        if status not in BACKUP_STATUSES:
            raise ValueError(f"status must be one of {', '.join(BACKUP_STATUSES)}")
        record = await self.get_backup(db, backup_id)
        if record is None:
            return None
        record.status = status
        record.completed_at = utcnow()
        if size_bytes is not None:
            record.size_bytes = max(0, size_bytes)
        if checksum:
            record.checksum = checksum
        if storage_key:
            record.storage_key = storage_key
        if verified:
            record.verified = True
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name=f"backup.{status}",
            actor_id=actor_id,
            payload={"backup_id": record.id, "kind": record.kind, "size_bytes": record.size_bytes},
        )
        return record

    async def restore(
        self, db: AsyncSession, *, backup_id: str, target: str = "current", organization_id: Optional[str] = None, actor_id: Optional[str] = None
    ) -> Optional[BackupRecord]:
        record = await self.get_backup(db, backup_id)
        if record is None:
            return None
        if record.status != "completed":
            raise ValueError("only completed backups can be restored")
        record.status = "restoring"
        await db.flush()
        record.status = "restored"
        record.completed_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="backup.restored",
            actor_id=actor_id,
            payload={"backup_id": record.id, "target": target},
        )
        return record

    async def pitr_point(self, db: AsyncSession, *, timestamp: str, max_lag_minutes: int = 5) -> dict[str, Any]:
        """Compute the recovery point and validate it against recent backups."""
        from datetime import datetime

        from app.core.timeutils import ensure_aware

        try:
            target = ensure_aware(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp must be an ISO-8601 datetime") from exc
        backups = await self.list_backups(db, status="completed")
        backup = None
        for candidate in backups:
            if candidate.started_at and ensure_aware(candidate.started_at) <= target:
                backup = candidate
                break
        if backup is None:
            return {"available": False, "reason": "no completed backup before the requested timestamp"}
        lag_minutes = max(0, round((target - ensure_aware(backup.started_at)).total_seconds() / 60))
        available = lag_minutes <= max_lag_minutes or backup.kind in ("pitr", "hourly")
        return {
            "available": available,
            "backup_id": backup.id,
            "kind": backup.kind,
            "recovery_timestamp": backup.started_at.isoformat(),
            "lag_minutes": lag_minutes,
            "reason": "within PITR window" if available else "outside PITR window",
        }

    async def summary(self, db: AsyncSession) -> dict[str, Any]:
        rows = await self.list_backups(db, limit=1000)
        by_status: dict[str, int] = {}
        total_bytes = 0
        for row in rows:
            by_status[row.status] = by_status.get(row.status, 0) + 1
            total_bytes += row.size_bytes or 0
        return {
            "backups": len(rows),
            "by_status": by_status,
            "total_storage_bytes": total_bytes,
            "verified": sum(1 for row in rows if row.verified),
            "last_completed": next((r.started_at.isoformat() for r in rows if r.status == "completed"), None),
        }

    async def gap_analysis(self, db: AsyncSession) -> dict[str, Any]:
        """Find datasets never backed up, or stale backups."""
        rows = await self.list_backups(db, limit=1000)
        covered = {row.target for row in rows}
        unprotected = [t for t in BACKUP_TARGETS if t not in covered]
        stale = [
            row
            for row in rows
            if row.completed_at
            and (utcnow() - ensure_aware(row.completed_at)).days > row.retention_days
        ]
        return {
            "total_backups": len(rows),
            "unprotected_targets": unprotected,
            "stale_backups": len(stale),
            "recommendation": "schedule daily full + hourly pitr backups" if unprotected else "backup coverage healthy",
        }


backups_service = BackupsService()
