"""Safe Backup Executor — production-grade backup execution with capability detection.

Implements repeatable backup execution with:
- Environment validation
- Backup method detection (pgbackrest, pg_basebackup, pg_dump)
- Pre-flight checks (disk space, permissions, connectivity)
- Metadata capture
- Artifact verification
- Recovery manifest generation
- Safe failure handling
"""

import asyncio
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.backup_manifest import (
    BackupManifest,
    BackupVerificationResult,
    BackupKind,
    BackupStatus,
    RecoveryManifest,
    RecoveryManifestState,
    RecoveryVerificationStatus,
)
from app.validation.capability_contract import (
    ValidationStatus,
    EnvironmentCapability,
    ValidationCheck,
    ValidationResult,
    CapabilityDetector,
    CapabilityAwareValidator,
)
from app.services.wal_archive_monitor import wal_archive_monitor

logger = logging.getLogger("vcos.backup_executor")


class BackupMethod(str, Enum):
    """Supported backup methods."""
    PGBACKREST = "pgbackrest"
    PG_BASEBACKUP = "pg_basebackup"
    PG_DUMP = "pg_dump"
    UNKNOWN = "unknown"


class BackupExecutorState(str, Enum):
    """Backup executor state."""
    IDLE = "idle"
    VALIDATING = "validating"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BackupEnvironmentInfo:
    """Backup environment validation result."""
    valid: bool
    backup_method: BackupMethod
    backup_method_version: str = ""
    available_disk_space_bytes: int = 0
    required_disk_space_bytes: int = 0
    pg_version: str = ""
    pg_data_directory: str = ""
    archive_mode: str = ""
    archive_command: str = ""
    wal_archive_directory: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Capability detections
    pgbackrest_available: bool = False
    pgbackrest_version: str = ""
    pg_basebackup_available: bool = False
    pg_basebackup_version: str = ""
    pg_dump_available: bool = False
    pg_dump_version: str = ""
    s3_storage_configured: bool = False
    local_storage_writable: bool = False


@dataclass
class BackupExecutionResult:
    """Result of backup execution."""
    success: bool
    backup_id: str
    backup_method: BackupMethod
    started_at: datetime
    completed_at: Optional[datetime] = None
    backup_size_bytes: int = 0
    checksum_sha256: str = ""
    backup_location: str = ""
    required_wal_start_lsn: str = ""
    required_wal_end_lsn: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    execution_log: List[str] = field(default_factory=list)
    
    # Recovery manifest
    recovery_manifest: Optional[RecoveryManifest] = None


