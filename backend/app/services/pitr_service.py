"""PITR (Point-in-Time Recovery) Service — integrates with backup/restore pipeline.

Implements capability-aware PITR operations:
- WAL archiving management
- Continuous backup coordination
- Target-time recovery with validation
- PITR window management
- Capability-aware PITR availability
- Integration with backup/restore pipeline
- RPO/RTO measurement integration
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List, Dict

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.backup_manifest import (
    BackupManifest,
    BackupKind,
    BackupStatus,
    RestoreOperation,
)
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
)
from app.validation.capability_contract import (
    ValidationStatus,
    ValidationCheck,
    ValidationResult,
    EnvironmentCapability,
    CapabilityDetector,
    CapabilityAwareValidator,
)
from app.services.backup_service import backup_service, BackupKind
from app.services.restore_service import restore_service
from app.services.rpo_rto_measurement import rpo_rto_service as rpo_rto_measurement_service
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    severity_matches,
)

logger = logging.getLogger("vcos.pitr")


class PITROperationType(str, Enum):
    """Types of PITR operations."""
    WAL_ARCHIVE = "wal_archive"
    BASE_BACKUP = "base_backup"
    TARGET_TIME_RECOVERY = "target_time_recovery"
    PITR_WINDOW_CHECK = "pitr_window_check"
    WAL_ARCHIVE_VERIFY = "wal_archive_verify"
    CONTINUOUS_BACKUP = "continuous_backup"


class PITRStatus(str, Enum):
    """PITR operation status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"


@dataclass
class PITRConfiguration:
    """PITR configuration settings."""
    enabled: bool = True
    window_hours: int = 336  # 14 days
    max_lag_minutes: int = 5
    wal_archive_interval_seconds: int = 60
    retention_hours: int = 336
    cross_region_replication: bool = True


@dataclass
class PITROperation:
    """A PITR operation record."""
    operation_id: str
    operation_type: PITROperationType
    status: PITRStatus
    organization_id: str
    target_time: Optional[datetime] = None
    backup_id: Optional[str] = None
    started_at: datetime = field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PITRWindowStatus:
    """PITR window availability status."""
    available: bool
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    latest_wal_archive: Optional[datetime] = None
    lag_minutes: Optional[float] = None
    max_lag_minutes: int = 5
    reason: str = ""


