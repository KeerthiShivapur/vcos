"""WAL Archive Monitoring Service — production-grade WAL archive health monitoring.

Implements capability-aware monitoring of PostgreSQL WAL archiving:
- archive_mode, archive_command
- pg_stat_archiver metrics
- pg_wal/archive_status (.ready/.done files)
- WAL archive file sizes and hash consistency
- Continuity from declared recovery baseline
- Automated alerts for anomalies
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.validation.capability_contract import (
    ValidationStatus,
    EnvironmentCapability,
    ValidationCheck,
    ValidationResult,
    CapabilityDetector,
    CapabilityAwareValidator,
)

logger = logging.getLogger("vcos.wal_monitor")


class WALArchiveHealthState(str, Enum):
    """Overall WAL archive health state."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class WALSegmentState(str, Enum):
    """WAL segment archive state."""
    ARCHIVED = "archived"
    PENDING = "pending"
    FAILED = "failed"
    MISSING = "missing"
    CORRUPT = "corrupt"
    UNKNOWN = "unknown"


@dataclass
class WALSegmentInfo:
    """Information about a single WAL segment."""
    segment_name: str
    state: WALSegmentState
    size_bytes: int = 0
    expected_size_bytes: int = 16777216  # 16MB
    hash_sha256: Optional[str] = None
    archive_time: Optional[datetime] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    location: str = ""  # "pg_wal" or "archive"


@dataclass
class WALArchiveHealthReport:
    """Comprehensive WAL archive health report."""
    report_id: str
    generated_at: datetime
    
    # Overall health
    overall_state: WALArchiveHealthState
    
    # Archiving process
    archive_mode: str = ""
    archive_command: str = ""
    archiving_process_state: str = ""  # "HEALTHY", "DEGRADED", "FAILED"
    
    # Latest archived segment
    latest_archived_segment: Optional[str] = None
    latest_segment_hash: Optional[str] = None
    latest_segment_hash_verified: bool = False
    
    # Failure tracking
    new_archive_failures: int = 0
    historical_failures_present: bool = False
    total_failed_count: int = 0
    last_failed_wal: Optional[str] = None
    last_failed_time: Optional[datetime] = None
    
    # Continuity
    continuous_chain_from_baseline: bool = False
    baseline_segment: Optional[str] = None
    verified_wal_range_start: Optional[str] = None
    verified_wal_range_end: Optional[str] = None
    missing_historical_segments: List[str] = field(default_factory=list)
    
    # Archive status directory
    ready_files_count: int = 0
    done_files_count: int = 0
    accumulating_ready_files: bool = False
    
    # File validation
    invalid_file_sizes: List[str] = field(default_factory=list)
    hash_mismatches: List[str] = field(default_factory=list)
    
    # Activity
    stale_archiving_activity: bool = False
    last_archive_time: Optional[datetime] = None
    archive_lag_minutes: Optional[float] = None
    max_allowed_lag_minutes: int = 5
    
    # Recovery readiness
    physical_backup_verified: bool = False
    restore_test_verified: bool = False
    pitr_test_verified: bool = False
    overall_recovery_readiness: str = "NOT_READY"
    
    # Alerts
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "overall_state": self.overall_state.value,
            "archive_mode": self.archive_mode,
            "archive_command": self.archive_command,
            "archiving_process_state": self.archiving_process_state,
            "latest_archived_segment": self.latest_archived_segment,
            "latest_segment_hash": self.latest_segment_hash,
            "latest_segment_hash_verified": self.latest_segment_hash_verified,
            "new_archive_failures": self.new_archive_failures,
            "historical_failures_present": self.historical_failures_present,
            "total_failed_count": self.total_failed_count,
            "last_failed_wal": self.last_failed_wal,
            "last_failed_time": self.last_failed_time.isoformat() if self.last_failed_time else None,
            "continuous_chain_from_baseline": self.continuous_chain_from_baseline,
            "baseline_segment": self.baseline_segment,
            "verified_wal_range_start": self.verified_wal_range_start,
            "verified_wal_range_end": self.verified_wal_range_end,
            "missing_historical_segments": self.missing_historical_segments,
            "ready_files_count": self.ready_files_count,
            "done_files_count": self.done_files_count,
            "accumulating_ready_files": self.accumulating_ready_files,
            "invalid_file_sizes": self.invalid_file_sizes,
            "hash_mismatches": self.hash_mismatches,
            "stale_archiving_activity": self.stale_archiving_activity,
            "last_archive_time": self.last_archive_time.isoformat() if self.last_archive_time else None,
            "archive_lag_minutes": self.archive_lag_minutes,
            "max_allowed_lag_minutes": self.max_allowed_lag_minutes,
            "physical_backup_verified": self.physical_backup_verified,
            "restore_test_verified": self.restore_test_verified,
            "pitr_test_verified": self.pitr_test_verified,
            "overall_recovery_readiness": self.overall_recovery_readiness,
            "alerts": self.alerts,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)


