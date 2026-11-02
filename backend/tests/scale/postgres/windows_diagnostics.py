"""Windows PostgreSQL Failure Classification and Diagnostics.

Provides proper Windows-specific failure classification and evidence collection
for PostgreSQL scale testing on Windows.

Critical: 0xC0000142 is STATUS_DLL_INIT_FAILED, NOT STATUS_DLL_NOT_FOUND.
"""

import asyncio
import os
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class WindowsFailureClassification(Enum):
    """Windows PostgreSQL failure classifications."""
    
    STARTUP_FAILURE = "STARTUP_FAILURE"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    BACKEND_CRASH = "BACKEND_CRASH"
    SERVER_CRASH = "SERVER_CRASH"
    DLL_INITIALIZATION_FAILURE = "DLL_INITIALIZATION_FAILURE"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    DISK_EXHAUSTION = "DISK_EXHAUSTION"
    WAL_PRESSURE = "WAL_PRESSURE"
    CHECKPOINT_PRESSURE = "CHECKPOINT_PRESSURE"
    LOCK_CONTENTION = "LOCK_CONTENTION"
    EXTENSION_FAILURE = "EXTENSION_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    ENVIRONMENT_INCOMPATIBILITY = "ENVIRONMENT_INCOMPATIBILITY"
    UNKNOWN = "UNKNOWN"


# Windows NT Status Codes
NT_STATUS_CODES = {
    0xC0000142: "STATUS_DLL_INIT_FAILED",
    0xC0000135: "STATUS_DLL_NOT_FOUND",
    0xC0000005: "STATUS_ACCESS_VIOLATION",
    0xC0000006: "STATUS_IN_PAGE_ERROR",
    0xC0000017: "STATUS_NO_MEMORY",
    0xC0000022: "STATUS_FILE_NOT_FOUND",
    0xC0000034: "STATUS_OBJECT_NAME_NOT_FOUND",
    0xC0000023: "STATUS_DISK_FULL",
    0xC000007B: "STATUS_INVALID_NAME",
    0xC00000FD: "STATUS_STACK_OVERFLOW",
    0x80000003: "STATUS_BREAKPOINT",
    0xC0000021: "STATUS_DATA_ERROR",
    0xC000013A: "STATUS_CTL_FILE_NOT_FOUND",
}


def classify_windows_nt_status(status_code: int) -> WindowsFailureClassification:
    """Classify Windows NT status code to failure classification.
    
    Critical: 0xC0000142 is STATUS_DLL_INIT_FAILED, NOT STATUS_DLL_NOT_FOUND.
    Microsoft explicitly distinguishes these two codes.
    """
    status_name = NT_STATUS_CODES.get(status_code, f"UNKNOWN_0x{status_code:08X}")
    
    if status_code == 0xC0000142:
        return WindowsFailureClassification.DLL_INITIALIZATION_FAILURE
    elif status_code == 0xC0000135:
        return WindowsFailureClassification.DLL_INITIALIZATION_FAILURE  # DLL not found is also init failure
    elif status_code == 0xC0000017:
        return WindowsFailureClassification.OUT_OF_MEMORY
    elif status_code == 0xC0000023:
        return WindowsFailureClassification.DISK_EXHAUSTION
    elif status_code == 0xC0000005:
        return WindowsFailureClassification.BACKEND_CRASH
    elif status_code == 0xC00000FD:
        return WindowsFailureClassification.BACKEND_CRASH  # Stack overflow
    else:
        return WindowsFailureClassification.UNKNOWN


@dataclass
class WindowsFailureEvidence:
    """Evidence collected for a Windows PostgreSQL failure."""
    
    timestamp: str
    failure_code: int
    failure_name: str
    failure_classification: WindowsFailureClassification
    postgresql_log_tail: str
    windows_event_log: List[str]
    process_exit_code: Optional[int]
    backend_pid: Optional[int]
    server_uptime_seconds: Optional[float]
    connection_count: int
    active_backend_count: int
    database_size_mb: float
    wal_size_mb: float
    temp_files_mb: float
    checkpoint_stats: Dict[str, Any]
    locks: List[Dict[str, Any]]
    server_version: str
    architecture: str
    os_version: str
    cpu_count: int
    total_physical_memory_mb: int
    available_memory_mb: int
    committed_memory_mb: int
    commit_limit_mb: int
    pagefile_size_mb: int
    free_disk_gb: float
    additional_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['failure_classification'] = self.failure_classification.value
        return d