@dataclass
class PITRRecoveryResult:
    """Result of a PITR recovery operation."""
    success: bool
    operation_id: str
    target_time: Optional[datetime] = None
    actual_recovery_time: Optional[datetime] = None
    backup_used: Optional[str] = None
    wal_files_applied: int = 0
    validation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PITRService(CapabilityAwareValidator):
    """Capability-aware PITR service integrating with backup/restore pipeline."""
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.config = PITRConfiguration()
        self._active_operations: Dict[str, PITROperation] = {}
        self._wal_archive_monitor_task: Optional[asyncio.Task] = None
    
    async def start_monitoring(self, db: AsyncSession) -> None:
        """Start PITR monitoring (WAL archive lag, window health)."""
        if self._wal_archive_monitor_task is None or self._wal_archive_monitor_task.done():
            self._wal_archive_monitor_task = asyncio.create_task(
                self._monitor_wal_archive_lag(db)
            )
            logger.info("PITR monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop PITR monitoring."""
        if self._wal_archive_monitor_task and not self._wal_archive_monitor_task.done():
            self._wal_archive_monitor_task.cancel()
            try:
                await self._wal_archive_monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("PITR monitoring stopped")
    
    async def _monitor_wal_archive_lag(self, db: AsyncSession) -> None:
        """Monitor WAL archive lag continuously."""
        while True:
            try:
                await asyncio.sleep(self.config.wal_archive_interval_seconds)
                await self.check_wal_archive_lag(db)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WAL archive monitoring error: {e}")
    
    async def check_wal_archive_lag(self, db: AsyncSession) -> PITRWindowStatus:
        """Check WAL archive lag and PITR window availability."""
        self.db = db
        self.detector.db = db
        
        # Check PITR capability
        pitr_available = await self.detector.detect(EnvironmentCapability.POSTGRESQL_PITR)
        if not pitr_available:
            return PITRWindowStatus(
                available=False,
                reason="PostgreSQL PITR capability not available",
                max_lag_minutes=self.config.max_lag_minutes,
            )
        
        try:
            # Check archive_mode
            archive_mode_result = await self.db.execute(text("SHOW archive_mode"))
            archive_mode = archive_mode_result.scalar()
            
            if archive_mode != "on":
                return PITRWindowStatus(
                    available=False,
                    reason=f"archive_mode is {archive_mode}, expected 'on'",
                    max_lag_minutes=self.config.max_lag_minutes,
                )
            
            # Check WAL archive status
            archive_status = await self.db.execute(text("""
                SELECT 
                    pg_walfile_name(pg_current_wal_lsn()) as current_wal,
                    pg_walfile_name(pg_current_wal_lsn()) as last_archived
            """))
            
            # Check pg_stat_archiver for lag
            archiver_stats = await self.db.execute(text("""
                SELECT 
                    archived_count,
                    last_archived_wal,
                    last_archived_time,
                    failed_count,
                    last_failed_time,
                    last_failed_wal
                FROM pg_stat_archiver
            """))
            
            archiver = archiver_stats.fetchone()
            
            if archiver and archiver.last_archived_time:
                last_archived = archiver.last_archived_time
                if last_archived.tzinfo is None:
                    last_archived = last_archived.replace(tzinfo=timezone.utc)
                
                lag_minutes = (utcnow() - last_archived).total_seconds() / 60
                
                window_end = utcnow()
                window_start = utcnow() - timedelta(hours=self.config.window_hours)
                
                available = lag_minutes <= self.config.max_lag_minutes
                
                return PITRWindowStatus(
                    available=available,
                    window_start=window_start,
                    window_end=window_end,
                    latest_wal_archive=last_archived,
                    lag_minutes=lag_minutes,
                    max_lag_minutes=self.config.max_lag_minutes,
                    reason="within PITR window" if available else f"WAL archive lag {lag_minutes:.1f} min > {self.config.max_lag_minutes} min",
                )
            else:
                return PITRWindowStatus(
                    available=False,
                    reason="No WAL archive activity recorded",
                    max_lag_minutes=self.config.max_lag_minutes,
                )
                
        except Exception as e:
            logger.error(f"WAL archive lag check failed: {e}")
            return PITRWindowStatus(
                available=False,
                reason=f"WAL archive check failed: {str(e)}",
                max_lag_minutes=self.config.max_lag_minutes,
            )
    
    async def create_continuous_backup(
        self,
        db: AsyncSession,
        organization_id: str,
        retention_hours: int = 336,
    ) -> Dict[str, Any]:
        """Create a continuous backup for PITR window."""
        self.db = db
        
        # Create a base backup for PITR
        backup_metadata = await backup_service.create_full_backup(
            db=db,
            kind=BackupKind.FULL,
            retention_days=self.config.window_hours // 24,
            organization_id=organization_id,
        )
        
        # Also create a PITR-specific backup record
        pitr_backup_id = f"pitr-{uuid.uuid4().hex[:12]}"
        
        return {
            "success": True,
            "backup_id": backup_metadata.backup_id,
            "pitr_backup_id": pitr_backup_id,
            "window_hours": self.config.window_hours,
            "retention_hours": retention_hours,
        }
    
    async def recover_to_point_in_time(
        self,
        db: AsyncSession,
        organization_id: str,
        target_time: datetime,
        initiated_by: str,
    ) -> PITRRecoveryResult:
        """
        Recover to a specific point in time using PITR.
        
        This is the main PITR recovery entry point.
        """
        self.db = db
        self.detector.db = db
        
        operation_id = f"pitr-{uuid.uuid4().hex[:12]}"
        started_at = utcnow()
        
        # Verify target time is within PITR window
        window_status = await self.check_wal_archive_lag(db)
        if not window_status.available:
            return PITRRecoveryResult(
                success=False,
                operation_id=f"pitr-{uuid.uuid4().hex[:12]}",
                target_time=target_time,
                error=f"Target time outside PITR window: {window_status.reason}",
            )
        
        if target_time < window_status.window_start or target_time > window_status.window_end:
            return PITRRecoveryResult(
                success=False,
                operation_id=f"pitr-{uuid.uuid4().hex[:12]}",
                target_time=target_time,
                error=f"Target time {target_time} outside PITR window ({window_status.window_start} to {window_status.window_end})",
            )
        
        # Create PITR operation record
        operation = PITROperation(
            operation_id=f"pitr-{uuid.uuid4().hex[:12]}",
            operation_type=PITROperationType.TARGET_TIME_RECOVERY,
            status=PITRStatus.IN_PROGRESS,
            organization_id=organization_id,
            target_time=target_time,
            started_at=utcnow(),
        )
        
        # Find the most recent base backup before target time
        backup = await self._find_base_backup_for_pitr(db, target_time)
        if not backup:
            return PITRRecoveryResult(
                success=False,
                operation_id=operation.operation_id,
                target_time=target_time,
                error="No suitable base backup found for PITR",
            )
        
        operation.backup_id = backup.id
        
        try:
            # Execute PITR restore using restore service
            restore_result = await restore_service.restore_to_point_in_time(
                db=db,
                backup_id=backup.id,
                organization_id=organization_id,
                target_time=target_time,
                initiated_by="pitr_service",
            )
            
            if not restore_result.get("success", False):
                return PITRRecoveryResult(
                    success=False,
                    operation_id=operation.operation_id,
                    target_time=target_time,
                    backup_used=backup.id,
                    error=restore_result.get("error", "Restore failed"),
                )
            
            # Run post-restore validation
            validation = await self._validate_pitr_recovery(db, target_time)
            
            # Measure RPO/RTO
            rpo_rto = await rpo_rto_measurement_service.measure_recovery(
                db=db,
                organization_id=organization_id,
                disaster_type="pitr_recovery",
                target_time=target_time,
                actual_recovery_time=utcnow(),
                backup_used=backup.id,
            )
            
            completed_at = utcnow()
            actual_recovery_time = completed_at
            
            return PITRRecoveryResult(
                success=True,
                operation_id=operation.operation_id,
                target_time=target_time,
                actual_recovery_time=actual_recovery_time,
                backup_used=backup.id,
                wal_files_applied=0,  # Would need pgbackrest output parsing
                validation=validation,
            )
            
        except Exception as e:
            logger.error(f"PITR recovery failed: {e}")
            return PITRRecoveryResult(
                success=False,
                operation_id=operation.operation_id,
                target_time=target_time,
                error=str(e),
            )
    
    async def _find_base_backup_for_pitr(
        self,
        db: AsyncSession,
        target_time: datetime,
    ) -> Optional[BackupManifest]:
        """Find the most recent verified full backup before target time."""
        from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
        
        result = await db.execute(
            select(BackupManifest)
            .where(
                BackupManifest.status == BackupStatus.VERIFIED,
                BackupManifest.backup_kind == BackupKind.FULL,
                BackupManifest.completed_at <= target_time,
            )
            .order_by(BackupManifest.completed_at.desc())
            .limit(1)
        )
        
        return result.scalars().first()
    
    async def _validate_pitr_recovery(
        self,
        db: AsyncSession,
        target_time: datetime,
    ) -> Dict[str, Any]:
        """Validate PITR recovery integrity."""
        validation_results = {}
        
        # Run canonical integrity checks
        integrity_result = await canonical_reality_integrity_service.run_integrity_scan(
            db=db,
            organization_id="pitr_recovery",
            checks=["structural", "tenant", "temporal", "provenance", "epistemic"],
            limit=10,
        )
        
        critical_findings = [f for f in integrity_result if severity_matches(f, "CRITICAL")]
        high_findings = [f for f in integrity_result if severity_matches(f, "HIGH")]
        
        validation_results = {
            "canonical_integrity": {
                "passed": len(critical_findings) == 0,
                "critical_findings": len(critical_findings),
                "high_findings": len(high_findings),
            },
            "temporal_target": target_time.isoformat(),
            "recovery_timestamp": utcnow().isoformat(),
        }
        
        return validation_results
    
    async def get_pitr_status(self, db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive PITR status."""
        self.db = db
        self.detector.db = db
        
        window_status = await self.check_wal_archive_lag(db)
        
        # Get backup coverage
        from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
        
        recent_backups = await db.execute(
            select(BackupManifest)
            .where(
                BackupManifest.status == BackupStatus.VERIFIED,
                BackupManifest.backup_kind.in_([BackupKind.FULL, BackupKind.DAILY]),
            )
            .order_by(BackupManifest.completed_at.desc())
            .limit(10)
        )
        backups = recent_backups.scalars().all()
        
        # Check WAL archive status
        wal_status = await self._get_wal_archive_status(db)
        
        return {
            "pitr_enabled": self.config.enabled,
            "window_hours": self.config.window_hours,
            "window_status": {
                "available": window_status.available,
                "window_start": window_status.window_start.isoformat() if window_status.window_start else None,
                "window_end": window_status.window_end.isoformat() if window_status.window_end else None,
                "lag_minutes": window_status.lag_minutes,
                "max_lag_minutes": window_status.max_lag_minutes,
                "reason": window_status.reason,
            },
            "wal_archive": wal_status,
            "backup_coverage": {
                "recent_verified_backups": len(backups),
                "latest_backup": backups[0].completed_at.isoformat() if backups else None,
                "oldest_backup": backups[-1].completed_at.isoformat() if backups else None,
            },
            "configuration": {
                "window_hours": self.config.window_hours,
                "max_lag_minutes": self.config.max_lag_minutes,
                "retention_hours": self.config.retention_hours,
            },
        }
    
    async def _get_wal_archive_status(self, db: AsyncSession) -> Dict[str, Any]:
        """Get WAL archive status from pg_stat_archiver."""
        try:
            result = await db.execute(text("""
                SELECT 
                    archived_count,
                    last_archived_wal,
                    last_archived_time,
                    failed_count,
                    last_failed_time,
                    last_failed_wal
                FROM pg_stat_archiver
            """))
            archiver = result.fetchone()
            
            if archiver:
                return {
                    "archived_count": archiver.archived_count,
                    "last_archived_wal": archiver.last_archived_wal,
                    "last_archived_time": archiver.last_archived_time.isoformat() if archiver.last_archived_time else None,
                    "failed_count": archiver.failed_count,
                    "last_failed_time": archiver.last_failed_time.isoformat() if archiver.last_failed_time else None,
                    "last_failed_wal": archiver.last_failed_wal,
                }
        except Exception as e:
            logger.warning(f"Could not get WAL archive status: {e}")
        
        return {"status": "unavailable", "error": "Could not query pg_stat_archiver"}


# Global instance
pitr_service = PITRService()