class BackupExecutor(CapabilityAwareValidator):
    """Safe backup executor with capability-aware method selection."""
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._state = BackupExecutorState.IDLE
        self._current_execution: Optional[BackupExecutionResult] = None
    
    async def validate_environment(self, db: AsyncSession) -> BackupEnvironmentInfo:
        """Validate the backup environment and detect capabilities."""
        self.db = db
        self.detector.db = db
        
        info = BackupEnvironmentInfo(
            valid=False,
            backup_method=BackupMethod.UNKNOWN,
        )
        
        try:
            # Get PostgreSQL version
            pg_version_result = await db.execute(text("SHOW server_version"))
            info.pg_version = pg_version_result.scalar() or "unknown"
            
            # Get data directory
            pg_data_result = await db.execute(text("SHOW data_directory"))
            info.pg_data_directory = pg_data_result.scalar() or ""
            
            # Get archive settings
            archive_mode_result = await db.execute(text("SHOW archive_mode"))
            info.archive_mode = archive_mode_result.scalar() or "off"
            
            archive_command_result = await db.execute(text("SHOW archive_command"))
            info.archive_command = archive_command_result.scalar() or ""
            
            # Check pgbackrest
            info.pgbackrest_available, info.pgbackrest_version = await self._check_pgbackrest()
            
            # Check pg_basebackup
            info.pg_basebackup_available, info.pg_basebackup_version = await self._check_pg_basebackup()
            
            # Check pg_dump
            info.pg_dump_available, info.pg_dump_version = await self._check_pg_dump()
            
            # Determine backup method (priority: pgbackrest > pg_basebackup > pg_dump)
            if info.pgbackrest_available:
                info.backup_method = BackupMethod.PGBACKREST
                info.backup_method_version = info.pgbackrest_version
            elif info.pg_basebackup_available:
                info.backup_method = BackupMethod.PG_BASEBACKUP
                info.backup_method_version = info.pg_basebackup_version
            elif info.pg_dump_available:
                info.backup_method = BackupMethod.PG_DUMP
                info.backup_method_version = info.pg_dump_version
            else:
                info.errors.append("No backup method available (pgbackrest, pg_basebackup, pg_dump)")
                return info
            
            # Check disk space
            await self._check_disk_space(info)
            
            # Check storage
            await self._check_storage(info)
            
            # Check WAL archive directory
            await self._check_wal_archive_directory(info)
            
            # Validate archive_mode for PITR
            if info.archive_mode != "on":
                info.warnings.append("archive_mode is not 'on' - PITR may not be available")
            
            # Overall validation
            info.valid = len(info.errors) == 0
            
        except Exception as e:
            info.errors.append(f"Environment validation failed: {str(e)}")
            logger.error(f"Environment validation failed: {e}")
        
        return info
    
    async def _check_pgbackrest(self) -> Tuple[bool, str]:
        """Check if pgbackrest is available and get version."""
        # Check common locations including Windows
        paths_to_check = [
            "pgbackrest",
            "/usr/bin/pgbackrest",
            "/usr/local/bin/pgbackrest",
            "C:\\Program Files\\pgbackrest\\pgbackrest.exe",
        ]
        
        for path in paths_to_check:
            try:
                result = subprocess.run(
                    [path, "version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True, result.stdout.strip()
            except FileNotFoundError:
                continue
            except Exception:
                continue
        return False, ""
    
    async def _check_pg_basebackup(self) -> Tuple[bool, str]:
        """Check if pg_basebackup is available and get version."""
        # Check common locations including Windows PostgreSQL bin directory
        paths_to_check = [
            "pg_basebackup",
            "/usr/bin/pg_basebackup",
            "/usr/local/bin/pg_basebackup",
            "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_basebackup.exe",
            "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_basebackup.exe",
            "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_basebackup.exe",
        ]
        
        for path in paths_to_check:
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True, result.stdout.strip()
            except FileNotFoundError:
                continue
            except Exception:
                continue
        return False, ""
    
    async def _check_pg_dump(self) -> Tuple[bool, str]:
        """Check if pg_dump is available and get version."""
        # Check common locations including Windows PostgreSQL bin directory
        paths_to_check = [
            "pg_dump",
            "/usr/bin/pg_dump",
            "/usr/local/bin/pg_dump",
            "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_dump.exe",
            "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_dump.exe",
            "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_dump.exe",
        ]
        
        for path in paths_to_check:
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True, result.stdout.strip()
            except FileNotFoundError:
                continue
            except Exception:
                continue
        return False, ""
    
    async def _check_disk_space(self, info: BackupEnvironmentInfo) -> None:
        """Check available disk space."""
        try:
            # Check backup destination (env > settings > platform default)
            backup_dest = self._resolve_backup_dest()
            if backup_dest.startswith("s3://"):
                # S3 - can't easily check, assume OK
                info.available_disk_space_bytes = 1024 * 1024 * 1024 * 100  # 100GB assumed
            else:
                probe = backup_dest
                while probe and not os.path.exists(probe):
                    parent = os.path.dirname(probe)
                    if parent == probe or not parent:
                        probe = ""
                        break
                    probe = parent
                stat = shutil.disk_usage(probe or ".")
                info.available_disk_space_bytes = stat.free
            
            # Estimate required space (database size + WAL)
            # We'll use pg_database_size as estimate
            try:
                db_size_result = await self.db.execute(text("SELECT pg_database_size(current_database())"))
                db_size = db_size_result.scalar() or 0
                info.required_disk_space_bytes = int(db_size * 1.5)  # 1.5x for safety
            except Exception:
                info.required_disk_space_bytes = 1024 * 1024 * 1024  # 1GB default
            
            if info.available_disk_space_bytes < info.required_disk_space_bytes:
                info.errors.append(
                    f"Insufficient disk space: {info.available_disk_space_bytes} bytes available, "
                    f"{info.required_disk_space_bytes} bytes required"
                )
        except Exception as e:
            info.warnings.append(f"Could not check disk space: {str(e)}")
    
    async def _check_storage(self, info: BackupEnvironmentInfo) -> None:
        """Check storage configuration."""
        # Check S3 configuration
        if hasattr(self.settings, 'VAULT_BUCKET') and self.settings.VAULT_BUCKET:
            info.s3_storage_configured = True
        
        # Check local storage writability
        backup_dest = self._resolve_backup_dest()
        if not backup_dest.startswith("s3://"):
            try:
                os.makedirs(backup_dest, exist_ok=True)
                test_file = os.path.join(backup_dest, ".vcos_write_test")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                info.local_storage_writable = True
            except Exception as e:
                info.errors.append(f"Backup destination not writable: {str(e)}")
    
    async def _check_wal_archive_directory(self, info: BackupEnvironmentInfo) -> None:
        """Check WAL archive directory."""
        # Try to get from archive_command
        if "wal_archive" in info.archive_command:
            # Extract path from archive_command
            # This is a simple heuristic
            info.wal_archive_directory = "/var/lib/vcos/wal_archive"
        else:
            info.wal_archive_directory = os.environ.get("WAL_ARCHIVE_DIR", "/var/lib/vcos/wal_archive")
    
    async def execute_backup(
        self,
        db: AsyncSession,
        kind: BackupKind = BackupKind.FULL,
        retention_days: int = 30,
        organization_id: Optional[str] = None,
        force_method: Optional[BackupMethod] = None,
    ) -> BackupExecutionResult:
        """Execute a backup with full validation."""
        self.db = db
        self.detector.db = db
        
        backup_id = f"bkp-{uuid.uuid4().hex[:12]}"
        started_at = utcnow()
        
        result = BackupExecutionResult(
            success=False,
            backup_id=backup_id,
            backup_method=BackupMethod.UNKNOWN,
            started_at=started_at,
        )
        
        self._state = BackupExecutorState.VALIDATING
        self._current_execution = result
        
        try:
            # Validate environment
            env_info = await self.validate_environment(db)
            result.execution_log.append(f"Environment validation: {'PASSED' if env_info.valid else 'FAILED'}")
            
            if not env_info.valid:
                result.error = f"Environment validation failed: {env_info.errors}"
                result.execution_log.extend([f"ERROR: {e}" for e in env_info.errors])
                self._state = BackupExecutorState.FAILED
                return result
            
            # Override method if forced
            if force_method:
                env_info.backup_method = force_method
            
            result.backup_method = env_info.backup_method
            result.execution_log.append(f"Using backup method: {env_info.backup_method.value}")
            
            # Create backup manifest
            org_id = organization_id or (self.settings.ORGANIZATION_ID if hasattr(self.settings, 'ORGANIZATION_ID') else "default")
            manifest = BackupManifest(
                id=backup_id,
                organization_id=org_id,
                backup_kind=kind,
                status=BackupStatus.IN_PROGRESS,
                started_at=utcnow(),
                retention_days=retention_days,
                expires_at=utcnow() + timedelta(days=retention_days),
                backup_format=env_info.backup_method.value,
                pg_version=env_info.pg_version,
                vault_bucket=getattr(self.settings, 'VAULT_BUCKET', None),
            )
            db.add(manifest)
            await db.flush()
            
            self._state = BackupExecutorState.EXECUTING
            
            # Execute backup based on method
            if env_info.backup_method == BackupMethod.PGBACKREST:
                await self._execute_pgbackrest_backup(db, manifest, kind, result)
            elif env_info.backup_method == BackupMethod.PG_BASEBACKUP:
                await self._execute_pg_basebackup(db, manifest, result)
            elif env_info.backup_method == BackupMethod.PG_DUMP:
                await self._execute_pg_dump(db, manifest, result)
            
            if not result.success:
                manifest.status = BackupStatus.FAILED
                manifest.error = result.error
                await db.flush()
                self._state = BackupExecutorState.FAILED
                return result
            
            # Verify backup
            self._state = BackupExecutorState.VERIFYING
            result.execution_log.append("Starting backup verification...")
            
            verification = await self._verify_backup_artifact(db, manifest, result)
            if not verification:
                manifest.status = BackupStatus.FAILED_VERIFICATION
                manifest.error = "Backup verification failed"
                result.error = "Backup verification failed"
                await db.flush()
                self._state = BackupExecutorState.FAILED
                return result
            
            # Finalize manifest from the verified artifact first so the recovery
            # manifest captures completion time, checksum, and artifact location.
            manifest.status = BackupStatus.VERIFIED
            manifest.completed_at = utcnow()
            manifest.backup_size_bytes = result.backup_size_bytes
            manifest.checksum_sha256 = result.checksum_sha256
            manifest.vault_path = result.backup_location
            await db.flush()
            
            # Create recovery manifest
            recovery_manifest = await self._create_recovery_manifest(db, manifest, env_info, result)
            result.recovery_manifest = recovery_manifest
            
            # Record this backup as the new recovery baseline (WAL segment + archive seal)
            await self._record_wal_baseline(db, manifest, result)
            
            result.completed_at = utcnow()
            result.success = True
            self._state = BackupExecutorState.COMPLETED
            
            # Record the verified physical backup as a recovery readiness input
            try:
                wal_archive_monitor.record_physical_backup_verified(
                    backup_id=manifest.id,
                    checksum_sha256=result.checksum_sha256,
                )
            except Exception as record_error:
                result.warnings.append(
                    f"Physical backup verification record failed: {record_error}"
                )
            
            logger.info(f"Backup {backup_id} completed successfully using {env_info.backup_method.value}")
            
        except Exception as e:
            result.error = str(e)
            result.execution_log.append(f"EXCEPTION: {str(e)}")
            logger.error(f"Backup {backup_id} failed: {e}")
            self._state = BackupExecutorState.FAILED
        
        return result
    
    async def _execute_pgbackrest_backup(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        kind: BackupKind,
        result: BackupExecutionResult,
    ) -> None:
        """Execute pgbackrest backup."""
        backup_type = "full" if kind == BackupKind.FULL else "incr"
        
        pgbackrest_path = self._get_binary_path("pgbackrest")
        
        cmd = [
            pgbackrest_path,
            "--stanza=vcos",
            f"--type={backup_type}",
            "--repo1-path", f"s3://{manifest.vault_bucket}",
            "backup",
        ]
        
        env = os.environ.copy()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            result.execution_log.append(f"pgbackrest exit code: {proc.returncode}")
            if stdout:
                result.execution_log.append(f"STDOUT: {stdout.decode()[:500]}")
            if stderr:
                result.execution_log.append(f"STDERR: {stderr.decode()[:500]}")
            
            if proc.returncode != 0:
                result.error = f"pgbackrest failed: {stderr.decode()[:500]}"
                return
            
            # Parse output for metadata
            await self._parse_pgbackrest_output(stdout.decode(), result)
            result.success = True
            
        except Exception as e:
            result.error = f"pgbackrest execution failed: {str(e)}"
    
    def _get_binary_path(self, binary_name: str) -> str:
        """Get the full path to a PostgreSQL binary, checking Windows locations first."""
        if binary_name == "pg_basebackup":
            paths = [
                "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_basebackup.exe",
                "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_basebackup.exe",
                "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_basebackup.exe",
                "pg_basebackup",
            ]
        elif binary_name == "pg_dump":
            paths = [
                "C:\\Program Files\\PostgreSQL\\18\\bin\\pg_dump.exe",
                "C:\\Program Files\\PostgreSQL\\17\\bin\\pg_dump.exe",
                "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_dump.exe",
                "pg_dump",
            ]
        elif binary_name == "pgbackrest":
            paths = [
                "C:\\Program Files\\pgbackrest\\pgbackrest.exe",
                "pgbackrest",
            ]
        else:
            paths = [binary_name]
        
        for path in paths:
            if os.path.exists(path) or shutil.which(path):
                return path
        return binary_name  # fallback
    
    def _resolve_backup_dest(self) -> str:
        """Resolve the local backup destination (env > settings > platform default)."""
        dest = os.environ.get("VAULT_BUCKET") or getattr(self.settings, "VAULT_BUCKET", None)
        if dest:
            return dest
        if os.name == "nt":
            return "C:\\VCOS-Backups"
        return "/var/lib/vcos/backups"
    
    def _connection_params(self) -> Dict[str, Any]:
        """Extract PostgreSQL connection parameters from the configured DATABASE_URL."""
        from sqlalchemy.engine import make_url
        try:
            url = make_url(str(self.settings.DATABASE_URL))
            return {
                "host": url.host or "127.0.0.1",
                "port": url.port or 5432,
                "user": url.username or "postgres",
                "password": url.password or "",
            }
        except Exception:
            return {"host": "127.0.0.1", "port": 5432, "user": "postgres", "password": ""}
    
    async def _execute_pg_basebackup(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        result: BackupExecutionResult,
    ) -> None:
        """Execute pg_basebackup backup."""
        backup_dest = self._resolve_backup_dest()
        if backup_dest.startswith("s3://"):
            # pg_basebackup doesn't support S3 directly
            # Would need to backup locally then upload
            result.error = "pg_basebackup doesn't support S3 directly; use pgbackrest or local storage"
            return
        
        backup_path = os.path.join(backup_dest, f"basebackup_{manifest.id}")
        os.makedirs(backup_path, exist_ok=True)
        
        pg_basebackup_path = self._get_binary_path("pg_basebackup")
        conn = self._connection_params()
        
        cmd = [
            pg_basebackup_path,
            "-h", conn["host"],
            "-p", str(conn["port"]),
            "-U", conn["user"],
            "-D", backup_path,
            "-F", "tar",
            "-z",
            "-P",
            "-X", "fetch",
            "-c", "fast",
        ]
        
        env = os.environ.copy()
        if conn["password"]:
            env["PGPASSWORD"] = conn["password"]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            result.execution_log.append(f"pg_basebackup exit code: {proc.returncode}")
            if stdout:
                result.execution_log.append(f"STDOUT: {stdout.decode()[:500]}")
            if stderr:
                result.execution_log.append(f"STDERR: {stderr.decode()[:500]}")
            
            if proc.returncode != 0:
                result.error = f"pg_basebackup failed: {stderr.decode()[:500]}"
                return
            
            # The tar artifact is the recoverable backup artifact (base.tar.gz)
            artifact = os.path.join(backup_path, "base.tar.gz")
            if not os.path.exists(artifact):
                candidates = sorted(
                    f for f in os.listdir(backup_path) if f.endswith(".tar.gz")
                )
                if not candidates:
                    result.error = f"pg_basebackup produced no tar artifact in {backup_path}"
                    return
                artifact = os.path.join(backup_path, candidates[0])
            
            await self._calculate_backup_metrics(artifact, result)
            result.backup_location = artifact
            result.success = True
            
        except Exception as e:
            result.error = f"pg_basebackup execution failed: {str(e)}"
    
    async def _execute_pg_dump(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        result: BackupExecutionResult,
    ) -> None:
        """Execute pg_dump backup (logical backup)."""
        backup_dest = self._resolve_backup_dest()
        if backup_dest.startswith("s3://"):
            result.error = "pg_dump doesn't support S3 directly"
            return
        
        dump_path = os.path.join(backup_dest, f"dump_{manifest.id}.sql.gz")
        
        # Get database URL (strip the async driver for pg_dump)
        db_url = str(self.settings.DATABASE_URL).replace("+asyncpg", "").replace("+aiosqlite", "")
        
        pg_dump_path = self._get_binary_path("pg_dump")
        
        cmd = [
            pg_dump_path,
            db_url,
            "--format=custom",
            "--compress=9",
            "--file", dump_path,
        ]
        
        env = os.environ.copy()
        conn = self._connection_params()
        if conn["password"]:
            env["PGPASSWORD"] = conn["password"]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            result.execution_log.append(f"pg_dump exit code: {proc.returncode}")
            if stderr:
                result.execution_log.append(f"STDERR: {stderr.decode()[:500]}")
            
            if proc.returncode != 0:
                result.error = f"pg_dump failed: {stderr.decode()[:500]}"
                return
            
            # Calculate size and checksum
            await self._calculate_backup_metrics(dump_path, result)
            result.backup_location = dump_path
            result.success = True
            
        except Exception as e:
            result.error = f"pg_dump execution failed: {str(e)}"
    
    async def _parse_pgbackrest_output(self, output: str, result: BackupExecutionResult) -> None:
        """Parse pgbackrest output for metadata."""
        try:
            # pgbackrest outputs JSON in some cases
            import json
            lines = output.strip().split('\n')
            for line in lines:
                if line.startswith('{'):
                    data = json.loads(line)
                    result.backup_size_bytes = data.get("size", 0)
                    result.checksum_sha256 = data.get("checksum", "")
                    break
        except json.JSONDecodeError:
            pass
        
        # Fallback: estimate from repository info
        if result.backup_size_bytes == 0:
            try:
                pgbackrest_path = self._get_binary_path("pgbackrest")
                cmd = [pgbackrest_path, "--stanza=vcos", "info", "--output=json"]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                data = json.loads(stdout.decode())
                if data and len(data) > 0:
                    repo = data[0].get("repository", [{}])[0]
                    backups = repo.get("backup", [])
                    if backups:
                        latest = backups[-1]
                        result.backup_size_bytes = latest.get("size", 0)
                        result.checksum_sha256 = latest.get("checksum", "")
            except Exception:
                pass
    
    async def _calculate_backup_metrics(self, path: str, result: BackupExecutionResult) -> None:
        """Calculate backup size and checksum."""
        if os.path.isfile(path):
            result.backup_size_bytes = os.path.getsize(path)
            result.checksum_sha256 = self._compute_sha256(path)
        elif os.path.isdir(path):
            total_size = 0
            hasher = hashlib.sha256()
            for root, dirs, files in os.walk(path):
                for file in files:
                    filepath = os.path.join(root, file)
                    size = os.path.getsize(filepath)
                    total_size += size
                    with open(filepath, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            hasher.update(chunk)
            result.backup_size_bytes = total_size
            result.checksum_sha256 = hasher.hexdigest()
    
    async def _verify_backup_artifact(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        result: BackupExecutionResult,
    ) -> bool:
        """Verify the backup artifact."""
        # For pgbackrest, use pgbackrest verify
        if manifest.backup_format == "pgbackrest":
            try:
                pgbackrest_path = self._get_binary_path("pgbackrest")
                cmd = [
                    pgbackrest_path,
                    "--stanza=vcos",
                    "--repo1-path", f"s3://{manifest.vault_bucket}",
                    "verify",
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    result.execution_log.append("pgbackrest verify: PASSED")
                    return True
                else:
                    result.execution_log.append(f"pgbackrest verify FAILED: {stderr.decode()[:500]}")
                    return False
            except Exception as e:
                result.execution_log.append(f"pgbackrest verify error: {str(e)}")
                return False
        
        # For local backups, verify checksum of the produced artifact
        if manifest.backup_format in ("pg_basebackup", "pg_dump"):
            artifact = result.backup_location or manifest.vault_path
            if not artifact or not os.path.exists(artifact):
                result.execution_log.append(f"Backup artifact not found: {artifact}")
                return False
            if os.path.isfile(artifact):
                computed_hash = self._compute_sha256(artifact)
            else:
                computed_hash = self._compute_dir_sha256(artifact)
            if computed_hash == result.checksum_sha256:
                result.execution_log.append("Local backup checksum: VERIFIED")
                return True
            else:
                result.execution_log.append(f"Checksum mismatch: expected {result.checksum_sha256}, got {computed_hash}")
                return False
        
        return False
    
    async def _create_recovery_manifest(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        env_info: BackupEnvironmentInfo,
        result: BackupExecutionResult,
    ) -> RecoveryManifest:
        """Create a recovery manifest for this backup."""
        recovery_manifest = RecoveryManifest(
            backup_id=manifest.id,
            backup_method=env_info.backup_method.value,
            backup_format=manifest.backup_format,
            backup_start_time=manifest.started_at,
            backup_completion_time=manifest.completed_at,
            postgresql_version=env_info.pg_version,
            database_system_identifier=await self._get_database_system_identifier(db),
            source_database_name=await self._get_current_database_name(db),
            source_environment_identity=(
                f"{getattr(self.settings, 'APP_ENV', 'unknown')}-"
                f"{platform.node() or 'unknown'}"
            ),
            vcos_revision=getattr(self.settings, 'APP_VERSION', '1.0.0'),
            schema_revision=await self._get_schema_version(db),
            required_extensions=await self._get_required_extensions(db),
            backup_artifact_location=result.backup_location,
            backup_artifact_size_bytes=result.backup_size_bytes,
            backup_integrity_checksum=result.checksum_sha256,
            required_wal_start_lsn=await self._get_backup_start_lsn(db, manifest),
            required_wal_end_lsn=await self._get_backup_end_lsn(db, manifest),
            earliest_verified_recovery_target=manifest.completed_at,
            latest_verified_recovery_target=utcnow(),
            verification_state=RecoveryManifestState.BACKUP_VERIFIED,
        )
        
        # Check for historical gaps
        gaps = await self._detect_wal_gaps(db)
        if gaps:
            recovery_manifest.historical_gaps = gaps
            recovery_manifest.limitations.append(f"Historical WAL gaps detected: {gaps}")
        
        # Store recovery manifest
        await self._store_recovery_manifest(db, manifest.id, recovery_manifest)
        
        return recovery_manifest
    
    async def _get_database_system_identifier(self, db: AsyncSession) -> str:
        """Get database system identifier."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("SELECT system_identifier FROM pg_control_system()"))
                return str(result.scalar() or "")
        except Exception:
            return ""

    async def _get_current_database_name(self, db: AsyncSession) -> str:
        """Get the name of the connected database (PostgreSQL sources)."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("SELECT current_database()"))
                return str(result.scalar() or "unknown")
        except Exception:
            return "unknown"
    
    async def _get_schema_version(self, db: AsyncSession) -> str:
        """Get current schema version (alembic head preferred)."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                revision = result.scalar()
            if revision:
                return str(revision)
        except Exception:
            pass
        try:
            async with db.begin_nested():
                result = await db.execute(text("""
                    SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1
                """))
                return result.scalar() or "unknown"
        except Exception:
            return "unknown"
    
    async def _get_required_extensions(self, db: AsyncSession) -> List[str]:
        """Get required PostgreSQL extensions."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("""
                    SELECT extname FROM pg_extension WHERE extname IN (
                        'pg_trgm', 'btree_gin', 'btree_gist', 'uuid-ossp', 'citext'
                    )
                """))
                return [row[0] for row in result.fetchall()]
        except Exception:
            return []
    
    async def _get_backup_start_lsn(self, db: AsyncSession, manifest: BackupManifest) -> str:
        """Get WAL LSN at backup start."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("SELECT pg_current_wal_lsn()::text"))
                return str(result.scalar() or "0/0")
        except Exception:
            return "0/0"
    
    async def _get_backup_end_lsn(self, db: AsyncSession, manifest: BackupManifest) -> str:
        """Get WAL LSN at backup end."""
        try:
            async with db.begin_nested():
                result = await db.execute(text("SELECT pg_current_wal_lsn()::text"))
                return str(result.scalar() or "0/0")
        except Exception:
            return "0/0"
    
    async def _detect_wal_gaps(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """Detect WAL gaps in archive."""
        gaps = []
        try:
            async with db.begin_nested():
                # Check pg_stat_archiver for failed segments
                result = await db.execute(text("""
                    SELECT failed_count, last_failed_wal, last_failed_time
                    FROM pg_stat_archiver
                """))
                archiver = result.fetchone()
                if archiver and archiver.failed_count > 0:
                    gaps.append({
                        "type": "archive_failures",
                        "count": archiver.failed_count,
                        "last_failed_wal": archiver.last_failed_wal,
                        "last_failed_time": archiver.last_failed_time.isoformat() if archiver.last_failed_time else None,
                    })
        except Exception:
            pass
        return gaps
    
    async def _store_recovery_manifest(
        self,
        db: AsyncSession,
        backup_id: str,
        recovery_manifest: RecoveryManifest,
    ) -> None:
        """Store recovery manifest in backup manifest."""
        manifest = await db.get(BackupManifest, backup_id)
        if manifest:
            # Store as JSON in verification_details or a new column
            # For now, store in verification_details
            manifest.verification_details = recovery_manifest.to_dict()
            await db.flush()
    
    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _compute_dir_sha256(self, dir_path: str) -> str:
        """Compute deterministic SHA-256 over all files in a directory."""
        hasher = hashlib.sha256()
        for root, dirs, files in os.walk(dir_path):
            for name in sorted(files):
                filepath = os.path.join(root, name)
                with open(filepath, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        hasher.update(chunk)
        return hasher.hexdigest()
    
    async def _record_wal_baseline(
        self,
        db: AsyncSession,
        manifest: BackupManifest,
        result: BackupExecutionResult,
    ) -> None:
        """Record the WAL segment at backup end as the recovery baseline and seal it."""
        try:
            end_lsn = await self._get_backup_end_lsn(db, manifest)
            if end_lsn in ("0/0", "", None):
                result.warnings.append("WAL baseline recording skipped: no end LSN resolved")
                return
            async with db.begin_nested():
                seg_result = await db.execute(
                    text("SELECT pg_walfile_name((:lsn)::text::pg_lsn)"), {"lsn": end_lsn}
                )
                baseline_segment = seg_result.scalar()
            if not baseline_segment:
                result.warnings.append("WAL baseline recording skipped: no segment resolved")
                return
            
            async with db.begin_nested():
                await db.execute(text("SELECT pg_switch_wal()"))
            wal_archive_monitor.set_baseline_segment(str(baseline_segment))
            result.execution_log.append(
                f"WAL baseline recorded: {baseline_segment} (segment sealed via pg_switch_wal)"
            )
        except Exception as e:
            result.warnings.append(f"WAL baseline recording skipped: {e}")
    
    def get_state(self) -> BackupExecutorState:
        """Get current executor state."""
        return self._state
    
    def get_current_execution(self) -> Optional[BackupExecutionResult]:
        """Get current execution result."""
        return self._current_execution


# Global instance
backup_executor = BackupExecutor()