@dataclass
class ScaleEnvironmentIncident:
    """A scale execution incident with full evidence."""
    
    environment: str
    platform: str
    database: str
    postgres_version: str
    scale_profile: str
    failure_classification: WindowsFailureClassification
    failure_code: int
    evidence: WindowsFailureEvidence
    timestamp: str
    stage: str  # "generation", "validation", "cleanup", "preflight"
    recoverability: str  # "retryable", "non_retryable", "unknown"
    validation_status: str  # "BLOCKED", "FAIL", "PASS", "INCONCLUSIVE"
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['failure_classification'] = self.failure_classification.value
        d['evidence'] = self.evidence.to_dict()
        return d


class WindowsCrashDiagnostics:
    """Collects diagnostic evidence for Windows PostgreSQL failures."""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = None
        self.session_factory = None
        
    async def initialize(self):
        """Initialize the diagnostics engine."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        
        self.engine = create_async_engine(
            self.db_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            echo=False,
        )
        self.session_factory = async_sessionmaker(
            create_async_engine(self.db_url, pool_size=1, max_overflow=0, pool_pre_ping=True, echo=False),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async def close(self):
        if self.engine:
            await self.engine.dispose()
    
    async def collect_failure_evidence(self, failure_code: int = 0xC0000142) -> WindowsFailureEvidence:
        """Collect comprehensive failure evidence for a Windows PostgreSQL crash."""
        
        timestamp = datetime.utcnow().isoformat()
        failure_name = NT_STATUS_CODES.get(failure_code, f"UNKNOWN_0x{failure_code:08X}")
        classification = classify_windows_nt_status(failure_code)
        
        # Collect PostgreSQL evidence
        postgresql_log_tail = await self._get_postgresql_log_tail()
        windows_events = await self._get_windows_events()
        pg_log_tail = await self._get_postgresql_log_tail_raw()
        
        # Collect system info
        os_version = platform.platform()
        cpu_count = os.cpu_count() or 0
        
        # Memory info
        total_memory_mb = 0
        available_memory_mb = 0
        committed_memory_mb = 0
        commit_limit_mb = 0
        pagefile_size_mb = 0
        free_disk_gb = 0.0
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_memory_mb = mem.total // (1024 * 1024)
            available_memory_mb = mem.available // (1024 * 1024)
            
            swap = psutil.swap_memory()
            pagefile_size_mb = swap.total // (1024 * 1024)
            
            disk = psutil.disk_usage('C:\\')
            free_disk_gb = disk.free / (1024**3)
        except Exception:
            pass
        
        # Collect PostgreSQL metrics if possible
        pg_metrics = {}
        server_version = "unknown"
        architecture = platform.machine()
        os_version = platform.platform()
        cpu_count = os.cpu_count() or 0
        
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
            from sqlalchemy.pool import NullPool
            
            engine = create_async_engine(
                self.db_url.replace("asyncpg", "asyncpg") if "asyncpg" not in self.db_url else self.db_url,
                pool_size=1, max_overflow=0, pool_pre_ping=True, poolclass=NullPool, echo=False
            )
            session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with session_factory() as session:
                result = await session.execute(text("SELECT version()"))
                server_version = result.scalar() or "unknown"
                
                result = await session.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))
                connection_count = result.scalar() or 0
                
                result = await session.execute(text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND datname = current_database()"))
                active_backend_count = result.scalar() or 0
                
                result = await session.execute(text("SELECT pg_database_size(current_database()) / 1024.0 / 1024.0 as size_mb"))
                database_size_mb = float(result.scalar() or 0)
                
                result = await session.execute(text("SELECT sum(pg_relation_size(indexrelid)) / 1024.0 / 1024.0 as size_mb FROM pg_stat_user_indexes WHERE schemaname = 'public'"))
                wal_size_mb = float(result.scalar() or 0)
                
                # WAL stats
                try:
                    result = await session.execute(text("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') / 1024.0 / 1024.0 as wal_mb"))
                    wal_size_mb = float(result.scalar() or 0)
                except Exception:
                    pass
                
                result = await session.execute(text("""
                    SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time,
                           buffers_checkpoint, buffers_clean, maxwritten_clean, buffers_backend, buffers_backend_fsync
                    FROM pg_stat_bgwriter
                """))
                row = result.first()
                if row:
                    checkpoint_stats = {
                        "checkpoints_timed": row.checkpoints_timed,
                        "checkpoints_req": row.checkpoints_req,
                        "checkpoint_write_time_ms": row.checkpoint_write_time,
                        "checkpoint_sync_time_ms": row.checkpoint_sync_time,
                        "buffers_checkpoint": row.buffers_checkpoint,
                        "buffers_clean": row.buffers_clean,
                        "maxwritten_clean": row.maxwritten_clean,
                    }
                else:
                    checkpoint_stats = {}
                
                result = await session.execute(text("""
                    SELECT temp_files, temp_bytes / 1024.0 / 1024.0 as temp_bytes_mb
                    FROM pg_stat_database WHERE datname = current_database()
                """))
                row = result.first()
                temp_files_mb = float(row.temp_bytes_mb) if row and row.temp_bytes_mb else 0.0
                
                # Locks
                result = await session.execute(text("""
                    SELECT locktype, mode, granted, relation::regclass as relation
                    FROM pg_locks WHERE NOT granted
                """))
                locks = [{"locktype": r.locktype, "mode": r.mode, "granted": r.granted, "relation": str(r.relation) if r.relation else None} for r in result]
                
        except Exception as e:
            pass
        
        # Windows system info
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_memory_mb = mem.total // (1024 * 1024)
            available_memory_mb = mem.available // (1024 * 1024)
            
            swap = psutil.swap_memory()
            pagefile_size_mb = swap.total // (1024 * 1024)
            
            disk = psutil.disk_usage('C:\\')
            free_disk_gb = disk.free / (1024**3)
        except Exception:
            pass
        
        # Collect additional notes
        notes = []
        if failure_code == 0xC0000142:
            notes.append("0xC0000142 = STATUS_DLL_INIT_FAILED (DLL initialization failed)")
            notes.append("NOT STATUS_DLL_NOT_FOUND (0xC0000135)")
            notes.append("Common causes: antivirus interference, third-party hooks, corrupted PostgreSQL binaries, missing DLL dependencies")
            notes.append("See: https://wiki.postgresql.org/wiki/PostgreSQL_on_Windows#Crash_handling")
        
        return WindowsFailureEvidence(
            timestamp=timestamp,
            failure_code=failure_code,
            failure_name=failure_name,
            failure_classification=classification,
            postgresql_log_tail=pg_log_tail[:5000] if pg_log_tail else "",
            windows_event_log=windows_events,
            process_exit_code=None,
            backend_pid=None,
            server_uptime_seconds=None,
            connection_count=0,
            active_backend_count=0,
            database_size_mb=0.0,
            wal_size_mb=0.0,
            temp_files_mb=0.0,
            checkpoint_stats={},
            locks=[],
            server_version="unknown",
            architecture=architecture,
            os_version=os_version,
            cpu_count=os.cpu_count() or 0,
            total_physical_memory_mb=total_memory_mb,
            available_memory_mb=available_memory_mb,
            committed_memory_mb=committed_memory_mb,
            commit_limit_mb=commit_limit_mb,
            pagefile_size_mb=pagefile_size_mb,
            free_disk_gb=free_disk_gb,
            additional_notes=notes,
        )
    
    async def _get_postgresql_log_tail(self) -> str:
        """Get PostgreSQL log tail from the data directory."""
        try:
            log_dir = Path(r"C:\Program Files\PostgreSQL\18\data\log")
            if not log_dir.exists():
                return ""
            
            log_files = sorted(log_dir.glob("postgresql-*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not log_files:
                return ""
            
            latest_log = log_files[0]
            content = latest_log.read_text(encoding='utf-8', errors='ignore')
            return content[-5000:]  # Last 5000 chars
        except Exception:
            return ""
    
    async def _get_postgresql_log_tail_raw(self) -> str:
        """Get raw PostgreSQL log tail."""
        return await self._get_postgresql_log_tail()
    
    async def _get_windows_events(self) -> List[str]:
        """Query Windows Event Log for PostgreSQL-related events."""
        events = []
        try:
            # Use wevtutil to query System and Application logs
            for log_name in ['System', 'Application']:
                cmd = ['wevtutil', 'qe', log_name, '/q:"*[System[Provider[@Name=\"postgresql\"]]]"', '/c:10', '/f:text', '/rd:true']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.stdout:
                    events.append(f"=== {log_name} ===")
                    events.append(result.stdout)
                if result.stderr:
                    events.append(f"wevtutil stderr: {result.stderr}")
        except Exception as e:
            events.append(f"Error querying Windows Event Log: {e}")
        
        return events


def classify_windows_crash(exit_code: int, log_tail: str = "") -> WindowsFailureClassification:
    """Classify a PostgreSQL failure based on exit code and log evidence."""
    
    # Check exit code first
    if exit_code != 0:
        classification = classify_windows_nt_status(exit_code)
        if classification != WindowsFailureClassification.UNKNOWN:
            return classification
    
    # Check log for clues
    log_lower = log_tail.lower()
    
    if "dll" in log_lower and ("init" in log_lower or "load" in log_lower or "initialize" in log_lower):
        return WindowsFailureClassification.DLL_INITIALIZATION_FAILURE
    
    if "out of memory" in log_lower or "cannot allocate memory" in log_lower:
        return WindowsFailureClassification.OUT_OF_MEMORY
    
    if "no space left on device" in log_lower or "disk full" in log_lower:
        return WindowsFailureClassification.DISK_EXHAUSTION
    
    if "checkpoint" in log_lower and ("timeout" in log_lower or "failed" in log_lower):
        return WindowsFailureClassification.CHECKPOINT_PRESSURE
    
    if "wal" in log_lower and ("full" in log_lower or "pressure" in log_lower or "exceeded" in log_lower):
        return WindowsFailureClassification.WAL_PRESSURE
    
    if "lock" in log_lower and ("deadlock" in log_lower or "contention" in log_lower):
        return WindowsFailureClassification.LOCK_CONTENTION
    
    if "extension" in log_lower and ("load" in log_lower or "error" in log_lower or "fail" in log_lower):
        return WindowsFailureClassification.EXTENSION_FAILURE
    
    if "permission denied" in log_lower or "access denied" in log_lower:
        return WindowsFailureClassification.PERMISSION_FAILURE
    
    if "dll" in log_lower:
        return WindowsFailureClassification.DLL_INITIALIZATION_FAILURE
    
    return WindowsFailureClassification.UNKNOWN


async def capture_windows_crash_evidence(db_url: str, failure_code: int = 0xC0000142) -> WindowsFailureEvidence:
    """Main entry point to capture Windows crash evidence."""
    diagnostics = WindowsCrashDiagnostics(db_url)
    await diagnostics.initialize()
    try:
        evidence = await diagnostics.collect_failure_evidence(failure_code)
        return evidence
    finally:
        await diagnostics.close()


# Synchronous version for use in sync contexts
def capture_windows_crash_evidence_sync(db_url: str, failure_code: int = 0xC0000142) -> WindowsFailureEvidence:
    """Synchronous wrapper for capturing Windows crash evidence."""
    return asyncio.run(capture_windows_crash_evidence(db_url, failure_code))


# Export the key symbols
__all__ = [
    'WindowsFailureClassification',
    'WindowsFailureEvidence',
    'ScaleEnvironmentIncident',
    'WindowsCrashDiagnostics',
    'classify_windows_nt_status',
    'classify_windows_crash',
    'capture_windows_crash_evidence',
    'capture_windows_crash_evidence_sync',
    'NT_STATUS_CODES',
]