class WALArchiveMonitor(CapabilityAwareValidator):
    """Production WAL archive monitoring service."""
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_interval_seconds = 60
        self._baseline_segment: Optional[str] = None
        self._historical_failure_baseline: int = 0
        self._last_known_archived_count: int = 0
    
    # =====================================================================
    # Baseline + path resolution helpers
    # =====================================================================
    
    def _wal_archive_dir(self) -> str:
        """Resolve the WAL archive directory (env > settings > platform default)."""
        configured = os.environ.get("WAL_ARCHIVE_DIR") or getattr(
            self.settings, "WAL_ARCHIVE_DIR", None
        )
        if configured:
            return configured
        if os.name == "nt":
            return "C:\\VCOS-Backups\\wal_archive"
        return "/var/lib/vcos/wal_archive"
    
    def _baseline_file(self) -> str:
        """Path of the persisted recovery baseline record."""
        return os.path.join(os.path.dirname(self._wal_archive_dir()), "wal_baseline.json")
    
    def set_baseline_segment(self, segment_name: str) -> None:
        """Declare a new recovery baseline (called after a verified base backup)."""
        self._baseline_segment = segment_name
        try:
            with open(self._baseline_file(), "w") as f:
                json.dump(
                    {
                        "baseline_segment": segment_name,
                        "set_at": utcnow().isoformat(),
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.warning(f"Could not persist WAL baseline: {e}")
    
    def _load_baseline(self) -> Optional[str]:
        """Load the persisted recovery baseline, if any."""
        try:
            path = self._baseline_file()
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                segment = data.get("baseline_segment")
                if segment:
                    return str(segment)
        except Exception as e:
            logger.warning(f"Could not load WAL baseline: {e}")
        return None
    
    def _verification_file(self) -> str:
        """Path of the persisted recovery verification record."""
        return os.path.join(os.path.dirname(self._wal_archive_dir()), "wal_recovery_verification.json")
    
    def _load_verification_state(self) -> Dict[str, Any]:
        """Load persisted recovery verification facts (they are never inferred)."""
        try:
            path = self._verification_file()
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Could not load recovery verification record: {e}")
        return {}
    
    def _save_verification_state(self, state: Dict[str, Any]) -> None:
        """Persist recovery verification facts atomically."""
        try:
            path = self._verification_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp, path)
        except Exception as e:
            logger.warning(f"Could not persist recovery verification record: {e}")
    
    def record_physical_backup_verified(self, backup_id: str, checksum_sha256: str = "") -> None:
        """Record a real, verified physical backup as a readiness input."""
        state = self._load_verification_state()
        state["physical_backup_verified"] = True
        state["physical_backup"] = {
            "backup_id": backup_id,
            "checksum_sha256": checksum_sha256,
            "verified_at": utcnow().isoformat(),
        }
        self._save_verification_state(state)
    
    def record_restore_test_verified(self, restore_id: str, isolated_port: Optional[int] = None) -> None:
        """Record a real isolated restore test as a readiness input."""
        state = self._load_verification_state()
        state["restore_test_verified"] = True
        state["restore_test"] = {
            "restore_id": restore_id,
            "isolated_port": isolated_port,
            "verified_at": utcnow().isoformat(),
        }
        self._save_verification_state(state)
    
    def record_pitr_test_verified(self, target_time: str = "", marker1: str = "", marker2: str = "") -> None:
        """Record a real PITR test as a readiness input."""
        state = self._load_verification_state()
        state["pitr_test_verified"] = True
        state["pitr_test"] = {
            "target_time": target_time,
            "marker1": marker1,
            "marker2": marker2,
            "verified_at": utcnow().isoformat(),
        }
        self._save_verification_state(state)
    
    async def _pgdata_dir(self, db: AsyncSession) -> str:
        """Resolve the PostgreSQL data directory (from the server, then env)."""
        try:
            result = await db.execute(text("SHOW data_directory"))
            value = result.scalar()
            if value:
                return str(value)
        except Exception:
            pass
        configured = os.environ.get("PGDATA")
        if configured:
            return configured
        if os.name == "nt":
            return "C:\\Program Files\\PostgreSQL\\18\\data"
        return "/var/lib/postgresql/data"
    
    def _list_archived_segments(self) -> List[str]:
        """List WAL segment file names present in the archive directory."""
        archive_dir = self._wal_archive_dir()
        if not os.path.isdir(archive_dir):
            return []
        segments = []
        for name in os.listdir(archive_dir):
            if len(name) == 24 and all(c in "0123456789ABCDEF" for c in name):
                segments.append(name)
        return sorted(segments)
    
    @staticmethod
    def _segment_seq(segment_name: str) -> tuple:
        """Parse a WAL segment name into (timeline, log, seg) integers."""
        return (
            int(segment_name[0:8], 16),
            int(segment_name[8:16], 16),
            int(segment_name[16:24], 16),
        )
    
    @staticmethod
    def _next_segment_name(segment_name: str) -> str:
        """Return the next WAL segment name (handles seg/log rollover)."""
        timeline, log, seg = WALArchiveMonitor._segment_seq(segment_name)
        seg += 1
        if seg > 0xFF:
            seg = 0
            log += 1
            if log > 0xFF:
                log = 0
                timeline += 1
        return f"{timeline:08X}{log:08X}{seg:08X}"
    
    async def _wal_segment_size(self, db: AsyncSession) -> Optional[int]:
        """Resolve the configured WAL segment size in bytes."""
        try:
            result = await db.execute(text("SHOW wal_segment_size"))
            value = str(result.scalar() or "")
            value = value.strip().upper()
            if value.endswith("MB"):
                return int(float(value[:-2]) * 1024 * 1024)
            if value.endswith("GB"):
                return int(float(value[:-2]) * 1024 * 1024 * 1024)
            if value.isdigit():
                return int(value)
        except Exception:
            pass
        return None
        
    async def initialize(self, db: AsyncSession) -> None:
        """Initialize the monitor and capture baseline state."""
        self.db = db
        self.detector.db = db
        
        # Load a persisted recovery baseline (if one was declared by a backup run)
        if not self._baseline_segment:
            self._baseline_segment = self._load_baseline()
        
        # Capture baseline for distinguishing historical vs new failures
        await self._capture_baseline(db)
        
        # Verify PITR capability
        pitr_available = await self.detector.detect(EnvironmentCapability.POSTGRESQL_PITR)
        if not pitr_available:
            logger.warning("PostgreSQL PITR capability not available in this environment")
    
    async def _capture_baseline(self, db: AsyncSession) -> None:
        """Capture baseline archiver state for delta detection."""
        try:
            result = await db.execute(text("""
                SELECT 
                    archived_count,
                    failed_count,
                    last_failed_wal,
                    last_failed_time
                FROM pg_stat_archiver
            """))
            archiver = result.fetchone()
            
            if archiver:
                self._last_known_archived_count = archiver.archived_count
                self._historical_failure_baseline = archiver.failed_count
                if archiver.last_failed_wal:
                    logger.info(f"Baseline captured: archived={archiver.archived_count}, failed={archiver.failed_count}, last_failed={archiver.last_failed_wal}")
        except Exception as e:
            logger.warning(f"Could not capture baseline: {e}")
    
    async def check_health(self, db: AsyncSession) -> WALArchiveHealthReport:
        """Perform comprehensive WAL archive health check."""
        self.db = db
        self.detector.db = db
        
        report = WALArchiveHealthReport(
            report_id=f"wal-health-{utcnow().strftime('%Y%m%d-%H%M%S')}",
            generated_at=utcnow(),
            overall_state=WALArchiveHealthState.UNKNOWN,
        )
        
        try:
            # Check PostgreSQL PITR capability
            pitr_available = await self.detector.detect(EnvironmentCapability.POSTGRESQL_PITR)
            if not pitr_available:
                report.overall_state = WALArchiveHealthState.UNKNOWN
                report.alerts.append({
                    "level": "WARNING",
                    "code": "PITR_UNAVAILABLE",
                    "message": "PostgreSQL PITR capability not available in this environment",
                })
                return report
            
            # Check archive_mode
            await self._check_archive_mode(db, report)
            
            # Check archive_command
            await self._check_archive_command(db, report)
            
            # Check archive_status directory
            await self._check_archive_status_directory(db, report)
            
            # Check pg_stat_archiver (uses ready-file count for stall detection)
            await self._check_pg_stat_archiver(db, report)
            
            # Check WAL archive files
            await self._check_wal_archive_files(db, report)
            
            # Check continuity from baseline
            await self._check_continuity_from_baseline(db, report)
            
            # Apply persisted recovery verification facts (real events only)
            verification_state = self._load_verification_state()
            report.physical_backup_verified = bool(
                verification_state.get("physical_backup_verified", False)
            )
            report.restore_test_verified = bool(
                verification_state.get("restore_test_verified", False)
            )
            report.pitr_test_verified = bool(
                verification_state.get("pitr_test_verified", False)
            )
            
            # Determine overall state
            self._determine_overall_state(report)
            
            # Generate alerts
            self._generate_alerts(report)
            
        except Exception as e:
            logger.error(f"WAL health check failed: {e}")
            report.overall_state = WALArchiveHealthState.UNHEALTHY
            report.alerts.append({
                "level": "CRITICAL",
                "code": "HEALTH_CHECK_FAILED",
                "message": f"WAL health check failed: {str(e)}",
            })
        
        return report
    
    async def _check_archive_mode(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check archive_mode setting."""
        try:
            result = await db.execute(text("SHOW archive_mode"))
            report.archive_mode = result.scalar() or "unknown"
            
            if report.archive_mode != "on":
                report.archiving_process_state = "FAILED"
                report.alerts.append({
                    "level": "CRITICAL",
                    "code": "ARCHIVE_MODE_OFF",
                    "message": f"archive_mode is '{report.archive_mode}', expected 'on'",
                })
            else:
                report.archiving_process_state = "HEALTHY"
        except Exception as e:
            report.alerts.append({
                "level": "CRITICAL",
                "code": "ARCHIVE_MODE_CHECK_FAILED",
                "message": f"Could not check archive_mode: {str(e)}",
            })
    
    async def _check_archive_command(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check archive_command setting."""
        try:
            result = await db.execute(text("SHOW archive_command"))
            report.archive_command = result.scalar() or "unknown"
        except Exception as e:
            report.alerts.append({
                "level": "WARNING",
                "code": "ARCHIVE_COMMAND_CHECK_FAILED",
                "message": f"Could not check archive_command: {str(e)}",
            })
    
    async def _check_pg_stat_archiver(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check pg_stat_archiver metrics."""
        try:
            result = await db.execute(text("""
                SELECT 
                    archived_count,
                    last_archived_wal,
                    last_archived_time,
                    failed_count,
                    last_failed_wal,
                    last_failed_time,
                    stats_reset
                FROM pg_stat_archiver
            """))
            archiver = result.fetchone()
            
            if not archiver:
                report.alerts.append({
                    "level": "WARNING",
                    "code": "NO_ARCHIVER_STATS",
                    "message": "pg_stat_archiver returned no rows",
                })
                return
            
            report.total_failed_count = archiver.failed_count
            report.last_failed_wal = archiver.last_failed_wal
            report.last_failed_time = archiver.last_failed_time
            
            if archiver.last_archived_wal:
                report.latest_archived_segment = archiver.last_archived_wal
            
            if archiver.last_archived_time:
                report.last_archive_time = archiver.last_archived_time
                if report.last_archive_time.tzinfo is None:
                    report.last_archive_time = report.last_archive_time.replace(tzinfo=timezone.utc)
                
                report.archive_lag_minutes = (utcnow() - report.last_archive_time).total_seconds() / 60
                
                # A large lag is only a stall if WAL is actually pending.
                # On idle databases (archive_timeout=0) no WAL is generated and the
                # timestamp grows without any archive failure.
                if report.ready_files_count > 0 and report.archive_lag_minutes > report.max_allowed_lag_minutes:
                    report.stale_archiving_activity = True
                    report.alerts.append({
                        "level": "WARNING",
                        "code": "ARCHIVE_LAG_HIGH",
                        "message": f"WAL archive lag {report.archive_lag_minutes:.1f} min > {report.max_allowed_lag_minutes} min with {report.ready_files_count} pending .ready files",
                        "lag_minutes": report.archive_lag_minutes,
                    })
            
            # Calculate new failures since baseline
            new_failures = archiver.failed_count - self._historical_failure_baseline
            report.new_archive_failures = max(0, new_failures)
            report.historical_failures_present = self._historical_failure_baseline > 0
            
            if report.new_archive_failures > 0:
                report.alerts.append({
                    "level": "CRITICAL",
                    "code": "NEW_ARCHIVE_FAILURES",
                    "message": f"{report.new_archive_failures} new archive failures since baseline",
                    "new_failures": report.new_archive_failures,
                    "total_failures": archiver.failed_count,
                })
            
            # Update last known archived count
            self._last_known_archived_count = archiver.archived_count
            
        except Exception as e:
            report.alerts.append({
                "level": "CRITICAL",
                "code": "PG_STAT_ARCHIVER_CHECK_FAILED",
                "message": f"Could not check pg_stat_archiver: {str(e)}",
            })
    
    async def _check_archive_status_directory(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check pg_wal/archive_status for .ready and .done files."""
        try:
            # Query pg_wal/archive_status using pg_ls_dir (PostgreSQL 15+)
            # For older versions, this may fail
            try:
                result = await db.execute(text("""
                    SELECT pg_ls_dir('pg_wal/archive_status') as files
                """))
                files = [row[0] for row in result.fetchall()]
            except Exception:
                # Fallback: try to count using system catalog
                # This is a best-effort check
                report.ready_files_count = 0
                report.done_files_count = 0
                return
            
            ready_files = [f for f in files if f.endswith('.ready')]
            done_files = [f for f in files if f.endswith('.done')]
            
            report.ready_files_count = len(ready_files)
            report.done_files_count = len(done_files)
            
            # Check for accumulating .ready files
            if len(ready_files) > 10:
                report.accumulating_ready_files = True
                report.alerts.append({
                    "level": "WARNING",
                    "code": "ACCUMULATING_READY_FILES",
                    "message": f"{len(ready_files)} .ready files accumulating in pg_wal/archive_status",
                    "ready_count": len(ready_files),
                })
            
        except Exception as e:
            logger.warning(f"Could not check archive_status directory: {e}")
    
    async def _check_wal_archive_files(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check WAL archive files for size and hash consistency."""
        archive_dir = self._wal_archive_dir()
        if not os.path.isdir(archive_dir):
            report.alerts.append({
                "level": "WARNING",
                "code": "WAL_ARCHIVE_DIR_MISSING",
                "message": f"WAL archive directory not found: {archive_dir}",
            })
            return
        
        expected_size = await self._wal_segment_size(db)
        segments = self._list_archived_segments()
        
        # Validate sizes of the most recent archived segments
        for name in segments[-3:]:
            path = os.path.join(archive_dir, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                report.invalid_file_sizes.append(f"{name} (unreadable)")
                continue
            if expected_size and size != expected_size:
                report.invalid_file_sizes.append(f"{name} ({size} bytes != {expected_size})")
        
        # Hash-verify the latest archived segment against its live counterpart when
        # it is still present in pg_wal (segments get recycled quickly, so absence
        # of the source copy is not by itself a failure).
        latest = report.latest_archived_segment
        if latest and latest in segments:
            archive_path = os.path.join(archive_dir, latest)
            try:
                report.latest_segment_hash = self._compute_sha256(archive_path)
            except OSError:
                report.latest_segment_hash = None
            
            try:
                pgdata = await self._pgdata_dir(db)
                source_path = os.path.join(pgdata, "pg_wal", latest)
                if os.path.exists(source_path):
                    source_hash = self._compute_sha256(source_path)
                    report.latest_segment_hash_verified = source_hash == report.latest_segment_hash
                    if not report.latest_segment_hash_verified:
                        report.hash_mismatches.append(latest)
            except Exception as e:
                logger.warning(f"Could not hash-verify latest segment: {e}")
    
    async def _check_continuity_from_baseline(self, db: AsyncSession, report: WALArchiveHealthReport) -> None:
        """Check WAL continuity from declared recovery baseline."""
        baseline = self._baseline_segment or self._load_baseline()
        if baseline:
            self._baseline_segment = baseline
        
        if not baseline:
            report.baseline_segment = None
            report.continuous_chain_from_baseline = False
            return
        
        report.baseline_segment = baseline
        latest = report.latest_archived_segment
        
        if not latest:
            report.continuous_chain_from_baseline = False
            return
        
        try:
            if self._segment_seq(latest) < self._segment_seq(baseline):
                # Latest archive is older than the baseline: nothing recorded yet
                # for the baseline window.
                report.continuous_chain_from_baseline = False
                return
        except (ValueError, IndexError):
            report.continuous_chain_from_baseline = False
            return
        
        archived = set(self._list_archived_segments())
        missing: List[str] = []
        segment = baseline
        guard = 0
        while True:
            if segment not in archived:
                missing.append(segment)
            if segment == latest:
                break
            segment = self._next_segment_name(segment)
            guard += 1
            if guard > 100000:
                missing.append("(chain walk aborted: >100000 segments)")
                break
        
        report.missing_historical_segments = missing
        report.verified_wal_range_start = baseline
        report.verified_wal_range_end = latest
        report.continuous_chain_from_baseline = len(missing) == 0
    
    def _determine_overall_state(self, report: WALArchiveHealthReport) -> None:
        """Determine overall WAL archive health state."""
        critical_alerts = [a for a in report.alerts if a.get("level") == "CRITICAL"]
        warning_alerts = [a for a in report.alerts if a.get("level") == "WARNING"]
        
        if critical_alerts:
            report.overall_state = WALArchiveHealthState.UNHEALTHY
        elif warning_alerts or report.stale_archiving_activity or report.accumulating_ready_files:
            report.overall_state = WALArchiveHealthState.DEGRADED
        elif report.archiving_process_state == "HEALTHY" and not report.stale_archiving_activity:
            report.overall_state = WALArchiveHealthState.HEALTHY
        else:
            report.overall_state = WALArchiveHealthState.UNKNOWN
        
        # Determine overall recovery readiness
        if (report.overall_state == WALArchiveHealthState.HEALTHY and
            report.physical_backup_verified and
            report.restore_test_verified and
            report.pitr_test_verified):
            report.overall_recovery_readiness = "READY"
        elif (report.overall_state == WALArchiveHealthState.HEALTHY and
              report.physical_backup_verified):
            report.overall_recovery_readiness = "BACKUP_VERIFIED_ONLY"
        else:
            report.overall_recovery_readiness = "NOT_READY"
    
    def _generate_alerts(self, report: WALArchiveHealthReport) -> None:
        """Generate additional alerts based on findings."""
        # Check for missing historical segments
        if report.missing_historical_segments:
            report.alerts.append({
                "level": "WARNING",
                "code": "MISSING_HISTORICAL_SEGMENTS",
                "message": f"Missing historical WAL segments: {report.missing_historical_segments}",
                "segments": report.missing_historical_segments,
            })
        
        # Check for invalid file sizes
        if report.invalid_file_sizes:
            report.alerts.append({
                "level": "CRITICAL",
                "code": "INVALID_WAL_FILE_SIZES",
                "message": f"WAL files with invalid sizes: {report.invalid_file_sizes}",
                "files": report.invalid_file_sizes,
            })
        
        # Check for hash mismatches
        if report.hash_mismatches:
            report.alerts.append({
                "level": "CRITICAL",
                "code": "WAL_HASH_MISMATCHES",
                "message": f"WAL hash mismatches detected: {report.hash_mismatches}",
                "files": report.hash_mismatches,
            })
    
    async def start_monitoring(self, db: AsyncSession) -> None:
        """Start continuous WAL archive monitoring."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop(db))
            logger.info("WAL archive monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("WAL archive monitoring stopped")
    
    async def _monitor_loop(self, db: AsyncSession) -> None:
        """Continuous monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self._monitor_interval_seconds)
                report = await self.check_health(db)
                
                # Log health state changes
                if report.overall_state != WALArchiveHealthState.HEALTHY:
                    logger.warning(f"WAL archive health: {report.overall_state.value}")
                    for alert in report.alerts:
                        logger.warning(f"  ALERT [{alert['level']}] {alert['code']}: {alert['message']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WAL monitoring error: {e}")
    
    async def get_segment_info(self, db: AsyncSession, segment_name: str) -> Optional[WALSegmentInfo]:
        """Get detailed information about a specific WAL segment."""
        self.db = db
        self.detector.db = db
        
        segment = WALSegmentInfo(
            segment_name=segment_name,
            state=WALSegmentState.UNKNOWN,
        )
        
        expected_size = await self._wal_segment_size(db) or segment.expected_size_bytes
        
        # Check in pg_wal
        pgdata = await self._pgdata_dir(db)
        pg_wal_path = os.path.join(pgdata, "pg_wal", segment_name)
        
        if os.path.exists(pg_wal_path):
            segment.location = "pg_wal"
            segment.size_bytes = os.path.getsize(pg_wal_path)
            if segment.size_bytes == expected_size:
                segment.state = WALSegmentState.ARCHIVED
            else:
                segment.state = WALSegmentState.CORRUPT
        
        # Check in archive directory
        archive_path = os.path.join(self._wal_archive_dir(), segment_name)
        
        if os.path.exists(archive_path):
            segment.location = "archive"
            segment.size_bytes = os.path.getsize(archive_path)
            if segment.size_bytes == expected_size:
                segment.state = WALSegmentState.ARCHIVED
            else:
                segment.state = WALSegmentState.CORRUPT
        
        return segment
    
    async def verify_segment_hash(
        self,
        db: AsyncSession,
        segment_name: str,
        expected_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """Verify SHA-256 hash of a WAL segment."""
        pgdata = await self._pgdata_dir(db)
        pg_wal_path = os.path.join(pgdata, "pg_wal", segment_name)
        
        archive_path = os.path.join(self._wal_archive_dir(), segment_name)
        
        result = {
            "segment": segment_name,
            "source_exists": os.path.exists(pg_wal_path),
            "archive_exists": os.path.exists(archive_path),
            "source_hash": None,
            "archive_hash": None,
            "hashes_match": False,
            "matches_expected": False,
        }
        
        if result["source_exists"]:
            result["source_hash"] = self._compute_sha256(pg_wal_path)
        
        if result["archive_exists"]:
            result["archive_hash"] = self._compute_sha256(archive_path)
        
        if result["source_hash"] and result["archive_hash"]:
            result["hashes_match"] = result["source_hash"] == result["archive_hash"]
        
        if expected_hash:
            if result["source_hash"]:
                result["matches_expected"] = result["source_hash"] == expected_hash
            elif result["archive_hash"]:
                result["matches_expected"] = result["archive_hash"] == expected_hash
        
        return result
    
    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


# Global instance
wal_archive_monitor = WALArchiveMonitor()